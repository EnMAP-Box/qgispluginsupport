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
import xmlrunner
from qgis.gui import QgsMapCanvas
from qgis.core import QgsMapLayer, QgsPointXY, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsMapLayerStore, \
    QgsProject, QgsCoordinateReferenceSystem
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from qps.testing import TestObjects, TestCase

from qps.cursorlocationvalue import *

class CursorLocationTest(TestCase):

    def setUp(self):
        self.wmsUri1 = r'crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'
        self.wmsUri2 = 'referer=OpenStreetMap%20contributors,%20under%20ODbL&type=xyz&url=http://tiles.wmflabs.org/hikebike/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=17&zmin=1'
        # self.wfsUri = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' typename=''fis:re_postleit'' url=''http://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' version=''auto'''
        # self.wfsUri = r"pagingEnabled='true' restrictToRequestBBOX='1' srsname='EPSG:26986' typename='massgis:GISDATA.WATERPIPES_ARC_M150' url='http://giswebservices.massgis.state.ma.us/geoserver/wfs' url='http://giswebservices.massgis.state.ma.us/geoserver/wfs?request=getcapabilities' version='auto' table="" sql='"

    def webLayers(self)->list:
        l1 = QgsRasterLayer(self.wmsUri1, 'XYZ Web Map Service Raster Layer', 'wms')
        l2 = QgsRasterLayer(self.wmsUri2, 'OSM', 'wms')
        # l3 = QgsVectorLayer(self.wfsUri, 'Lee Water Pipes', 'WFS')

        layers = [l1, l2]
        for l in layers:
            self.assertIsInstance(l, QgsMapLayer)
            self.assertTrue(l.isValid())
        return layers

    def test_maptool(self):

        lyr = TestObjects.createRasterLayer(ns=50, nl=50, no_data_rectangle=40)
        QgsProject.instance().addMapLayer(lyr)
        c = QgsMapCanvas()
        c.setLayers([lyr])
        c.setDestinationCrs(lyr.crs())
        c.zoomToFullExtent()

        center = SpatialPoint.fromMapLayerCenter(lyr)
        dock = CursorLocationInfoDock()
        dock.setCanvas(c)
        dock.loadCursorLocation(center, c)

        from qps.maptools import CursorLocationMapTool
        mt = CursorLocationMapTool(c)
        c.setMapTool(mt)

        def onLocationRequest(crs:QgsCoordinateReferenceSystem, pt: QgsPointXY):
            canvas: QgsMapCanvas = mt.canvas()
            spt = SpatialPoint(canvas.mapSettings().destinationCrs(), pt)
            dock.loadCursorLocation(spt, canvas)

        mt.sigLocationRequest.connect(onLocationRequest)

        w = QWidget()
        l = QHBoxLayout()
        l.addWidget(dock)
        l.addWidget(c)
        w.setLayout(l)
        self.showGui(w)

    def test_locallayers(self):

        canvas = QgsMapCanvas()

        layers = [#TestObjects.createRasterLayer(nc=3),
                  TestObjects.createRasterLayer(nb=5, eType=gdal.GDT_Int16),
                  #TestObjects.createVectorLayer()
        ]

        for lyr in layers:
            self.assertIsInstance(lyr, QgsMapLayer)
            self.assertTrue(lyr.isValid())

            if isinstance(lyr, QgsRasterLayer):
                center = SpatialPoint.fromMapLayerCenter(lyr)

            elif isinstance(lyr, QgsVectorLayer):
                for feature in lyr.getFeatures():
                    assert isinstance(feature, QgsFeature)
                    if not feature.geometry().isNull():
                        center = feature.geometry().centroid().asPoint()
                        center = SpatialPoint(lyr.crs(), center)
                        break


            store = QgsMapLayerStore()
            store.addMapLayer(lyr)
            canvas.setLayers([lyr])
            cldock = CursorLocationInfoDock()

            self.assertIsInstance(cldock, CursorLocationInfoDock)
            cldock.cursorLocation() == center
            cldock.loadCursorLocation(center, canvas)
            point = cldock.cursorLocation()
            self.assertIsInstance(point, SpatialPoint)

        self.showGui(cldock)

    def test_weblayertest(self):

        if os.environ.get('CI'):
            # do not run in CI
            return
        canvas = QgsMapCanvas()

        layers = self.webLayers()
        center = SpatialPoint.fromMapLayerCenter(layers[0])
        store = QgsMapLayerStore()
        store.addMapLayers(layers)

        canvas.setLayers(layers)
        canvas.setCenter(center)
        cldock = CursorLocationInfoDock()


        self.assertIsInstance(cldock, CursorLocationInfoDock)

        cldock.loadCursorLocation(center, canvas)
        point = cldock.cursorLocation()
        self.assertIsInstance(point, SpatialPoint)

        self.showGui([cldock, canvas])


if __name__ == "__main__":

    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)

