from pathlib import Path

from qgis.core import QgsProject
from qgis.core import QgsVectorLayer
from qps.speclib.core import is_spectral_feature, is_spectral_library
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.io.ecosis import EcoSISSpectralLibraryReader
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import start_app, TestCase
from qps.utils import file_search
from qpstestdata import DIR_ECOSIS

# noinspection PyPep8Naming

start_app()


class TestSpeclibIO_EcoSIS(TestCase):

    def test_reading_speed(self):
        path = DIR_ECOSIS / 'fresh-leaf-spectra-to-estimate-leaf-traits-for-california-ecosystems.csv'

        if not path.is_file():
            return

        reader = EcoSISSpectralLibraryReader(path)
        features = reader.asFeatures()

        s = ""

    def test_EcoSIS_Reader(self):
        ecosysFiles = list(file_search(DIR_ECOSIS, '*.csv', recursive=True))

        for file in ecosysFiles:

            with open(file, 'r') as f:
                data = f.read()
                n_lines = len(data.strip().split('\n'))

            reader = EcoSISSpectralLibraryReader(file)
            features = reader.asFeatures()
            assert len(features) == n_lines - 1
            for f in features:
                assert is_spectral_feature(f)
            s = ""

    def test_read_EcoSIS_processing_alg(self):

        ecosysFiles = file_search(DIR_ECOSIS, '*.csv', recursive=True)

        OUTPUT_DIR = self.createTestOutputDirectory()

        for file in ecosysFiles:
            alg = ImportSpectralProfiles()
            alg.initAlgorithm({})

            path_output = OUTPUT_DIR / f'{Path(file).stem}.gpkg'
            context, feedback = self.createProcessingContextFeedback()
            p = QgsProject()
            context.setProject(p)
            par = {alg.P_INPUT: file,
                   alg.P_INPUT_TYPE: 'EcoSIS',
                   alg.P_OUTPUT: path_output.as_posix()
                   }

            self.assertTrue(alg.prepareAlgorithm(par, context, feedback))
            results = alg.processAlgorithm(par, context, feedback)
            results = alg.postProcessAlgorithm(context, feedback)
            lyr = results.get(ImportSpectralProfiles.P_OUTPUT)
            assert isinstance(lyr, QgsVectorLayer)
            for f in lyr.getFeatures():
                dump = f.attribute('reflectance')
                data = decodeProfileValueDict(dump)
                for k in ['x', 'y', 'xUnit']:
                    assert k in data

                for a in f.attributes():
                    self.assertTrue(a is not None)
                s = ""

    def test_read_EcoSIS(self):

        ecosysFiles = file_search(DIR_ECOSIS, '*.csv', recursive=True)
        context, feedback = self.createProcessingContextFeedback()

        for path in ecosysFiles:
            print('Read {}...'.format(path))

            # profiles = EcoSISSpectralLibraryIO.importProfiles(path, feedback=feedback)
            self.assertTrue(EcoSISSpectralLibraryReader.canReadFile(path))
            profiles = EcoSISSpectralLibraryReader(path).asFeatures()

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

            print('Read {} (generic IO)...'.format(path))

            context, feedback = self.createProcessingContextFeedback()

            sl = SpectralLibraryUtils.readFromSource(path)
            self.assertTrue(is_spectral_library(sl))
            self.assertTrue(sl.featureCount() > 0)
