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
import xmlrunner

from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import TestObjects, TestCase

from qpstestdata import enmap, landcover
from qpstestdata import speclib as speclibpath

from qps.speclib.io.vectorsources import *
from qps.speclib.io.csvdata import *
from qps.speclib.io.envi import *
from qps.speclib.io.rastersources import *

from qps.utils import *
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


    def test_VSI(self):

        slib1 = TestObjects.createSpectralLibrary()
        path = slib1.source()
        feedback = self.createProcessingFeedback()
        slib2 = SpectralLibrary.readFrom(path, feedback=feedback)
        self.assertIsInstance(slib2, SpectralLibrary)

        s = ""

    def test_jsonIO(self):

        slib = TestObjects.createSpectralLibrary()
        pathJSON = tempfile.mktemp(suffix='.json', prefix='tmpSpeclib')

        # no additional info, no JSON file
        # slib.writeJSONProperties(pathJSON)
        # self.assertFalse(os.path.isfile(pathJSON))

        # add categorical info
        slib.startEditing()
        slib.addAttribute(QgsField('class1', QVariant.String, 'varchar'))
        slib.addAttribute(QgsField('class2', QVariant.Int, 'int'))
        slib.commitChanges()
        slib.startEditing()

        from qps.classification.classificationscheme import ClassificationScheme, ClassInfo, EDITOR_WIDGET_REGISTRY_KEY, \
            classSchemeToConfig

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

        slib.setEditorWidgetSetup(idx1, QgsEditorWidgetSetup('', {}))
        slib.setEditorWidgetSetup(idx2, QgsEditorWidgetSetup('', {}))
        data = slib.readJSONProperties(pathJSON)
        s = ""

    @unittest.skip('CSV driver needs new SpectralLibraryIO')
    def test_CSV2(self):
        from qpstestdata import speclib
        from qps.speclib.io.csvdata import CSVSpectralLibraryIO
        feedback = self.createProcessingFeedback()
        SLIB = SpectralLibrary.readFrom(speclib, feedback=feedback)
        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')

        CSVSpectralLibraryIO.write(SLIB, pathCSV, feedback=feedback)

        self.assertTrue(os.path.isfile(pathCSV))
        dialect = CSVSpectralLibraryIO.canRead(pathCSV)
        self.assertTrue(dialect is not None)
        speclib2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, feedback=feedback)
        self.assertTrue(len(SLIB) == len(speclib2))
        for i, (p1, p2) in enumerate(zip(SLIB[:], speclib2[:])):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            if p1 != p2:
                s = ""
            self.assertEqual(p1, p2)

        SLIB = TestObjects.createSpectralLibrary()
        # pathCSV = os.data_source.join(os.data_source.dirname(__file__), 'speclibcvs2.out.csv')
        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        print(pathCSV)
        CSVSpectralLibraryIO.write(SLIB, pathCSV, feedback=feedback)

        self.assertTrue(os.path.isfile(pathCSV))
        dialect = CSVSpectralLibraryIO.canRead(pathCSV)
        self.assertTrue(dialect is not None)
        speclib2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, feedback=feedback)
        self.assertTrue(len(SLIB) == len(speclib2))
        for i, (p1, p2) in enumerate(zip(SLIB[:], speclib2[:])):
            self.assertIsInstance(p1, SpectralProfile)
            self.assertIsInstance(p2, SpectralProfile)
            self.assertEqual(p1.xValues(), p2.xValues())
            self.assertEqual(p1.yValues(), p2.yValues())
            if p1 != p2:
                s = ""
            self.assertEqual(p1, p2)

        # self.assertEqual(SLIB, speclib2)

        # addresses issue #8
        from qpstestdata import speclib
        SL1 = SpectralLibrary.readFrom(speclib, feedback=feedback)
        self.assertIsInstance(SL1, SpectralLibrary)

        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        print(pathCSV)
        for dialect in [pycsv.excel_tab, pycsv.excel]:
            pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
            CSVSpectralLibraryIO.write(SL1, pathCSV, dialect=dialect, feedback=feedback)
            d = CSVSpectralLibraryIO.canRead(pathCSV)
            self.assertEqual(d, dialect)
            SL2 = CSVSpectralLibraryIO.readFrom(pathCSV, dialect=dialect, feedback=feedback)
            self.assertIsInstance(SL2, SpectralLibrary)
            self.assertTrue(len(SL1) == len(SL2))

            for p1, p2 in zip(SL1[:], SL2[:]):
                self.assertIsInstance(p1, SpectralProfile)
                self.assertIsInstance(p2, SpectralProfile)
                if p1 != p2:
                    s = ""
                self.assertEqual(p1, p2)

        # addresses issue #8 loading modified CSV values

        SL = SpectralLibrary.readFrom(speclib, feedback=feedback)

        pathCSV = tempfile.mktemp(suffix='.csv', prefix='tmpSpeclib')
        CSVSpectralLibraryIO.write(SL, pathCSV, feedback=feedback)

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

        SL2 = CSVSpectralLibraryIO.readFrom(pathCSV, feedback=feedback)

        self.assertEqual(len(SL), len(SL2))

        for p in SL2:
            self.assertIsInstance(p, SpectralProfile)
            self.assertEqual(p.yValues()[0], 42)
            self.assertEqual(p.yValues()[99], 42)


    @unittest.skip('EcoSIS driver needs refactoring')
    def test_EcoSIS(self):

        feedback = QgsProcessingFeedback()

        from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
        from qpstestdata import speclib
        self.assertFalse(EcoSISSpectralLibraryIO.canRead(speclib))

        # 1. read
        from qpstestdata import DIR_ECOSIS
        for path in file_search(DIR_ECOSIS, '*.csv'):
            print('Read {}...'.format(path))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(path), msg='Unable to read {}'.format(path))
            sl = EcoSISSpectralLibraryIO.readFrom(path, feedback=feedback)
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
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, feedback=QProgressDialog())
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, feedback=None)
        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(p))

            slPart = EcoSISSpectralLibraryIO.readFrom(p, feedback=QProgressDialog())
            self.assertIsInstance(slPart, SpectralLibrary)

            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)

    @unittest.skip('SPECCHIO driver needs refactoring')
    def test_SPECCHIO(self):

        from qps.speclib.io.specchio import SPECCHIOSpectralLibraryIO

        # 1. read
        from qpstestdata import DIR_SPECCHIO
        for path in reversed(list(file_search(DIR_SPECCHIO, '*.csv'))):

            self.assertTrue(SPECCHIOSpectralLibraryIO.canRead(path))
            sl = SPECCHIOSpectralLibraryIO.readFrom(path, feedback=QProgressDialog())
            self.assertIsInstance(sl, SpectralLibrary)
            self.assertTrue(len(sl) > 0)
            for p in sl:
                self.assertIsInstance(p, SpectralProfile)
                self.assertListEqual(p.xValues(), sorted(p.xValues()))
        # 2. write
        speclib = TestObjects.createSpectralLibrary(50, n_empty=1)
        pathCSV = os.path.join(TEST_DIR, 'speclib.specchio.csv')
        csvFiles = SPECCHIOSpectralLibraryIO.write(speclib, pathCSV, feedback=QProgressDialog())

        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(SPECCHIOSpectralLibraryIO.canRead(p))

            slPart = SPECCHIOSpectralLibraryIO.readFrom(p, feedback=QProgressDialog())
            self.assertIsInstance(slPart, SpectralLibrary)
            for p in slPart:
                self.assertIsInstance(p, SpectralProfile)
                self.assertListEqual(p.xValues(), sorted(p.xValues()))

            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)

    @unittest.skip('needs SpectralLibraryIO for vector layers')
    def test_speclib2vector(self):

        testDir = self.createTestOutputDirectory() / 'speclib2vector'
        os.makedirs(testDir, exist_ok=True)

        from qps.speclib.io.vectorsources import VectorSourceSpectralLibraryIO

        slib = TestObjects.createSpectralLibrary(2, n_bands=[-1, 3, 24])
        self.assertIsInstance(slib, SpectralLibrary)
        self.assertTrue(len(slib) == 6)

        extensions = ['.json', '.geojson', '.geojsonl', '.csv', '.gpkg']

        hasLIBKML = isinstance(ogr.GetDriverByName('LIBKML'), ogr.Driver)
        if hasLIBKML:
            extensions.append('.kml')

        for ext in extensions:
            print('Test vector file type {}'.format(ext))
            path = testDir / f'speclib_{ext[1:]}{ext}'

            if ext == '.kml':
                s = ""

            # write
            writtenFiles = VectorSourceSpectralLibraryIO.write(slib, path, feedback=QProgressDialog())
            self.assertTrue(len(writtenFiles) == 1)


            # read
            file = writtenFiles[0]
            self.assertTrue(VectorSourceSpectralLibraryIO.canRead(file),
                            msg='Failed to read speclib from {}'.format(file))
            sl = VectorSourceSpectralLibraryIO.readFrom(file, feedback=QProgressDialog())
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

    def test_ARTMO(self):

        from qpstestdata import DIR_ARTMO

        p = os.path.join(DIR_ARTMO, 'directional_reflectance.txt')

        from qps.speclib.io.artmo import ARTMOSpectralLibraryIO

        self.assertTrue(ARTMOSpectralLibraryIO.canRead(p))
        pd = QProgressDialog()
        sl = ARTMOSpectralLibraryIO.readFrom(p, feedback=pd)

        self.assertIsInstance(sl, SpectralLibrary)
        self.assertEqual(len(sl), 10)


    def test_enmapbox_issue_463(self):
        # see https://bitbucket.org/hu-geomatics/enmap-box/issues/463/string-attributes-not-correctly-imported
        # for details

        TESTDATA = pathlib.Path(r'D:\Repositories\enmap-box\enmapboxtestdata')

        landcover_points = TESTDATA / 'landcover_berlin_point.shp'
        enmap = TESTDATA / 'enmap_berlin.bsq'

        if os.path.isfile(landcover_points) and os.path.isfile(enmap):
            lyrV = QgsVectorLayer(landcover_points.as_posix())
            lyrR = QgsRasterLayer(enmap.as_posix())

            slib = SpectralLibrary.readFromVector(lyrV, lyrR,
                                                  copy_attributes=True,
                                                  name_field='level_1',
                                                  )

            for profile in slib:
                value = profile.attribute('level_2')
                self.assertIsInstance(value, str)
                self.assertTrue(len(value) > 0)

            # test speed by
            uri = '/vsimem/temppoly.gpkg'
            drv: ogr.Driver = ogr.GetDriverByName('GPKG')
            ds: ogr.DataSource = drv.CreateDataSource(uri)

            lyr: ogr.Layer = ds.CreateLayer('polygon',
                                            srs=osrSpatialReference(lyrR.crs()),
                                            geom_type=ogr.wkbPolygon)

            pd = QProgressDialog()

            f = ogr.Feature(lyr.GetLayerDefn())
            ext = SpatialExtent.fromLayer(lyrR)
            g = ogr.CreateGeometryFromWkt(ext.asWktPolygon())
            f.SetGeometry(g)
            lyr.CreateFeature(f)
            ds.FlushCache()

            t0 = datetime.datetime.now()
            slib = SpectralLibrary.readFromVector(uri, lyrR, progress_handler=pd)
            self.assertIsInstance(slib, SpectralLibrary)
            dt = datetime.datetime.now() - t0
            print(f'Loaded {len(slib)} speclib profiles in {dt}')

            self.assertTrue(pd.value() == -1)

            pd.setValue(0)

            t0 = datetime.datetime.now()
            profiles = SpectralLibrary.readFromVector(uri, lyrR, return_profile_list=True)

            self.assertIsInstance(profiles, list)
            dt = datetime.datetime.now() - t0
            print(f'Loaded {len(profiles)} profiles in {dt}')
            s = ""

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

        feedback = self.createProcessingFeedback()
        sl1 = SpectralLibrary.readFrom(binarypath, feedback=feedback)
        sl2 = SpectralLibrary.readFrom(headerPath, feedback=feedback)

        self.assertTrue(len(sl1) == len(sl2))

        # this should fail

        pathWrong = enmap
        hdr, bin = findENVIHeader(pathWrong)
        self.assertTrue((hdr, bin) == (None, None))


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
