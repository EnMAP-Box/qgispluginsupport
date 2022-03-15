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
import pickle
import unittest

import numpy as np
import xmlrunner
from osgeo import ogr
from qgis.PyQt.QtCore import QJsonDocument
from qgis.PyQt.QtCore import QMimeData, QByteArray, QVariant
from qgis.core import QgsProject, QgsField, QgsVectorLayer, QgsRasterLayer, QgsFeature, \
    QgsVectorLayerCache, QgsCoordinateReferenceSystem, QgsApplication, QgsTaskManager, QgsFields
from qgis.gui import QgsGui

from qps import initResources
from qps.speclib import EDITOR_WIDGET_REGISTRY_KEY
from qps.speclib.core import is_spectral_library, profile_field_list, profile_fields, supports_field, \
    create_profile_field, is_profile_field
from qps.speclib.core.spectrallibrary import MIMEDATA_SPECLIB_LINK, SpectralLibraryUtils
from qps.speclib.core.spectrallibraryrasterdataprovider import featuresToArrays
from qps.speclib.core.spectralprofile import decodeProfileValueDict, SpectralProfile, SpectralSetting, \
    SpectralProfileBlock, encodeProfileValueDict, SpectralProfileLoadingTask, prepareProfileValueDict, ProfileEncoding
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.speclib.io.csvdata import CSVSpectralLibraryIO
from qps.testing import TestObjects, TestCase
from qps.utils import toType, findTypeFromString, SpatialPoint, SpatialExtent, FeatureReferenceIterator, \
    createQgsField, qgsFields2str, str2QgsFields


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestCore, cls).setUpClass(*args, **kwds)
        initResources()
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        registerSpectralProfileEditorWidget()
        from qps import registerEditorWidgets
        registerEditorWidgets()

        from qps import registerMapLayerConfigWidgetFactories
        registerMapLayerConfigWidgetFactories()

    def test_fields(self):

        f1 = createQgsField('foo', 9999)

        self.assertEqual(f1.name(), 'foo')
        self.assertEqual(f1.type(), QVariant.Int)
        self.assertEqual(f1.typeName(), 'int')

        f2 = createQgsField('bar', 9999.)
        self.assertEqual(f2.type(), QVariant.Double)
        self.assertEqual(f2.typeName(), 'double')

        f3 = createQgsField('text', 'Hello World')
        self.assertEqual(f3.type(), QVariant.String)
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

    def test_SpectralProfile_Math(self):
        sp = SpectralProfile()
        xvals = [1, 2, 3, 4, 5]
        yvals = [2, 3, 4, 5, 6]
        sp.setValues(x=xvals, y=yvals)

        self.assertListEqual(sp.yValues(), yvals)

        sp2 = sp + 2
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v + 2 for v in yvals])

        sp2 = sp - 2
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v - 2 for v in yvals])

        sp2 = sp / 2
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v / 2 for v in yvals])

        sp2 = sp * 2
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v * 2 for v in yvals])

        sp2 = sp + sp
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v + v for v in yvals])

        sp2 = sp - sp
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v - v for v in yvals])

        sp2 = sp / sp
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v / v for v in yvals])

        sp2 = sp * sp
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertListEqual(sp2.yValues(), [v * v for v in yvals])

    @unittest.skipIf(TestCase.runsInCI(), 'processes finish error')
    def test_SpectralProfileLoadingTask(self):

        speclib = TestObjects.createSpectralLibrary(n=10, n_bands=[-1, 64])
        self.assertIsInstance(speclib, QgsVectorLayer)
        self.assertTrue(speclib.featureCount() == 20)
        self.assertEqual(len(profile_field_list(speclib)), 1)

        RESULTS = dict()

        def onProfilesLoaded(loaded_profiles):
            print(loaded_profiles)
            RESULTS.update(loaded_profiles)

        def onFinished(result, task):
            print('Finished')
            self.assertIsInstance(task, SpectralProfileLoadingTask)
            self.assertTrue(result)
            self.assertEqual(len(task.RESULTS), speclib.featureCount())
            RESULTS.update(task.RESULTS)
            self.assertEqual(len(RESULTS), speclib.featureCount())

        task = SpectralProfileLoadingTask(speclib, callback=onFinished)
        task.finished(task.run())

        tm: QgsTaskManager = QgsApplication.instance().taskManager()
        task = SpectralProfileLoadingTask(speclib, callback=onFinished)
        # task.sigProfilesLoaded.connect(onProfilesLoaded)
        taskID = tm.addTask(task)

        while tm.countActiveTasks() > 0:
            QgsApplication.processEvents()
            pass

    def test_SpectralProfile_BadBandList(self):

        sp = SpectralProfile()
        xvals = [1, 2, 3, 4, 5]
        yvals = [2, 3, 4, 5, 6]
        sp.setValues(x=xvals, y=yvals)
        self.assertEqual(len(xvals), sp.nb())
        self.assertIsInstance(sp.bbl(), list)
        self.assertListEqual(sp.bbl(), np.ones(len(xvals)).tolist())

        bbl = [1, 0, 1, 1, 1]
        sp.setValues(bbl=bbl)
        self.assertIsInstance(sp.bbl(), list)
        self.assertListEqual(sp.bbl(), bbl)

    def test_Serialization(self):

        x = [1, 2, 3, 4, 5]
        y = [2, 3, 4, 5, 6]
        bbl = [1, 0, 1, 1, 0]
        xUnit = 'μm'
        yUnit = 'reflectnce ä$32{}'  # special characters to test UTF-8 compatibility

        d = prepareProfileValueDict(x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)
        sl = SpectralLibraryUtils.createSpectralLibrary()

        self.assertTrue(sl.startEditing())
        pField = profile_fields(sl).at(0)
        feature = QgsFeature(sl.fields())
        SpectralLibraryUtils.setProfileValues(feature, field=pField, x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)

        vd1 = decodeProfileValueDict(feature.attribute(pField.name()))
        dump = encodeProfileValueDict(vd1, QgsField('test', QVariant.ByteArray))
        self.assertIsInstance(dump, QByteArray)

        vd2 = decodeProfileValueDict(dump)
        self.assertIsInstance(vd2, dict)
        self.assertEqual(vd1, vd2)
        sl.addFeature(feature)
        self.assertTrue(sl.commitChanges())

        # serialize to text formats
        field = QgsField('text', QVariant.String)
        dump = encodeProfileValueDict(vd1, field)
        self.assertIsInstance(dump, str)

        vd2 = decodeProfileValueDict(dump)
        self.assertIsInstance(vd2, dict)
        self.assertEqual(vd1, vd2)

        # decode valid inputs
        valid_inputs = {  # 'str(d)': str(d),  #  missed double quotes
            'dictionary': d,
            'json dump': json.dumps(d),
            'pickle dump': pickle.dumps(d),
            'QByteArray from pickle dump': QByteArray(pickle.dumps(d)),
            'QJsonDocument': QJsonDocument.fromVariant(d),
            'QJsonDocument->toJson': QJsonDocument.fromVariant(d).toJson(),
            'QJsonDocument->toBinaryData': QJsonDocument.fromVariant(d).toBinaryData(),
            "bytes(json.dumps(d), 'utf-8')": bytes(json.dumps(d), 'utf-8'),
        }
        for info, v in valid_inputs.items():
            d2 = decodeProfileValueDict(v)
            self.assertIsInstance(d, dict)
            self.assertEqual(d2, d, msg=f'Failed to decode {info}. Got: {d2}')

        # decode invalid inputs
        invalid_inputs = ['{invalid',
                          bytes('{x:}', 'utf-8')
                          ]
        for v in invalid_inputs:
            vd2 = decodeProfileValueDict(invalid_inputs)
            self.assertIsInstance(vd2, dict)
            self.assertTrue(len(vd2) == 0)

        # test encoding

        for e in ['ByTeS', ProfileEncoding.Bytes,
                  QgsField('dummy', type=QVariant.ByteArray)]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, QByteArray)

        for e in [None, 'TeXt', 'JsOn',
                  ProfileEncoding.Text,
                  ProfileEncoding.Json,
                  QgsField('dummy', type=QVariant.String),
                  QgsField('dummy', type=8)
                  ]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, str)

        for e in ['dIcT', 'mAp', ProfileEncoding.Dict, ProfileEncoding.Map]:
            dump = encodeProfileValueDict(d, e)
            self.assertIsInstance(dump, dict)

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
            self.assertTrue(supports_field(field))

        for name in ['text10', 'int', 'float', 'date', 'datetime']:
            field = fields.field(name)
            self.assertIsInstance(field, QgsField)
            self.assertFalse(supports_field(field))
        lyr.startEditing()
        lyr.addFeature(QgsFeature(fields))
        lyr.commitChanges(False)
        fid = lyr.allFeatureIds()[0]

        profiles = [
            dict(y=[1, 2, 3]),
            dict(y=[1, 2.0, 3], x=[350, 400, 523.4]),
            dict(y=[1, 2, 3], x=[350, 400, 523.4], xUnit='nm', bbl=[0, 1, 1])
        ]

        for profile1 in profiles:
            for field in fields:
                if supports_field(field):
                    idx = fields.lookupField(field.name())
                    value1 = encodeProfileValueDict(profile1, encoding=field)
                    self.assertTrue(value1 is not None)
                    self.assertTrue(lyr.changeAttributeValue(fid, idx, value1))
                    lyr.commitChanges(False)
                    value2 = lyr.getFeature(fid)[field.name()]

                    if lyr.fields().field(field.name()).typeName() == 'JSON':
                        self.assertEqual(value2, profile1)
                    else:
                        self.assertEqual(value1, value2)
                        profile2 = decodeProfileValueDict(value2)
                        self.assertEqual(profile1, profile2)
                s = ""
        s = ""

    def test_SpectralProfileMath(self):

        sp = SpectralProfile()
        x = [1, 2, 3, 4, 5]
        y = [1, 1, 2, 2, 3]
        sp.setValues(x, y)

        for n in [2, 2.2, int(2), float(2.2)]:
            sp1 = sum([sp, sp])
            self.assertListEqual(sp1.yValues(), [v + v for v in y])
            sp2 = sp + n
            self.assertListEqual(sp2.yValues(), [v + n for v in y])
            sp3 = n + sp
            self.assertListEqual(sp3.yValues(), sp2.yValues())

            sp2 = sp - n
            self.assertListEqual(sp2.yValues(), [v - n for v in y])
            sp3 = n - sp
            self.assertListEqual(sp3.yValues(), [n - v for v in y])

            sp1 = sp * n
            self.assertListEqual(sp1.yValues(), [v * n for v in y])
            sp2 = n * sp
            self.assertListEqual(sp2.yValues(), sp1.yValues())
            sp3 = sp * sp
            self.assertListEqual(sp3.yValues(), [v * v for v in y])

            sp1 = sp / n
            self.assertListEqual(sp1.yValues(), [v / n for v in y])
            sp2 = n / sp
            self.assertListEqual(sp2.yValues(), [n / v for v in y])
            sp3 = sp / sp
            self.assertListEqual(sp3.yValues(), [v / v for v in y])

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

    def test_SpectralProfileBlock(self):

        coredata, core_wl, core_wlu, core_gt, core_wkt = TestObjects.coreData()

        setting = SpectralSetting(core_wl, core_wlu)
        block1 = SpectralProfileBlock(coredata, setting)

        self.assertIsInstance(block1, SpectralProfileBlock)
        self.assertFalse(block1.hasGeoPositions())

        kwds = block1.toVariantMap()
        self.assertIsInstance(kwds, dict)

        block2 = SpectralProfileBlock.fromVariantMap(kwds)
        self.assertIsInstance(block2, SpectralProfileBlock)
        self.assertEqual(block1, block2)

        newCRS = QgsCoordinateReferenceSystem('EPSG:32632')
        profiles = TestObjects.spectralProfiles()
        for block3 in SpectralProfileBlock.fromSpectralProfiles(profiles):
            self.assertIsInstance(block3, SpectralProfileBlock)
            self.assertTrue(block3.hasGeoPositions())
            setting = block3.spectralSetting()
            for i, p in enumerate(block3.profiles()):
                self.assertIsInstance(p, QgsFeature)
                d = decodeProfileValueDict(p.attribute(setting.fieldName()))
                self.assertTrue(len(d) > 0)
            block3.toCrs(newCRS)
            self.assertTrue(block3.crs() == newCRS)

    def test_SpectralProfileReading(self):

        lyr = TestObjects.createRasterLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)

        center = SpatialPoint.fromMapLayerCenter(lyr)
        extent = SpatialExtent.fromLayer(lyr)
        x, y = extent.upperLeft()

        outOfImage = SpatialPoint(extent.crs(), extent.xMinimum() - 10, extent.yMaximum() + 10)

        sp = SpectralProfile.fromRasterLayer(lyr, center)
        self.assertIsInstance(sp, SpectralProfile)
        self.assertIsInstance(sp.xValues(), list)
        self.assertIsInstance(sp.yValues(), list)
        self.assertEqual(len(sp.xValues()), lyr.bandCount())
        self.assertEqual(len(sp.yValues()), lyr.bandCount())

        sp = SpectralProfile.fromRasterLayer(lyr, outOfImage)
        self.assertTrue(sp is None)

    @unittest.SkipTest
    def test_spectralProfileSpeedUpacking(self):

        n_profiles = 10000
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
        sl = QgsVectorLayer(path_local.as_posix())
        self.assertIsInstance(sl, QgsVectorLayer)
        self.assertEqual(sl.featureCount(), n_profiles)
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

        for f in sl.getFeatures():
            ba = encodeProfileValueDict(DATA[f.id()], pfield)
            f.setAttribute(pfield.name(), ba)

        print(f'{pinfo}: encode & write: {now() - t0}')

        n_reads = 10
        t0 = now()
        for i in range(n_reads):

            for j, f in enumerate(sl.getFeatures()):
                ba = f.attribute(pfield.name())
                DATA[f.id()] = decodeProfileValueDict(ba)
            assert j == n_profiles - 1
        print(f'{pinfo}: read & decode {n_reads}x without feature cache: {now() - t0}')

        cacheSizes = [256, 512, 1024, 2048, 4096]
        for cacheSize in cacheSizes:
            cache = QgsVectorLayerCache(sl, cacheSize)
            t0 = now()
            for i in range(n_reads):
                for j, f in enumerate(cache.getFeatures()):
                    ba = f.attribute(pfield.name())
                    DATA[f.id()] = decodeProfileValueDict(ba)
                assert j == n_profiles - 1
            print(f'{pinfo}: read & decode {n_reads}x with feature cache ({cacheSize}): {now() - t0}')

    def test_speclib_mimedata(self):

        sp1 = SpectralProfile()
        # sp1.setName('Name A')
        sp1.setValues(y=[0, 4, 3, 2, 1], x=[450, 500, 750, 1000, 1500])

        sp2 = SpectralProfile()
        # sp2.setName('Name B')
        sp2.setValues(y=[3, 2, 1, 0, 1], x=[450, 500, 750, 1000, 1500])

        sl1 = SpectralLibraryUtils.createSpectralLibrary()

        self.assertEqual(sl1.name(), 'SpectralLibrary')
        sl1.setName('MySpecLib')
        self.assertEqual(sl1.name(), 'MySpecLib')

        sl1.startEditing()
        sl1.addFeatures([sp1, sp2])
        sl1.commitChanges()

        # test link
        mimeData = SpectralLibraryUtils.mimeData(sl1, MIMEDATA_SPECLIB_LINK)

        slRetrieved = SpectralLibraryUtils.readFromMimeData(mimeData)
        self.assertEqual(slRetrieved, sl1)

        writeOnly = []
        formats = [MIMEDATA_SPECLIB_LINK,
                   # MIMEDATA_SPECLIB,
                   # MIMEDATA_TEXT
                   ]
        for format in formats:
            print('Test MimeData I/O "{}"'.format(format))
            mimeData = SpectralLibraryUtils.mimeData(sl1, format)
            self.assertIsInstance(mimeData, QMimeData)

            if format in writeOnly:
                continue

            slRetrieved = SpectralLibraryUtils.readFromMimeData(mimeData)
            self.assertIsInstance(slRetrieved, QgsVectorLayer,
                                  'Re-Import from MIMEDATA failed for MIME type "{}"'.format(format))

            n = len(slRetrieved)
            self.assertEqual(n, len(sl1))
            for p, pr in zip(sl1.getFeatures(), slRetrieved.getFeatures()):
                self.assertIsInstance(p, QgsFeature)
                self.assertIsInstance(pr, QgsFeature)
                self.assertEqual(p.fields().names(), pr.fields().names())
                self.assertEqual(p.attributeMap(), pr.attributeMap())

    def test_groupBySpectralProperties(self):

        sl1 = TestObjects.createSpectralLibrary(n_empty=1)
        groups = SpectralLibraryUtils.groupBySpectralProperties(sl1, excludeEmptyProfiles=False)
        self.assertTrue(len(groups) > 0)
        for key, profiles in groups.items():
            self.assertIsInstance(key, SpectralSetting)

            xvalues = key.x()
            xunit = key.xUnit()
            yunit = key.yUnit()

            self.assertTrue(xvalues is None or isinstance(xvalues, list) and len(xvalues) > 0)
            self.assertTrue(xunit is None or isinstance(xunit, str) and len(xunit) > 0)
            self.assertTrue(yunit is None or isinstance(yunit, str) and len(yunit) > 0)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

            d = decodeProfileValueDict(profiles[0].attribute(key.fieldName()))
            if len(d) == 0:
                continue
            x = d['x']

            for p in profiles:
                d2 = decodeProfileValueDict(profiles[0].attribute(key.fieldName()))
                self.assertEqual(d2['x'], x)

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

    def test_example_profile_fields(self):
        fieldNP = QgsField('no profile', type=QVariant.ByteArray)
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

    def test_SpectralLibraryUtils(self):

        from qpstestdata import speclib

        vl = SpectralLibraryUtils.readFromSource(speclib)
        self.assertIsInstance(vl, QgsVectorLayer)
        self.assertTrue(is_spectral_library(vl))

        vl2 = SpectralLibraryUtils.readFromVectorLayer(vl)
        self.assertTrue(vl2, QgsVectorLayer)
        self.assertTrue(is_spectral_library(vl2))

    def test_featuresToArrays(self):
        # lyrWMS = QgsRasterLayer(WMS_GMAPS, 'test', 'wms')

        # lyr = TestObjects.createRasterProcessingModel()
        n_bands = [[256, 2500],
                   [123, 42]]
        n_features = 500

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
                self.assertEqual(array.shape[0], setting.n_bands())
                self.assertEqual(array.shape[1], len(fids))

    def test_others(self):

        self.assertEqual(23, toType(int, '23'))
        self.assertEqual([23, 42], toType(int, ['23', '42']))
        self.assertEqual(23., toType(float, '23'))
        self.assertEqual([23., 42.], toType(float, ['23', '42']))

        self.assertTrue(findTypeFromString('23') is int)
        self.assertTrue(findTypeFromString('23.3') is float)
        self.assertTrue(findTypeFromString('xyz23.3') is str)
        self.assertTrue(findTypeFromString('') is str)

        regex = CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN

        # REGEX to identify band value column names

        for text in ['b1', 'b1_']:
            match = regex.match(text)
            self.assertEqual(match.group('band'), '1')
            self.assertEqual(match.group('xvalue'), None)
            self.assertEqual(match.group('xunit'), None)

        match = regex.match('b1 23.34 nm')
        self.assertEqual(match.group('band'), '1')
        self.assertEqual(match.group('xvalue'), '23.34')
        self.assertEqual(match.group('xunit'), 'nm')

    def test_writeAsRaster(self):

        speclib = SpectralLibraryUtils.createSpectralLibrary()
        speclib.startEditing()
        speclib.addFeatures(
            TestObjects.createSpectralLibrary(n=5, n_empty=2, n_bands=5, wlu='Nanometers').getFeatures())
        speclib.addFeatures(
            TestObjects.createSpectralLibrary(n=4, n_bands=[10, 25], wlu='Micrometers', n_empty=2).getFeatures())
        speclib.commitChanges()

        self.assertIsInstance(speclib, QgsVectorLayer)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
