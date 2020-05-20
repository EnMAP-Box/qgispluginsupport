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
import unittest
from qps.testing import TestObjects, TestCase


from qpstestdata import enmap, landcover
from qpstestdata import speclib as speclibpath

from qps.speclib.io.csvdata import *
from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *


TEST_DIR = os.path.join(os.path.dirname(__file__), 'temp')

class TestIO(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        os.makedirs(TEST_DIR, exist_ok=True)
        super(TestIO, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestIO, cls).tearDownClass()
        if os.path.isdir(TEST_DIR):
            import shutil
            shutil.rmtree(TEST_DIR)

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        for s in SpectralLibrary.instances():
            del s

        for file in vsiSpeclibs():
            gdal.Unlink(file)

    def test_VSI(self):

        slib1 = TestObjects.createSpectralLibrary()
        path = slib1.source()

        slib2 = SpectralLibrary.readFrom(path, progressDialog=QProgressDialog())
        self.assertIsInstance(slib2, SpectralLibrary)
        self.assertEqual(slib1, slib2)
        s = ""

    def test_jsonIO(self):

        slib = TestObjects.createSpectralLibrary()
        pathJSON = tempfile.mktemp(suffix='.json', prefix='tmpSpeclib')

        # no additional info, no JSON file
        slib.writeJSONProperties(pathJSON)
        self.assertFalse(os.path.isfile(pathJSON))

        # add categorical info
        slib.startEditing()
        slib.addAttribute(QgsField('class1', QVariant.String, 'varchar'))
        slib.addAttribute(QgsField('class2', QVariant.Int, 'int'))
        slib.commitChanges()
        slib.startEditing()

        from qps.classification.classificationscheme import ClassificationScheme, ClassInfo, EDITOR_WIDGET_REGISTRY_KEY, classSchemeToConfig

        cs = ClassificationScheme()
        cs.insertClass(ClassInfo(name='unclassified'))
        cs.insertClass(ClassInfo(name='class a', color=QColor('red')))
        cs.insertClass(ClassInfo(name='class b', color=QColor('blue')))

        idx1 = slib.fields().lookupField('class1')
        idx2 = slib.fields().lookupField('class2')

        config = classSchemeToConfig(cs)
        setup1 = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, config)
        setup2 = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, config)
        slib.setEditorWidgetSetup(idx1, setup1)
        slib.setEditorWidgetSetup(idx2, setup2)

        slib.writeJSONProperties(pathJSON)
        self.assertTrue(os.path.isfile(pathJSON))
        with open(pathJSON, 'r') as file:
            jsonData = json.load(file)
            self.assertTrue('class1' in jsonData.keys())
            self.assertTrue('class2' in jsonData.keys())

        slib.setEditorWidgetSetup(idx1, QgsEditorWidgetSetup('', {}))
        slib.setEditorWidgetSetup(idx2, QgsEditorWidgetSetup('', {}))
        data = slib.readJSONProperties(pathJSON)
        s = ""

    def test_CSV2(self):
        from qpstestdata import speclib
        from qps.speclib.io.csvdata import CSVSpectralLibraryIO
        SLIB = SpectralLibrary.readFrom(speclib, progressDialog=QProgressDialog())
        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')

        CSVSpectralLibraryIO.write(SLIB, pathCSV, progressDialog=QProgressDialog())

        self.assertTrue(os.path.isfile(pathCSV))
        dialect = CSVSpectralLibraryIO.canRead(pathCSV)
        self.assertTrue(dialect is not None)
        speclib2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, progressDialog=QProgressDialog())
        self.assertTrue(len(SLIB) == len(speclib2))
        for i, (p1, p2) in enumerate(zip(SLIB[:], speclib2[:])):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            if p1 != p2:
                s = ""
            self.assertEqual(p1, p2)

        SLIB = TestObjects.createSpectralLibrary()
        #pathCSV = os.path.join(os.path.dirname(__file__), 'speclibcvs2.out.csv')
        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        print(pathCSV)
        CSVSpectralLibraryIO.write(SLIB, pathCSV, progressDialog=QProgressDialog())

        self.assertTrue(os.path.isfile(pathCSV))
        dialect = CSVSpectralLibraryIO.canRead(pathCSV)
        self.assertTrue(dialect is not None)
        speclib2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, progressDialog=QProgressDialog())
        self.assertTrue(len(SLIB) == len(speclib2))
        for i, (p1, p2) in enumerate(zip(SLIB[:], speclib2[:])):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertEqual(p1.xValues(), p2.xValues())
            self.assertEqual(p1.yValues(), p2.yValues())
            if p1 != p2:
                s = ""
            self.assertEqual(p1, p2)


        #self.assertEqual(SLIB, speclib2)


        # addresses issue #8
        from qpstestdata import speclib
        SL1 = SpectralLibrary.readFrom(speclib, progressDialog=QProgressDialog())
        self.assertIsInstance(SL1, SpectralLibrary)

        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        print(pathCSV)
        for dialect in [pycsv.excel_tab, pycsv.excel]:
            pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
            CSVSpectralLibraryIO.write(SL1, pathCSV, dialect=dialect, progressDialog=QProgressDialog())
            d = CSVSpectralLibraryIO.canRead(pathCSV)
            self.assertEqual(d, dialect)
            SL2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, progressDialog=QProgressDialog())
            self.assertIsInstance(SL2, SpectralLibrary)
            self.assertTrue(len(SL1) == len(SL2))

            for p1, p2 in zip(SL1[:], SL2[:]):
                self.assertIsInstance(p1, SpectralProfile)
                self.assertIsInstance(p2, SpectralProfile)
                if p1 != p2:
                    s = ""
                self.assertEqual(p1, p2)


        # addresses issue #8 loading modified CSV values

        SL = SpectralLibrary.readFrom(speclib, progressDialog=QProgressDialog())

        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        CSVSpectralLibraryIO.write(SL, pathCSV, progressDialog=QProgressDialog())

        with open(pathCSV, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # change band values of b1 and b3

        WKT = None
        delimiter = '\t'
        for i in range(len(lines)):
            line = lines[i]
            if line.strip() in ['']:
                continue
            if line.startswith('#'):
                continue

            if line.startswith('WKT'):
                WKT = line.split(delimiter)
                continue


            parts = line.split(delimiter)
            parts[WKT.index('b1')] = '42.0'
            parts[WKT.index('b100')] = '42'
            line = delimiter.join(parts)
            lines[i] = line

        with open(pathCSV, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        SL2 = CSVSpectralLibraryIO.readFrom(pathCSV, progressDialog=QProgressDialog())

        self.assertEqual(len(SL), len(SL2))

        for p in SL2:
            self.assertIsInstance(p, SpectralProfile)
            self.assertEqual(p.yValues()[0], 42)
            self.assertEqual(p.yValues()[99], 42)

    def test_vector2speclib(self):

        lyrRaster = QgsRasterLayer(enmap)
        h, w = lyrRaster.height(), lyrRaster.width()

        factor = [0, 0.5, 1.]
        pxPositions = []

        for x in factor:
            for y in factor:
                pxPositions.append(QPoint(int(x * (w-1)), int(y * (h-1))))

        speclib1 = SpectralLibrary.readFromRasterPositions(enmap, pxPositions)

        ds = gdal.Open(enmap)
        data = ds.ReadAsArray()
        for i, px in enumerate(pxPositions):

            vector = data[:, px.y(), px.x()]

            profile = speclib1[i]

            self.assertIsInstance(profile, SpectralProfile)
            vector2 = profile.yValues()
            self.assertListEqual(list(vector), vector2)

        progress = QProgressDialog()

        speclib2 = SpectralLibrary.readFromVector(speclib1, lyrRaster, progressDialog=progress)
        self.assertIsInstance(speclib2, SpectralLibrary)
        self.assertEqual(len(speclib1), len(speclib2))
        self.assertTrue(speclib1.crs().toWkt() == speclib2.crs().toWkt())

        profiles1 = sorted(speclib1[:], key=lambda f:f.name())
        profiles2 = sorted(speclib1[:], key=lambda f:f.name())

        for p1, p2 in zip(profiles1, profiles2):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertListEqual(p1.yValues(), p2.yValues())
            self.assertTrue(p1.geometry().equals(p2.geometry()))


        vlLandCover = QgsVectorLayer(landcover)
        rlEnMAP = QgsRasterLayer(enmap)
        speclib3 = SpectralLibrary.readFromVector(vlLandCover, rlEnMAP, progressDialog=progress)

        self.assertIsInstance(speclib3, SpectralLibrary)
        self.assertTrue(len(speclib3) > 0)

        speclib4 = SpectralLibrary.readFromVector(vlLandCover, rlEnMAP, copy_attributes=True, progressDialog=progress)
        self.assertIsInstance(speclib3, SpectralLibrary)
        self.assertTrue(len(speclib3) > 0)
        self.assertTrue(len(speclib3.fieldNames()) < len(speclib4.fieldNames()))
        for fieldName in vlLandCover.fields().names():
            self.assertTrue(fieldName in speclib4.fieldNames())


    def test_reloadProfiles(self):
        lyr = QgsRasterLayer(enmap)
        QgsProject.instance().addMapLayer(lyr)
        lyr.setName('ENMAP')
        self.assertIsInstance(lyr, QgsRasterLayer)
        locations = []
        for x in range(lyr.width()):
            for y in range(lyr.height()):
                locations.append(QPoint(x, y))

        print('load speclibA', flush=True)
        speclibA = SpectralLibrary.readFromRasterPositions(lyr.source(), locations)
        self.assertIsInstance(speclibA, SpectralLibrary)

        print('load speclibREF', flush=True)
        speclibREF = SpectralLibrary.readFromRasterPositions(lyr.source(), locations)
        self.assertIsInstance(speclibREF, SpectralLibrary)
        speclibREF.setName('REF SPECLIB')
        self.assertIsInstance(speclibA, SpectralLibrary)
        self.assertTrue(len(locations) == len(speclibA))

        self.assertFalse(speclibA.isEditable())
        print('speclibA is editable', flush=True)

        # clean values
        self.assertTrue(speclibA.startEditing())
        idx = speclibA.fields().indexOf(FIELD_VALUES)

        n = 0
        for p in speclibA:
            n += 1
            #if n > 10:
            #    break
            print('Change attribute values profile {}'.format(p.id()), flush=True)
            self.assertIsInstance(p, SpectralProfile)
            speclibA.changeAttributeValue(p.id(), idx, None)
            QApplication.processEvents()

        print('Commit changes', flush=True)
        self.assertTrue(speclibA.commitChanges())

        print('Check yValues(', flush=True)

        for p in speclibA:
            self.assertIsInstance(p, SpectralProfile)
            self.assertListEqual(p.yValues(), [])
            QApplication.processEvents()

        QApplication.processEvents()
        # re-read values
        print('select all', flush=True)
        speclibA.selectAll()
        print('start editing', flush=True)
        speclibA.startEditing()
        QApplication.processEvents()
        print('reload spectral values', flush=True)
        speclibA.reloadSpectralValues(enmap)
        self.assertTrue(speclibA.commitChanges())

        print('Compare speclibA with speclibREF', flush=True)
        for a, b in zip(speclibA[:], speclibREF[:]):
            self.assertIsInstance(a, SpectralProfile)
            self.assertIsInstance(b, SpectralProfile)
            self.assertListEqual(a.xValues(), b.xValues())
            self.assertListEqual(a.yValues(), b.yValues())

        print('load SpectralLibraryWidget', flush=True)
        slw = SpectralLibraryWidget(speclib=speclibA)
        QApplication.processEvents()

        # clean values
        speclibA.startEditing()
        idx = speclibA.fields().indexOf(FIELD_VALUES)
        for p in speclibA:
            self.assertIsInstance(p, SpectralProfile)
            speclibA.changeAttributeValue(p.id(), idx, None)
        self.assertTrue(speclibA.commitChanges())
        QApplication.processEvents()
        self.showGui(slw)

    def test_EcoSIS(self):

        from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
        from qpstestdata import speclib
        self.assertFalse(EcoSISSpectralLibraryIO.canRead(speclib))

        # 1. read
        from qpstestdata import DIR_ECOSIS
        for path in file_search(DIR_ECOSIS, '*.csv'):
            print('Read {}...'.format(path))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(path), msg='Unable to read {}'.format(path))
            sl = EcoSISSpectralLibraryIO.readFrom(path, progressDialog=QProgressDialog())
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) > 0)

        # 2. write
        speclib = TestObjects.createSpectralLibrary(50)

        # remove x/y values from first profile. this profile should be skipped in the outputs
        p0 = speclib[0]
        self.assertIsInstance(p0, SpectralProfile)
        p0.setValues(x=[], y=[])
        speclib.startEditing()
        speclib.updateFeature(p0)
        self.assertTrue(speclib.commitChanges())

        pathCSV = os.path.join(TEST_DIR, 'speclib.ecosys.csv')
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, progressDialog=QProgressDialog())
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, progressDialog=None)
        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(p))

            slPart = EcoSISSpectralLibraryIO.readFrom(p, progressDialog=QProgressDialog())
            self.assertIsInstance(slPart, SpectralLibrary)


            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)




    def test_SPECCHIO(self):


        from qps.speclib.io.specchio import SPECCHIOSpectralLibraryIO

        # 1. read
        from qpstestdata import DIR_SPECCHIO
        for path in reversed(list(file_search(DIR_SPECCHIO, '*.csv'))):

            self.assertTrue(SPECCHIOSpectralLibraryIO.canRead(path))
            sl = SPECCHIOSpectralLibraryIO.readFrom(path, progressDialog=QProgressDialog())
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) > 0)
            for p in sl:
                self.assertIsInstance(p, SpectralProfile)
                self.assertListEqual(p.xValues(), sorted(p.xValues()))
        # 2. write
        speclib = TestObjects.createSpectralLibrary(50, n_empty=1)
        pathCSV = os.path.join(TEST_DIR, 'speclib.specchio.csv')
        csvFiles = SPECCHIOSpectralLibraryIO.write(speclib, pathCSV, progressDialog=QProgressDialog())

        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(SPECCHIOSpectralLibraryIO.canRead(p))

            slPart = SPECCHIOSpectralLibraryIO.readFrom(p, progressDialog=QProgressDialog())
            self.assertIsInstance(slPart, SpectralLibrary)
            for p in slPart:
                self.assertIsInstance(p, SpectralProfile)
                self.assertListEqual(p.xValues(), sorted(p.xValues()))

            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)


    def test_ASD(self):

        # read binary files
        from qps.speclib.io.asd import ASDSpectralLibraryIO, ASDBinaryFile
        from qpstestdata import DIR_ASD_BIN, DIR_ASD_TXT

        binaryFiles = list(file_search(DIR_ASD_BIN, '*.asd'))
        pd = QProgressDialog()
        for path in binaryFiles:
            self.assertTrue(ASDSpectralLibraryIO.canRead(path))
            asdFile = ASDBinaryFile().readFromBinaryFile(path)

            self.assertIsInstance(asdFile, ASDBinaryFile)

            sl = ASDSpectralLibraryIO.readFrom(path, progressDialog=pd)
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertEqual(len(sl), 1)

        sl = ASDSpectralLibraryIO.readFrom(binaryFiles, progressDialog=pd)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertEqual(len(sl), len(binaryFiles))

        textFiles = list(file_search(DIR_ASD_TXT, '*.asd.txt'))
        for path in textFiles:
            self.assertTrue(ASDSpectralLibraryIO.canRead(path))

            sl = ASDSpectralLibraryIO.readFrom(path, progressDialog=pd)
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertEqual(len(sl), 1)

        sl = ASDSpectralLibraryIO.readFrom(textFiles, progressDialog=pd)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertEqual(len(sl), len(textFiles))

    def test_speclib2vector(self):

        testDir = self.testOutputDirectory() / 'speclib2vector'
        os.makedirs(testDir, exist_ok=True)

        from qps.speclib.io.vectorsources import VectorSourceSpectralLibraryIO

        slib = TestObjects.createSpectralLibrary(2, n_bands=[-1, 3, 24])
        self.assertTrue(len(slib) == 6)

        extensions = ['.json', '.geojson', '.geojsonl', '.csv', '.gpkg']

        hasLIBKML = isinstance(ogr.GetDriverByName('LIBKML'), ogr.Driver)
        if hasLIBKML:
            extensions.append('.kml')

        for ext in extensions:
            print('Test vector file type {}'.format(ext))
            path = testDir / f'speclib_{ext[1:]}{ext}'

            # write
            writtenFiles = VectorSourceSpectralLibraryIO.write(slib, path, progressDialog=QProgressDialog())
            self.assertTrue(len(writtenFiles) == 1)

            # read
            file = writtenFiles[0]
            self.assertTrue(VectorSourceSpectralLibraryIO.canRead(file),
                            msg='Failed to read speclib from {}'.format(file))
            sl = VectorSourceSpectralLibraryIO.readFrom(file, progressDialog=QProgressDialog())
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertEqual(len(sl), len(slib))

            for p1, p2 in zip(slib[:], sl[:]):
                self.assertIsInstance(p1, SpectralProfile)
                self.assertIsInstance(p2, SpectralProfile)
                self.assertEqual(p1.name(), p2.name())
                self.assertEqual(p1.xUnit(), p2.xUnit())
                self.assertEqual(p1.yUnit(), p2.yUnit())
                self.assertListEqual(p1.xValues(), p2.xValues())
                self.assertListEqual(p1.yValues(), p2.yValues())




    def test_AbstractSpectralLibraryIOs(self):
        """
        A generic test to check all AbstractSpectralLibraryIO implementations
        """
        slib = TestObjects.createSpectralLibrary()

        nFeatures = len(slib)
        nProfiles = 0
        for p in slib:
            if len(p.yValues()) > 0:
                nProfiles += 1

        pd = QProgressDialog()
        for c in allSubclasses(AbstractSpectralLibraryIO):
            print('Test {}'.format(c.__name__))
            path = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
            writtenFiles = c.write(slib, path, progressDialog=pd)

            # if it can write, it should read the profiles too
            if len(writtenFiles) > 0:

                n = 0
                for path in writtenFiles:
                    self.assertTrue(os.path.isfile(path), msg='Failed to write file. {}'.format(c))
                    sl = c.readFrom(path, progressDialog=pd)
                    self.assertIsInstance(sl, SpectralLibrary)
                    n += len(sl)

                self.assertTrue(n == nProfiles or n == nFeatures)
            pass


    def test_ARTMO(self):

        from qpstestdata import DIR_ARTMO

        p = os.path.join(DIR_ARTMO, 'directional_reflectance.txt')

        from qps.speclib.io.artmo import ARTMOSpectralLibraryIO

        self.assertTrue(ARTMOSpectralLibraryIO.canRead(p))
        pd = QProgressDialog()
        sl = ARTMOSpectralLibraryIO.readFrom(p, progressDialog=pd)

        self.assertIsInstance(sl, SpectralLibrary)
        self.assertEqual(len(sl), 10)

    def test_CSV(self):
        # TEST CSV writing


        speclib = TestObjects.createSpectralLibrary()

        # txt = CSVSpectralLibraryIO.asString(speclib)
        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        #pathCSV = os.path.join(os.path.dirname(__file__), 'speclibcvs3.out.csv')
        writtenFiles = speclib.exportProfiles(pathCSV)
        self.assertIsInstance(writtenFiles, list)
        self.assertTrue(len(writtenFiles) == 1)

        path = writtenFiles[0]
        lines = None
        with open(path, 'r') as f:
            lines = f.read()
        self.assertTrue(CSVSpectralLibraryIO.canRead(path), msg='Unable to read {}'.format(path))
        sl_read1 = CSVSpectralLibraryIO.readFrom(path, progressDialog=QProgressDialog())
        sl_read2 = SpectralLibrary.readFrom(path, progressDialog=QProgressDialog())

        self.assertTrue(len(sl_read1) > 0)
        self.assertIsInstance(sl_read1, SpectralLibrary)
        self.assertIsInstance(sl_read2, SpectralLibrary)

        self.assertEqual(len(sl_read1), len(speclib), msg='Should return {} instead of {} SpectralProfiles'.format(len(speclib), len(sl_read1)))

        profilesA = sorted(speclib.profiles(), key=lambda p: p.id())
        profilesB = sorted(sl_read1.profiles(), key=lambda p: p.attribute('fid'))

        for p1, p2 in zip(profilesA, profilesB):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertEqual(p1.name(), p2.name())
            self.assertEqual(p1.xUnit(), p2.xUnit())
            self.assertEqual(p1.yUnit(), p2.yUnit())

        self.SPECLIB = speclib

        try:
            os.remove(pathCSV)
        except:
            pass

    def test_csv_from_string(self):
        from qps.speclib.io.csvdata import CSVSpectralLibraryIO
        # see https://bitbucket.org/hu-geomatics/enmap-box/issues/321/error-when-dropping-a-raster-eg
        # test if CSVSpectralLibraryIO.fromString() handles obviously none-CSV data

        p = str(QUrl.fromLocalFile(pathlib.Path(__file__).resolve().as_posix()))
        result = CSVSpectralLibraryIO.fromString(p)
        self.assertTrue(result == None)


    def test_findEnviHeader(self):

        binarypath = speclibpath

        hdr, bin = findENVIHeader(speclibpath)

        self.assertTrue(os.path.isfile(hdr))
        self.assertTrue(os.path.isfile(bin))

        self.assertTrue(bin == speclibpath)
        self.assertTrue(hdr.endswith('.hdr'))

        headerPath = hdr

        # is is possible to use the *.hdr
        hdr, bin = findENVIHeader(headerPath)

        self.assertTrue(os.path.isfile(hdr))
        self.assertTrue(os.path.isfile(bin))

        self.assertTrue(bin == speclibpath)
        self.assertTrue(hdr.endswith('.hdr'))


        sl1 = SpectralLibrary.readFrom(binarypath, progressDialog=QProgressDialog())
        sl2 = SpectralLibrary.readFrom(headerPath, progressDialog=QProgressDialog())

        self.assertEqual(sl1, sl2)


        # this should fail

        pathWrong = enmap
        hdr, bin = findENVIHeader(pathWrong)
        self.assertTrue((hdr, bin) == (None, None))


    def test_ENVI(self):


        pathESL = speclibpath

        from qpstestdata import speclib

        self.assertTrue(EnviSpectralLibraryIO.canRead(speclib))

        sl = EnviSpectralLibraryIO.readFrom(speclib)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertTrue(len(sl) > 0)

        sl = SpectralLibrary.readFrom(speclib)
        self.assertIsInstance(sl, SpectralLibrary)
        self.assertTrue(len(sl) > 0)
        csv = readCSVMetadata(pathESL)


        sl1 = EnviSpectralLibraryIO.readFrom(pathESL, progressDialog=QProgressDialog())

        self.assertIsInstance(sl1, SpectralLibrary)
        p0 = sl1[0]
        self.assertIsInstance(p0, SpectralProfile)

        self.assertEqual(sl1.fieldNames(), ['fid', 'name', 'source', 'values'])
        self.assertEqual(p0.fieldNames(), ['fid', 'name', 'source', 'values'])

        self.assertEqual(p0.attribute('name'), p0.name())


        sl2 = SpectralLibrary.readFrom(pathESL, progressDialog=QProgressDialog())
        self.assertIsInstance(sl2, SpectralLibrary)
        self.assertEqual(sl1, sl2)
        p1 = sl2[0]
        self.assertIsInstance(p1, SpectralProfile)
        self.assertIsInstance(p1.xValues(), list)


        # test ENVI Spectral Library
        pathTmp = tempfile.mktemp(prefix='tmpESL', suffix='.sli')
        writtenFiles = EnviSpectralLibraryIO.write(sl1, pathTmp, progressDialog=QProgressDialog())


        nWritten = 0
        for pathHdr in writtenFiles:
            self.assertTrue(os.path.isfile(pathHdr))
            self.assertTrue(pathHdr.endswith('.sli'))

            basepath = os.path.splitext(pathHdr)[0]
            pathHDR = basepath + '.hdr'
            pathCSV = basepath + '.csv'
            self.assertTrue(os.path.isfile(pathHDR))
            self.assertTrue(os.path.isfile(pathCSV))

            self.assertTrue(EnviSpectralLibraryIO.canRead(pathHdr))
            sl_read1 = EnviSpectralLibraryIO.readFrom(pathHdr, progressDialog=QProgressDialog())
            self.assertIsInstance(sl_read1, SpectralLibrary)

            for fieldA in sl1.fields():
                self.assertIsInstance(fieldA, QgsField)
                a = sl_read1.fields().lookupField(fieldA.name())
                self.assertTrue(a >= 0)
                fieldB = sl_read1.fields().at(a)
                self.assertIsInstance(fieldB, QgsField)
                #if fieldA.type() != fieldB.type():
                #    s  = ""
                #self.assertEqual(fieldA.type(), fieldB.type())




            sl_read2 = SpectralLibrary.readFrom(pathHdr, progressDialog=QProgressDialog())
            self.assertIsInstance(sl_read2, SpectralLibrary)

            print(sl_read1)

            self.assertTrue(len(sl_read1) > 0)
            self.assertEqual(sl_read1, sl_read2)
            nWritten += len(sl_read1)

        self.assertEqual(len(sl1), nWritten, msg='Written and restored {} instead {}'.format(nWritten, len(sl1)))

        # addresses issue #11:
        # No error is generated when trying (by accident) to read the ENVI header file instead of the .sli/.esl file itself.


        pathHdr = os.path.splitext(speclibpath)[0]+'.hdr'
        self.assertTrue(os.path.isfile(pathHdr))
        sl1 = SpectralLibrary.readFrom(speclibpath, progressDialog=QProgressDialog())
        sl2 = SpectralLibrary.readFrom(pathHdr, progressDialog=QProgressDialog())
        self.assertIsInstance(sl1, SpectralLibrary)
        self.assertTrue(len(sl1) > 0)

        for p1, p2 in zip(sl1[:], sl2[:]):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertEqual(p1, p2)



    def test_ENVILabeled(self):

        from qpstestdata import speclib_labeled as pathESL
        from qps import registerEditorWidgets
        from qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as RasterClassificationKey
        registerEditorWidgets()


        sl1 = EnviSpectralLibraryIO.readFrom(pathESL, progressDialog=QProgressDialog())

        self.assertIsInstance(sl1, SpectralLibrary)
        p0 = sl1[0]
        self.assertIsInstance(p0, SpectralProfile)
        self.assertEqual(sl1.fieldNames(), ['fid', 'name', 'source', 'values', 'level_1', 'level_2', 'level_3'])


        setupTypes = []
        setupConfigs = []
        for i in range(sl1.fields().count()):
            setup = sl1.editorWidgetSetup(i)
            self.assertIsInstance(setup, QgsEditorWidgetSetup)
            setupTypes.append(setup.type())
            setupConfigs.append(setup.config())


        classValueFields = ['level_1', 'level_2', 'level_3']
        for name in classValueFields:
            i = sl1.fields().indexFromName(name)
            self.assertEqual(setupTypes[i], RasterClassificationKey)

        sl = SpectralLibrary()
        sl.startEditing()
        sl.addSpeclib(sl1)
        self.assertTrue(sl.commitChanges())

        for name in classValueFields:
            i = sl.fields().indexFromName(name)
            j = sl1.fields().indexFromName(name)
            self.assertTrue(i > 0)
            self.assertTrue(j > 0)
            setupNew = sl.editorWidgetSetup(i)
            setupOld = sl1.editorWidgetSetup(j)
            self.assertEqual(setupOld.type(), RasterClassificationKey)
            self.assertEqual(setupNew.type(), RasterClassificationKey,
                             msg='EditorWidget type is "{}" not "{}"'.format(setupNew.type(), setupOld.type()))

        sl = SpectralLibrary()
        sl.startEditing()
        sl.addSpeclib(sl1, copyEditorWidgetSetup=False)
        self.assertTrue(sl.commitChanges())

        for name in classValueFields:
            i = sl.fields().indexFromName(name)
            j = sl1.fields().indexFromName(name)
            self.assertTrue(i > 0)
            self.assertTrue(j > 0)
            setupNew = sl.editorWidgetSetup(i)
            setupOld = sl1.editorWidgetSetup(j)
            self.assertEqual(setupOld.type(), RasterClassificationKey)
            self.assertNotEqual(setupNew.type(), RasterClassificationKey)


if __name__ == '__main__':
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)



