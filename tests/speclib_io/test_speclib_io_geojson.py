# noinspection PyPep8Naming
import os
import unittest

import xmlrunner

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProcessingFeedback, QgsFeature, QgsVectorFileWriter, QgsField, QgsVectorLayer
from qps.qgsfunctions import registerQgsExpressionFunctions
from qps.speclib.core import is_profile_field, profile_field_names
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportDialog
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.io.geojson import GeoJsonSpectralLibraryIO, GeoJsonSpectralLibraryExportWidget, \
    GeoJsonFieldValueConverter
from qps.testing import TestObjects, TestCase


class TestSpeclibIOGeoJSON(TestCase):
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

        feedback = QgsProcessingFeedback()

        exportWidget = IO.createExportWidget()
        self.assertIsInstance(exportWidget, GeoJsonSpectralLibraryExportWidget)
        exportWidget.setSpeclib(sl)

        testdir = self.createTestOutputDirectory() / 'GeoJSON'
        os.makedirs(testdir, exist_ok=True)

        path = testdir / 'exported_profiles.geojson'
        features = sl.getFeatures()
        files = GeoJsonSpectralLibraryIO.exportProfiles(path, features, {}, feedback)
        self.assertEqual(len(files), 1)
        files = GeoJsonSpectralLibraryIO.exportProfiles(path, features, {}, feedback)
        self.assertEqual(len(files), 1)

        files = SpectralLibraryUtils.writeToSource(sl, path)
        self.assertEqual(len(files), 1)

        features2 = GeoJsonSpectralLibraryIO.importProfiles(files[0], {}, feedback)

        pfields = profile_field_names(sl)

        for f1, f2 in zip(sl.getFeatures(), features2):
            self.assertIsInstance(f1, QgsFeature)
            self.assertIsInstance(f2, QgsFeature)
            for pfield in pfields:
                d1 = decodeProfileValueDict(f1[pfield])
                d2 = decodeProfileValueDict(f2[pfield])
                self.assertEqual(d1, d2)

        w = GeoJsonSpectralLibraryIO.createImportWidget()
        w.setSource(path.as_posix())
        s = ""


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
