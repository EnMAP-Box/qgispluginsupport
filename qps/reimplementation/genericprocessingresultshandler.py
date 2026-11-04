# -*- coding: utf-8 -*-

"""
ProcessingResultsHandler reimplementation for QGIS Python plugins.

This module provides a Python reimplementation of the C++ QgsAppProcessingResultsHandler
class from QGIS src/app/processing/qgsappprocessingutils.cpp
"""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsProcessingAlgorithm, QgsProcessingFeedback, QgsProcessingUtils
from qgis.core import QgsProcessingContext, QgsMapLayer
from qgis.gui import QgisInterface, QgsLayerTreeView, QgsProcessingGuiUtils
from qgis.utils import iface as _iface


class GenericProcessingResultsHandler(object):
    """
    Python reimplementation of the QgsAppProcessingResultsHandler (QGIS 4.4+).
    in QGIS Repo
    - src/app/processing/qgsappprocessingutils.cpp
    - src/core/processing/qgsprocessingpostprocessor.cpp
    to be used with individual QgsInterface instances
    """

    def __init__(self, parent=None,
                 iface: QgisInterface | None = None,
                 layer_tree_view: QgsLayerTreeView | None = None):
        """
        Constructor for ProcessingResultsHandler.
        
        :param parent: Parent object (optional)
        """
        if iface is None:
            iface = _iface
        self._iface = _iface

        if layer_tree_view is None:
            layer_tree_view = iface.layerTreeView()
        self._layer_tree_view: QgsLayerTreeView = layer_tree_view

    def handleAlgorithmResults(
        self,
        algorithm: QgsProcessingAlgorithm,
        context: QgsProcessingContext,
        parameters,
        feedback: QgsProcessingFeedback | None = None
    ) -> bool:

        if feedback is None:
            feedback = QgsProcessingFeedback()

        # Disable updates to layer tree view during processing
        layer_tree_view = self._layer_tree_view
        if layer_tree_view:
            layer_tree_view.setUpdatesEnabled(False)

        # Call base class implementation
        result = self.handleAlgorithmResultsProtected(algorithm, context, parameters, feedback)

        # Re-enable updates to layer tree view
        if layer_tree_view:
            layer_tree_view.setUpdatesEnabled(True)

        return result

    def handleAlgorithmResultsProtected(
        self,
        algorithm,
        context,
        parameters,
        feedback
    ):

        added_layers: list[QgsProcessingGuiUtils.ResultLayerDetails] = []

        # Store the current selected node
        if self._layer_tree_view:
            current_node = self._layer_tree_view.currentNode()
        else:
            current_node = None

        feedback.setProgressText("Loading resulting layers")

        layers_to_post_process: list[
            tuple[QgsMapLayer, QgsProcessingContext.LayerDetails]
        ] = []

        for i, (dest_id, details) in enumerate(context.layersToLoadOnCompletion().items()):
            if feedback.isCanceled():
                return False

            if len(context.layersToLoadOnCompletion()) > 2:
                # only show progress feedback if we're loading a bunch of layers
                feedback.setProgress(
                    100 * i / float(len(context.layersToLoadOnCompletion()))
                )

            try:
                layer = QgsProcessingUtils.mapLayerFromString(dest_id, context, typeHint=details.layerTypeHint)
                # check if it is available inthe temporary store
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
        s = ""

    def handleAddResultLayers(
        self,
        details,
        context: QgsProcessingContext
    ) -> bool:

        return True

    def setNewActiveLayer(self, layer: QgsMapLayer):
        """
        Sets the new project active layer after processing the results.
        
        This override sets the active layer in the QGIS application.
        
        :param layer: The layer to set as active
        """
        if isinstance(self._iface, QgisInterface):
            self._iface.setActiveLayer(layer)
