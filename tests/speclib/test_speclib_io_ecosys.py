# noinspection PyPep8Naming
import os

from qgis.core import QgsFeature, QgsVectorLayer
from qps.speclib.core import is_spectral_feature
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO
from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
from qps.testing import TestCase, TestObjects, start_app
from qps.utils import file_search
from qpstestdata import DIR_ECOSIS

start_app()

s = ""


class TestSpeclibIO_EcoSIS(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_EcoSIS, cls).setUpClass(*args, **kwds)
        cls.registerIO(cls)

    def registerIO(self):

        ios = [
            EcoSISSpectralLibraryIO(),
        ]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_read_EcoSIS(self):

        ecosysFiles = file_search(DIR_ECOSIS, '*.csv', recursive=True)
        context, feedback = self.createProcessingContextFeedback()

        for path in ecosysFiles:
            print('Read {}...'.format(path))
            importSettings = {}
            profiles = EcoSISSpectralLibraryIO.importProfiles(path, importSettings=importSettings, feedback=feedback)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

    def test_write_EcoSIS(self):
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
