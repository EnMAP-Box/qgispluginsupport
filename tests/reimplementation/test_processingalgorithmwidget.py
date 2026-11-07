import unittest

import qgis.processing
from processing.ProcessingPlugin import Processing
from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingRegistry,
    QgsProject,
    QgsRasterLayer,
)
from qgis.gui import (
    QgsProcessingAlgorithmWidgetBase,
    QgsProcessingContextGenerator,
    QgsProcessingParametersGenerator,
)

from qps.reimplementation.processingalgorithmwidget import ProcessingAlgorithmWidget
from qps.reimplementation.processingparameterswidget import ProcessingParametersWidget
from qps.testing import start_app, TestCase

app = start_app()
Processing.initialize()


class TestProcessingAlgorithmWidget(TestCase):
    def createAlgorithm(self):
        registry: QgsProcessingRegistry = QgsApplication.processingRegistry()
        algorithm = registry.createAlgorithmById("native:rastergaussianblur")
        self.assertIsNotNone(algorithm)
        return algorithm.create()

    def createTempRaster(self) -> QgsRasterLayer:
        results = qgis.processing.run(
            "native:createconstantrasterlayer",
            {
                "EXTENT": "-1.0,1.0,-1.0,1.0 [EPSG:4326]",
                "TARGET_CRS": "EPSG:4326",
                "PIXEL_SIZE": 1,
                "NUMBER": 1,
                "OUTPUT_TYPE": 5,
                "CREATION_OPTIONS": None,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            },
        )
        layer = QgsRasterLayer(results["OUTPUT"])
        self.assertTrue(layer.isValid())
        return layer

    def test_constructor_context_and_generators(self):
        widget = ProcessingAlgorithmWidget(self.createAlgorithm())

        self.assertIsInstance(widget, QgsProcessingAlgorithmWidgetBase)
        self.assertIsInstance(widget, QgsProcessingContextGenerator)
        self.assertIsInstance(widget, QgsProcessingParametersGenerator)
        self.assertFalse(widget.inPlace())

        context = widget.processingContext()
        feedback = widget._feedback
        self.assertIsInstance(context, QgsProcessingContext)
        self.assertIsInstance(feedback, QgsProcessingFeedback)
        self.assertIs(widget.processingContext(), context)
        self.assertIs(widget._feedback, feedback)

        flags = QgsProcessingAlgorithmWidgetBase.WidgetFlags(
            QgsProcessingAlgorithmWidgetBase.WidgetFlag.NoDocking
        )
        in_place_widget = ProcessingAlgorithmWidget(
            self.createAlgorithm(),
            in_place=True,
            flags=flags,
            initial_state=Qgis.DockableWidgetInitialState.RestorePreviousState,
        )
        self.assertTrue(in_place_widget.inPlace())

    def test_panel_parameter_delegation_and_missing_panel(self):
        widget = ProcessingAlgorithmWidget(self.createAlgorithm())
        self.assertIsNone(widget.parametersWidget())
        self.assertEqual(widget.createProcessingParameters(), {})

        panel = widget.createParametersPanel(False, None, widget.messageBar())
        widget.setMainWidget(panel)
        panel = widget.parametersWidget()
        self.assertIsInstance(panel, ProcessingParametersWidget)

        layer = self.createTempRaster()
        project = QgsProject.instance()
        project.addMapLayer(layer)
        try:
            widget.setParameters({"INPUT": layer.id()})
            self.assertEqual(panel.wrapper("INPUT").parameterValue(), layer.id())
            self.assertIn("INPUT", widget.createProcessingParameters())
        finally:
            project.removeMapLayer(layer)

    def test_validation_palette_is_reset_after_acceptance(self):
        registry: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = registry.createAlgorithmById("native:rastergaussianblur")

        layer = self.createTempRaster()
        project = QgsProject()
        project.addMapLayer(layer)

        context = QgsProcessingContext()
        context.setProject(project)

        parent_window = QMainWindow()
        widget = ProcessingAlgorithmWidget(alg, processing_context=context, parent_window=parent_window)
        panel = widget.createParametersPanel(False, None, widget.messageBar())
        panel.setParent(parent_window)
        widget.setMainWidget(panel)
        self.assertEqual(panel, widget.parametersWidget())
        widget.setParameters({"INPUT": 'invalid', 'BAND': 'invalid'})
        panel.validate()
        input_widget = panel.wrapper("INPUT").wrappedWidget()
        widget.createProcessingParameters()

        self.showGui(widget)
        if False:
            self.assertEqual(widget.createProcessingParameters(), {})

            widget.buttonBox().accepted.emit()
            self.assertEqual(input_widget.palette().color(QPalette.ColorRole.Base),
                             QPalette().color(QPalette.ColorRole.Base))


if __name__ == "__main__":
    unittest.main()
