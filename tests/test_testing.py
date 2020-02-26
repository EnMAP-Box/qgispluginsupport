# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
from qgis.core import *
import unittest, pickle
import qgis.testing
import qps.testing
from osgeo import gdal, gdal_array, ogr, osr

class testClassTesting(unittest.TestCase):


    def test_init(self):

        import qps.testing
        self.assertTrue(qps.testing != None)

        qgis_app = qps.testing.start_app(options=qps.testing.StartOptions.All)

        from qgis.core import QgsApplication, QgsProcessingRegistry
        from qgis.gui import QgsGui
        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)

        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0, msg='Standard QgsEditorWidgetWrapper not initialized')

        app = QgsApplication.instance()
        ENV = app.systemEnvVars()
        for k in sorted(ENV.keys()):
            print('{}={}'.format(k, ENV[k]))

        qgis_app.quit()

    def test_init_minimal(self):
        import qps.testing
        from qgis.core import QgsApplication
        qgis_app = qps.testing.start_app(options=qps.testing.StartOptions.Minimized)

        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)
        qgis_app.quit()


class test_TestObject(qps.testing.TestCase):

    def test_spectralProfiles(self):

        from qps.testing import TestObjects

        profiles = list(TestObjects.spectralProfiles(10))
        self.assertIsInstance(profiles, list)
        self.assertTrue(len(profiles) == 10)


    def test_VectorLayers(self):

        from qps.testing import TestObjects, start_app
        from osgeo import ogr, osr

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


        lyr = TestObjects.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        self.assertIsInstance(lyr.crs(), QgsCoordinateReferenceSystem)
        self.assertTrue(lyr.crs().isValid())

    def test_RasterData(self):

        from qps.testing import TestObjects

        cl = TestObjects.createRasterDataset(10, 20, nc=7)
        self.assertIsInstance(cl, gdal.Dataset)
        self.assertEqual(cl.RasterCount, 1)
        self.assertEqual(cl.RasterXSize, 10)
        self.assertEqual(cl.RasterYSize, 20)

        classNames = cl.GetRasterBand(1).GetCategoryNames()
        self.assertEqual(len(classNames), 7)

        ds = TestObjects.createRasterDataset(1000, 2000, nb=100, eType=gdal.GDT_Float32)
        self.assertIsInstance(ds, gdal.Dataset)
        self.assertEqual(ds.RasterCount, 100)
        self.assertEqual(ds.RasterXSize, 1000)
        self.assertEqual(ds.RasterYSize, 2000)
        self.assertEqual(ds.GetRasterBand(1).DataType, gdal.GDT_Float32)

    def test_Speclibs(self):

        from qps.testing import TestObjects
        from qps.speclib.core import SpectralLibrary
        slib = TestObjects.createSpectralLibrary(7)
        self.assertIsInstance(slib, SpectralLibrary)
        self.assertTrue(len(slib) == 7)

if __name__ == "__main__":

    unittest.main()



