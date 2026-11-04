import datetime
import time
import traceback
from typing import Optional

from processing.core.ProcessingConfig import ProcessingConfig
from processing.core.ProcessingResults import resultsList
from processing.gui import RenderingStyles
from processing.gui.AlgorithmExecutor import executeIterating, execute_in_place, execute
from processing.gui.BatchAlgorithmDialog import BatchAlgorithmDialog
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMainWindow, QPushButton, QDialogButtonBox, QMessageBox
from qgis.core import QgsLayerTreeNode, QgsWkbTypes
from qgis.core import QgsProcessingAlgRunnerTask, QgsProxyProgressTask, QgsApplication, QgsProcessingOutputHtml, \
    QgsProcessingContext, QgsMessageLog, QgsProcessingFeedback, QgsMapLayer, QgsProcessingUtils
from qgis.core import QgsProcessingAlgorithm, Qgis, QgsProcessingFeatureSourceDefinition
from qgis.gui import QgsGui, QgsProcessingParameterWidgetContext, QgsProcessingGuiUtils
from qgis.gui import QgsLayerTreeView
from qgis.gui import QgsProcessingAlgorithmWidgetBase, QgsProcessingParametersGenerator
from qgis.utils import iface

from .genericprocessingresultshandler import GenericProcessingResultsHandler
from .processingalgorithmwidget import ProcessingAlgorithmWidget


