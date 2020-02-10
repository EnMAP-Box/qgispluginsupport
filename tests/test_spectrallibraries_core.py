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
import unittest, shutil, pathlib
from qgis.core import *
from qgis.gui import *
from qps.testing import TestObjects, TestCase


from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath


import qps
import qps.speclib

from qps.speclib.csvdata import *
from qps.speclib.envi import *
from qps.speclib.asd import *
from qps.speclib.plotting import *


os.environ['CI'] = 'True'

TEST_DIR = pathlib.Path(__file__).parent / 'temp'


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        os.makedirs(TEST_DIR, exist_ok=True)
        super(TestCore, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestCore, cls).tearDownClass()
        if os.path.isdir(TEST_DIR):
            shutil.rmtree(TEST_DIR)


    def setUp(self):
        print('RUN TEST {}'.format(self.id()))
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        for s in SpectralLibrary.instances():
            del s
        SpectralLibrary.__refs__.clear()

        for file in vsiSpeclibs():
            gdal.Unlink(file)

    def tearDown(self):

        print('FINISHED {}'.format(self.id()))


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
        self.assertIsInstance(serialized,str)

        fields2 = str2QgsFields(serialized)
        self.assertIsInstance(fields2, QgsFields)
        self.assertEqual(fields.count(), fields2.count())
        for i in range(fields.count()):
            f1 = fields.at(i)
            f2 = fields2.at(i)
            self.assertEqual(f1.type(), f2.type())
            self.assertEqual(f1.name(), f2.name())
            self.assertEqual(f1.typeName(), f2.typeName())


    def test_AttributeDialog(self):

        SLIB = TestObjects.createSpectralLibrary()

        d = AddAttributeDialog(SLIB)

        self.showGui(d)



    def test_SpectralProfile_BandBandList(self):

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


        import qps.speclib.spectrallibraries
        x = [1, 2, 3, 4, 5]
        y = [2, 3, 4, 5, 6]
        bbl = [1, 0, 1, 1, 0]
        xUnit = 'nm'
        yUnit = None

        reminder = qps.speclib.spectrallibraries.SERIALIZATION

        for mode in [SerializationMode.JSON, SerializationMode.PICKLE]:
            qps.speclib.spectrallibraries.SERIALIZATION = mode

            sl = SpectralLibrary()
            self.assertTrue(sl.startEditing())
            sp = SpectralProfile()
            sp.setValues(x=x, y=y, bbl=bbl, xUnit=xUnit, yUnit=yUnit)

            vd1 = sp.values()
            dump = encodeProfileValueDict(vd1)

            if mode == SerializationMode.JSON:
                self.assertIsInstance(dump, str)
            elif mode == SerializationMode.PICKLE:
                self.assertIsInstance(dump, QByteArray)

            vd2 = decodeProfileValueDict(dump)
            self.assertIsInstance(vd2, dict)
            self.assertEqual(vd1, vd2)
            sl.addProfiles([sp])
            self.assertTrue(sl.commitChanges())

            rawValues = sl.getFeature(sl.allFeatureIds()[0]).attribute(FIELD_VALUES)

            if mode == SerializationMode.JSON:
                self.assertIsInstance(rawValues, str)
            elif mode == SerializationMode.PICKLE:
                self.assertIsInstance(rawValues, QByteArray)



        qps.speclib.spectrallibraries.SERIALIZATION = reminder


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
        for k in ['x','y', 'yUnit', 'xUnit', 'bbl']:
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
        lyr1 = QgsRasterLayer(enmap)
        lyr2 = QgsRasterLayer(hymap)
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

        name = 'missingAttribute'
        sp1.setMetadata(name, 'myvalue')
        self.assertTrue(name not in sp1.fieldNames())
        sp1.setMetadata(name, 'myvalue', addMissingFields=True)
        self.assertTrue(name in sp1.fieldNames())
        self.assertEqual(sp1.metadata(name), 'myvalue')
        sp1.removeField(name)
        self.assertTrue(name not in sp1.fieldNames())

        sp1.setXUnit('nm')
        self.assertEqual(sp1.xUnit(), 'nm')

        self.assertEqual(sp1, sp1)


        for sp2 in[sp1.clone(), copy.copy(sp1), sp1.__copy__()]:
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
            self.assertEqual(p1.name(), p2.name())
            self.assertEqual(p1.id(), p2.id())


        sp2 = SpectralProfile()
        sp2.setValues(x=xVal, y=yVal, xUnit='um')
        self.assertNotEqual(sp1, sp2)
        sp2.setValues(xUnit='nm')
        self.assertEqual(sp1, sp2)
        sp2.setYUnit('reflectance')
        #self.assertNotEqual(sp1, sp2)




        values = [('key','value'),('key', 100),('Üä','ÜmlÄute')]
        for md in values:
            k, d = md
            sp1.setMetadata(k,d)
            v2 = sp1.metadata(k)
            self.assertEqual(v2, None)

        for md in values:
            k, d = md
            sp1.setMetadata(k, d, addMissingFields=True)
            v2 = sp1.metadata(k)
            self.assertEqual(d, v2)

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

    def test_SpectralProfileReading(self):

        lyr = TestObjects.createRasterLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)

        center = SpatialPoint.fromMapLayerCenter(lyr)
        extent = SpatialExtent.fromLayer(lyr)
        x,y = extent.upperLeft()

        outOfImage = SpatialPoint(center.crs(), x - 10, y + 10)

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
        sp1.setName('Name A')
        sp1.setValues(y=[0, 4, 3, 2, 1], x=[450, 500, 750, 1000, 1500])

        sp2 = SpectralProfile()
        sp2.setName('Name B')
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
            self.assertIsInstance(slRetrieved, SpectralLibrary, 'Re-Import from MIMEDATA failed for MIME type "{}"'.format(format))

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
                self.assertEqual(p.name(), pr.name())
                self.assertEqual(p, pr)


            self.assertEqual(sl1, slRetrieved)


    def test_groupBySpectralProperties(self):

        sl1 = TestObjects.createSpectralLibrary()
        groups = sl1.groupBySpectralProperties(excludeEmptyProfiles=False)
        self.assertTrue(len(groups) > 0)
        for key, profiles in groups.items():
            self.assertTrue(len(key) == 3)
            xvalues, xunit, yunit = key
            self.assertTrue(xvalues is None or isinstance(xvalues, tuple) and len(xvalues) > 0)
            self.assertTrue(xunit is None or isinstance(xunit, str) and len(xunit) > 0)
            self.assertTrue(yunit is None or isinstance(yunit, str) and len(yunit) > 0)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

            l = len(profiles[0].xValues())

            for p in profiles:
                self.assertEqual(l, len(p.xValues()))

    def test_SpectralLibrary(self):

        self.assertListEqual(vsiSpeclibs(), [])
        self.assertTrue(len(SpectralLibrary.instances()) == 0)
        sp1 = SpectralProfile()
        sp1.setName('Name 1')
        sp1.setValues(y=[1, 1, 1, 1, 1], x=[450, 500, 750, 1000, 1500])

        sp2 = SpectralProfile()
        sp2.setName('Name 2')
        sp2.setValues(y=[2, 2, 2, 2, 2], x=[450, 500, 750, 1000, 1500])

        SLIB = SpectralLibrary()
        self.assertEqual(len(vsiSpeclibs()), 1)
        self.assertEqual(len(SpectralLibrary.instances()), 1)
        self.assertEqual(len(SpectralLibrary.instances()), 1)

        sl2 = SpectralLibrary()
        self.assertEqual(len(vsiSpeclibs()), 2)
        self.assertEqual(len(SpectralLibrary.instances()), 2)
        self.assertEqual(len(SpectralLibrary.instances()), 2)

        del sl2
        self.assertEqual(len(SpectralLibrary.instances()), 1)

        self.assertEqual(SLIB.name(), 'SpectralLibrary')
        SLIB.setName('MySpecLib')
        self.assertEqual(SLIB.name(), 'MySpecLib')

        SLIB.startEditing()
        SLIB.addProfiles([sp1, sp2])
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

        self.assertEqual(p.values(), sp1.values(), msg='Unequal values:\n\t{}\n\t{}'.format(str(p.values()), str(sp1.values())))
        self.assertEqual(SLIB[0].values(), sp1.values())

        #self.assertNotEqual(speclib[0], sp1) #because sl1 has an FID


        subset = SLIB[0:1]
        self.assertIsInstance(subset, list)
        self.assertEqual(len(subset), 1)


        self.assertEqual(set(SLIB.allFeatureIds()), set([1,2]))
        slSubset = SLIB.speclibFromFeatureIDs(fids=2)
        self.assertEqual(set(SLIB.allFeatureIds()), set([1, 2]))
        self.assertIsInstance(slSubset, SpectralLibrary)

        refs = list(SpectralLibrary.instances())
        self.assertTrue(len(refs) == 2)

        self.assertEqual(len(slSubset), 1)
        self.assertEqual(slSubset[0].values(), SLIB[1].values())

        n = len(vsiSpeclibs())
        dump = pickle.dumps(SLIB)
        restoredSpeclib = pickle.loads(dump)
        self.assertIsInstance(restoredSpeclib, SpectralLibrary)
        self.assertEqual(len(vsiSpeclibs()), n+1)
        self.assertEqual(len(SLIB), len(restoredSpeclib))

        for i in range(len(SLIB)):
            p1 = SLIB[i]
            r1 = restoredSpeclib[i]

            if p1.values() != r1.values():
                s  =""

            self.assertEqual(p1.values(), r1.values(), msg='dumped and restored values are not the same')

        restoredSpeclib.startEditing()
        restoredSpeclib.addProfiles([sp2])
        self.assertTrue(restoredSpeclib.commitChanges())
        self.assertNotEqual(SLIB, restoredSpeclib)
        self.assertEqual(restoredSpeclib[-1].values(), sp2.values())


        #read from image

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
        self.assertTrue(len(SLIB) == n1+n2)
        SLIB.addProfiles(slSubset[:])
        self.assertTrue(len(SLIB) == n1 + n2 + n2)
        self.assertTrue(SLIB.commitChanges())

    def test_others(self):

        self.assertEqual(23, toType(int, '23'))
        self.assertEqual([23, 42], toType(int, ['23','42']))
        self.assertEqual(23., toType(float, '23'))
        self.assertEqual([23., 42.], toType(float, ['23','42']))

        self.assertTrue(findTypeFromString('23') is int)
        self.assertTrue(findTypeFromString('23.3') is float)
        self.assertTrue(findTypeFromString('xyz23.3') is str)
        self.assertTrue(findTypeFromString('') is str)

        regex = CSVSpectralLibraryIO.REGEX_BANDVALUE_COLUMN

        #REGEX to identify band value column names

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
        sp2 = SpectralLibrary.readFrom(speclibpath, progressDialog=pd)

        self.assertIsInstance(sp1, SpectralLibrary)
        self.assertIsInstance(sp2, SpectralLibrary)

        n = len(sp1)
        with self.assertRaises(Exception):
            sp1.addSpeclib(sp2)
        self.assertTrue(len(sp1), n)

        sp1.startEditing()
        sp1.addSpeclib(sp2)
        self.assertTrue(len(sp1), n+len(sp2))




    def test_SpectralProfileEditorWidget(self):

        SLIB = TestObjects.createSpectralLibrary()

        w = SpectralProfileEditorWidget()
        p = SLIB[-1]
        w.setProfileValues(p)

        self.showGui(w)

    def test_SpectralProfileValueTableModel(self):

        speclib = TestObjects.createSpectralLibrary()
        p3 = speclib[2]
        self.assertIsInstance(p3, SpectralProfile)

        xUnit = p3.xUnit()
        yUnit = p3.yUnit()

        if yUnit is None:
            yUnit = '-'
        if xUnit is None:
            xUnit = '-'

        m = SpectralProfileValueTableModel()

        self.assertIsInstance(m, SpectralProfileValueTableModel)
        self.assertTrue(m.rowCount() == 0)
        self.assertTrue(m.columnCount() == 2)
        self.assertEqual('Y [-]', m.headerData(0, orientation=Qt.Horizontal, role=Qt.DisplayRole))
        self.assertEqual('X [-]', m.headerData(1, orientation=Qt.Horizontal, role=Qt.DisplayRole))

        m.setProfileData(p3)
        self.assertTrue(m.rowCount() == len(p3.xValues()))
        self.assertEqual('Y [{}]'.format(yUnit), m.headerData(0, orientation=Qt.Horizontal, role=Qt.DisplayRole))
        self.assertEqual('X [{}]'.format(xUnit), m.headerData(1, orientation=Qt.Horizontal, role=Qt.DisplayRole))

        m.setColumnValueUnit(0, '')

    def test_SpectralProfileEditorWidgetFactory(self):

        # init some other requirements
        print('initialize EnMAP-Box editor widget factories')
        # register Editor widgets, if not done before

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        registerSpectralProfileEditorWidget()
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, SpectralProfileEditorWidgetFactory)
        vl = TestObjects.createSpectralLibrary()
        am = vl.actions()
        self.assertIsInstance(am, QgsActionManager)

        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())
        dv = QgsDualView()
        dv.init(vl, c)
        dv.setView(QgsDualView.AttributeTable)
        dv.setAttributeTableConfig(vl.attributeTableConfig())
        cb = QCheckBox()
        cb.setText('Show Editor')
        def onClicked(b:bool):
            if b:
                dv.setView(QgsDualView.AttributeEditor)
            else:
                dv.setView(QgsDualView.AttributeTable)
        cb.clicked.connect(onClicked)
        w.layout().addWidget(dv)
        w.layout().addWidget(cb)

        w.resize(QSize(300, 250))
        print(vl.fields().names())
        look = vl.fields().lookupField

        parent = QWidget()
        configWidget = factory.configWidget(vl, look(FIELD_VALUES), None)
        self.assertIsInstance(configWidget, SpectralProfileEditorConfigWidget)

        self.assertIsInstance(factory.createSearchWidget(vl, 0, dv), QgsSearchWidgetWrapper)

        eww = factory.create(vl, 0, None, dv )
        self.assertIsInstance(eww, SpectralProfileEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), SpectralProfileEditorWidget)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))

        fields = vl.fields()
        vl.startEditing()
        value = eww.value()
        f = vl.getFeature(1)
        self.assertTrue(vl.updateFeature(f))

        self.showGui([w, configWidget])


    def test_largeLibs(self):

        r = r'T:/4bj/20140615_fulllib_clean.sli'
        if os.path.isfile(r):
            import time

            pps_min = 1000 #minium number of profiles per second

            t0 = time.time()
            pd = QProgressDialog()
            sl = SpectralLibrary.readFrom(r, progressDialog=pd)
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) > 1000)

            t1 = time.time()
            pps = float(len(sl)) / (t1-t0)

            print('read ESL {}'.format(pps))
            #self.assertTrue(pps > pps_min, msg='spectra import took tooo long. Need to have {} profiles per second at least. got {}'.format(pps_min, pps))


            slw = SpectralLibraryWidget()


            QgsApplication.processEvents()

            time0 = time.time()
            slw.addSpeclib(sl)
            QgsApplication.processEvents()
            time1 = time.time()

            pps = float(len(sl)) / (time1 - time0)
            print('visualize ESL {}'.format(pps))

            QgsApplication.processEvents()

            if not self.showGui([slw]):
                self.assertTrue(pps > 5*60,
                                msg='spectra visualization took tooo long. Need to have {} profiles per second at least. got {}'.format(
                                    pps_min, pps))


    def test_multiinstances(self):

        sl1 = SpectralLibrary(name='A')
        sl2 = SpectralLibrary(name='B')

        self.assertIsInstance(sl1, SpectralLibrary)
        self.assertIsInstance(sl2, SpectralLibrary)
        self.assertNotEqual(id(sl1), id(sl2))

    def test_qmainwindow(self):

        w1 = QWidget()
        w1.setWindowTitle('Parent')
        w1.setLayout(QVBoxLayout())

        w2 = QMainWindow()
        w2.setWindowTitle('CENTRAL MAIN APP')
        l = QLabel('CENTRAL')
        w2.setCentralWidget(l)

        w1.layout().addWidget(w2)


        self.showGui(w1)

    def test_SpectralLibrary_readFromVector(self):

        from qpstestdata import enmap_pixel, landcover, enmap

        rl = QgsRasterLayer(enmap)
        vl = QgsVectorLayer(enmap_pixel)

        progressDialog = QProgressDialog()
        #progressDialog.show()

        info ='Test read from \n'+ \
              'Vector: {}\n'.format(vl.crs().description()) + \
              'Raster: {}\n'.format(rl.crs().description())
        print(info)

        sl = SpectralLibrary.readFromVector(vl, rl, progressDialog=progressDialog)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertTrue(len(sl) > 0, msg='Failed to read SpectralProfiles')
        self.assertEqual(len(sl), rl.width() * rl.height())

        self.assertTrue(progressDialog.value(), [-1, progressDialog.maximum()])

        data = gdal.Open(enmap).ReadAsArray()
        nb, nl, ns = data.shape

        for p in sl:
            self.assertIsInstance(p, SpectralProfile)

            x = p.attribute('px_x')
            y = p.attribute('px_y')
            yValues = p.values()['y']
            yValues2 = list(data[:, y, x])
            self.assertListEqual(yValues, yValues2)
            s = ""

        self.assertTrue(sl.crs() != vl.crs())


        info ='Test read from \n'+ \
              'Vector: {} (speclib)\n'.format(sl.crs().description()) + \
              'Raster: {}\n'.format(rl.crs().description())
        print(info)


        sl2 = SpectralLibrary.readFromVector(sl, rl)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertTrue(len(sl2) > 0, msg='Failed to re-read SpectralProfiles')
        self.assertEqual(sl, sl2)

        rl = QgsRasterLayer(enmap)
        vl = QgsVectorLayer(landcover)
        sl = SpectralLibrary.readFromVector(vl, rl)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertTrue(len(sl) > 0)


    def test_mergeSpeclibSpeed(self):

        from qpstestdata import speclib

        pd = QProgressDialog()
        sl1 = SpectralLibrary.readFrom(speclib, progressDialog=pd)

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

        self.assertEqual(len(sl2), n*2)



        s = ""
    def test_speclibImportSpeed(self):

        pathRaster = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\enmap-box\enmapboxtestdata\enmap_berlin.bsq'
        #pathPoly = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\enmap-box\enmapboxtestdata\landcover_berlin_polygon.shp'
        pathPoly = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\enmap-box\enmapboxtestdata\landcover_berlin_point.shp'

        for p in [pathRaster, pathPoly]:
            if not os.path.isfile(p):
                return

        progressDialog = QProgressDialog()
        #progressDialog.show()
        vl = QgsVectorLayer(pathPoly)
        vl.setName('Polygons')
        rl = QgsRasterLayer(pathRaster)
        rl.setName('Raster Data')
        if not vl.isValid() and rl.isValid():
            return

        max_spp = 1 # seconds per profile

        def timestats(t0, sl, info='time'):
            dt = time.time() - t0
            spp = dt / len(sl)
            pps = len(sl) / dt
            print('{}: dt={}sec spp={} pps={}'.format(info, dt, spp, pps ))
            return dt, spp, pps

        t0 = time.time()
        sl = SpectralLibrary.readFromVector(vl, rl, progressDialog=progressDialog)
        dt, spp, pps = timestats(t0, sl, info='read profiles')
        self.assertTrue(spp <= max_spp, msg='{} seconds per profile are too much!')

        self.assertTrue(progressDialog.value() == -1)
        t0 = time.time()
        sl.startEditing()
        sl.addSpeclib(sl)
        sl.commitChanges()
        dt, spp, pps = timestats(t0, sl, info='merge speclibs')
        self.assertTrue(spp <= max_spp, msg='too slow!')


        sl0 = SpectralLibrary()
        t0 = time.time()
        sl0.startEditing()
        sl0.addSpeclib(sl)
        dt, spp, pps = timestats(t0, sl, info='merge speclibs2')
        self.assertTrue(spp <= max_spp, msg='too slow!')


        w = SpectralLibraryWidget()

        t0 = time.time()
        w.addSpeclib(sl)

        dt = time.time()-t0

        QgsProject.instance().addMapLayers([vl, rl])
        w = SpectralLibraryWidget()
        self.showGui(w)

    def test_SpectralProfileImportPointsDialog(self):

        lyrRaster = QgsRasterLayer(enmap)
        lyrRaster.setName('EnMAP')
        h, w = lyrRaster.height(), lyrRaster.width()

        pxPositions = [QPoint(0, 0), QPoint(w - 1, h - 1)]

        speclib1 = SpectralLibrary.readFromRasterPositions(enmap, pxPositions)
        speclib1.setName('Extracted Spectra')
        self.assertIsInstance(speclib1, SpectralLibrary)
        self.assertTrue(len(speclib1) > 0)

        vl1 = TestObjects.createVectorLayer(QgsWkbTypes.Polygon)
        vl2 = TestObjects.createVectorLayer(QgsWkbTypes.LineGeometry)
        vl3 = TestObjects.createVectorLayer(QgsWkbTypes.Point)
        QgsProject.instance().addMapLayers([speclib1, lyrRaster, vl1, vl2, vl3])

        d = SpectralProfileImportPointsDialog()
        self.assertIsInstance(d, SpectralProfileImportPointsDialog)
        d.setRasterSource(lyrRaster)
        d.setVectorSource(speclib1)
        d.show()
        self.assertEqual(lyrRaster, d.rasterSource())
        self.assertEqual(speclib1, d.vectorSource())

        d.run()

        slib = d.speclib()
        self.assertIsInstance(slib, SpectralLibrary)
        print('TEST ENDED', file=sys.stderr)
        self.showGui(d)

    def test_SpectralLibraryPanel(self):

        sp = SpectralLibraryPanel()
        self.showGui(sp)


    def test_SpectralLibraryWidgetProgressDialog(self):

        slib = TestObjects.createSpectralLibrary(3000)
        self.assertIsInstance(slib, SpectralLibrary)
        self.assertTrue(slib.isValid())
        #sw = SpectralLibraryWidget()
        #sw.show()
        #QApplication.processEvents()
        #sw.addSpeclib(slib)
        #QApplication.processEvents()

        #self.showGui(sw)



    def test_SpectralLibraryWidget(self):

        from qpstestdata import enmap, landcover, enmap_pixel

        l1 = QgsRasterLayer(enmap, 'EnMAP')
        l2 = QgsVectorLayer(landcover, 'LandCover')
        l3 = QgsVectorLayer(enmap_pixel, 'Points of Interest')
        QgsProject.instance().addMapLayers([l1, l2, l3])

        pd = QProgressDialog()
        speclib = SpectralLibrary.readFrom(speclibpath, progressDialog=pd)
        slw = SpectralLibraryWidget(speclib=speclib)

        QgsProject.instance().addMapLayer(slw.speclib())

        self.assertEqual(slw.speclib(), speclib)
        self.assertIsInstance(slw.speclib(), SpectralLibrary)
        fieldNames = slw.speclib().fieldNames()
        self.assertIsInstance(fieldNames, list)

        for mode in list(SpectralLibraryWidget.CurrentProfilesMode):
            assert isinstance(mode, SpectralLibraryWidget.CurrentProfilesMode)
            slw.setCurrentProfilesMode(mode)
            assert slw.currentProfilesMode() == mode

        cs = [speclib[0], speclib[3], speclib[-1]]
        l = len(speclib)
        self.assertTrue(slw.speclib() == speclib)

        self.assertTrue(len(slw.currentSpectra()) == 0)
        slw.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.block)
        slw.setCurrentSpectra(cs)
        self.assertTrue(len(slw.currentSpectra()) == 0)

        slw.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.automatically)
        slw.setCurrentSpectra(cs)
        self.assertTrue(len(slw.currentSpectra()) == 0)

        slw.setCurrentProfilesMode(SpectralLibraryWidget.CurrentProfilesMode.normal)
        slw.setCurrentSpectra(cs)
        self.assertTrue(len(slw.currentSpectra()) == 3)

        speclib.selectByIds([1, 2, 3])

        n = len(speclib)
        sids = speclib.selectedFeatureIds()

        self.assertTrue(len(sids) > 0)
        slw.copySelectedFeatures()
        slw.cutSelectedFeatures()
        slw.pasteFeatures()

        self.assertEqual(n, len(speclib))



        self.showGui(slw)


    def test_SpectralLibraryWidgetCanvas(self):

        # speclib = self.createSpeclib()

        lyr = QgsRasterLayer(hymap)
        h, w = lyr.height(), lyr.width()
        speclib = SpectralLibrary.readFromRasterPositions(enmap, [QPoint(0,0), QPoint(w-1, h-1), QPoint(2, 2)])
        slw = SpectralLibraryWidget(speclib=speclib)


        QgsProject.instance().addMapLayers([lyr, slw.speclib()])

        canvas = QgsMapCanvas()

        canvas.setLayers([lyr, slw.speclib()])
        canvas.setDestinationCrs(slw.speclib().crs())
        canvas.setExtent(slw.speclib().extent())


        def setLayers():
            canvas.mapSettings().setDestinationCrs(slw.mCanvas.mapSettings().destinationCrs())
            canvas.setExtent(slw.canvas().extent())
            canvas.setLayers(slw.canvas().layers())

        slw.sigMapCenterRequested.connect(setLayers)
        slw.sigMapExtentRequested.connect(setLayers)

        self.showGui([canvas, slw])

    def test_editing(self):

        slib = TestObjects.createSpectralLibrary()
        self.assertTrue(len(slib) > 0)
        slw = SpectralLibraryWidget()
        slw.speclib().startEditing()
        slw.speclib().addSpeclib(slib)

        slw.actionToggleEditing.setChecked(True)

        #self.assertTrue()
        self.showGui(slw)


    def test_speclibAttributeWidgets(self):

        import qps
        qps.registerEditorWidgets()
        speclib = TestObjects.createSpectralLibrary()

        slw = SpectralLibraryWidget(speclib=speclib)

        import qps.layerproperties
        properties = qps.layerproperties.VectorLayerProperties(speclib, None)

        self.showGui([slw, properties])




    def test_toolbarStackedActions(self):

        tb = QToolBar()
        a1 = tb.addAction('Action1')
        a2 = tb.addAction('ActionA2')

        a21 = QAction('A2.1')
        a22 = QAction('A2.2')
        a22.setCheckable(True)

        setToolButtonDefaultActionMenu(a2, [a21, a22])


        btn2 = tb.findChildren(QToolButton)[2]
        self.assertIsInstance(btn2, QToolButton)

        self.showGui(tb)

if __name__ == '__main__':

    unittest.main()
