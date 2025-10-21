# noinspection PyPep8Naming
import unittest

from osgeo import ogr, gdal

from qgis.core import QgsFeature, QgsVectorLayer
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryWriter
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestSpeclibIO_GPKG(TestCase):

    def test_writer(self):

        sl: QgsVectorLayer = TestObjects.createSpectralLibrary(n_bands=[[20, 10], [7, 13]])

        testdir = self.createTestOutputDirectory()
        path = testdir / 'exported_library.gpkg'

        writer = GeoPackageSpectralLibraryWriter(path, crs=sl.crs())
        files = writer.writeFeatures(path, list(sl.getFeatures()))

        self.assertTrue(len(files) == 1)
        for f in files:
            ds: gdal.Dataset = ogr.Open(f.as_posix())
            self.assertEqual(ds.GetDriver().ShortName, 'GPKG')
            lyr = QgsVectorLayer(f.as_posix())
            self.assertTrue(lyr.isValid())
            self.assertEqual(lyr.featureCount(), sl.featureCount())

            for p1, p2 in zip(sl.getFeatures(), lyr.getFeatures()):
                d1, d2 = p1.attributeMap(), p2.attributeMap()

                for n in sl.fields().names():
                    self.assertEqual(d1[n], d2[n])
                s = ""

    def test_write_profiles(self):
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        sl.startEditing()
        for f in sl.getFeatures():
            f: QgsFeature
            f.setAttribute('name', f'Name {f.id()}')
            sl.updateFeature(f)
        self.assertTrue(sl.commitChanges())

        testdir = self.createTestOutputDirectory()
        path = testdir / 'exported_profiles.gpkg'

        files = SpectralLibraryUtils.writeToSource(sl, path)
        self.assertTrue(len(files) == 1)

        # overwrite
        files = SpectralLibraryUtils.writeToSource(sl, path)
        self.assertTrue(len(files) == 1)

        self.assertIsInstance(files, list)
        for file in files:
            file = file.as_posix()
            ds = ogr.Open(file)
            self.assertIsInstance(ds, gdal.Dataset)

            lyr = QgsVectorLayer(file)
            self.assertIsInstance(lyr, QgsVectorLayer)
            self.assertTrue(lyr.isValid())
            self.assertTrue(lyr.featureCount() > 0)


if __name__ == '__main__':
    unittest.main(buffer=False)
