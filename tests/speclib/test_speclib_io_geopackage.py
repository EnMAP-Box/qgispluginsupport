# noinspection PyPep8Naming
import os
import re
import unittest
import xmlrunner


from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog, \
    SpectralLibraryIO
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget
from qps.testing import TestObjects, TestCase

from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsEditorWidgetSetup, QgsField


from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, GeoPackageSpectralLibraryExportWidget


from qps.utils import *


class TestSpeclibIO_GPKG(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_GPKG, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_GPKG, cls).tearDownClass()

    def registerIO(self):

        ios = [GeoPackageSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_write_profiles(self):

        IO = GeoPackageSpectralLibraryIO()

        exportWidget = IO.createExportWidget()
        self.assertIsInstance(exportWidget, GeoPackageSpectralLibraryExportWidget)
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        exportWidget.setSpeclib(sl)
        testdir = self.createTestOutputDirectory() / 'Geopackage'
        os.makedirs(testdir, exist_ok=True)

        path = testdir / 'exported_profiles.gpkg'
        exportSettings = dict()
        feedback = QgsProcessingFeedback()
        files = IO.exportProfiles(path.as_posix(), exportSettings, sl.getFeatures(), feedback)

        self.assertIsInstance(files, list)
        for file in files:
            ds = ogr.Open(file)
            self.assertIsInstance(ds, ogr.DataSource)
            lyr = QgsVectorLayer(file)
            self.assertIsInstance(lyr, QgsVectorLayer)
            self.assertTrue(lyr.isValid())
            self.assertTrue(lyr.featureCount() > 0)

        s = ""


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
