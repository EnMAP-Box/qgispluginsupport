# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming
import datetime
import json
import math
import pickle
import re
import unittest
from typing import List

import numpy as np
from osgeo import ogr

from qgis.PyQt.QtCore import NULL, QByteArray, QJsonDocument, QVariant
from qgis.core import edit, QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsFields, QgsRasterLayer, \
    QgsVectorLayer, QgsWkbTypes
from qps import initAll
from qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QBYTEARRAY, QMETATYPE_QSTRING
from qps.speclib import EDITOR_WIDGET_REGISTRY_KEY
from qps.speclib.core import can_store_spectral_profiles, create_profile_field, is_profile_field, is_spectral_library, \
    profile_field_list, profile_fields
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryrasterdataprovider import featuresToArrays
from qps.speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, isProfileValueDict, \
    nanToNone, prepareProfileValueDict, ProfileEncoding, SpectralSetting, validateProfileValueDict
from qps.testing import start_app, TestCase, TestObjects
from qps.unitmodel import BAND_NUMBER
from qps.utils import createQgsField, FeatureReferenceIterator, findTypeFromString, qgsFields2str, SpatialExtent, \
    SpatialPoint, str2QgsFields, toType
from qpstestdata import enmap, envi_sli

start_app()
initAll()


# registerSpectralProfileEditorWidget()
# registerEditorWidgets()
#
# registerMapLayerConfigWidgetFactories()

