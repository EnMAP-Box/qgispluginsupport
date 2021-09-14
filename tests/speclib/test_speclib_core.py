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
import time
import unittest
import xmlrunner
from qgis.gui import QgsMapCanvas
from qgis.core import QgsField, QgsFields, QgsProject, QgsGeometry, QgsRasterLayer
from qps.testing import TestObjects, TestCase
from qpstestdata import hymap
from qpstestdata import speclib as speclibpath

from qps.utils import *
from qps.speclib.core.spectralprofile import *
from qps.speclib.core.spectrallibrary import *
from qps.speclib.io.csvdata import *
from qps.speclib.io.asd import *
from qps import initResources
import numpy as np


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestCore, cls).setUpClass(*args, **kwds)
        initResources()

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        for file in vsiSpeclibs():
            gdal.Unlink(file)

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

    def test_SpectralProfileLoadingTask(self):

        speclib = TestObjects.createSpectralLibrary(n=10, n_bands=[-1, 64])
        self.assertIsInstance(speclib, QgsVectorLayer)
        self.assertTrue(speclib.featureCount() == 10)
        self.assertTrue(len(profile_field_list(speclib)) == 2)

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
        self._tsk = task
        w = QWidget()
        QTimer.singleShot(500, lambda w=w: w.close())
        self.showGui(w)

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
        xUnit = 'nm'
        yUnit = None

        sl = SpectralLibrary()
        self.assertTrue(sl.startEditing())
        sp = SpectralProfile()
        sp.setValues(x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)

        vd1 = sp.values()
        dump = encodeProfileValueDict(vd1)
        self.assertIsInstance(dump, QByteArray)

        vd2 = decodeProfileValueDict(dump)
        self.assertIsInstance(vd2, dict)
        self.assertEqual(vd1, vd2)
        sl.addProfiles([sp])
        self.assertTrue(sl.commitChanges())

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

    def test_SpectralProfile(self):

        # empty profile
        sp = SpectralProfile()
        d = sp.values()
        self.assertIsInstance(d, dict)
        for k in ['x', 'y', 'xUnit', 'yUnit']:
            self.assertTrue(k in d.keys())
            v = d[k]
            self.assertTrue(v == EMPTY_PROFILE_VALUES[k])
        self.assertEqual(sp.xValues(), [])
        self.assertEqual(sp.yValues(), [])

        y = [0.23, 0.4, 0.3, 0.8, 0.7]
        x = [300, 400, 600, 1200, 2500]
        with self.assertRaises(Exception):
            # we need y values
            sp.setValues(x=x)

        d = sp.values()
        self.assertIsInstance(d, dict)
        for k in ['x', 'y', 'yUnit', 'xUnit', 'bbl']:
            self.assertEqual(d[k], EMPTY_PROFILE_VALUES[k])

        sp.setValues(y=y)
        self.assertListEqual(sp.xValues(), list(range(len(y))))

        sp.setValues(x=x)
        self.assertListEqual(sp.xValues(), x)
        d = sp.values()
        self.assertListEqual(d['y'], y)
        self.assertListEqual(d['x'], x)

        sClone = sp.clone()
        self.assertIsInstance(sClone, SpectralProfile)
        self.assertEqual(sClone, sp)
        sClone.setId(-9999)
        self.assertEqual(sClone, sp)

        canvas = QgsMapCanvas()
        lyr1 = TestObjects.createRasterLayer(ns=1000, nl=1000)
        lyr2 = TestObjects.createRasterLayer(ns=900, nl=900)
        canvas.setLayers([lyr1, lyr2])
        canvas.setExtent(lyr1.extent())
        canvas.setDestinationCrs(lyr1.crs())
        pos = SpatialPoint(lyr2.crs(), *lyr2.extent().center())
        profiles = SpectralProfile.fromMapCanvas(canvas, pos)
        self.assertIsInstance(profiles, list)
        self.assertEqual(len(profiles), 2)
        for p in profiles:
            self.assertIsInstance(p, SpectralProfile)
            self.assertIsInstance(p.geometry(), QgsGeometry)
            self.assertTrue(p.hasGeometry())

        yVal = [0.23, 0.4, 0.3, 0.8, 0.7]
        xVal = [300, 400, 600, 1200, 2500]
        sp1 = SpectralProfile()
        sp1.setValues(x=xVal, y=yVal)

        self.assertEqual(xVal, sp1.xValues())
        self.assertEqual(yVal, sp1.yValues())

        sp1.setXUnit('nm')
        self.assertEqual(sp1.xUnit(), 'nm')

        self.assertEqual(sp1, sp1)

        for sp2 in [sp1.clone(), copy.copy(sp1), sp1.__copy__()]:
            self.assertIsInstance(sp2, SpectralProfile)
            self.assertEqual(sp1, sp2)

        dump = pickle.dumps(sp1)
        sp2 = pickle.loads(dump)
        self.assertIsInstance(sp2, SpectralProfile)
        self.assertEqual(sp1, sp2)
        self.assertEqual(sp1.values(), sp2.values())

        dump = pickle.dumps([sp1, sp2])
        loads = pickle.loads(dump)

        for i, p1 in enumerate([sp1, sp2]):
            p2 = loads[i]
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertEqual(p1.values(), p2.values())
            # self.assertEqual(p1.name(), p2.name())
            self.assertEqual(p1.id(), p2.id())

        sp2 = SpectralProfile()
        sp2.setValues(x=xVal, y=yVal, xUnit='um')
        self.assertNotEqual(sp1, sp2)
        sp2.setValues(xUnit='nm')
        self.assertEqual(sp1, sp2)
        sp2.setYUnit('reflectance')
        # self.assertNotEqual(sp1, sp2)

        self.SP = sp1

        dump = pickle.dumps(sp1)

        unpickled = pickle.loads(dump)
        self.assertIsInstance(unpickled, SpectralProfile)
        self.assertEqual(sp1, unpickled)
        self.assertEqual(sp1.values(), unpickled.values())
        self.assertEqual(sp1.geometry().asWkt(), unpickled.geometry().asWkt())
        dump = pickle.dumps([sp1, sp2])
        unpickled = pickle.loads(dump)
        self.assertIsInstance(unpickled, list)
        r1, r2 = unpickled
        self.assertEqual(sp1.values(), r1.values())
        self.assertEqual(sp2.values(), r2.values())
        self.assertEqual(sp2.geometry().asWkt(), r2.geometry().asWkt())

    def test_SpectralProfileBlock(self):

        profiles = TestObjects.spectralProfiles()
        coredata, core_wl, core_wlu, core_gt, core_wkt = TestObjects.coreData()

        setting = SpectralSetting(core_wl, core_wlu)
        block1 = SpectralProfileBlock(coredata, setting)

        self.assertIsInstance(block1, SpectralProfileBlock)

        kwds = block1.toVariantMap()
        self.assertIsInstance(kwds, dict)

        block2 = SpectralProfileBlock.fromVariantMap(kwds)
        self.assertIsInstance(block2, SpectralProfileBlock)
        self.assertEqual(block1, block2)

    def test_read_temporal_wavelength(self):

        p = r'D:\Repositories\qgispluginsupport\qpstestdata\2010-2020_001-365_HL_TSA_LNDLG_NBR_TSS.tif'
        if os.path.isfile(p):
            lyr = QgsRasterLayer(p)
            self.assertIsInstance(lyr, QgsRasterLayer)
            self.assertTrue(lyr.isValid())
            center = SpatialPoint.fromMapLayerCenter(lyr)
            p = SpectralProfile.fromRasterLayer(lyr, center)
            p.setName('Test Profile')
            self.assertIsInstance(p, SpectralProfile)

            speclib = SpectralLibrary()
            speclib.startEditing()
            speclib.addProfiles([p])
            speclib.commitChanges()

            from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
            w = SpectralLibraryWidget(speclib=speclib)
            self.showGui(w)

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
        self.assertTrue(sp == None)

    def test_speclib_mimedata(self):

        sp1 = SpectralProfile()
        # sp1.setName('Name A')
        sp1.setValues(y=[0, 4, 3, 2, 1], x=[450, 500, 750, 1000, 1500])

        sp2 = SpectralProfile()
        # sp2.setName('Name B')
        sp2.setValues(y=[3, 2, 1, 0, 1], x=[450, 500, 750, 1000, 1500])

        sl1 = SpectralLibrary()

        self.assertEqual(sl1.name(), 'SpectralLibrary')
        sl1.setName('MySpecLib')
        self.assertEqual(sl1.name(), 'MySpecLib')

        sl1.startEditing()
        sl1.addProfiles([sp1, sp2])
        sl1.commitChanges()

        # test link
        mimeData = sl1.mimeData(MIMEDATA_SPECLIB_LINK)

        slRetrieved = SpectralLibrary.readFromMimeData(mimeData)
        self.assertEqual(slRetrieved, sl1)

        writeOnly = []
        for format in [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_TEXT]:
            print('Test MimeData I/O "{}"'.format(format))
            mimeData = sl1.mimeData(format)
            self.assertIsInstance(mimeData, QMimeData)

            if format in writeOnly:
                continue

            slRetrieved = SpectralLibrary.readFromMimeData(mimeData)
            self.assertIsInstance(slRetrieved, SpectralLibrary,
                                  'Re-Import from MIMEDATA failed for MIME type "{}"'.format(format))

            n = len(slRetrieved)
            self.assertEqual(n, len(sl1))
            for p, pr in zip(sl1.profiles(), slRetrieved.profiles()):
                self.assertIsInstance(p, SpectralProfile)
                self.assertIsInstance(pr, SpectralProfile)
                self.assertEqual(p.fieldNames(), pr.fieldNames())
                if p.yValues() != pr.yValues():
                    s = ""
                self.assertEqual(p.yValues(), pr.yValues())

                self.assertEqual(p.xValues(), pr.xValues())
                self.assertEqual(p.xUnit(), pr.xUnit())
                # self.assertEqual(p.name(), pr.name())
                if p != pr:
                    s = ""
                self.assertEqual(p, pr)

            self.assertEqual(sl1, slRetrieved)

    def test_groupBySpectralProperties(self):

        sl1 = TestObjects.createSpectralLibrary()
        groups = sl1.groupBySpectralProperties(excludeEmptyProfiles=False)
        self.assertTrue(len(groups) > 0)
        for key, profiles in groups.items():
            self.assertIsInstance(key, SpectralSetting)
            xvalues = key.x()
            xunit = key.xUnit()
            yunit = key.yUnit()

            self.assertTrue(xvalues is None or isinstance(xvalues, tuple) and len(xvalues) > 0)
            self.assertTrue(xunit is None or isinstance(xunit, str) and len(xunit) > 0)
            self.assertTrue(yunit is None or isinstance(yunit, str) and len(yunit) > 0)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

            l = len(profiles[0].xValues())

            for p in profiles:
                self.assertEqual(l, len(p.xValues()))

    def test_SpectralLibraryValueFields(self):

        sl = SpectralLibrary(profile_fields=['profiles', 'derived1'])

        fields = sl.spectralProfileFields()
        self.assertIsInstance(fields, list)
        self.assertTrue(len(fields) == 2)
        for f in fields:
            self.assertIsInstance(f, QgsField)
            self.assertTrue(f.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY)
        self.assertFalse(sl.addSpectralProfileField('derived2'))
        sl.startEditing()
        self.assertTrue(sl.addSpectralProfileField('derived2'))
        self.assertTrue(sl.commitChanges())
        self.assertTrue(len(sl.spectralProfileFields()) == 3)

    def test_SpectralLibrary(self):

        self.assertListEqual(vsiSpeclibs(), [])

        sp1 = SpectralProfile()
        # sp1.setName('Name 1')
        sp1.setValues(y=[1, 1, 1, 1, 1], x=[450, 500, 750, 1000, 1500])

        sp2 = SpectralProfile()
        # sp2.setName('Name 2')
        sp2.setValues(y=[2, 2, 2, 2, 2], x=[450, 500, 750, 1000, 1500])

        SLIB = SpectralLibrary()

        self.assertEqual(SLIB.name(), 'SpectralLibrary')
        SLIB.setName('MySpecLib')
        self.assertEqual(SLIB.name(), 'MySpecLib')

        SLIB.startEditing()
        profiles = [sp1, sp2]
        addedFIDs = SLIB.addProfiles(profiles)
        self.assertTrue(len(addedFIDs) == len(profiles))
        for i, fid in enumerate(addedFIDs):
            f = SLIB.getFeature(fid)
            # self.assertEqual(f.attribute('name'), profiles[i].name())

        SLIB.rollBack()
        self.assertEqual(len(SLIB), 0)

        SLIB.startEditing()
        SLIB.addProfiles([sp1, sp2])
        SLIB.commitChanges()
        self.assertEqual(len(SLIB), 2)

        # test subsetting
        p = SLIB[0]
        self.assertIsInstance(p, SpectralProfile)
        self.assertIsInstance(p.values(), dict)

        if p.values() != sp1.values():
            s = ""

        self.assertEqual(p.values(), sp1.values(),
                         msg='Unequal values:\n\t{}\n\t{}'.format(str(p.values()), str(sp1.values())))
        self.assertEqual(SLIB[0].values(), sp1.values())

        # self.assertNotEqual(speclib[0], sp1) #because sl1 has an FID

        subset = SLIB[0:1]
        self.assertIsInstance(subset, list)
        self.assertEqual(len(subset), 1)

        self.assertEqual(set(SLIB.allFeatureIds()), set([1, 2]))
        slSubset = SLIB.speclibFromFeatureIDs(fids=2)
        self.assertEqual(set(SLIB.allFeatureIds()), set([1, 2]))
        self.assertIsInstance(slSubset, SpectralLibrary)

        self.assertEqual(len(slSubset), 1)
        self.assertEqual(slSubset[0].values(), SLIB[1].values())

        n = len(vsiSpeclibs())
        dump = pickle.dumps(SLIB)
        restoredSpeclib = pickle.loads(dump)
        self.assertIsInstance(restoredSpeclib, SpectralLibrary)
        self.assertEqual(len(vsiSpeclibs()), n + 1)
        self.assertEqual(len(SLIB), len(restoredSpeclib))

        for i in range(len(SLIB)):
            p1 = SLIB[i]
            r1 = restoredSpeclib[i]

            if p1.values() != r1.values():
                s = ""

            self.assertEqual(p1.values(), r1.values(), msg='dumped and restored values are not the same')

        restoredSpeclib.startEditing()
        restoredSpeclib.addProfiles([sp2])
        self.assertTrue(restoredSpeclib.commitChanges())
        self.assertNotEqual(SLIB, restoredSpeclib)
        self.assertEqual(restoredSpeclib[-1].values(), sp2.values())

        # read from image

        lyr1 = QgsRasterLayer(hymap)

        center1 = lyr1.extent().center()
        center2 = SpatialPoint.fromSpatialExtent(SpatialExtent.fromLayer(lyr1))

        SLIB = SpectralLibrary.readFromRasterPositions(hymap, center1)
        slSubset = SpectralLibrary.readFromRasterPositions(hymap, center2)
        restoredSpeclib = SpectralLibrary.readFromRasterPositions(hymap, [center1, center2])

        for sl in [SLIB, slSubset]:
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) == 1)
            self.assertIsInstance(sl[0], SpectralProfile)
            self.assertTrue(sl[0].hasGeometry())

        self.assertTrue(len(restoredSpeclib) == 2)

        n1 = len(SLIB)
        n2 = len(slSubset)

        SLIB.startEditing()
        SLIB.addProfiles(slSubset[:])
        self.assertTrue(len(SLIB) == n1 + n2)
        SLIB.addProfiles(slSubset[:])
        self.assertTrue(len(SLIB) == n1 + n2 + n2)
        self.assertTrue(SLIB.commitChanges())

        # save and restore
        path = self.createTestOutputDirectory() / 'speclib' / 'testsli.gpkg'
        os.makedirs(path.parent, exist_ok=True)
        SLIB.write(path)

        pathQml = path.parent / 'testsli.qml'
        self.assertTrue(pathQml.is_file())

        SLIB2 = SpectralLibrary(path)
        self.assertIsInstance(SLIB2, SpectralLibrary)
        SLIB2.loadNamedStyle(pathQml.as_posix())

        for p1, p2 in zip(SLIB, SLIB2):
            self.assertEqual(p1, p2)

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

    def test_mergeSpeclibs(self):
        sp1 = TestObjects.createSpectralLibrary()
        pd = QProgressDialog()
        sp2 = SpectralLibrary.readFrom(speclibpath, feedback=pd)

        self.assertIsInstance(sp1, SpectralLibrary)
        self.assertIsInstance(sp2, SpectralLibrary)

        n = len(sp1)
        with self.assertRaises(Exception):
            sp1.addSpeclib(sp2)
            s = ""
        self.assertTrue(len(sp1), n)

        sp1.startEditing()
        sp1.addSpeclib(sp2)
        self.assertTrue(len(sp1), n + len(sp2))

    def test_merge(self):

        sl1: SpectralLibrary = TestObjects.createSpectralLibrary(10)
        self.assertIsInstance(sl1, SpectralLibrary)

        profiles = []

        NAME2NAME = dict()
        color = QColor('green')
        for i in range(20):
            p = SpectralProfile()
            name = f'N{i + 1}'
            color = nextColor(color, mode='cat')
            NAME2NAME[name] = color.name()
            profiles.append(p)


        import random
        profiles = random.choices(profiles, k=len(profiles))

        sl1.startEditing()
        added_fids = sl1.addProfiles(profiles)

        for fid in added_fids:
            p = sl1.profile(fid)
            self.assertIsInstance(p, SpectralProfile)

        # assign styles
        for p in sl1:
            self.assertIsInstance(p, SpectralProfile)


    def test_writeAsRaster(self):

        speclib = SpectralLibrary()
        speclib.startEditing()
        speclib.addSpeclib(TestObjects.createSpectralLibrary(n=5, n_empty=2, n_bands=5, wlu='Nanometers'))
        speclib.addSpeclib(TestObjects.createSpectralLibrary(n=4, n_bands=[10, 25], wlu='Micrometers', n_empty=2))
        speclib.commitChanges()

        self.assertIsInstance(speclib, SpectralLibrary)

        groups = speclib.groupBySpectralProperties()

        pathOne = '/vsimem/tempraster.tif'
        images = speclib.writeRasterImages(pathOne)
        from qps.unitmodel import XUnitModel
        xUnitModel = XUnitModel()

        for image, item in zip(images, groups.items()):
            settings, profiles = item
            xunits = settings.x()
            xunit = settings.xUnit()
            yunit = settings.yUnit()
            ds: gdal.Dataset = gdal.Open(image.as_posix())
            self.assertIsInstance(ds, gdal.Dataset)
            wl, wlu = parseWavelength(ds)
            xunit = xUnitModel.findUnit(xunit)
            self.assertListEqual(list(xunits), wl.tolist())
            self.assertEqual(xunit, wlu)
            self.assertEqual(ds.RasterCount, len(xunits))

    def test_multiinstances(self):

        sl1 = SpectralLibrary(baseName='A')
        sl2 = SpectralLibrary(baseName='B')

        self.assertIsInstance(sl1, SpectralLibrary)
        self.assertIsInstance(sl2, SpectralLibrary)
        self.assertNotEqual(id(sl1), id(sl2))

    def test_mergeSpeclibSpeed(self):

        from qpstestdata import speclib


        sl1 = SpectralLibrary.readFrom(speclib)

        sl2 = SpectralLibrary()

        n = 3000
        p = sl1[0]
        profiles = []

        for i in range(n):
            profiles.append(p.clone())
        sl2.startEditing()
        sl2.addProfiles(profiles, addMissingFields=True)
        sl2.commitChanges()

        sl2.startEditing()
        sl2.addSpeclib(sl2)
        sl2.commitChanges()

        self.assertEqual(len(sl2), n * 2)
        s = ""


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
