from math import isnan

from qgis.core import QgsFeature
from qps.speclib.core import is_spectral_feature
from qps.testing import start_app, TestCase
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO
from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
from qps.utils import file_search
from qpstestdata import DIR_ECOSIS

# noinspection PyPep8Naming

start_app()


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
            profiles = EcoSISSpectralLibraryIO.importProfiles(path, feedback=feedback)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

            print('Read {} (generic IO)...'.format(path))

            profiles2 = SpectralLibraryIO.readProfilesFromUri(path)
            self.assertIsInstance(profiles2, list)
            self.assertTrue(len(profiles2) > 0)
            for p1, p2 in zip(profiles, profiles2):
                p1: QgsFeature
                p2: QgsFeature
                self.assertTrue(is_spectral_feature(p2))
                data1 = p1.attributeMap()
                data2 = p2.attributeMap()

                for k in data1.keys():
                    v1 = data1[k]
                    v2 = data2[k]
                    if v1 != v2 and not (isnan(v1) and isnan(v2)):
                        self.assertEqual(v1, v2, msg=f'{p1}: {k} {v1} != {v2}')
