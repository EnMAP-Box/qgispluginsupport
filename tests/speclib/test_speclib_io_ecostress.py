from qgis.core import QgsProject
from qgis.core import QgsVectorLayer
from qps.speclib.core import is_spectral_feature, is_spectral_library
from qps.speclib.io.ecostress import ECOSTRESSSpectralProfileReader
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import TestCase
from qps.utils import file_search
from qpstestdata import DIR_ECOSTRESS


class ECOSTRESSSpectralProfileReaderTests(TestCase):

    def ecostressTestFiles(self):

        return file_search(DIR_ECOSTRESS, '*.spectrum.txt')

    def test_read_ecostress_file(self):

        for file in self.ecostressTestFiles():

            self.assertTrue(ECOSTRESSSpectralProfileReader.canReadFile(file))

            reader = ECOSTRESSSpectralProfileReader(file)
            profiles = reader.asFeatures()
            self.assertEqual(1, len(profiles))
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

    def test_import_algorithm_ecostress(self):

        OUTPUT_DIR = self.createTestOutputDirectory()

        alg = ImportSpectralProfiles()
        alg.initAlgorithm({})

        path_output = OUTPUT_DIR / 'ecostressprofiles.geojson'
        context, feedback = self.createProcessingContextFeedback()
        p = QgsProject()
        context.setProject(p)
        par = {alg.P_INPUT: DIR_ECOSTRESS.as_posix(),
               alg.P_INPUT_TYPE: 'ECOSTRESS',
               alg.P_OUTPUT: path_output.as_posix()
               }

        self.assertTrue(alg.prepareAlgorithm(par, context, feedback))
        results = alg.processAlgorithm(par, context, feedback)
        results = alg.postProcessAlgorithm(context, feedback)

        layer = results[ImportSpectralProfiles.P_OUTPUT]
        if isinstance(layer, str):
            layer = QgsVectorLayer(layer)
            layer.loadDefaultStyle()

        self.assertTrue(is_spectral_library(layer))
        self.assertTrue(layer.featureCount() > 0)
        s = ""