class AlgorithmWidget(ProcessingAlgorithmWidget):
    """
    QgsProcessingAlgorithmWidgetBase with python specific logic
    """

    def __init__(
        self,
        alg: QgsProcessingAlgorithm,
        in_place: bool = False,
        parent: Optional[QMainWindow] = None,
        flags: QgsProcessingAlgorithmWidgetBase.WidgetFlags = QgsProcessingAlgorithmWidgetBase.WidgetFlags(),
        initial_state: Qgis.DockableWidgetInitialState = Qgis.DockableWidgetInitialState.RestorePreviousState,
        processing_context: Optional[QgsProcessingContext] = None,
        widget_context: Optional[QgsProcessingParameterWidgetContext] = None,
        layer_tree_node: Optional[QgsLayerTreeNode] = None,
    ):
        super().__init__(
            alg,
            in_place,
            parent or (iface and iface.mainWindow()),
            flags=flags,
            initial_state=initial_state,
            processing_context=processing_context,
            widget_context=widget_context,
        )

        self.feedback_dialog = None
        self.active_layer = iface.activeLayer() if self.inPlace() else None

        self.context = None
        self.feedback = None
        self.history_log_id = None
        self.history_details = {}
        if layer_tree_node is None:
            tv = iface.layerTreeView()
            if isinstance(tv, QgsLayerTreeView):
                layer_tree_node = tv.currentNode()

        self._layer_tree_node = layer_tree_node

        self._is_running = False

        self._parameters_panel = self.createParametersPanel(
            self.inPlace(), self.active_layer, self.messageBar()
        )

        self.setMainWidget(self._parameters_panel)

        if not self.inPlace():
            self.runAsBatchButton = QPushButton(
                QCoreApplication.translate("AlgorithmDialog", "Run as Batch Process…")
            )
            self.runAsBatchButton.clicked.connect(self.runAsBatch)
            self.buttonBox().addButton(
                self.runAsBatchButton, QDialogButtonBox.ButtonRole.ResetRole
            )  # reset role to ensure left alignment
        else:
            in_place_input_parameter_name = "INPUT"
            if hasattr(alg, "inputParameterName"):
                in_place_input_parameter_name = alg.inputParameterName()

            self.mainWidget().setParameters(
                {in_place_input_parameter_name: self.active_layer}
            )

            self.runAsBatchButton = None

            if self.active_layer:
                self.updateRunButtonText()
                self.active_layer.selectionChanged.connect(self.updateRunButtonText)
                self.active_layer.willBeDeleted.connect(self.close)
                self.setWindowTitle(
                    self.windowTitle() + " | " + self.active_layer.name()
                )

        self.updateRunButtonVisibility()

    def updateRunButtonText(self):
        has_selection = self.active_layer.selectedFeatureCount() > 0
        self.buttonBox().button(QDialogButtonBox.StandardButton.Ok).setText(
            QCoreApplication.translate("AlgorithmDialog", "Modify Selected Features")
            if has_selection
            else QCoreApplication.translate("AlgorithmDialog", "Modify All Features")
        )

    def runAsBatch(self):
        self.reject()
        p = self.parent()
        if not isinstance(p, QMainWindow):
            p = QMainWindow()
        dlg = BatchAlgorithmDialog(self.algorithm().create(), parent=p)
        dlg.exec()
        s = ""

    def resetAdditionalGui(self):
        if not self.inPlace():
            self.runAsBatchButton.setEnabled(True)

    def blockAdditionalControlsWhileRunning(self):
        if not self.inPlace():
            self.runAsBatchButton.setEnabled(False)

    def runAlgorithm(self):
        self.feedback = self.createFeedback()
        self.context = self.processingContext()
        self.applyContextOverrides(self.context)
        self.algorithmAboutToRun.emit(self.context)

        checkCRS = ProcessingConfig.getSetting(ProcessingConfig.WARN_UNMATCHING_CRS)

        # messy as all heck, but we don't want to call the dialog's implementation of
        # createProcessingParameters as we want to catch the exceptions raised by the
        # parameter panel instead...
        parameters = {}
        validation_result = []
        if self.mainWidget() is not None:
            parameters, validation_result = (
                self.mainWidget().createAndValidateParameters(
                    QgsProcessingParametersGenerator.Flags()
                )
            )

        all_valid = self.handleValidationResults(validation_result)
        if not all_valid:
            return

        if checkCRS and not self.algorithm().validateInputCrs(parameters, self.context):
            reply = QMessageBox.question(
                self,
                self.tr("Unmatching CRS's"),
                self.tr(
                    "Parameters do not all use the same CRS. This can "
                    "cause unexpected results.\nDo you want to "
                    "continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
        ok, msg = self.algorithm().checkParameterValues(parameters, self.context)
        if not ok:
            QMessageBox.warning(self, self.tr("Unable to execute algorithm"), msg)
            return

        self.blockControlsWhileRunning()
        self.setExecutedAnyResult(True)
        self.cancelButton().setEnabled(False)

        self.iterateParam = None
        self._is_running = True

        for param in self.algorithm().parameterDefinitions():
            if (
                isinstance(
                    parameters.get(param.name(), None),
                    QgsProcessingFeatureSourceDefinition,
                )
                and parameters[param.name()].flags
                & QgsProcessingFeatureSourceDefinition.Flag.FlagCreateIndividualOutputPerInputFeature
            ):
                self.iterateParam = param.name()
                break

        self.clearProgress()
        self.feedback.pushVersionInfo(self.algorithm().provider())
        if self.algorithm().provider() and self.algorithm().provider().warningMessage():
            self.feedback.reportError(self.algorithm().provider().warningMessage())

        self.feedback.pushInfo(
            QCoreApplication.translate(
                "AlgorithmDialog", "Algorithm started at: {}"
            ).format(datetime.datetime.now().replace(microsecond=0).isoformat())
        )

        self.setInfo(
            QCoreApplication.translate(
                "AlgorithmDialog", "<b>Algorithm '{0}' starting&hellip;</b>"
            ).format(self.algorithm().displayName()),
            escapeHtml=False,
        )

        self.feedback.pushInfo(self.tr("Input parameters:"))
        display_params = []
        for k, v in parameters.items():
            display_params.append(
                "'"
                + k
                + "' : "
                + self.algorithm()
                .parameterDefinition(k)
                .valueAsPythonString(v, self.context)
            )
        self.feedback.pushCommandInfo("{ " + ", ".join(display_params) + " }")
        self.feedback.pushInfo("")
        start_time = time.time()

        def elapsed_time(start_time) -> str:
            delta_t = time.time() - start_time
            hours = int(delta_t / 3600)
            minutes = int((delta_t % 3600) / 60)
            seconds = delta_t - hours * 3600 - minutes * 60

            str_hours = [self.tr("hour"), self.tr("hours")][hours > 1]
            str_minutes = [self.tr("minute"), self.tr("minutes")][minutes > 1]
            str_seconds = [self.tr("second"), self.tr("seconds")][seconds != 1]

            if hours > 0:
                elapsed = f"{delta_t:0.2f} {str_seconds} ({hours} {str_hours} {minutes} {str_minutes} {seconds:0.0f} {str_seconds})"
            elif minutes > 0:
                elapsed = f"{delta_t:0.2f} {str_seconds} ({minutes} {str_minutes} {seconds:0.0f} {str_seconds})"
            else:
                elapsed = f"{delta_t:0.2f} {str_seconds}"

            return elapsed

        if self.iterateParam:
            # Make sure the Log tab is visible before executing the algorithm
            try:
                self.showLog()
                self.repaint()
            except:
                pass

            self.cancelButton().setEnabled(
                self.algorithm().flags() & QgsProcessingAlgorithm.Flag.FlagCanCancel
            )
            if executeIterating(
                self.algorithm(),
                parameters,
                self.iterateParam,
                self.context,
                self.feedback,
            ):
                self.feedback.pushInfo(
                    self.tr("Execution completed in {}").format(
                        elapsed_time(start_time)
                    )
                )
                self.cancelButton().setEnabled(False)
                self.finish(True, parameters, self.context, self.feedback)
            else:
                self.cancelButton().setEnabled(False)
                self.resetGui()
        else:
            self.history_details = {
                "python_command": self.algorithm().asPythonCommand(
                    parameters, self.context
                ),
                "algorithm_id": self.algorithm().id(),
                "parameters": self.algorithm().asMap(parameters, self.context),
            }
            process_command, command_ok = self.algorithm().asQgisProcessCommand(
                parameters, self.context
            )
            if command_ok:
                self.history_details["process_command"] = process_command
            self.history_log_id, _ = QgsGui.historyProviderRegistry().addEntry(
                "processing", self.history_details
            )

            QgsGui.instance().processingRecentAlgorithmLog().push(self.algorithm().id())
            self.cancelButton().setEnabled(
                self.algorithm().flags() & QgsProcessingAlgorithm.Flag.FlagCanCancel
            )

            def on_complete(ok, results):
                if sip.isdeleted(self):
                    return

                if ok:
                    self.feedback.pushInfo(
                        self.tr("Execution completed in {}").format(
                            elapsed_time(start_time)
                        )
                    )
                    self.feedback.pushFormattedResults(
                        self.algorithm(), self.context, results
                    )
                else:
                    self.feedback.reportError(
                        self.tr("Execution failed after {}").format(
                            elapsed_time(start_time)
                        )
                    )
                self.feedback.pushInfo("")

                if self.history_log_id is not None:
                    # can't deepcopy this!
                    self.history_details["results"] = {
                        k: v for k, v in results.items() if k != "CHILD_INPUTS"
                    }
                    self.history_details["log"] = self.feedback.htmlLog()

                    QgsGui.historyProviderRegistry().updateEntry(
                        self.history_log_id, self.history_details
                    )

                if self.feedback_dialog is not None:
                    self.feedback_dialog.close()
                    self.feedback_dialog.deleteLater()
                    self.feedback_dialog = None

                self.cancelButton().setEnabled(False)

                self.finish(
                    ok, results, self.context, self.feedback, in_place=self.inPlace()
                )

                self.feedback = None
                self.context = None

            if not self.inPlace() and not (
                self.algorithm().flags() & QgsProcessingAlgorithm.Flag.FlagNoThreading
            ):
                # Make sure the Log tab is visible before executing the algorithm
                self.showLog()

                task = QgsProcessingAlgRunnerTask(
                    self.algorithm(), parameters, self.context, self.feedback
                )
                if task.isCanceled():
                    on_complete(False, {})
                else:
                    task.executed.connect(on_complete)
                    self.setCurrentTask(task)
            else:
                self.proxy_progress = QgsProxyProgressTask(
                    QCoreApplication.translate(
                        "AlgorithmDialog", "Executing “{}”"
                    ).format(self.algorithm().displayName())
                )
                QgsApplication.taskManager().addTask(self.proxy_progress)
                self.feedback.progressChanged.connect(
                    self.proxy_progress.setProxyProgress
                )
                self.feedback_dialog = self.createProgressDialog()
                self.feedback_dialog.show()
                if self.inPlace():
                    ok, results = execute_in_place(
                        self.algorithm(), parameters, self.context, self.feedback
                    )
                else:
                    ok, results = execute(
                        self.algorithm(), parameters, self.context, self.feedback
                    )
                self.feedback.progressChanged.disconnect()
                self.proxy_progress.finalize(ok)
                on_complete(ok, results)

    def finish(self, successful, result, context, feedback, in_place=False):
        keepOpen = not successful or ProcessingConfig.getSetting(
            ProcessingConfig.KEEP_DIALOG_OPEN
        )
        generated_html_outputs = False

        self._is_running = False

        if not in_place and self.iterateParam is None:
            # add html results to results dock
            for out in self.algorithm().outputDefinitions():
                if (
                    isinstance(out, QgsProcessingOutputHtml)
                    and out.name() in result
                    and result[out.name()]
                ):
                    resultsList.addResult(
                        icon=self.algorithm().icon(),
                        name=out.description(),
                        timestamp=time.localtime(),
                        result=result[out.name()],
                    )
                    generated_html_outputs = True

            wc = self.createWidgetContext()

            result_handler = GenericProcessingResultsHandler()
            if not result_handler.handleAlgorithmResults(self.algorithm(), context, result, feedback):
                self.resetGui()
                return

        self.setExecuted(True)
        self.setResults(result)
        self.setInfo(
            self.tr("Algorithm '{0}' finished").format(self.algorithm().displayName()),
            escapeHtml=False,
        )
        try:
            self.algorithmFinished.emit(successful, result, self.context)
        except TypeError as ex:
            # QGIS <= 4.4
            self.algorithmFinished.emit(successful, result)

        if not in_place and not keepOpen:
            self.close()
        else:
            self.resetGui()
            if generated_html_outputs:
                self.setInfo(
                    self.tr(
                        "HTML output has been generated by this algorithm."
                        "\nOpen the results dialog to check it."
                    ),
                    escapeHtml=False,
                )

    def isRunning(self):
        return self._is_running

    def ____handleAlgorithmResults(
        self,
        alg: QgsProcessingAlgorithm,
        context: QgsProcessingContext,
        result,
        feedback: Optional[QgsProcessingFeedback] = None,
        parameters: Optional[dict] = None,
    ):
        # Re-implementation of QgsProcessingResultsHandler::handleAlgorithmResults
        # from QGIS Repo src/core/processing/qgsprocessingpostprocessor.cpp

        if not parameters:
            parameters = {}
        if feedback is None:
            feedback = QgsProcessingFeedback()

        wrong_layers = []

        feedback.setProgressText(
            QCoreApplication.translate("Postprocessing", "Loading resulting layers")
        )
        i = 0

        added_layers: list[QgsProcessingGuiUtils.ResultLayerDetails] = []

        layers_to_post_process: list[
            tuple[QgsMapLayer, QgsProcessingContext.LayerDetails]
        ] = []

        for dest_id, details in context.layersToLoadOnCompletion().items():
            if feedback.isCanceled():
                return False

            if len(context.layersToLoadOnCompletion()) > 2:
                # only show progress feedback if we're loading a bunch of layers
                feedback.setProgress(
                    100 * i / float(len(context.layersToLoadOnCompletion()))
                )

            try:
                layer = QgsProcessingUtils.mapLayerFromString(dest_id, context, typeHint=details.layerTypeHint)
                # check if it is available in temporary store
                if layer is None:
                    layer = context.temporaryLayerStore().mapLayer(dest_id)

                if isinstance(layer, QgsMapLayer) and layer.isValid():
                    details.setOutputLayerName(layer)

                    output_name = determine_output_name(
                        dest_id, details, alg, context, parameters
                    )
                    post_process_layer(output_name, layer, alg)

                    # Load layer to layer tree root or to a specific group
                    results_group = QgsProcessingGuiUtils.layerTreeResultsGroup(
                        details, context
                    )

                    # note here that we may not retrieve an owned layer -- eg if the
                    # output layer already exists in the destination project
                    owned_map_layer = context.temporaryLayerStore().takeMapLayer(layer)
                    if owned_map_layer:
                        # we don't add the layer to the tree yet -- that's done
                        # later, after we've sorted all added layers
                        result_layer_details = QgsProcessingGuiUtils.ResultLayerDetails(
                            owned_map_layer
                        )
                        result_layer_details.targetLayerTreeGroup = results_group
                        result_layer_details.sortKey = details.layerSortKey or 0
                        result_layer_details.destinationProject = details.project
                        added_layers.append(result_layer_details)

                    if details.postProcessor():
                        # we defer calling the postProcessor set in the context
                        # until the layer has been added to the project's layer
                        # tree, just in case the postProcessor contains logic
                        # relating to layer tree handling
                        layers_to_post_process.append((layer, details))

                else:
                    wrong_layers.append(str(dest_id))
            except Exception:
                QgsMessageLog.logMessage(
                    QCoreApplication.translate(
                        "Postprocessing", "Error loading result layer:"
                    )
                    + "\n"
                    + traceback.format_exc(),
                    "Processing",
                    Qgis.MessageLevel.Critical,
                )
                wrong_layers.append(str(dest_id))
            i += 1

        if iface is not None:
            iface.layerTreeView().setUpdatesEnabled(False)

        QgsProcessingGuiUtils.addResultLayers(
            added_layers, context, iface.layerTreeView() if iface else None
        )

        # all layers have been added to the layer tree, so safe to call
        # postProcessors now
        for layer, details in layers_to_post_process:
            details.postProcessor().postProcessLayer(layer, context, feedback)

        if iface is not None:
            iface.layerTreeView().setUpdatesEnabled(True)

        feedback.setProgress(100)

        if wrong_layers:
            msg = QCoreApplication.translate(
                "Postprocessing", "The following layers were not correctly generated."
            )
            msg += "\n" + "\n".join([f"• {lay}" for lay in wrong_layers]) + "\n"
            msg += QCoreApplication.translate(
                "Postprocessing",
                "You can check the 'Log Messages Panel' in QGIS main window "
                "to find more information about the execution of the algorithm.",
            )
            feedback.reportError(msg)

        return len(wrong_layers) == 0


def determine_output_name(
    dest_id: str,
    details: QgsProcessingContext.LayerDetails,
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext,
    parameters: dict,
) -> str:
    """
    If running a model, the execution will arrive here when an
    algorithm that is part of that model is executed. We check if
    its output is a final output of the model, and adapt the output
    name accordingly
    """
    for out in alg.outputDefinitions():
        if out.name() not in parameters:
            continue
        output_value = parameters[out.name()]
        if hasattr(output_value, "sink"):
            output_value = output_value.sink.valueAsString(context.expressionContext())[
                0
            ]
        else:
            output_value = str(output_value)
        if output_value == dest_id:
            return out.name()

    return details.outputName


def post_process_layer(
    output_name: str, layer: QgsMapLayer, alg: QgsProcessingAlgorithm
):
    """
    Applies post-processing steps to a layer
    """
    style = None
    if output_name:
        style = RenderingStyles.getStyle(alg.id(), output_name)

    if style is None:
        if layer.type() == Qgis.LayerType.Raster:
            style = ProcessingConfig.getSetting(ProcessingConfig.RASTER_STYLE)
        elif layer.type() == Qgis.LayerType.Vector:
            if layer.geometryType() == QgsWkbTypes.GeometryType.PointGeometry:
                style = ProcessingConfig.getSetting(ProcessingConfig.VECTOR_POINT_STYLE)
            elif layer.geometryType() == QgsWkbTypes.GeometryType.LineGeometry:
                style = ProcessingConfig.getSetting(ProcessingConfig.VECTOR_LINE_STYLE)
            else:
                style = ProcessingConfig.getSetting(
                    ProcessingConfig.VECTOR_POLYGON_STYLE
                )
    if style:
        layer.loadNamedStyle(style)

    if layer.type() == Qgis.LayerType.PointCloud:
        try:
            from qgis._3d import QgsPointCloudLayer3DRenderer

            if layer.renderer3D() is None:
                # If the layer has no 3D renderer and syncing 3D to 2D
                # renderer is enabled, we create a renderer and set it up
                # with the 2D renderer
                if layer.sync3DRendererTo2DRenderer():
                    renderer_3d = QgsPointCloudLayer3DRenderer()
                    renderer_3d.convertFrom2DRenderer(layer.renderer())
                    layer.setRenderer3D(renderer_3d)
        except ImportError:
            QgsMessageLog.logMessage(
                QCoreApplication.translate(
                    "Postprocessing",
                    "3D library is not available, "
                    "can't assign a 3d renderer to a layer.",
                )
            )
