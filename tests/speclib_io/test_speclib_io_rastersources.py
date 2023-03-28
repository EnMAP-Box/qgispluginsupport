# noinspection PyPep8Naming
import pathlib
import unittest

from qgis.core import QgsWkbTypes

from qgis.core import QgsProject
from qps.speclib.core.spectrallibraryio import SpectralLibraryImportDialog, \
    SpectralLibraryIO
from qps.speclib.io.rastersources import RasterLayerSpectralLibraryIO, RasterLayerSpectralLibraryImportWidget
from qps.testing import TestObjects, TestCaseBase, start_app2

start_app2()


class TestSpeclibIO_Raster(TestCaseBase):
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
        QgsProject.instance().removeAllMapLayers()

    def test_read_raster(self):
        self.registerIO()

    def test_write_raster(self):
        self.registerIO()

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Test skipped because it opens a blocking dialog')
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
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
