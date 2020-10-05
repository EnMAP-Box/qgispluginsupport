# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
import pickle
import xml.etree.ElementTree as ET
from qgis import *
from qgis.core import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.Qt import *
from qgis.PyQt.QtCore import *
from osgeo import gdal, ogr, osr
from qps.testing import TestObjects

from qps.utils import *
from qps.testing import TestCase


class TestUtils(TestCase):
    def setUp(self):
        super().setUp()

        self.wmsUri = r'crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'
        self.wfsUri = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' typename=''fis:re_postleit'' url=''http://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' version=''auto'''

    def tearDown(self):

        super().tearDown()

    def test_loadUi(self):

        import qps
        sources = list(file_search(dn(qps.__file__), '*.ui', recursive=True))
        sources = [s for s in sources if not 'pyqtgraph' in s]
        sources = [s for s in sources if not 'externals' in s]

        for pathUi in sources:
            tree = ET.parse(pathUi)
            root = tree.getroot()
            self.assertEqual(root.tag, 'ui')
            baseClass = root.find('widget').attrib['class']

            print('Try to load {} as {}'.format(pathUi, baseClass))
            self.assertIsInstance(baseClass, str)

            if baseClass == 'QDialog':
                class TestWidget(QDialog):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)

            elif baseClass == 'QWidget':
                class TestWidget(QWidget):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)

            elif baseClass == 'QMainWindow':
                class TestWidget(QMainWindow):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            elif baseClass == 'QDockWidget':
                class TestWidget(QDockWidget):
                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            else:
                warnings.warn('BaseClass {} not implemented\nto test {}'.format(baseClass, pathUi), Warning)
                continue

            w = None
            try:
                w = TestWidget()
                s = ""

            except Exception as ex:
                info = 'Failed to load {}'.format(pathUi)
                info += '\n' + str(ex)
                self.fail(info)

    def test_gdal_filesize(self):

        DIR_VRT_STACK = r'Q:\Processing_BJ\99_OSARIS_Testdata\Loibl-2019-OSARIS-Ala-Archa\BJ_VRT_Stacks'

        if os.path.isdir(DIR_VRT_STACK):
            for path in file_search(DIR_VRT_STACK, '*.vrt'):
                size = gdalFileSize(path)
                self.assertTrue(size > 0)

    def test_findmaplayerstores(self):

        ref = [QgsProject.instance(), QgsMapLayerStore(), QgsMapLayerStore()]

        found = list(findMapLayerStores())
        self.assertTrue(len(ref) <= len(found))
        for s in found:
            self.assertIsInstance(s, (QgsProject, QgsMapLayerStore))
        for s in ref:
            self.assertTrue(s in found)

    def test_findwavelength(self):
        from qpstestdata import enmap

        lyr = TestObjects.createRasterLayer()
        paths = [lyr.source(),
                 r'J:\diss_bj\level2\s-america\X0048_Y0029\20160624_LEVEL2_SEN2A_BOA.tif',
                 r'J:\diss_bj\level2\s-america\X0048_Y0029\20180721_LEVEL2_LND08_BOA.tif',
                 ]
        for p in paths:
            if os.path.isfile(p):
                ds = gdal.Open(p)
                self.assertIsInstance(ds, gdal.Dataset)
                wl, wlu = parseWavelength(ds)
                self.assertIsInstance(wl, np.ndarray)
                self.assertTrue(len(wl), ds.RasterCount)
                self.assertIsInstance(wlu, str)

    def test_file_search(self):

        rootQps = pathlib.Path(__file__).parents[1]
        self.assertTrue(rootQps.is_dir())

        results = list(file_search(rootQps, 'test_utils.py', recursive=False))
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) == 0)

        for pattern in ['test_utils.py', 'test_utils*.py', re.compile(r'test_utils\.py')]:
            results = list(file_search(rootQps, pattern, recursive=True))
            self.assertIsInstance(results, list)
            self.assertTrue(len(results) == 1)
            self.assertTrue(os.path.isfile(results[0]))

    def test_vsimem(self):

        from qps.utils import check_vsimem

        b = check_vsimem()
        self.assertIsInstance(b, bool)

    def test_spatialObjects(self):

        pt1 = SpatialPoint('EPSG:4326', 300, 300)
        self.assertIsInstance(pt1, SpatialPoint)
        d = pickle.dumps(pt1)
        pt2 = pickle.loads(d)
        self.assertEqual(pt1, pt2)

        doc = QDomDocument('qps')
        node = doc.createElement('POINT_NODE')
        pt1.writeXml(node, doc)
        pt3 = SpatialPoint.readXml(node)

        self.assertEqual(pt1, pt3)

        ext1 = SpatialExtent('EPSG:4326', QgsPointXY(0, 0), QgsPointXY(10, 20))
        d = pickle.dumps(ext1)
        ext2 = pickle.loads(d)
        self.assertEqual(ext1, ext2)

        node = doc.createElement('EXTENT_NODE')
        ext1.writeXml(node, doc)
        ext2 = SpatialExtent.readXml(node)
        self.assertEqual(ext1, ext2)

    def createTestOutputDirectory(self, name: str = 'test-outputs') -> pathlib.Path:

        DIR = super().createTestOutputDirectory(name) / 'utils'
        os.makedirs(DIR, exist_ok=True)
        return DIR

    def test_fid2pixelIndices(self):

        # create test datasets
        from qpstestdata import enmap_pixel, landcover, enmap, enmap_polygon
        rl = QgsRasterLayer(enmap)
        vl = QgsVectorLayer(enmap_pixel)

        DIR_TEST = self.createTestOutputDirectory()
        burned, no_data = fid2pixelindices(rl, vl,
                                           layer=vl.dataProvider().subLayers()[0].split('!!::!!')[1],
                                           all_touched=True)

        self.assertIsInstance(no_data, int)

        pathDst = DIR_TEST / 'fid2{}.tif'.format(pathlib.Path(vl.source().split('|')[0]).name)

        gdal_array.SaveArray(burned, pathDst.as_posix(), prototype=enmap)
        self.assertIsInstance(burned, np.ndarray)
        fidsA = set(vl.allFeatureIds())
        fidsB = set([fid for fid in np.unique(burned) if fid != no_data])
        self.assertEqual(fidsA, fidsB)
        self.assertEqual(burned.shape[1], rl.width())
        self.assertEqual(burned.shape[0], rl.height())

    def test_block_size(self):

        ds = TestObjects.createRasterDataset(200, 300, 100, eType=gdal.GDT_Int16)

        for cache in [10,
                      2 * 100,
                      10 * 2 ** 20,
                      100 * 2 ** 20]:
            bs = optimize_block_size(ds, cache=cache)
            self.assertIsInstance(bs, list)
            self.assertTrue(len(bs) == 2)
            self.assertTrue(0 < bs[0] <= ds.RasterXSize)
            self.assertTrue(0 < bs[1] <= ds.RasterYSize)
            s = ""

    def test_osrSpatialReference(self):

        for input in ['EPSG:32633',
                      QgsCoordinateReferenceSystem('EPSG:32633')
                      ]:
            srs = osrSpatialReference(input)
            self.assertIsInstance(srs, osr.SpatialReference)
            self.assertTrue(srs.Validate() == ogr.OGRERR_NONE)

    def test_geo_coordinates(self):

        lyrR = TestObjects.createRasterLayer()

        gx1, gy1 = px2geocoordinates(lyrR)
        gx2, gy2 = px2geocoordinates(lyrR, 'EPSG:4326')
        s = ""

    def test_gdalDataset(self):

        ds = TestObjects.createRasterDataset()
        path = ds.GetDescription()
        ds1 = gdalDataset(path)
        self.assertIsInstance(ds1, gdal.Dataset)
        ds2 = gdalDataset(ds1)
        self.assertEqual(ds1, ds2)

    def test_maplayers(self):

        lyr = TestObjects.createRasterLayer()

        url = QUrl.fromLocalFile(lyr.source())

        inputs = [lyr, lyr.source(), gdal.Open(lyr.source()), url]

        for source in inputs:
            l = qgsRasterLayer(source)
            self.assertIsInstance(l, QgsRasterLayer)

    def test_UnitLookup(self):

        for u in ['nm', 'm', 'km', 'um', 'μm', u'μm']:
            self.assertTrue(UnitLookup.isMetricUnit(u), msg='Not detected as metric unit:{}'.format(u))
            bu = UnitLookup.baseUnit(u)
            self.assertIsInstance(bu, str)
            self.assertTrue(len(bu) > 0)

    def test_bandNames(self):

        ds = TestObjects.createRasterDataset()
        pathRaster = ds.GetDescription()

        validSources = [QgsRasterLayer(self.wmsUri, '', 'wms'),
                        pathRaster,
                        QgsRasterLayer(pathRaster),
                        gdal.Open(pathRaster)]

        for src in validSources:
            names = displayBandNames(src, leadingBandNumber=True)
            self.assertIsInstance(names, list, msg='Unable to derive band names from {}'.format(src))
            self.assertTrue(len(names) > 0)

    def test_coordinateTransformations(self):

        ds = TestObjects.createRasterDataset(300, 500)
        lyr = QgsRasterLayer(ds.GetDescription())

        self.assertEqual(ds.GetGeoTransform(), layerGeoTransform(lyr))

        self.assertIsInstance(ds, gdal.Dataset)
        self.assertIsInstance(lyr, QgsRasterLayer)
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        self.assertTrue(crs.isValid())

        geoCoordinateUL = QgsPointXY(gt[0], gt[3])
        shiftToCenter = QgsVector(gt[1] * 0.5, gt[5] * 0.5)
        geoCoordinateCenter = geoCoordinateUL + shiftToCenter
        pxCoordinate = geo2px(geoCoordinateUL, gt)
        pxCoordinate2 = geo2px(geoCoordinateUL, lyr)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinateCenter)

        self.assertEqual(pxCoordinate, pxCoordinate2)

        spatialPoint = SpatialPoint(crs, geoCoordinateUL)
        pxCoordinate = geo2px(spatialPoint, gt)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinateUL + shiftToCenter)

    def test_createQgsField(self):

        values = [1, 2.3, 'text',
                  np.int8(1),
                  np.int16(1),
                  np.int32(1),
                  np.int64(1),
                  np.uint8(1),
                  np.uint(1),
                  np.uint16(1),
                  np.uint32(1),
                  np.uint64(1),
                  np.float(1),
                  np.float16(1),
                  np.float32(1),
                  np.float64(1),
                  ]

        for v in values:
            print('Create QgsField for {}'.format(type(v)))
            field = createQgsField('field', v)
            self.assertIsInstance(field, QgsField)

    def test_convertMetricUnits(self):

        self.assertEqual(convertMetricUnit(100, 'm', 'km'), 0.1)
        self.assertEqual(convertMetricUnit(0.1, 'km', 'm'), 100)

        self.assertEqual(convertMetricUnit(400, 'nm', 'μm'), 0.4)
        self.assertEqual(convertMetricUnit(0.4, 'μm', 'nm'), 400)

        self.assertEqual(convertMetricUnit(400, 'nm', 'km'), 4e-10)

    def test_decimalYearConversions(self):
        baseDate = np.datetime64('2020-01-01')
        for seconds in range(0, 200000, 13):
            dateA = baseDate + np.timedelta64(seconds, 's')
            decimalDate = convertDateUnit(dateA, 'DecimalYear')
            DOY = convertDateUnit(decimalDate, 'DOY')
            self.assertTrue(DOY >= 1)

            is_leap_year = calendar.isleap(dateA.astype(object).year)
            if is_leap_year:
                self.assertTrue(DOY <= 366)
            else:
                self.assertTrue(DOY <= 365)

            self.assertIsInstance(decimalDate, float)
            dateB = datetime64(decimalDate)
            self.assertIsInstance(dateB, np.datetime64)
            self.assertEqual(dateA, dateB)

        for days in range(0, 5000):
            dateA = baseDate + np.timedelta64(days, 'D')
            decimalDate = convertDateUnit(dateA, 'DecimalYear')
            self.assertIsInstance(decimalDate, float)
            dateB = datetime64(decimalDate)
            self.assertIsInstance(dateB, np.datetime64)
            self.assertEqual(dateA, dateB)

    def test_convertTimeUnits(self):

        refDate = np.datetime64('2020-01-01')
        self.assertEqual(datetime64(refDate), refDate)  ## datetime64 to datetime64
        self.assertEqual(datetime64('2020-01-01'), refDate)  # string to datetime64
        self.assertEqual(datetime64(QDate(2020, 1, 1, )), refDate)
        self.assertEqual(datetime64(QDateTime(2020, 1, 1, 0, 0)), refDate)
        self.assertEqual(datetime64(datetime.date(year=2020, month=1, day=1)), refDate)
        self.assertEqual(datetime64(datetime.datetime(year=2020, month=1, day=1)), refDate)
        self.assertEqual(datetime64(2020), refDate)  # decimal year to datetime64

        date_arrays = [np.asarray(['2020-01-01', '2019-01-01'], dtype=np.datetime64),
                       np.asarray([2020, 2019]),
                       np.asarray([2020.023, 2019.023]),
                       ]
        for array in date_arrays:
            dpy = days_per_year(array)
            self.assertIsInstance(dpy, np.ndarray)
            self.assertTrue(np.array_equal(dpy, np.asarray([366, 365])))

        leap_years = [2020,
                      2020.034,
                      np.datetime64('2020', 'Y'),
                      datetime.date(year=2020, month=1, day=1),
                      datetime.date(year=2020, month=12, day=31),
                      datetime.datetime(year=2020, month=1, day=1, hour=0, minute=0, second=0),
                      datetime.datetime(year=2020, month=12, day=31, hour=23, minute=59, second=59)
                      ]
        non_leap_years = [2019,
                          2019.034,
                          np.datetime64('2019', 'Y'),
                          datetime.date(year=2019, month=1, day=1),
                          datetime.date(year=2019, month=12, day=31),
                          datetime.datetime(year=2019, month=1, day=1, hour=0, minute=0, second=0),
                          datetime.datetime(year=2019, month=12, day=31, hour=23, minute=59, second=59)
                          ]

        for y in leap_years:
            dpy = days_per_year(y)
            if not dpy == 366:
                s = ""
            self.assertEqual(dpy, 366)

        for y in non_leap_years:
            dpy = days_per_year(y)
            self.assertEqual(dpy, 365)

        self.assertEqual(convertDateUnit('2020-01-01', 'DOY'), 1)
        self.assertEqual(convertDateUnit('2020-12-31', 'DOY'), 366)
        self.assertEqual(convertDateUnit('2020-12-31', 'Y'), 2020)

        self.assertEqual(convertDateUnit('2019-01-01', 'DOY'), 1)
        self.assertEqual(convertDateUnit('2019-12-31', 'DOY'), 365)

        self.assertEqual(convertDateUnit('2019-01-01', 'M'), 1)
        self.assertEqual(convertDateUnit('2019-01-01', 'D'), 1)
        self.assertEqual(convertDateUnit('2019-07-08', 'M'), 7)
        self.assertEqual(convertDateUnit('2019-07-08', 'D'), 8)
        self.assertEqual(convertDateUnit('2019-07-08', 'Y'), 2019)

        for dtg in ['2019-01-01T00:00:00',
                    '2019-12-31T23:59:59',
                    '2020-01-01T00:00:00',
                    '2020-12-31T23:59:59']:

            dj0a = convertDateUnit(dtg, 'DecimalYear')
            dj0b = convertDateUnit(dtg, 'DecimalYear[365]')
            dj0c = convertDateUnit(dtg, 'DecimalYear[366]')

            year = np.datetime64(dtg).astype(object).year
            doy = int((np.datetime64(dtg) - np.datetime64('{:04}-01-01'.format(year)))
                      .astype('timedelta64[D]')
                      .astype(int)) + 1

            self.assertEqual(year, int(dj0a))

            if not calendar.isleap(year):
                self.assertEqual(dj0a, dj0b)
                self.assertEqual(int((dj0a - int(dj0a)) * 365 + 1), doy)

            else:
                self.assertEqual(dj0a, dj0c)
                self.assertEqual(int((dj0a - int(dj0a)) * 366 + 1), doy)

    def test_appendItemsToMenu(self):
        B = QMenu()

        action = B.addAction('Do something')
        menuA = QMenu()
        appendItemsToMenu(menuA, B)

        self.assertTrue(action in menuA.children())

    def test_value2string(self):

        valueSet = [[1, 2, 3],
                    1,
                    '',
                    None,
                    np.zeros((3, 3,))
                    ]

        for i, values in enumerate(valueSet):
            print('Test {}:{}'.format(i + 1, values))
            s = value2str(values, delimiter=';')
            self.assertIsInstance(s, str)

    def test_savefilepath(self):

        valueSet = ['dsdsds.png',
                    'foo\\\\\\?<>bar',
                    None,
                    r"_bound method TimeSeriesDatum.date of TimeSeriesDatum(2014-01-15,_class 'timeseriesviewer.timeseries.SensorInstrument'_ LS)_.Map View 1.png"
                    ]

        for i, text in enumerate(valueSet):
            s = filenameFromString(text)
            print('Test {}:"{}"->"{}"'.format(i + 1, text, s))
            self.assertIsInstance(s, str)

    def test_selectMapLayersDialog(self):

        lyrR = TestObjects.createRasterLayer()
        lyrV = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayers([lyrR, lyrV])
        d = SelectMapLayersDialog()
        d.addLayerDescription('Any Type', QgsMapLayerProxyModel.All)
        layers = d.mapLayers()
        self.assertIsInstance(layers, list)
        self.assertTrue(len(layers) == 1)
        self.assertListEqual(layers, [lyrR])

        d.addLayerDescription('A Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        d.addLayerDescription('A Raster Layer', QgsMapLayerProxyModel.RasterLayer)

        self.showGui(d)

    def test_defaultBands(self):

        ds = TestObjects.createRasterDataset(nb=10)
        self.assertIsInstance(ds, gdal.Dataset)

        self.assertListEqual([0, 1, 2], defaultBands(ds))
        self.assertListEqual([0, 1, 2], defaultBands(ds.GetDescription()))

        ds.SetMetadataItem('default bands', '{4,3,1}', 'ENVI')
        self.assertListEqual([4, 3, 1], defaultBands(ds))

        ds.SetMetadataItem('default_bands', '{4,3,1}', 'ENVI')
        self.assertListEqual([4, 3, 1], defaultBands(ds))

    def test_relativePath(self):

        refDir = '/data/foo/'
        absPath = '/data/foo/bar/file.txt'
        relPath = relativePath(absPath, refDir).as_posix()
        self.assertEqual(relPath, 'bar/file.txt')

        if os.sep == '\\':
            refDir = r'C:\data\foo'
            absPath = r'C:\data\foo\bar\file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath.as_posix(), 'bar/file.txt')

            refDir = r'D:\data\foo'
            absPath = r'C:\data\foo\bar\file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath, pathlib.Path(absPath))
        else:

            refDir = '/data/foo/bar/sub/sub/sub'
            absPath = '/data/foo/bar/file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath.as_posix(), '../../../file.txt')
        # self.assertEqual((pathlib.Path(refDir) / relPath).resolve(), pathlib.Path(absPath))

    def test_nextColor(self):

        c = QColor('#ff012b')
        for i in range(500):
            c = nextColor(c, mode='con')
            self.assertIsInstance(c, QColor)
            self.assertTrue(c.name() != '#000000')

        c = QColor('black')
        for i in range(500):
            c = nextColor(c, mode='cat')
            self.assertIsInstance(c, QColor)
            self.assertTrue(c.name() != '#000000')


if __name__ == "__main__":
    import xmlrunner

    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
