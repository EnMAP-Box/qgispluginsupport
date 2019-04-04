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

import unittest, pickle
from qgis import *
from qgis.core import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from osgeo import gdal, ogr, osr
from qps.testing import initQgisApplication, TestObjects
SHOW_GUI = False and os.environ.get('CI') is None
QGIS_APP = initQgisApplication()
from qps.utils import *




class testClassUtils(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        self.w = QMainWindow()
        self.cw = QWidget()
        self.cw.setLayout(QVBoxLayout())
        self.w.setCentralWidget(self.cw)
        self.w.show()
        self.menuBar = self.w.menuBar()
        self.menuA = self.menuBar.addMenu('Menu A')
        self.wmsUri = r'crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'
        self.wfsUri = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' typename=''fis:re_postleit'' url=''http://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' version=''auto'''

    def tearDown(self):
        self.w.close()


    def test_loadformClasses(self):

        import qps
        sources = list(file_search(dn(qps.__file__), '*.ui', recursive=True))
        for pathUi in sources[4:5]:
            print('Test "{}"'.format(pathUi))
            t = loadUIFormClass(pathUi)
            self.assertIsInstance(t, object)


    def test_file_search(self):


        rootQps = os.path.join(os.path.dirname(__file__), *['..','qps'])
        self.assertTrue(os.path.isdir(rootQps))

        results = list(file_search(rootQps, 'spectrallibraries.py', recursive=False))
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) == 0)

        for pattern in ['spectrallibraries.py', 'spectrallib*.py', re.compile(r'spectrallibraries\.py')]:

            results = list(file_search(rootQps, pattern, recursive=True))
            self.assertIsInstance(results, list)
            self.assertTrue(len(results) == 1)
            self.assertTrue(os.path.isfile(results[0]))

        results = list(file_search(rootQps, 'speclib', directories=True, recursive=True))
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) == 1)
        self.assertTrue(os.path.isdir(results[0]))


    def test_vsimem(self):

        from qps.utils import check_vsimem

        b = check_vsimem()
        self.assertIsInstance(b, bool)


    def test_spatialObjects(self):

        pt1 = SpatialPoint('EPSG:4326', 300,300)
        self.assertIsInstance(pt1, SpatialPoint)
        d = pickle.dumps(pt1)
        pt2 = pickle.loads(d)


        self.assertEqual(pt1, pt2)


    def test_gdalDataset(self):

        ds = TestObjects.inMemoryImage()
        path = ds.GetFileList()[0]
        ds1 = gdalDataset(path)
        self.assertIsInstance(ds1, gdal.Dataset)
        ds2 = gdalDataset(ds1)
        self.assertEqual(ds1, ds2)


    def test_bandNames(self):

        ds = TestObjects.inMemoryImage()
        pathRaster = ds.GetFileList()[0]

        validSources = [QgsRasterLayer(self.wmsUri, '', 'wms'),
                        pathRaster,
                        QgsRasterLayer(pathRaster),
                        gdal.Open(pathRaster)]

        for src in validSources:
            names = displayBandNames(src, leadingBandNumber=True)
            self.assertIsInstance(names, list, msg='Unable to derive band names from {}'.format(src))
            self.assertTrue(len(names) > 0)


    def test_coordinateTransformations(self):

        ds = TestObjects.inMemoryImage(300, 500)
        lyr = QgsRasterLayer(ds.GetFileList()[0])

        self.assertEqual(ds.GetGeoTransform(), layerGeoTransform(lyr))

        self.assertIsInstance(ds, gdal.Dataset)
        self.assertIsInstance(lyr, QgsRasterLayer)
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        self.assertTrue(crs.isValid())

        geoCoordinateUL = QgsPointXY(gt[0], gt[3])
        shiftToCenter = QgsVector(gt[1]*0.5, gt[5]*0.5)
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

    def test_appendItemsToMenu(self):

        B = QMenu()
        action = B.addAction('Do something')

        appendItemsToMenu(self.menuA, B)

        self.assertTrue(action in self.menuA.children())


    def test_value2string(self):

        valueSet = [[1,2,3],
                        1,
                        '',
                        None,
                        np.zeros((3,3,))
                        ]

        for i, values in enumerate(valueSet):
            print('Test {}:{}'.format(i+1, values))
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



if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()

QGIS_APP.quit()

