import unittest

import qgis.processing
from processing.ProcessingPlugin import Processing
from processing.gui.algorithm_widget import AlgorithmWidget
from qgis.core import (
    Qgis, QgsProcessing, QgsProcessingParameterRasterLayer, QgsProcessingRegistry, QgsApplication, QgsProject,
    QgsRasterLayer, QgsProcessingFeedback, QgsProcessingContext)
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

    def test_CustomContextAlgorithmWidget(self):
        # an example using an AlgorithmWidget, just for visualization

        class CustomContextAlgorithmWidget(AlgorithmWidget):
            def __init__(self, *args, context=None, **kwds):
                self._context = context
                self._mbar = QgsMessageBar()
                self.n_processing_context_calls = 0
                super().__init__(*args, **kwds)

            def messageBar(self):
                return self._mbar

            def processingContext(self):
                self.n_processing_context_calls += 1
                if not isinstance(self._context, QgsProcessingContext):
                    raise ValueError('custom context is not set')
                print(f'# Custom context layers: {self._context.project().mapLayers()}')
                return self._context

        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = reg.algorithmById('native:rastergaussianblur')

        lyr_standard = self.createTempRaster('LayerStandardContext')
        QgsProject.instance().addMapLayer(lyr_standard)

        # create a custom context with custom layers
        lyr_custom = self.createTempRaster('LayerCustomContext')
        custom_project = QgsProject()
        custom_project.addMapLayer(lyr_custom)
        feedback = QgsProcessingFeedback()
        custom_context = QgsProcessingContext()
        custom_context.setProject(custom_project)
        custom_context.setFeedback(feedback)

        # the custom dialogs should show 'LayerCustomContext' but shows 'LayerStandardContext'
        d = CustomContextAlgorithmWidget(alg, context=custom_context)
        d.show()
        self.assertTrue(d.n_processing_context_calls > 0)
        if not self.is_ci_run():
            app.exec()

        QgsProject.instance().removeAllMapLayers()

    def test_createParametersPanel(self):

        lyr1 = TestObjects.createRasterLayer(name='Raster Layer1')
        lyr2 = TestObjects.createRasterLayer(name='Raster Layer2')
        QgsProject.instance().addMapLayers([lyr1])

        project2 = QgsProject()
        project2.addMapLayers([lyr2])

        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = reg.algorithmById('native:rastergaussianblur')
        from qps.reimplementation.processingparameterswidget import ProcessingParametersWidget
        mbar = QgsMessageBar()
        widget = ProcessingParametersWidget(alg, False, None, mbar)
        widget.initWidgets()
        parameters = widget.createProcessingParameters()
        self.assertEqual(parameters.get('INPUT'), lyr1.id())

        widget = ProcessingParametersWidget(alg, False, None, mbar)
        widget.registerProcessingContextGenerator()

        self.showGui(widget)


if __name__ == '__main__':
    unittest.main()
