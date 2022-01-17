# noinspection PyPep8Naming
import os
import pathlib
import re
import unittest

from qgis.core import QgsProcessingFeedback, QgsFeature, QgsVectorLayer

from qps.speclib.core.spectrallibraryio import SpectralLibraryIO
from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
from qps.testing import TestObjects, TestCase


class TestSpeclibIO_EcoSIS(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_EcoSIS, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_EcoSIS, cls).tearDownClass()

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path

    def registerIO(self):

        ios = [
            EcoSISSpectralLibraryIO(),
        ]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    @unittest.skip('Needs update to new API')
    def test_EcoSIS(self):
        feedback = QgsProcessingFeedback()

        from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
        import qpstestdata
        ecosysFiles = []
        for f in os.scandir(pathlib.Path(qpstestdata.__file__).parent / 'ecosis'):
            if re.search(r'\.(csv|xlsx)$', f.name):
                ecosysFiles.append(pathlib.Path(f.path))

        # 1. read
        feedback = QgsProcessingFeedback()

        for path in ecosysFiles:

            print('Read {}...'.format(path))

            importSettings = dict()
            continue
            profiles = EcoSISSpectralLibraryIO.importProfiles(path, importSettings=importSettings, feedback=feedback)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

        # 2. write
        speclib = TestObjects.createSpectralLibrary(50)

        # remove x/y values from first profile. this profile should be skipped in the outputs
        p0 = speclib[0]

        self.assertIsInstance(p0, QgsFeature)
        p0.setValues(x=[], y=[])
        speclib.startEditing()
        speclib.updateFeature(p0)
        self.assertTrue(speclib.commitChanges())
        TEST_DIR = self.createTestOutputDirectory()
        pathCSV = os.path.join(TEST_DIR, 'speclib.ecosys.csv')
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, feedback=None)
        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(p))

            slPart = EcoSISSpectralLibraryIO.readFrom(p)
            self.assertIsInstance(slPart, QgsVectorLayer)

            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)
