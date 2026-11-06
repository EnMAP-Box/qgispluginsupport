import unittest

import qgis.processing
from processing.ProcessingPlugin import Processing
from qgis.core import Qgis
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingRegistry, QgsApplication, QgsProject
from qgis.core import QgsRasterLayer, QgsProcessingFeedback, QgsProcessingContext
from qgis.gui import QgsProcessingParametersGenerator, QgsProcessingContextGenerator, \
    QgsProcessingParameterWidgetContext

from qps.reimplementation.algorithmwidget import AlgorithmWidget
from qps.testing import start_app, TestCase

app = start_app()
Processing.initialize()

print(f'QGIS Version: {Qgis.version} ({Qgis.versionInt()})')
print(f'Dev Version: {Qgis.devVersion()}')


class TestAlgorithmWidgetContextHandling(TestCase):
    """
    Test cases for AlgorithmWidget external context support.
    """

    def createTempRaster(self) -> QgsRasterLayer:
        results = qgis.processing.run("native:createconstantrasterlayer",
                                      {'EXTENT': '-1.169703872,1.169703872,-1.000000000,1.000000000 [EPSG:4326]',
                                       'TARGET_CRS': 'EPSG:4326', 'PIXEL_SIZE': 1, 'NUMBER': 1,
                                       'OUTPUT_TYPE': 5, 'CREATION_OPTIONS': None,
                                       'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
        layer = QgsRasterLayer(results['OUTPUT'])
        self.assertTrue(layer.isValid())
        return layer

    def test_algorithmwidget(self):
        """
        Test that AlgorithmWidget class exists.
        """
        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = reg.createAlgorithmById('native:virtualrastercalc')

        lyr_custom = self.createTempRaster()
        lyr_custom.setName('LayerCustomContext')

        project = QgsProject()
        project.addMapLayer(lyr_custom)
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(project)
        context.setFeedback(feedback)

        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(project)

        parameters = {'LAYERS': [lyr_custom],
                      'EXPRESSION': f'"{lyr_custom.name()}@1"', 'EXTENT': None, 'CELL_SIZE': None, 'CRS': None,
                      'LAYER_NAME': 'testlayer'}

        d = AlgorithmWidget(alg, processing_context=context, widget_context=widget_context)

        if Qgis.versionInt() >= 44000:
            from qgis.gui import QgsProcessingWidgetContextGenerator
            self.assertIsInstance(d, QgsProcessingWidgetContextGenerator)
        self.assertIsInstance(d, QgsProcessingContextGenerator)
        self.assertIsInstance(d, QgsProcessingParametersGenerator)

        d.setParameters(parameters)
        d.runButton().click()
        results = d.results()

        # ensure that temporary outputs have been transferred to the context.project()
        result_id = results.get('OUTPUT')
        layer = context.project().mapLayer(result_id)

        self.assertIsInstance(layer, QgsRasterLayer)
        self.assertTrue(layer.isValid())

        self.showGui(d)


if __name__ == '__main__':
    unittest.main()
