# noinspection PyPep8Naming
import pathlib
import re
import unittest
from typing import List

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsFeature, QgsVectorLayerExporter
from qps.speclib.core import is_spectral_feature
from qps.speclib.io.asd import ASDBinaryFile, ASDCSVFile
from qps.testing import TestCase, start_app
from qps.utils import file_search

start_app()


class TestSpeclibIO_ASD(TestCase):

    def test_read_with_gps(self):
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd' / 'gps'
        files = list(file_search(ASD_DIR, '*.asd', recursive=True))

        features = []
        for file in files:
            print(file)
            asd = ASDBinaryFile(file)
            features.extend(asd.asFeatures())

        self.assertTrue(len(features) > 0)

        refFeature: QgsFeature = features[0]
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

        for f in features:
            if not exporter.addFeature(f):
                if exporter.errorCode() != Qgis.VectorExportResult.Success:
                    raise Exception(f'Error when creating feature: {exporter.errorMessage()}')

        exporter.flushBuffer()
        s = ""

    def test_read_asd_files(self):

        for file in self.asdBinFiles():
            print(f'read {file}')
            asd = ASDBinaryFile(file)
            profiles = asd.asFeatures()
            self.assertEqual(1, len(profiles))
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

        for file in self.asdCSVFiles():

            asd = ASDCSVFile(file)
            profiles = asd.asFeatures()
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
        return list(file_search(ASD_DIR / 'txt', re.compile(r'\.(csv|txt)$'), recursive=True))


if __name__ == '__main__':
    unittest.main(buffer=False)
