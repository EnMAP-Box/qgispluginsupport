import unittest

import qgis.processing
from processing.ProcessingPlugin import Processing
from qgis._core import QgsProcessingFeedback
from qgis._gui import QgsProcessingParametersGenerator, QgsProcessingParameterWidgetContext
from qgis.core import (
    Qgis, QgsProcessing, QgsProcessingParameterRasterLayer, QgsProcessingRegistry, QgsApplication, QgsProject,
    QgsRasterLayer, QgsProcessingContext)
from qgis.gui import QgsGui, QgsMessageBar, QgsProcessingContextGenerator

from qps.testing import start_app, TestCase, TestObjects

app = start_app()
Processing.initialize()

print(f'QGIS Version: {Qgis.version()} ({Qgis.versionInt()})')
print(f'Dev Version: {Qgis.devVersion()}')


class TestAlgorithmWidgetContextHandling(TestCase):
    """
    Test cases for AlgorithmWidget external context support.
    """

    def createTempRaster(self, name: str) -> QgsRasterLayer:
        results = qgis.processing.run(
            "native:createconstantrasterlayer",
            {'EXTENT': '-1.0,1.0,-1.0,1.0 [EPSG:4326]',
             'TARGET_CRS': 'EPSG:4326', 'PIXEL_SIZE': 1, 'NUMBER': 1,
             'OUTPUT_TYPE': 5, 'CREATION_OPTIONS': None,
             'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT}
        )
        layer = QgsRasterLayer(results['OUTPUT'])
        layer.setName(name)
        self.assertTrue(layer.isValid())
        return layer

    def test_parameter_widget_wrapper_widget(self):
        # Aim: use a custom processing context
        # from which a user can select layers

        class CustomProcessingContextGenerator(QgsProcessingContextGenerator):
            def __init__(self, context):
                super().__init__()
                self._context = context
                self.n_processing_context_calls = 0

            def processingContext(self):
                self.n_processing_context_calls += 1
                return self._context

        lyr_custom = self.createTempRaster('LayerCustomContext')
        lyr_standard = self.createTempRaster('LayerStandardContext')
        QgsProject.instance().addMapLayer(lyr_standard)

        # create a custom context with layers different to QgsProject.instance()
        c_project = QgsProject()
        c_project.addMapLayer(lyr_custom)
        c_context = QgsProcessingContext()
        c_context.setProject(c_project)

        c_generator = CustomProcessingContextGenerator(c_context)

        # the following lines simulate what happens within
        # QgsProcessingParametersWidget::initWidgets()
        # https://github.com/qgis/QGIS/blob/2829fc55840474e42c64f0bca756c2fda272a0bf/src/gui/processing/qgsprocessingparameterswidget.cpp#L326

        processing_context = c_generator.processingContext()
        widget_context = QgsGui.processingGuiRegistry().createWidgetContext()

        definition = QgsProcessingParameterRasterLayer('myraster')
        wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(
            definition, Qgis.ProcessingMode.Standard
        )

        # uncomment the next line to let the widget context use the same project as the
        # processing context andnensure, that the custom context layers are shown
        # in the map layer combox
        # w_context.setProject(c_context.project())

        wrapper.setWidgetContext(widget_context)
        wrapper.registerProcessingContextGenerator(c_generator)

        raster_widget = wrapper.createWrappedWidget(processing_context)

        # get the current text of the raster layer combobox
        combobox_text = raster_widget.children()[1].currentText()
        print(f'Raster layer combobox text: {combobox_text}')
        self.assertTrue(
            lyr_custom.name() in combobox_text,
            msg=f'Layer name "{lyr_custom.name()}" is not in combobox text "{combobox_text}"'
        )

    def test_createParametersPanel(self):
        lyr1 = TestObjects.createRasterLayer(name='Raster Layer')
        lyr2 = TestObjects.createRasterLayer(name='Raster Layer Custom')
        QgsProject.instance().addMapLayers([lyr1])

        custom_project = QgsProject()
        custom_project.addMapLayers([lyr2])

        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = reg.algorithmById('native:rastergaussianblur')
        from qps.reimplementation.processingparameterswidget import ProcessingParametersWidget
        mbar = QgsMessageBar()

        widget = ProcessingParametersWidget(alg, False, None, mbar)

        custom_feedback = QgsProcessingFeedback()
        custom_context = QgsProcessingContext()
        custom_context.setFeedback(custom_feedback)

        custom_widget_context = QgsProcessingParameterWidgetContext()
        custom_widget_context.setProject(custom_project)

        class ContextGenerator(QgsProcessingContextGenerator,
                               QgsProcessingParametersGenerator):

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def processingContext(self):
                return custom_context

            def createWidgetContext(self):
                return custom_widget_context

            def createProcessingParameters(self):
                return {}

        gen = ContextGenerator()
        widget.registerWidgetContextGenerator(gen)
        widget.registerProcessingContextGenerator(gen)
        widget.registerProcessingParametersGenerator(gen)

        widget.initWidgets()
        self.showGui(widget)
        parameters = widget.createProcessingParameters()
        self.assertEqual(parameters.get('INPUT'), lyr2.id())

        self.showGui(widget)

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
