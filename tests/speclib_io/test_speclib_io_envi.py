# noinspection PyPep8Naming
import os
import pathlib
import unittest

import numpy as np
import xmlrunner

from qgis.core import QgsProcessingFeedback, QgsFeature, QgsFields
from qps.speclib import FIELD_NAME, FIELD_VALUES
from qps.speclib.core import profile_field_list
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryExportWidget, \
    SpectralLibraryImportWidget
from qps.speclib.io.envi import EnviSpectralLibraryIO, findENVIHeader, EnviSpectralLibraryExportWidget, \
    EnviSpectralLibraryImportWidget
from qps.testing import TestObjects, TestCase
from qpstestdata import enmap
from qpstestdata import speclib as speclibpath


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

    def test_ENVI_Import(self):

        w = EnviSpectralLibraryIO.createImportWidget()
        w.setSource(speclibpath)

        fields = w.sourceFields()
        self.assertIsInstance(fields, QgsFields)
        for n in [FIELD_VALUES, FIELD_NAME, 'source', 'wkt']:
            self.assertTrue(n in fields.names())
        settings = w.importSettings({})
        profiles = EnviSpectralLibraryIO.importProfiles(speclibpath, settings)
        s = ""

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
        files = ENVI_IO.exportProfiles(path.as_posix(), profiles, settings, feedback)
        self.assertIsInstance(files, list)
        self.assertTrue(len(files) == n_bands.shape[0])

        speclib2 = TestObjects.createSpectralLibrary(n=0)
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
