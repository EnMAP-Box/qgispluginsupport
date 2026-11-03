import unittest

import processing
from processing.ProcessingPlugin import Processing
from processing.gui.algorithm_widget import AlgorithmWidget
from qgis.core import Qgis
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingRegistry, QgsApplication, QgsProject
from qgis.core import QgsRasterLayer, QgsProcessingFeedback, QgsProcessingContext

from qps.testing import start_app, TestCase

app = start_app()
Processing.initialize()

print(f'QGIS Version: {Qgis.version} ({Qgis.versionInt()})')
print(f'Dev Version: {Qgis.devVersion()}')

from qps.reimplementation.algorithmwidget import AlgorithmWidget


class TestAlgorithmWidgetContextHandling(TestCase):
    """
    Test cases for AlgorithmWidget external context support.
    """

    def createTempRaster(self) -> QgsRasterLayer:
        results = processing.run("native:createconstantrasterlayer",
                                 {'EXTENT': '-1.169703872,1.169703872,-1.000000000,1.000000000 [EPSG:4326]',
                                  'TARGET_CRS': 'EPSG:4326', 'PIXEL_SIZE': 1, 'NUMBER': 1,
                                  'OUTPUT_TYPE': 5, 'CREATION_OPTIONS': None, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT})
        layer = QgsRasterLayer(results['OUTPUT'])
        self.assertTrue(layer.isValid())
        return layer

    def test_algorithmwidget(self):
        """
        Test that AlgorithmWidget class exists.
        """
        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg = reg.algorithmById('native:rastergaussianblur')

        lyr_custom = self.createTempRaster()
        lyr_custom.setName('LayerCustomContext')

        project = QgsProject()
        project.addMapLayer(lyr_custom)
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(project)
        context.setFeedback(feedback)

        d = AlgorithmWidget(alg, context=context)
        self.showGui(d)


if __name__ == '__main__':
    unittest.main()
