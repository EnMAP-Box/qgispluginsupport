import pathlib
import unittest

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsProcessingFeedback, \
    QgsVectorLayerExporter
from qps.speclib.core import is_spectral_feature
from qps.speclib.core.spectrallibraryio import SpectralLibraryImportDialog, \
    SpectralLibraryIO
from qps.speclib.io.spectralevolution import SEDFile, SEDSpectralLibraryIO
from qps.testing import start_app, TestCaseBase, TestObjects
from qps.utils import file_search

start_app()


class TestSpeclibIO_SED(TestCaseBase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_SED, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_SED, cls).tearDownClass()

    def registerIO(self):

        ios = [SEDSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_read_sed_files(self):
        import qpstestdata
        SED_DIR = pathlib.Path(qpstestdata.__file__).parent / 'spectralevolution'
        files = list(file_search(SED_DIR, '*.sed', recursive=True))

        self.assertTrue(len(files) > 0)

        features = []
        for file in files:
            asd = SEDFile(file)

            feature: QgsFeature = asd.asFeature()
            self.assertIsInstance(feature, QgsFeature)
            is_spectral_feature(feature)

            g = feature.geometry()
            self.assertIsInstance(g, QgsGeometry)
            self.assertTrue(g.isSimple())
            self.assertTrue(g.isGeosValid())

            features.append(feature)

        io = SEDSpectralLibraryIO()
        conf = dict()
        feedback = QgsProcessingFeedback()
        paths = '"' + '" "'.join(files) + '"'
        features2 = io.importProfiles(paths, conf, feedback)
        self.assertEqual(len(features), len(features2))

        refFeature: QgsFeature = features2[0]
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        path = self.createTestOutputDirectory() / 'sed_profiles.gpkg'
        options = dict()
        exporter = QgsVectorLayerExporter(path.as_posix(),
                                          'ogr',
                                          refFeature.fields(),
                                          refFeature.geometry().wkbType(),
                                          crs=crs,
                                          overwrite=True,
                                          options=options)
        if exporter.errorCode() != Qgis.VectorExportResult.Success:
            raise Exception(f'Error when creating {path}: {exporter.errorMessage()}')

        for f in features2:
            if not exporter.addFeature(f):
                if exporter.errorCode() != Qgis.VectorExportResult.Success:
                    raise Exception(f'Error when creating feature: {exporter.errorMessage()}')

        exporter.flushBuffer()
        s = ""

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Skipped QDialog test in CI')
    def test_dialog(self):
        self.registerIO()
        sl = TestObjects.createSpectralLibrary()
        import qpstestdata.asd
        root = pathlib.Path(qpstestdata.__file__).parent / 'spectralevolution'

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())


if __name__ == '__main__':
    unittest.main(buffer=False)
