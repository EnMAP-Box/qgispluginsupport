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
from qps.testing import initQgisApplication
SHOW_GUI = False
QGIS_APP = initQgisApplication()
from qps.utils import *

from enmapboxtestdata import enmap


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



    def test_spatialObjects(self):

        pt1 = SpatialPoint('EPSG:4326', 300,300)
        self.assertIsInstance(pt1, SpatialPoint)
        d = pickle.dumps(pt1)
        pt2 = pickle.loads(d)


        self.assertEqual(pt1, pt2)


    def test_gdalDataset(self):

        ds1 = gdalDataset(enmap)
        self.assertIsInstance(ds1, gdal.Dataset)
        ds2 = gdalDataset(ds1)
        self.assertEqual(ds1, ds2)


    def test_bandNames(self):

        validSources = [QgsRasterLayer(self.wmsUri,'', 'wms'),enmap, QgsRasterLayer(enmap), gdal.Open(enmap)]

        for src in validSources:
            names = displayBandNames(src, leadingBandNumber=True)
            self.assertIsInstance(names, list, msg='Unable to derive band names from {}'.format(src))
            self.assertTrue(len(names) > 0)


    def test_coordinateTransformations(self):

        ds = gdalDataset(enmap)
        lyr = QgsRasterLayer(enmap)

        self.assertEqual(ds.GetGeoTransform(), layerGeoTransform(lyr))

        self.assertIsInstance(ds, gdal.Dataset)
        self.assertIsInstance(lyr, QgsRasterLayer)
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        #self.assertTrue(crs.isValid())

        geoCoordinate = QgsPointXY(gt[0], gt[3])
        pxCoordinate = geo2px(geoCoordinate, gt)
        pxCoordinate2 = geo2px(geoCoordinate, lyr)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinate)

        self.assertEqual(pxCoordinate, pxCoordinate2)

        spatialPoint = SpatialPoint(crs, geoCoordinate)
        pxCoordinate = geo2px(spatialPoint, gt)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinate)


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


if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



