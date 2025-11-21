# noinspection PyPep8Naming
import unittest

from osgeo import ogr

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsCoordinateReferenceSystem, QgsField, QgsPoint, QgsProject, \
    QgsVectorFileWriter, QgsVectorLayer
from qps.speclib.core import is_profile_field, profile_field_names
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geojson import GeoJsonFieldValueConverter, GeoJSONSpectralLibraryReader, \
    GeoJSONSpectralLibraryWriter
from qps.testing import start_app, TestCase, TestObjects

start_app()


class TestSpeclibIOGeoJSON(TestCase):

    def test_write(self):
        crsUTM = QgsCoordinateReferenceSystem('EPSG:32632')
        crs4326 = QgsCoordinateReferenceSystem('EPSG:4326')
        sl1 = TestObjects.createSpectralLibrary(n_bands=4, crs=crsUTM)
        sl2 = TestObjects.createSpectralLibrary(n_bands=4, crs=crs4326)
        self.assertEqual(crsUTM, sl1.crs())
        self.assertEqual(crs4326, sl2.crs())

        p1: QgsPoint = sl1.getFeature(1).geometry().constGet()
        p2: QgsPoint = sl2.getFeature(2).geometry().constGet()
        self.assertTrue(10000 < p1.x() < 10000000)
        self.assertTrue(10000 < p1.y() < 10000000)

        self.assertTrue(-1800 < p2.x() < 180)
        self.assertTrue(-90 < p2.y() < 90)

        DIR = self.createTestOutputDirectory()
        path0 = DIR / 'test_rfc7946-a.geojson'

        writer = GeoJSONSpectralLibraryWriter(crs=sl1.crs(), rfc7946=True)
        writer.writeFeatures(path0, sl1.getFeatures())

        path1 = DIR / 'test_rfc7946.geojson'
        path2 = DIR / 'test_GeoJSON2008.geojson'

        drv: ogr.Driver = ogr.GetDriverByName('GeoJSON')
        md = drv.GetMetadata_Dict()

        filesRFCYes = SpectralLibraryUtils.writeToSource(sl1, path1, rfc7946=True, crs=sl1.crs())
        filesRFCNo = SpectralLibraryUtils.writeToSource(sl1, path2, rfc7946=False, crs=sl1.crs())
        n = len(sl1)
        lyrYes = QgsVectorLayer(filesRFCYes[0].as_posix())
        lyrNo = QgsVectorLayer(filesRFCNo[0].as_posix())
        for lyr in [lyrYes, lyrNo]:
            self.assertTrue(lyr.isValid())
            self.assertEqual(n, lyr.featureCount())
        self.assertEqual(lyrYes.crs(), crs4326)
        self.assertEqual(lyrNo.crs(), crsUTM)

    def test_GeoJsonFieldValueConverter(self):
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        converter = GeoJsonFieldValueConverter(sl.fields())

        self.assertIsInstance(converter, QgsVectorFileWriter.FieldValueConverter)
        cloned = converter.clone()
        self.assertIsInstance(cloned, QgsVectorFileWriter.FieldValueConverter)

        for field in sl.fields():
            field2 = converter.fieldDefinition(field)
            self.assertIsInstance(field2, QgsField)
            self.assertTrue(field2.type() not in [QVariant.ByteArray, 8])
            fieldc = cloned.fieldDefinition(field)
            self.assertEqual(field2, fieldc)

        for profile in sl.getFeatures():
            for field in profile.fields():
                idx = profile.fieldNameIndex(field.name())
                value1 = profile.attribute(field.name())
                value2 = converter.convert(idx, value1)
                print(type(value2), value2)
                value3 = cloned.convert(idx, value1)
                self.assertEqual(value2, value3)
                if not is_profile_field(field):
                    self.assertEqual(value1, value2)

    def test_read(self):

        from qpstestdata import speclib_geojson

        self.assertTrue(GeoJSONSpectralLibraryReader.canReadFile(speclib_geojson))

        reader = GeoJSONSpectralLibraryReader(speclib_geojson)
        profiles = reader.asFeatures()
        self.assertTrue(len(profiles) > 0)
        for p in profiles:
            self.assertTrue(len(profile_field_names(p)) > 0)

        lyr = QgsVectorLayer(speclib_geojson.as_posix(), 'GeoJSON')
        QgsProject.instance().addMapLayer(lyr)
        self.assertTrue(lyr.isValid())

        w = SpectralLibraryWidget(speclib=lyr)
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
