# noinspection PyPep8Naming
import pathlib
import re
import unittest
from typing import List

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsFeature, QgsProcessingFeedback, QgsVectorLayer, \
    QgsVectorLayerExporter
from qps.speclib.core import is_spectral_feature
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportDialog
from qps.speclib.io.asd import ASDBinaryFile, ASDSpectralLibraryIO, ASDSpectralLibraryImportWidget
from qps.testing import TestCase, TestObjects, start_app
from qps.utils import file_search

start_app()


class TestSpeclibIO_ASD(TestCase):

    def registerIO(self):

        ios = [ASDSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_read_with_gps(self):
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd' / 'gps'
        files = list(file_search(ASD_DIR, '*.asd', recursive=True))

        features = []
        for file in files:
            print(file)
            asd = ASDBinaryFile(file)
            features.extend(asd.asFeatures())

        io = ASDSpectralLibraryIO()
        conf = dict()
        feedback = QgsProcessingFeedback()
        paths = '"' + '" "'.join(files) + '"'
        features2 = io.importProfiles(paths, conf, feedback)
        self.assertEqual(len(features), len(features2))

        refFeature: QgsFeature = features2[0]
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        path = self.createTestOutputDirectory() / 'asd_profiles.gpkg'
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

    def test_read_asdFile(self):

        for file in self.asdBinFiles():
            print(f'read {file}')
            asd = ASDBinaryFile(file)
            self.assertIsInstance(asd, ASDBinaryFile)
            for profile in asd.asFeatures():
                self.assertTrue(is_spectral_feature(profile))

        for file in self.asdCSVFiles():

            profiles = ASDSpectralLibraryIO.readCSVFile(file)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

    def asdBinFiles(self) -> List[str]:
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd'
        return list(file_search(ASD_DIR, re.compile(r'\w+\d+\.(asd)$'), recursive=True))

    def asdCSVFiles(self):
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd'
        return list(file_search(ASD_DIR, re.compile(r'\w+\d+\.(csv|txt)$'), recursive=True))

    def test_read_profiles(self):
        self.registerIO()

        IO = ASDSpectralLibraryIO()

        importWidget = IO.createImportWidget()
        self.assertIsInstance(importWidget, ASDSpectralLibraryImportWidget)
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        importWidget.setSpeclib(sl)

        files = self.asdBinFiles() + self.asdCSVFiles()

        paths = '"' + '" "'.join(files) + '"'
        feedback = QgsProcessingFeedback()
        profiles = IO.importProfiles(paths, {}, feedback)
        self.assertTrue(len(profiles) == len(files))
        for p in profiles:
            self.assertTrue(is_spectral_feature(p))

        self.showGui(importWidget)

    @unittest.skipIf(TestCase.runsInCI(), 'Skipped QDialog test in CI')
    def test_dialog(self):
        self.registerIO()
        sl = TestObjects.createSpectralLibrary()
        import qpstestdata.asd
        root = pathlib.Path(qpstestdata.__file__).parent / 'asd'

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())


if __name__ == '__main__':
    unittest.main(buffer=False)
