# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest

import numpy as np

from qgis.PyQt.QtCore import QVariant
from osgeo import gdal, ogr
from qgis.core import Qgis, QgsFields, QgsField
from qgis.core import QgsFeature, QgsGeometry, QgsWkbTypes
from qgis.core import QgsVectorLayer, QgsCoordinateReferenceSystem
from qps.speclib.core import create_profile_field
from qps.testing import TestObjects, start_app, TestCaseBase

start_app()


class TestCasesTestObject(TestCaseBase):

    def test_spectralProfiles(self):

        profiles = list(TestObjects.spectralProfiles(10))
        self.assertIsInstance(profiles, list)
        self.assertTrue(len(profiles) == 10)

    def test_EmptyMemoryLayer(self):

        fields = QgsFields()
        fields.append(QgsField('f1', QVariant.String))
        fields.append(QgsField('f2', QVariant.Double))
        fields.append(create_profile_field('profilesB', 'bytes'))
        fields.append(create_profile_field('profilesJ', 'json'))
        fields.append(create_profile_field('profilesS', 'text'))

        lyr = TestObjects.createEmptyMemoryLayer(fields)

        for i, name in enumerate(fields.names()):
            f1: QgsField = fields.at(i)
            f2: QgsField = lyr.fields().field(name)

            self.assertEqual(f1.name(), f2.name())
            self.assertEqual(f1.type(), f2.type())
            self.assertEqual(f1.editorWidgetSetup().type(), f2.editorWidgetSetup().type())

    def test_VectorLayers(self):

        ds = TestObjects.createVectorDataSet(wkb=ogr.wkbPoint)
        self.assertIsInstance(ds, ogr.DataSource)
        self.assertTrue(ds.GetLayerCount() == 1)
        lyr = ds.GetLayer(0)
        self.assertIsInstance(lyr, ogr.Layer)
        self.assertEqual(lyr.GetGeomType(), ogr.wkbPoint)
        self.assertTrue(lyr.GetFeatureCount() > 0)

        ds = TestObjects.createVectorDataSet(wkb=ogr.wkbLineString)
        self.assertIsInstance(ds, ogr.DataSource)
        self.assertTrue(ds.GetLayerCount() == 1)
        lyr = ds.GetLayer(0)
        self.assertIsInstance(lyr, ogr.Layer)

        self.assertTrue(lyr.GetFeatureCount() > 0)
        self.assertEqual(lyr.GetGeomType(), ogr.wkbLineString)

        geomTypes = [QgsWkbTypes.PointGeometry, QgsWkbTypes.Point,
                     QgsWkbTypes.LineGeometry, QgsWkbTypes.LineString,
                     QgsWkbTypes.PolygonGeometry, QgsWkbTypes.Polygon]
        for i, geomType in enumerate(geomTypes):
            lyr = TestObjects.createVectorLayer(geomType)
            self.assertIsInstance(lyr, QgsVectorLayer)
            if Qgis.versionInt() >= 33000:
                msg = f'Failed test {i + 1} to create layer of geometry type: {geomType} "{geomType.name}"'
            else:
                msg = f'Failed test {i + 1}'
            self.assertTrue(lyr.isValid(), msg=msg)

            self.assertIsInstance(lyr.crs(), QgsCoordinateReferenceSystem)
            self.assertTrue(lyr.crs().isValid())

            for f in lyr.getFeatures():
                f: QgsFeature
                g: QgsGeometry = f.geometry()
                self.assertFalse(g.isNull())
                self.assertFalse(g.isEmpty())
                self.assertTrue(g.isGeosValid(), msg=f'{f.id()} {f.attributeMap()}')

    def test_coredata(self):
        array, wl, wlu, gt, wkt = TestObjects.coreData()
        self.assertIsInstance(array, np.ndarray)
        self.assertIsInstance(wl, np.ndarray)
        self.assertTrue(len(wl) > 0)
        self.assertIsInstance(wlu, str)
        self.assertTrue(len(gt) == 6)
        self.assertIsInstance(wkt, str)

    def test_RasterData(self):

        cl = TestObjects.createRasterDataset(10, 20, nc=7)
        self.assertIsInstance(cl, gdal.Dataset)
        self.assertEqual(cl.RasterCount, 1)
        self.assertEqual(cl.RasterXSize, 10)
        self.assertEqual(cl.RasterYSize, 20)

        classNames = cl.GetRasterBand(1).GetCategoryNames()
        self.assertEqual(len(classNames), 7)

        ns = 250
        nl = 100
        nb = 10
        ds = TestObjects.createRasterDataset(ns, nl, nb=nb, eType=gdal.GDT_Float32)
        self.assertIsInstance(ds, gdal.Dataset)
        from qps.utils import parseWavelength
        wl, wlu = parseWavelength(ds)
        self.assertIsInstance(wl, np.ndarray)
        self.assertIsInstance(wlu, str)

        self.assertEqual(ds.RasterCount, nb)
        self.assertEqual(ds.RasterXSize, ns)
        self.assertEqual(ds.RasterYSize, nl)
        self.assertEqual(ds.GetRasterBand(1).DataType, gdal.GDT_Float32)

        dsSrc = TestObjects.createRasterDataset(100, 100, 1)
        woptions = gdal.WarpOptions(dstSRS='EPSG:4326')
        pathDst = '/vsimem/warpDest.tif'
        dsDst = gdal.Warp(pathDst, dsSrc, options=woptions)
        self.assertIsInstance(dsDst, gdal.Dataset)

    def test_Speclibs(self):

        slib = TestObjects.createSpectralLibrary(7)
        self.assertIsInstance(slib, QgsVectorLayer)
        self.assertTrue(len(slib) == 7)


if __name__ == "__main__":
    unittest.main(buffer=False)
