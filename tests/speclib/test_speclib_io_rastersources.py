# noinspection PyPep8Naming
import os
import pathlib
import re
import typing
import unittest
import xmlrunner

from qgis._core import QgsWkbTypes
from qps.speclib.core import is_spectral_feature
from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog, \
    SpectralLibraryIO
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.asd import ASDSpectralLibraryIO, ASDSpectralLibraryImportWidget, ASDBinaryFile
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget
from qps.speclib.io.rastersources import RasterLayerSpectralLibraryIO, RasterLayerSpectralLibraryImportWidget
from qps.testing import TestObjects, TestCase

from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsEditorWidgetSetup, QgsField

from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget




class TestSpeclibIO_Raster(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_Raster, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_Raster, cls).tearDownClass()

    def registerIO(self):
        ios = [RasterLayerSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_raster_input_widget(self):
        layers = [TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.LineString),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point),
                  TestObjects.createRasterLayer()]

        QgsProject.instance().addMapLayers(layers)
        w = RasterLayerSpectralLibraryImportWidget()

        self.showGui(w)

    def test_read_raster(self):
        self.registerIO()

    def test_write_raster(self):
        self.registerIO()

    @unittest.skipIf(TestCase.runsInCI(), 'Test skipped because it opens a blocking dialog')
    def test_dialog(self):
        self.registerIO()
        layers = [TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.LineString),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point),
                  TestObjects.createRasterLayer()]

        QgsProject.instance().addMapLayers(layers)

        sl = TestObjects.createSpectralLibrary()
        import qpstestdata

        root = pathlib.Path(qpstestdata.__file__).parent

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
