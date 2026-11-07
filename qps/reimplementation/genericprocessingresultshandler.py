# -*- coding: utf-8 -*-

"""
ProcessingResultsHandler reimplementation for QGIS Python plugins.

This module provides a Python reimplementations of the
C++ QgsAppProcessingResultsHandler and QgsProcessingResultsHandler
which by now (Nov 2027) are considered to be released with QGIS 4.4 but not stable Python API
Aim is to use similar functionality with QGS 4.0+ and allow to run with QgisInterface instances
different to the QGIS Main Desktop

see QGIS src/app/processing/qgsappprocessingutils.cpp
"""
import traceback
from typing import Tuple

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsMessageLog, Qgis, QgsSettings, QgsVectorLayer, QgsRasterLayer
from qgis.core import QgsProcessingAlgorithm, QgsProcessingFeedback, QgsProcessingUtils
from qgis.core import QgsProcessingContext, QgsMapLayer
from qgis.core import (
    QgsProject, QgsLayerTreeGroup, QgsProcessingOutputDefinition, QgsProcessingOutputLayerDefinition,
    QgsProperty
)
from qgis.gui import QgisInterface, QgsLayerTreeView
from qgis.utils import iface as _iface


class GenericProcessingResultsHandler(object):
    """
    Python reimplementation of the QgsAppProcessingResultsHandler (QGIS 4.4+).
    in QGIS Repo
    - src/app/processing/qgsappprocessingutils.cpp
    - src/core/processing/qgsprocessingpostprocessor.cpp
    to be used with individual QgsInterface instances
    """

    def __init__(self, parent=None,  # noqa: QGS105 # support for other QgisInterfaces
                 iface: QgisInterface | None = None,
                 layer_tree_view: QgsLayerTreeView | None = None):
        """
        Constructor for ProcessingResultsHandler.
        :param parent: Parent object (optional)
        """
        if iface is None:
            iface = _iface
        self._iface = iface

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
        success, results = self.handleAlgorithmResultsProtected(algorithm, context, parameters, feedback)

        # Re-enable updates to layer tree view
        if layer_tree_view:
            layer_tree_view.setUpdatesEnabled(True)

        return success

    def layerTreeResultsGroup(
        self,
        layer_details: QgsProcessingContext.LayerDetails,
        context: QgsProcessingContext
    ) -> QgsLayerTreeGroup | None:
        # imitates QgsProcessingResultsHandler::layerTreeResultsGroup
        destinationProject = layer_details.project if hasattr(layer_details, 'project') else context.project()

        layerTreeRoot = None
        if isinstance(self._layer_tree_view, QgsLayerTreeView):
            layerTreeRoot = self._layer_tree_view.layerTreeModel().rootGroup()
        elif isinstance(destinationProject, QgsProject):
            layerTreeRoot = destinationProject.layerTreeRoot()

        if not isinstance(layerTreeRoot, QgsLayerTreeGroup):
            return None

        resultsGroup = None
        if layer_details.groupName in ['', None]:
            resultsGroup = layerTreeRoot
        else:
            resultsGroup = layerTreeRoot.findGroup(layer_details.groupName)
            if resultsGroup is None:
                resultsGroup = layerTreeRoot.insertGroup(0, layer_details.groupName)
                resultsGroup.setExpanded(True)

        return resultsGroup

    def postProcessLayer(self, layer: QgsMapLayer, output_name: str, algorithm: QgsProcessingAlgorithm):
        # imitates QgsProcessingLayerPostProcessor::postProcessLayer
        if not isinstance(layer, QgsMapLayer) or not layer.isValid():
            return

        styleFilePath = None
        if output_name not in ['', None] and isinstance(algorithm, QgsProcessingAlgorithm):
            # todo: get styleFilePath from QgsApplication.
            # available with QGS 4.4
            pass

        if styleFilePath is None:
            settings = QgsSettings()
            if isinstance(layer, QgsVectorLayer):
                gt = layer.geometryType()
                if gt == Qgis.GeometryType.Point:
                    styleFilePath = settings.value('Processing/Configuration/VECTOR_POINT_STYLE')
                elif gt == Qgis.GeometryType.Line:
                    styleFilePath = settings.value('Processing/Configuration/VECTOR_LINE_STYLE')
                elif gt == Qgis.GeometryType.Polygon:
                    styleFilePath = settings.value('Processing/Configuration/VECTOR_POLYGON_STYLE')

            elif isinstance(layer, QgsRasterLayer):
                styleFilePath = settings.value('Processing/Configuration/RASTER_STYLE')

        if isinstance(styleFilePath, str):
            layer.loadNamedStyle(styleFilePath)

    def determineOutputName(
        self, destinationId: str,
        details: QgsProcessingContext.LayerDetails,
        algorithm: QgsProcessingAlgorithm,
        context: QgsProcessingContext,
        parameters: dict
    ) -> str:
        # imitates QgsProcessingResultsHandler::determineOutputName
        if not isinstance(algorithm, QgsProcessingAlgorithm):
            return details.outputName

        for output in algorithm.outputDefinitions():
            output: QgsProcessingOutputDefinition
            outputValue = parameters.get(output.name())
            if outputValue is None:
                continue

            if isinstance(outputValue, QgsProcessingOutputLayerDefinition):
                sink: QgsProperty = output.sink
                outputValue = sink.valueAsString(context.expressionContext())
            else:
                outputValue = str(outputValue)
            if outputValue == destinationId:
                return output.name()

        return details.outputName

    def handleAlgorithmResultsProtected(
        self,
        algorithm,
        context,
        parameters,
        feedback
    ) -> Tuple[bool, list]:

        feedback.setProgressText("Loading resulting layers")
        added_layer_details: list = []
        invalid_layers: list = []

        for i, (dest_id, details) in enumerate(context.layersToLoadOnCompletion().items()):
            dest_id: str
            details: QgsProcessingContext.LayerDetails

            if feedback.isCanceled():
                return False, added_layer_details

            if len(context.layersToLoadOnCompletion()) > 2:
                # only show progress feedback if we're loading a bunch of layers
                feedback.setProgress(
                    100 * i / float(len(context.layersToLoadOnCompletion()))
                )

            try:
                layer = QgsProcessingUtils.mapLayerFromString(dest_id, context, typeHint=details.layerTypeHint)
                # check if layer is available in temporary store
                if layer is None:
                    layer = context.temporaryLayerStore().mapLayer(dest_id)

                if isinstance(layer, QgsMapLayer) and layer.isValid():
                    details.setOutputLayerName(layer)

                    output_name = self.determineOutputName(dest_id, details, algorithm, context, parameters)
                    self.postProcessLayer(layer, output_name, algorithm)

                    # Load layer to layer tree root or to a specific group
                    resultsGroup = self.layerTreeResultsGroup(details, context)
                    if isinstance(resultsGroup, QgsLayerTreeGroup):
                        resultsGroup.addLayer(layer)
                        self.postProcessLayer(layer, output_name, algorithm)

                    added_layer_details.append(layer)
                else:
                    invalid_layers.append(dest_id)
            except Exception:
                msg = QCoreApplication.translate(
                    "Postprocessing", "Error loading result layer:"
                ) + "\n" + traceback.format_exc()

                QgsMessageLog.logMessage(
                    msg, "Processing", Qgis.MessageLevel.Critical,
                )
                invalid_layers.append(dest_id)

        newActiveLayer = self.handleAddResultLayers(added_layer_details, context)
        self.setNewActiveLayer(newActiveLayer)

        feedback.setProgress(100)

        if invalid_layers:
            msg = QCoreApplication.translate(
                "Postprocessing", "The following layers were not correctly generated."
            )
            msg += "\n" + "\n".join([f"• {lay}" for lay in invalid_layers]) + "\n"
            msg += QCoreApplication.translate(
                "Postprocessing",
                "You can check the 'Log Messages Panel' in QGIS main window "
                "to find more information about the execution of the algorithm.",
            )
            feedback.reportError(msg)

        return len(invalid_layers) == 0, added_layer_details

    def handleAddResultLayers(self, layers, context: QgsProcessingContext):

        for layer in layers:
            # move layer from temporary store to context project, if necessary
            tmp = context.temporaryLayerStore().takeMapLayer(layer)
            target_project = context.project()
            target_project.addMapLayer(tmp)

        pass

    def setNewActiveLayer(self, layer: QgsMapLayer):
        """
        Sets the new project active layer after processing the results.

        This override sets the active layer in the QGIS application.
        :param layer: The layer to set as active
        """
        if isinstance(self._iface, QgisInterface):
            self._iface.setActiveLayer(layer)
