# noinspection PyPep8Naming
import os
import unittest

from osgeo import ogr

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsPoint, QgsProcessingFeedback, QgsProject, \
    QgsVectorFileWriter, QgsVectorLayer
from qps.qgsfunctions import registerQgsExpressionFunctions
from qps.speclib.core import is_profile_field, profile_field_names
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportDialog
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geojson import GeoJsonFieldValueConverter, GeoJsonSpectralLibraryExportWidget, \
    GeoJsonSpectralLibraryIO
from qps.testing import TestCaseBase, TestObjects, start_app

start_app()


class TestSpeclibIOGeoJSON(TestCaseBase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIOGeoJSON, cls).setUpClass(*args, **kwds)
        cls.registerIO(cls)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIOGeoJSON, cls).tearDownClass()

    def registerIO(self):
        ios = [GeoJsonSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_GeoJSON2008(self):
        crsUTM = QgsCoordinateReferenceSystem('EPSG:32632')
        crs4325 = QgsCoordinateReferenceSystem('EPSG:4326')
        sl1 = TestObjects.createSpectralLibrary(n_bands=4, crs=crsUTM)
        sl2 = TestObjects.createSpectralLibrary(n_bands=4, crs=crs4325)
        self.assertEqual(crsUTM, sl1.crs())
        self.assertEqual(crs4325, sl2.crs())

        p1: QgsPoint = sl1.getFeature(1).geometry().constGet()
        p2: QgsPoint = sl2.getFeature(2).geometry().constGet()
        self.assertTrue(10000 < p1.x() < 10000000)
        self.assertTrue(10000 < p1.y() < 10000000)

        self.assertTrue(-1800 < p2.x() < 180)
        self.assertTrue(-90 < p2.y() < 90)

        DIR = self.createTestOutputDirectory()
        path1 = DIR / 'test_rfc7946.geojson'
        path2 = DIR / 'test_GeoJSON2008.geojson'
        io = GeoJsonSpectralLibraryIO()

        drv: ogr.Driver = ogr.GetDriverByName('GeoJSON')
        md = drv.GetMetadata_Dict()
        filesRFCYes = io.exportProfiles(path1, sl1)
        filesRFCNo = io.exportProfiles(path2, sl1, exportSettings={'rfc7946': False})

        lyrYes = QgsVectorLayer(filesRFCYes[0])
        lyrNo = QgsVectorLayer(filesRFCNo[0])
        self.assertTrue(lyrYes.isValid())
        self.assertTrue(lyrNo.isValid())
        self.assertEqual(lyrYes.crs(), crs4325)
        self.assertEqual(lyrNo.crs(), crsUTM)

        path3 = DIR / 'test_GeoJson2008_b.geojson'
        lyrNo2 = QgsVectorLayer(io.writeToSource(sl1, path3, rfc7946=False)[0])
        self.assertTrue(lyrNo2.isValid())
        self.assertEqual(lyrNo2.crs(), crsUTM)

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

    def test_import(self):
        IO = GeoJsonSpectralLibraryIO()
        from qpstestdata import speclib_geojson

        profiles = IO.importProfiles(speclib_geojson)
        self.assertTrue(len(profiles) > 0)
        for p in profiles:
            self.assertTrue(len(profile_field_names(p)) > 0)

        lyr = QgsVectorLayer(speclib_geojson, 'GeoJSON')
        QgsProject.instance().addMapLayer(lyr)
        self.assertTrue(lyr.isValid())

        w = SpectralLibraryWidget(speclib=lyr)
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Blocking dialog')
    def test_import_merge(self):
        IO = GeoJsonSpectralLibraryIO()
        registerQgsExpressionFunctions()

        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        testdir = self.createTestOutputDirectory() / 'GeoJSON'
        os.makedirs(testdir, exist_ok=True)

        path = testdir / 'exported_profiles2.geojson'
        feedback = QgsProcessingFeedback()
        files = GeoJsonSpectralLibraryIO.exportProfiles(path, sl.getFeatures(), {}, feedback)
        self.assertEqual(len(files), 1)
        sl.startEditing()
        sl.deleteFeatures(sl.allFeatureIds())
        sl.commitChanges(False)
        SpectralLibraryImportDialog.importProfiles(sl, files[0])

        for f in sl.getFeatures():
            v = f.attribute('profiles0')
            d = decodeProfileValueDict(v)
            self.assertTrue(len(d.get('x', [])) > 0)
            print(d)

        s = ""

    def test_write_profiles(self):
        IO = GeoJsonSpectralLibraryIO()

        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()

        self.assertTrue(sl.featureCount() > 0)
        self.assertTrue(sl.startEditing())
        for f in sl.getFeatures():
            f: QgsFeature
            f.setAttribute('name', f'Name {f.id()}')
            sl.updateFeature(f)
        self.assertTrue(sl.commitChanges())

        ref_profiles = list(sl.getFeatures())

        feedback = QgsProcessingFeedback()

        exportWidget = IO.createExportWidget()
        self.assertIsInstance(exportWidget, GeoJsonSpectralLibraryExportWidget)
        exportWidget.setSpeclib(sl)

        testdir = self.createTestOutputDirectory() / 'GeoJSON'
        os.makedirs(testdir, exist_ok=True)

        path = testdir / 'exported_profiles.geojson'

        files = GeoJsonSpectralLibraryIO.exportProfiles(path, ref_profiles, {}, feedback)
        self.assertEqual(len(files), 1)
        files = GeoJsonSpectralLibraryIO.exportProfiles(path, ref_profiles, {}, feedback)
        self.assertEqual(len(files), 1)

        files = SpectralLibraryUtils.writeToSource(ref_profiles, path, settings=dict(crs=sl.crs()))
        self.assertEqual(len(files), 1)

        features2 = GeoJsonSpectralLibraryIO.importProfiles(files[0], {}, feedback)

        pfields = profile_field_names(sl)

        F1 = {f.attribute('name'): f for f in ref_profiles}
        F2 = {f.attribute('name'): f for f in features2}

        self.assertEqual(F1.keys(), F2.keys())

        # compare
        for name in F1.keys():
            f1 = F1[name]
            f2 = F2[name]
            self.assertIsInstance(f1, QgsFeature)
            self.assertIsInstance(f2, QgsFeature)
            for pfield in pfields:
                d1 = decodeProfileValueDict(f1[pfield])
                d2 = decodeProfileValueDict(f2[pfield])
                self.assertEqual(d1.keys(), d2.keys())
                for k in d1.keys():
                    v1, v2 = d1[k], d2[k]
                    if v1 != v2:
                        s = ""
                    self.assertEqual(v1, v2, msg=f'features differ in key {k}')

        w = GeoJsonSpectralLibraryIO.createImportWidget()
        w.setSource(path.as_posix())
        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
