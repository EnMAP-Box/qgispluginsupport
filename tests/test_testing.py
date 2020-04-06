# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
from qgis.core import *
from qgis.gui import *
import unittest, pickle
import qgis.testing
import qps.testing
from osgeo import gdal, gdal_array, ogr, osr
import numpy as np

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
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0,
                        msg='Standard QgsEditorWidgetWrapper not initialized')

        # test iface
        import qgis.utils
        iface = qgis.utils.iface

        self.assertIsInstance(iface, QgisInterface)
        self.assertIsInstance(iface, qps.testing.QgisMockup)

        lyr1 = qps.testing.TestObjects.createVectorLayer()
        lyr2 = qps.testing.TestObjects.createVectorLayer()

        self.assertIsInstance(iface.layerTreeView(), QgsLayerTreeView)
        self.assertIsInstance(iface.layerTreeView().model(), QgsLayerTreeModel)
        root = iface.layerTreeView().model().rootGroup()
        self.assertIsInstance(root, QgsLayerTree)
        self.assertEqual(len(root.findLayers()), 0)

        #QgsProject.instance().layersAdded.connect(lambda : print('ADDED'))
        #QgsProject.instance().legendLayersAdded.connect(lambda: print('ADDED LEGEND'))

        QgsProject.instance().addMapLayer(lyr1, False)
        QgsProject.instance().addMapLayer(lyr2, True)

        QgsApplication.processEvents()

        self.assertTrue(lyr1.id() not in root.findLayerIds())
        self.assertTrue(lyr2.id() in root.findLayerIds())


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

    def test_coredata(self):
        from qps.testing import TestObjects
        import numpy as np
        array, wl, wlu, gt, wkt = TestObjects.coreData()
        self.assertIsInstance(array, np.ndarray)
        self.assertIsInstance(wl, np.ndarray)
        self.assertTrue(len(wl) > 0)
        self.assertIsInstance(wlu, str)
        self.assertTrue(len(gt) == 6)
        self.assertIsInstance(wkt, str)

    def test_RasterData(self):

        from qps.testing import TestObjects

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
        from qpstestdata import enmap
        woptions = gdal.WarpOptions(dstSRS='EPSG:4326')
        pathDst = '/vsimem/warpDest.tif'
        dsDst = gdal.Warp(pathDst, dsSrc, options=woptions)
        self.assertIsInstance(dsDst, gdal.Dataset)



    def test_Speclibs(self):

        from qps.testing import TestObjects
        from qps.speclib.core import SpectralLibrary
        slib = TestObjects.createSpectralLibrary(7)
        self.assertIsInstance(slib, SpectralLibrary)
        self.assertTrue(len(slib) == 7)

if __name__ == "__main__":

    unittest.main()



