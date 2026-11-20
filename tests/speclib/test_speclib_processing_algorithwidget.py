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

        speclib = TestObjects.createSpectralLibrary()

        SpectralProcessingAlgorithmWidget.resetSettings()
        widget = SpectralProcessingAlgorithmWidget(speclib)
        self.assertTrue(widget.algorithm() is None)

        widget = SpectralProcessingAlgorithmWidget(speclib, algorithm=alg1)
        self.assertTrue(widget.algorithm() is alg1)
        self.assertTrue(widget.parent().windowTitle().endswith(alg1.displayName()))

        widget.setAlgorithm(alg2)
        self.assertTrue(widget.algorithm() is alg2)

        with self.assertRaises(ValueError):
            widget.setAlgorithm(None)
        # self.assertTrue(widget.algorithm() is None)
        # widget.setAlgorithm(None)
        # self.assertTrue(widget.algorithm() is None)
        self.showGui(widget)

    def test_settings(self):
        reg: QgsProcessingRegistry = QgsApplication.processingRegistry()
        alg1 = reg.createAlgorithmById('gdal:translate')
        alg2 = reg.createAlgorithmById('native:rescaleraster')

        speclib = TestObjects.createSpectralLibrary()

        widget = SpectralProcessingAlgorithmWidget(speclib, algorithm=alg1)
        self.assertEqual(alg1.id(), widget.algorithm().id())
        par1 = {'NODATA': 1234}
        widget.setParameters(par1)
        widget.saveSettings()

        widget = SpectralProcessingAlgorithmWidget(speclib)
        self.assertEqual(widget.algorithm().id(), alg1.id())
        par_restored = widget.createProcessingParameters()
        self.assertIn('NODATA', par_restored)
        self.assertEqual(par_restored['NODATA'], 1234)
        widget.setAlgorithm(alg2)
        widget.saveSettings()

        widget = SpectralProcessingAlgorithmWidget(speclib)
        self.assertEqual(widget.algorithm().id(), alg2.id())

        widget.resetSettings()

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
