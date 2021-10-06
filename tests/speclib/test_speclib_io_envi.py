# noinspection PyPep8Naming
import os
import re
import unittest
import xmlrunner

from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget
from qps.testing import TestObjects, TestCase

from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsEditorWidgetSetup, QgsField

from qpstestdata import enmap, landcover
from qpstestdata import speclib as speclibpath

from qps.speclib.io.vectorsources import *
from qps.speclib.io.csvdata import *
from qps.speclib.io.envi import *
from qps.speclib.io.rastersources import *

from qps.utils import *


class TestSpeclibIO_ENVI(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_ENVI, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_ENVI, cls).tearDownClass()

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path

    def registerIO(self):

        ios = [
            EnviSpectralLibraryIO(),
        ]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_findEnviHeader(self):

        binarypath = speclibpath

        hdr, bin = findENVIHeader(speclibpath)

        self.assertTrue(os.path.isfile(hdr))
        self.assertTrue(os.path.isfile(bin))

        self.assertTrue(bin == speclibpath)
        self.assertTrue(hdr.endswith('.hdr'))

        headerPath = hdr

        # is is possible to use the *.hdr
        hdr, bin = findENVIHeader(headerPath)

        self.assertTrue(os.path.isfile(hdr))
        self.assertTrue(os.path.isfile(bin))

        self.assertTrue(bin == speclibpath)
        self.assertTrue(hdr.endswith('.hdr'))

        feedback = self.createProcessingFeedback()

        pathWrong = enmap
        hdr, bin = findENVIHeader(pathWrong)
        self.assertTrue((hdr, bin) == (None, None))

    def test_ENVI_IO(self):

        testdir = self.testDir()

        n_bands = [[25, 50],
                   [75, 100]
                   ]
        n_bands = np.asarray(n_bands)
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        ENVI_IO = EnviSpectralLibraryIO()
        wExport = ENVI_IO.createExportWidget()
        self.assertIsInstance(wExport, SpectralLibraryExportWidget)
        self.assertIsInstance(wExport, EnviSpectralLibraryExportWidget)
        wExport.setSpeclib(speclib)
        self.assertEqual(EnviSpectralLibraryIO.formatName(), wExport.formatName())
        filter = wExport.filter()
        self.assertIsInstance(filter, str)
        self.assertTrue('*.sli' in filter)

        settings = dict()
        settings = wExport.exportSettings(settings)

        self.assertIsInstance(settings, dict)
        feedback = QgsProcessingFeedback()
        profiles = list(speclib.getFeatures())
        path = self.testDir() / 'exampleENVI.sli'
        files = ENVI_IO.exportProfiles(path.as_posix(), settings, profiles, feedback)
        self.assertIsInstance(files, list)
        self.assertTrue(len(files) == n_bands.shape[0])

        speclib2 = SpectralLibrary()
        wImport = ENVI_IO.createImportWidget()
        self.assertIsInstance(wImport, SpectralLibraryImportWidget)
        self.assertIsInstance(wImport, EnviSpectralLibraryImportWidget)

        for path, nb in zip(files, n_bands[:, 0]):
            self.assertTrue(os.path.exists(path))

            wImport.setSpeclib(speclib2)
            wImport.setSource(path)
            importSettings = wImport.importSettings({})
            self.assertIsInstance(importSettings, dict)
            feedback = QgsProcessingFeedback()
            fields = wImport.sourceFields()
            self.assertIsInstance(fields, QgsFields)
            self.assertTrue(fields.count() > 0)
            self.assertTrue(len(profile_field_list(fields)) > 0)
            ENVI_IO.importProfiles(path, importSettings, feedback)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for profile in profiles:
                self.assertIsInstance(profile, QgsFeature)

        self.showGui([wImport])


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
