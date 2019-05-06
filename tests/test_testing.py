# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, pickle
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *

class testClassTesting(unittest.TestCase):


    def test_init(self):

        import qps.testing
        self.assertTrue(qps.testing != None)

        qgis_app = qps.testing.initQgisApplication()


        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)

        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0, msg='Standard QgsEditorWidgetWrapper not initialized')

        app = QgsApplication.instance()
        ENV = app.systemEnvVars()
        for k in sorted(ENV.keys()): print('{}={}'.format(k, ENV[k]))

        qgis_app.quit()

    def test_init_minimal(self):
        import qps.testing
        qgis_app = qps.testing.initQgisApplication(minimal=True)
        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)
        qgis_app.quit()


    def test_TestObject(self):

        from qps.testing import TestObjects, initQgisApplication
        qgis_app = initQgisApplication(minimal=True)
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

        qgis_app.quit()

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