class SpeclibCoreTests(TestCase):

    # @unittest.skip('')
    def test_fields(self):

        f1 = createQgsField('foo', 9999)

        self.assertEqual(f1.name(), 'foo')
        self.assertEqual(f1.type(), QMETATYPE_INT)
        self.assertEqual(f1.typeName(), 'int')

        f2 = createQgsField('bar', 9999.)
        self.assertEqual(f2.type(), QMETATYPE_DOUBLE)
        self.assertEqual(f2.typeName(), 'double')

        f3 = createQgsField('text', 'Hello World')
        self.assertEqual(f3.type(), QMETATYPE_QSTRING)
        self.assertEqual(f3.typeName(), 'varchar')

        fields = QgsFields()
        fields.append(f1)
        fields.append(f2)
        fields.append(f3)

        serialized = qgsFields2str(fields)
        self.assertIsInstance(serialized, str)

        fields2 = str2QgsFields(serialized)
        self.assertIsInstance(fields2, QgsFields)
        self.assertEqual(fields.count(), fields2.count())
        for i in range(fields.count()):
            f1 = fields.at(i)
            f2 = fields2.at(i)
            self.assertEqual(f1.type(), f2.type())
            self.assertEqual(f1.name(), f2.name())
            self.assertEqual(f1.typeName(), f2.typeName())

    @staticmethod
    def valid_profile_dicts() -> List[dict]:
        examples = [
            dict(y=[1, 2, 3], bbl=[1, 2, 3]),
            dict(y=[1, 2, 3]),
            dict(y=[1, 2, 3], x=[2, 3, 4]),
            dict(y=[1, 2, 3], x=['2005-02-25', '2005-03-25', '2005-04-25']),
            dict(y=[1, 2, 3], x=[2, 3, 4], xUnit=BAND_NUMBER),
            dict(y=[1, 2, 3], x=[2, 3, 4], xUnit='foobar'),
            dict(y=[1, 2, 3], bbl=[1, 1, 0]),

        ]
        return examples

    @staticmethod
    def invalid_profile_dicts() -> List[dict]:
        examples = [
            None,
            NULL,
            QVariant(None),
            dict(),
            dict(foobar=[1, 2, 3]),
            dict(x=[1, 2, 3]),
            dict(y=[1, 2, 3], x=['2005-02-25', '2005-03-25', '2005-34-25']),
            dict(y='dsd'),
            dict(y=[1, 2, 3], x=[2, 3]),
            dict(y=[1, 2, 3], xUnit=BAND_NUMBER),
            dict(y=[1, 2, 3], bbl=[1, 0])
        ]
        return examples

    # @unittest.skip('')
    def test_validate_profile_dict(self):

        for p in self.valid_profile_dicts():
            success, msg, d = validateProfileValueDict(p)
            self.assertTrue(success)
            self.assertEqual(msg, '')
            self.assertTrue(len(d) > 0)

        for p in [None, dict(), NULL, QVariant(None)]:
            self.assertFalse(validateProfileValueDict(p)[0])
            self.assertTrue(validateProfileValueDict(p, allowEmpty=True)[0])

        for p in self.invalid_profile_dicts():
            success, msg, d = validateProfileValueDict(p)
            self.assertFalse(success)
            self.assertIsInstance(msg, str)
            self.assertTrue(len(msg) > 0)
            self.assertEqual(d, dict())

    def test_SerializationJSON(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 3, 4, np.nan, 6]
        bbl = [1, 0, 1, 1, 0]
        xUnit = 'μm'
        yUnit = 'reflectance ä$32{}'  # special characters to test UTF-8 compatibility

        vector_keys = ['x', 'y', 'bbl']

        d = prepareProfileValueDict(x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)
        self.assertIsInstance(d, dict)

        r = encodeProfileValueDict(d, encoding='dict')
        self.assertIsInstance(r, dict)
        self.assertListEqual(x, r['x'])
        self.assertListEqual(y, r['y'])
        self.assertListEqual(bbl, r['bbl'])

        rJSON = encodeProfileValueDict(d, encoding='JSON')
        self.assertIsInstance(rJSON, dict)
        self.assertTrue(None not in rJSON['y'])

        r = decodeProfileValueDict(rJSON)
        self.assertIsInstance(r, dict)

        self.assertTrue(np.array_equal(x, r['x'], equal_nan=True))
        self.assertTrue(np.array_equal(y, r['y'], equal_nan=True))
        self.assertTrue(np.array_equal(bbl, r['bbl'], equal_nan=True))

    # @unittest.skip('')
    def test_Serialization(self):

        x = [1, 2, 3, 4, 5]
        y = [2, 3, None, np.nan, np.inf]
        bbl = [1, 0, 1, 1, 0]
        xUnit = 'μm'
        yUnit = 'reflectance ä$32{}'  # special characters to test UTF-8 compatibility

        def compareSpeclibDictionaries(d1, d2):
            self.assertIsInstance(d1, dict)
            self.assertIsInstance(d2, dict)
            self.assertTrue('y' in d1)
            for k in ['x', 'y', 'bbl', 'xUnit', 'yUnit']:
                if k in d1:
                    self.assertTrue(k in d2)
                    v1, v2 = d1[k], d2[k]

                    if isinstance(v1, list):
                        v1 = [nanToNone(v) for v in v1]
                        v2 = [nanToNone(v) for v in v2]
                        self.assertListEqual(v1, v2)
                    else:
                        self.assertEqual(v1, v2)

        d = prepareProfileValueDict(x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)
        self.assertIsInstance(d, dict)

        sl = SpectralLibraryUtils.createSpectralLibrary()

        self.assertTrue(sl.startEditing())
        pField = profile_fields(sl).at(0)
        feature = QgsFeature(sl.fields())
        SpectralLibraryUtils.setProfileValues(feature, field=pField, x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)

        vd1 = decodeProfileValueDict(feature.attribute(pField.name()))
        dump = encodeProfileValueDict(vd1, QgsField('test', QMETATYPE_QBYTEARRAY))
        self.assertIsInstance(dump, QByteArray)

        vd2 = decodeProfileValueDict(dump)
        compareSpeclibDictionaries(vd1, vd2)

        sl.addFeature(feature)
        self.assertTrue(sl.commitChanges())

        # serialize to text formats
        field = QgsField('text', QMETATYPE_QSTRING)
        dump = encodeProfileValueDict(vd1, field)
        self.assertIsInstance(dump, str)

        vd2 = decodeProfileValueDict(dump)
        self.assertIsInstance(vd2, dict)
        compareSpeclibDictionaries(vd1, vd2)

        # decode valid inputs
        valid_inputs = {  # 'str(d)': str(d),  #  missed double quotes
            "bytes(json.dumps(d), 'utf-8')": bytes(re.sub('(NaN|Infinity)', 'null', json.dumps(d)), 'utf-8'),

            'dictionary': d,
            'json dump': json.dumps(d, default=nanToNone),
            'pickle dump': pickle.dumps(d),
            'QByteArray from pickle dump': QByteArray(pickle.dumps(d)),
            'QJsonDocument': QJsonDocument.fromVariant(d),
            'QJsonDocument->toJson': QJsonDocument.fromVariant(d).toJson(),
            'QJsonDocument->toBinaryData': QJsonDocument.fromVariant(d).toBinaryData(),

        }
        for info, v in valid_inputs.items():
            d2 = decodeProfileValueDict(v)
            self.assertIsInstance(d2, dict)
            self.assertTrue(isProfileValueDict(d2))

        # decode invalid inputs
        invalid_inputs = ['{invalid',
                          bytes('{x:}', 'utf-8')
                          ]
        for v in invalid_inputs:
            vd2 = decodeProfileValueDict(v)
            self.assertEqual(vd2, {})

        # test encoding

        for e in ['ByTeS', ProfileEncoding.Bytes,
                  QgsField('dummy', type=QMETATYPE_QBYTEARRAY)]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, QByteArray)

        for e in [None, 'TeXt',
                  ProfileEncoding.Text,
                  QgsField('dummy', type=QMETATYPE_QSTRING),
                  ]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, str)

        for e in ['dIcT', 'mAp', ProfileEncoding.Dict, ProfileEncoding.Map]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, dict)

        for e in ['jSoN', ProfileEncoding.Json, QgsField('dummy', type=8)]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, dict)

        for d in self.valid_profile_dicts():
            dump = encodeProfileValueDict(d, ProfileEncoding.Text)
            decode = decodeProfileValueDict(dump)
            self.assertEqual(d, decode)

        # ensure that 0 stays 0
        d = {'y': [0, 8, 15]}
        d2 = decodeProfileValueDict(encodeProfileValueDict(d, ProfileEncoding.Text))
        self.assertListEqual(d['y'], d2['y'])

        # convert None to NaN
        d = {'y': [None, 8, 15]}
        d2 = decodeProfileValueDict(encodeProfileValueDict(d, ProfileEncoding.Text))
        self.assertTrue(math.isnan(d2['y'][0]))
        self.assertListEqual(d['y'][1:], d2['y'][1:])

    # @unittest.skip('')
    def test_profile_fields(self):

        path = '/vsimem/test.gpkg'
        options = ['OVERWRITE=YES',
                   'DESCRIPTION=TestLayer']

        drv: ogr.Driver = ogr.GetDriverByName('GPKG')
        ds: ogr.DataSource = drv.CreateDataSource(path)
        self.assertIsInstance(ds, ogr.DataSource)

        lyr: ogr.Layer = ds.CreateLayer('TestLayer', geom_type=ogr.wkbPoint, options=options)
        self.assertIsInstance(lyr, ogr.Layer)

        def createField(name: str, ogrType: str, ogrSubType: str = None, width: int = None) -> ogr.FieldDefn:
            field = ogr.FieldDefn(name, field_type=ogrType)
            if ogrSubType:
                field.SetSubType(ogrSubType)
            if width:
                field.SetWidth(width)
            return field

        lyr.CreateField(createField('json', ogr.OFTString, ogrSubType=ogr.OFSTJSON))
        lyr.CreateField(createField('text', ogr.OFTString))
        lyr.CreateField(createField('blob', ogr.OFTBinary))

        # not supported
        lyr.CreateField(createField('text10', ogr.OFTString, width=10))
        lyr.CreateField(createField('int', ogr.OFTInteger))
        lyr.CreateField(createField('float', ogr.OFTReal))
        lyr.CreateField(createField('date', ogr.OFTDate))
        lyr.CreateField(createField('datetime', ogr.OFTDateTime))
        ds.FlushCache()
        del ds
        lyr = QgsVectorLayer(path)
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        fields: QgsFields = lyr.fields()
        for name in ['json', 'text', 'blob']:
            field = fields.field(name)
            self.assertIsInstance(field, QgsField)
            self.assertTrue(can_store_spectral_profiles(field))

        for name in ['text10', 'int', 'float', 'date', 'datetime']:
            field = fields.field(name)
            self.assertIsInstance(field, QgsField)
            self.assertFalse(can_store_spectral_profiles(field))
        lyr.startEditing()
        lyr.addFeature(QgsFeature(fields))
        lyr.commitChanges(False)
        fid = lyr.allFeatureIds()[0]

        profiles = [
            dict(y=[1, 2, 3]),
            dict(y=[1, 2.0, 3], x=[350, 400, 523.4]),
            dict(y=[1, 2, 3], x=[350, 400, 523.4], xUnit='nm', bbl=[0, 1, 1])
        ]

        for iProfile, profile1 in enumerate(profiles):
            for iField, field in enumerate(fields):
                if can_store_spectral_profiles(field):
                    idx = fields.lookupField(field.name())
                    value1 = encodeProfileValueDict(profile1, encoding=field)
                    self.assertTrue(value1 is not None)
                    self.assertTrue(lyr.changeAttributeValue(fid, idx, value1))
                    lyr.commitChanges(False)
                    f2 = lyr.getFeature(fid)
                    value2 = f2[field.name()]

                    if lyr.fields().field(field.name()).typeName() == 'JSON':
                        self.assertEqual(value2, profile1)
                    else:
                        self.assertEqual(value1, value2)
                        profile2 = decodeProfileValueDict(value2)
                        self.assertEqual(profile1, profile2)
                s = ""
        s = ""

    # @unittest.skip('')
    def test_FeatureReferenceIterator(self):
        sl = TestObjects.createSpectralLibrary(10)
        all_profiles = list(sl.getFeatures())

        def check_profiles(profiles):
            profiles = list(profiles)
            self.assertEqual(len(profiles), len(all_profiles))
            for i, p in enumerate(profiles):
                self.assertIsInstance(p, QgsFeature)
                self.assertEqual(p.attributes(), all_profiles[i].attributes())

        fpi = FeatureReferenceIterator([])
        self.assertTrue(fpi.referenceFeature() is None)
        self.assertEqual(len(list(fpi)), 0)

        fpi = FeatureReferenceIterator(sl.getFeatures())
        self.assertIsInstance(fpi.referenceFeature(), QgsFeature)
        check_profiles(fpi)

        fpi = FeatureReferenceIterator(sl)
        self.assertIsInstance(fpi.referenceFeature(), QgsFeature)
        check_profiles(fpi)

        fpi = FeatureReferenceIterator(all_profiles)
        self.assertIsInstance(fpi.referenceFeature(), QgsFeature)
        check_profiles(fpi)

    # @unittest.skip('')
    def test_SpectralProfileReading(self):

        lyr = TestObjects.createRasterLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)

        center = SpatialPoint.fromMapLayerCenter(lyr)
        extent = SpatialExtent.fromLayer(lyr)
        x, y = extent.upperLeft()

        outOfImage = SpatialPoint(extent.crs(), extent.xMinimum() - 10, extent.yMaximum() + 10)

        sp = SpectralLibraryUtils.readProfileDict(lyr, center)
        self.assertTrue(isProfileValueDict(sp))

        sp = SpectralLibraryUtils.readProfileDict(lyr, outOfImage)
        self.assertTrue(sp is None)

    # @unittest.SkipTest
    def test_spectralProfileSpeedUnpacking(self):

        n_profiles = 2000
        n_bands = 300
        pinfo = f'{n_profiles} profiles[{n_bands} bands]'
        print(f'Test loading/writing times for {pinfo}')

        def now():
            return datetime.datetime.now()

        t0 = now()
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary(n_profiles, n_bands=[n_bands])
        print(f'Initialized in-memory speclib with {pinfo}: {now() - t0}')

        n_profiles = sl.featureCount()
        DIR = self.createTestOutputDirectory()
        path_local = DIR / 'speedtest.gpkg'
        # files = sl.write(path_local)
        pfield = profile_field_list(sl)[0]

        SpectralLibraryUtils.writeToSource(sl, path_local)
        sl = QgsVectorLayer(path_local.as_posix())

        self.assertTrue(sl.isValid())
        self.assertEqual(sl.featureCount(), n_profiles)

        iPField = sl.fields().indexOf(pfield.name())
        DATA = dict()

        # test decoding
        t0 = now()
        for f in sl.getFeatures():
            ba = f.attribute(pfield.name())
        print(f'{pinfo}: read only: {now() - t0}')
        t0 = now()
        for f in sl.getFeatures():
            ba = f.attribute(pfield.name())
            DATA[f.id()] = decodeProfileValueDict(ba)
        print(f'{pinfo}: read & decode: {now() - t0}')
        self.assertEqual(n_profiles, sl.featureCount())

        t0 = now()
        with edit(sl):
            sl.beginEditCommand('read & write profiles')
            for f in sl.getFeatures():
                dump = encodeProfileValueDict(DATA[f.id()], pfield)
                sl.changeAttributeValue(f.id(), iPField, dump)
            sl.endEditCommand()
        dt = now() - t0
        print(f'Read & write {sl.featureCount()} profiles from/to GPKG: {dt}')

    # @unittest.skip('')
    def test_groupBySpectralProperties(self):

        sl1 = TestObjects.createSpectralLibrary(n_empty=1)
        groups = SpectralLibraryUtils.groupBySpectralProperties(sl1)
        self.assertTrue(len(groups) > 0)
        for key, profiles in groups.items():
            key: SpectralSetting
            self.assertIsInstance(key, SpectralSetting)

            xvalues = key.wavelengths()
            xunit = key.xUnit()
            # yunit = key.yUnit()

            self.assertTrue(xvalues is None or isinstance(xvalues, list) and len(xvalues) > 0)
            self.assertTrue(xunit is None or isinstance(xunit, str) and len(xunit) > 0)
            # self.assertTrue(yunit is None or isinstance(yunit, str) and len(yunit) > 0)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

            d = decodeProfileValueDict(profiles[0].attribute(key.fieldName()))
            if len(d) == 0:
                continue
            x = d['x']

            for p in profiles:
                d2 = decodeProfileValueDict(profiles[0].attribute(key.fieldName()))
                self.assertEqual(d2['x'], x)

    # @unittest.skip('')
    def test_SpectralProfileFields(self):

        sl = SpectralLibraryUtils.createSpectralLibrary(profile_fields=['profiles', 'derived1'])

        fields = profile_field_list(sl)
        self.assertIsInstance(fields, list)
        self.assertTrue(len(fields) == 2)
        for f in fields:
            self.assertIsInstance(f, QgsField)
            self.assertTrue(f.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY)
        self.assertFalse(SpectralLibraryUtils.addAttribute(sl, create_profile_field('derived2')))
        sl.startEditing()
        self.assertTrue(SpectralLibraryUtils.addAttribute(sl, create_profile_field('derived2')))
        self.assertTrue(sl.commitChanges())
        self.assertEqual(profile_fields(sl).count(), 3)

    # @unittest.skip('')
    def test_example_profile_fields(self):
        fieldNP = QgsField('no profile', type=QMETATYPE_QBYTEARRAY)
        self.assertFalse(is_profile_field(fieldNP))

        fieldP = create_profile_field('profiles')
        self.assertTrue(is_profile_field(fieldP))

        self.assertTrue(is_profile_field(QgsField(fieldP)))

        lyr = QgsVectorLayer('point?crs=epsg:4326', 'Test', 'memory')
        self.assertTrue(lyr.startEditing())
        lyr.addAttribute(fieldP)

        self.assertTrue(lyr.commitChanges())

        i = lyr.fields().lookupField('profiles')

        print(f'Is SpectralProfile field? {is_profile_field(lyr.fields().at(i))}')
        lyr.setEditorWidgetSetup(i, fieldP.editorWidgetSetup())
        print(f'Is SpectralProfile field? {is_profile_field(lyr.fields().at(i))}')

    # @unittest.skip('')
    def test_SpectralLibraryUtils(self):

        vl = SpectralLibraryUtils.readFromSource(envi_sli)
        self.assertIsInstance(vl, QgsVectorLayer)
        self.assertTrue(is_spectral_library(vl))

        vl2 = SpectralLibraryUtils.readFromVectorLayer(vl)
        self.assertTrue(vl2, QgsVectorLayer)
        self.assertTrue(is_spectral_library(vl2))

        rl = QgsRasterLayer(enmap.as_posix())
        rl = TestObjects.createRasterLayer()
        self.assertTrue(rl.crs().isValid())
        # QgsProject.instance().addMapLayer(rl)
        pt = SpatialPoint.fromMapLayerCenter(rl)

        d = SpectralLibraryUtils.readProfileDict(rl, pt)
        self.assertTrue(isProfileValueDict(d))

        # read and set attribute dictionaries
        f1 = vl.getFeature(1)
        self.assertIsInstance(f1, QgsFeature)
        d = f1.attributeMap()
        self.assertIsInstance(d['profiles'], str)
        d2 = SpectralLibraryUtils.attributeMap(f1)
        self.assertIsInstance(d2['profiles'], dict)
        self.assertIsInstance(d2['profiles']['y'], list)

        d3 = SpectralLibraryUtils.attributeMap(f1, numpy_arrays=True)
        self.assertIsInstance(d3['profiles'], dict)
        self.assertIsInstance(d3['profiles']['y'], np.ndarray)

        for dSrc in [d, d2, d3]:
            fDst = QgsFeature(vl.fields())
            SpectralLibraryUtils.setAttributeMap(fDst, dSrc)
            self.assertEqual(f1['profiles'], fDst['profiles'])
        s = ""

    def test_save_gpkg_crs(self):
        crs = QgsCoordinateReferenceSystem('EPSG:32632')
        lyr = TestObjects.createVectorLayer(QgsWkbTypes.Point, crs=crs)
        self.assertEqual(lyr.crs(), crs)
        TESTDIR = self.createTestOutputDirectory()
        filenameCopy = TESTDIR / 'copy.gpkg'
        SpectralLibraryUtils.writeToSource(lyr, filenameCopy.as_posix())
        layerCopy = QgsVectorLayer(filenameCopy.as_posix())
        self.assertEqual(layerCopy.crs(), crs)

    # @unittest.skip('')
    def test_featuresToArrays(self):
        # lyrWMS = QgsRasterLayer(WMS_GMAPS, 'test', 'wms')

        # lyr = TestObjects.createRasterProcessingModel()
        n_bands = [[256, 2500],
                   [123, 42]]
        n_features = 10

        SLIB = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)

        pfields = profile_fields(SLIB)

        ARRAYS = featuresToArrays(SLIB, spectral_profile_fields=pfields)

        self.assertIsInstance(ARRAYS, dict)
        self.assertTrue(len(ARRAYS) == 2)
        for i in range(2):
            settings = list(ARRAYS.keys())[i]
            fids, arrays = list(ARRAYS.values())[i]
            self.assertEqual(len(fids), n_features)
            for j, setting in enumerate(settings):
                self.assertIsInstance(setting, SpectralSetting)
                array = arrays[j]
                self.assertIsInstance(array, np.ndarray)
                self.assertEqual(array.shape[0], setting.bandCount())
                self.assertEqual(array.shape[1], len(fids))

    # @unittest.skip('')
    def test_others(self):

        self.assertEqual(23, toType(int, '23'))
        self.assertEqual([23, 42], toType(int, ['23', '42']))
        self.assertEqual(23., toType(float, '23'))
        self.assertEqual([23., 42.], toType(float, ['23', '42']))

        self.assertTrue(findTypeFromString('23') is int)
        self.assertTrue(findTypeFromString('23.3') is float)
        self.assertTrue(findTypeFromString('xyz23.3') is str)
        self.assertTrue(findTypeFromString('') is str)

    # @unittest.skip('')
    def test_writeAsRaster(self):

        speclib = SpectralLibraryUtils.createSpectralLibrary()
        speclib.startEditing()
        speclib.addFeatures(
            TestObjects.createSpectralLibrary(n=5, n_empty=2, n_bands=5, wlu='Nanometers').getFeatures())
        speclib.addFeatures(
            TestObjects.createSpectralLibrary(n=4, n_empty=2, n_bands=[10, 25], wlu='Micrometers',
                                              ).getFeatures())
        speclib.commitChanges()

        self.assertIsInstance(speclib, QgsVectorLayer)


if __name__ == '__main__':
    unittest.main(buffer=False)
