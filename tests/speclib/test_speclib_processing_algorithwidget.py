import unittest

from qgis.core import (
    QgsApplication, QgsProcessingContext, QgsProcessingRegistry, QgsProject
)
from qgis.core import QgsProcessingAlgorithm

from qps import initAll
from qps.speclib.gui.spectralprocessingalgorithmwidget import SpectralProcessingAlgorithmWidget
from qps.testing import TestCase, TestObjects, start_app

start_app()
initAll()


class SpectralProcessingAlgorithmWidgetTests(TestCase):

    def test_algorithm_updates(self):
        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg1 = reg.createAlgorithmById('gdal:translate')
        alg2 = reg.createAlgorithmById('native:rescaleraster')

        widget = SpectralProcessingAlgorithmWidget(None)
        self.assertTrue(widget.algorithm() is None)

        widget = SpectralProcessingAlgorithmWidget(alg1)
        self.assertTrue(widget.algorithm() is alg1)
        self.assertTrue(widget.windowTitle().endswith(alg1.displayName()))

        widget.setAlgorithm(alg2)
        self.assertTrue(widget.algorithm() is alg2)

        # widget.setAlgorithm(None)
        # self.assertTrue(widget.algorithm() is None)
        self.showGui(widget)

    def test_spectral_processing_algorithm_widget(self):
        sl = TestObjects.createSpectralLibrary()

        p = QgsProject()
        p.addMapLayer(sl)
        context = QgsProcessingContext()
        context.setProject(p)

        reg = QgsApplication.processingRegistry()
        self.assertIsInstance(reg, QgsProcessingRegistry)
        alg1 = reg.createAlgorithmById('gdal:translate')
        alg2 = reg.createAlgorithmById('native:rescaleraster')

        self.assertIsInstance(alg1, QgsProcessingAlgorithm)
        self.assertIsInstance(alg2, QgsProcessingAlgorithm)

        w = SpectralProcessingAlgorithmWidget(sl)
        w.setAlgorithm(alg1)
        self.assertEqual(w.algorithm(), alg1)
        w.setAlgorithm(alg2)
        self.assertEqual(w.algorithm(), alg2)

        self.showGui(w)


if __name__ == '__main__':
    unittest.main(buffer=False)
