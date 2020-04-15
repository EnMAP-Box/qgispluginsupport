# coding=utf-8
"""

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__copyright__ = 'Copyright 2019, Benjamin Jakimow'

import unittest
from qps.testing import TestObjects, TestCase

from qgis import *
from qgis.core import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from osgeo import gdal, ogr, osr


from qps.utils import *
from qps.maptools import *

class TestMapTools(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(self.lyr)

    def createCanvas(self)->QgsMapCanvas:
        canvas = QgsMapCanvas()
        lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(lyr)
        canvas.setLayers([lyr])
        canvas.setExtent(lyr.extent())
        canvas.setExtent(canvas.fullExtent())
        return canvas

    def tearDown(self):
        self.canvas.close()
        QgsProject.instance().removeMapLayer(self.lyr)

    def test_QgsMapTools(self):

        lyrR = TestObjects.createRasterLayer()
        lyrV_Point = TestObjects.createVectorLayer(QgsWkbTypes.PointGeometry)
        lyrV_Poly = TestObjects.createVectorLayer(QgsWkbTypes.PolygonGeometry)
        lyrV_Line = TestObjects.createVectorLayer(QgsWkbTypes.LineGeometry)
        layers = [lyrR, lyrV_Point, lyrV_Line, lyrV_Poly]
        QgsProject.instance().addMapLayers(layers)

        canvas = QgsMapCanvas()
        cadDockWidget = QgsAdvancedDigitizingDockWidget(canvas)
        cadDockWidget.setVisible(True)
        cadDockWidget.show()
        canvas.show()
        canvas.setLayers(layers)
        canvas.setDestinationCrs(lyrV_Poly.crs())
        canvas.setExtent(canvas.fullExtent())

        w, h = canvas.size().width(), canvas.size().height()
        
        canvas.setCurrentLayer(lyrV_Point)

        lyrV_Point.startEditing()
        mt = QgsMapToolAddFeature(canvas, QgsMapToolCapture.CapturePoint, cadDockWidget)
        self.assertIsInstance(mt, QgsMapToolAddFeature)
        canvas.setMapTool(mt)
        mt.activate()
        me1 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0.5*w, 0.5*h), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mousePressEvent(me1)
        #mt = QgsMapToolCapture(c, d, QgsMapToolCapture.CapturePolygon)
        


        mts = QgsMapToolSelect(canvas)
        mts.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        canvas.setMapTool(mts)
        canvas.setCurrentLayer(lyrV_Poly)

        #QMouseEvent(QEvent::Type type, const QPointF &localPos, Qt::MouseButton button, Qt::MouseButtons buttons, Qt::KeyboardModifiers modifiers)
        

        me1 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0,0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me2 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0, w), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me3 = QMouseEvent(QEvent.MouseButtonPress, QPointF(h, w), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me4 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0.5*h, 0.5*w), Qt.RightButton, Qt.RightButton, Qt.NoModifier)
        canvas.mousePressEvent(me1)
        canvas.mousePressEvent(me2)
        canvas.mousePressEvent(me3)
        canvas.mousePressEvent(me4)

        self.showGui(canvas)

    def test_CenterMapCanvasMapTool(self):

        canvas = self.createCanvas()
        canvas.show()
        mt = MapToolCenter(canvas)
        canvas.setMapTool(mt)

        self.showGui(canvas)

    def onExtentReceived(self, spatialExtent:SpatialExtent):
        self.assertIsInstance(spatialExtent, SpatialExtent)
        self.mSpatialExtent = spatialExtent

    def test_SpatialExtentMapTool(self):

        canvas = self.createCanvas()
        canvas.show()
        canvas.setCurrentLayer(canvas.layers()[0])
        mt = SpatialExtentMapTool(canvas)
        canvas.setMapTool(mt)


        mt.sigSpatialExtentSelected.connect(self.onExtentReceived)
        self.mSpatialExtent = None
        size = canvas.size()
        point = QPointF(0.3 * size.width(), 0.3 * size.height())
        event = QMouseEvent(QEvent.MouseButtonPress, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mousePressEvent(event)

        point = QPointF(0.4 * size.width(), 0.4 * size.height())
        event = QMouseEvent(QEvent.MouseMove, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mouseMoveEvent(event)

        point = QPointF(0.6 * size.width(), 0.6 * size.height())
        event = QMouseEvent(QEvent.MouseButtonRelease, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        canvas.mouseReleaseEvent(event)

        self.assertIsInstance(self.mSpatialExtent, SpatialExtent)


    def test_QgsFeatureSelectTool(self):

        canvas = self.createCanvas()
        canvas.show()
        canvas.setCurrentLayer(canvas.layers()[0])
        mt = QgsMapToolSelect(canvas)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        canvas.setMapTool(mt)

        m2 = QgsMapToolZoom(canvas, True)
        canvas.setMapTool(m2)

        canvas.setMapTool(mt)

        self.showGui(canvas)

    def test_AddFeature(self):

        canvas = self.createCanvas()
        canvas.show()
        cadDockWidget = QgsAdvancedDigitizingDockWidget(canvas)
        for l in canvas.layers():
            if isinstance(l, QgsVectorLayer):
                canvas.setCurrentLayer(l)
                l.startEditing()
                break
        mt = QgsMapToolAddFeature(canvas, QgsMapToolDigitizeFeature.CaptureNone, cadDockWidget)
        canvas.setMapTool(mt)
        self.showGui(canvas)


    def test_MapTools(self):
        canvas = QgsMapCanvas()
        cadDockWidget = QgsAdvancedDigitizingDockWidget(canvas)


        for name in MapTools.mapToolNames():
            mte = MapTools.toMapToolEnum(name)
            self.assertIsInstance(mte, MapTools)

        for value in MapTools.mapToolNames():
            mte = MapTools.toMapToolEnum(value)
            self.assertIsInstance(mte, MapTools)


        tools = []

        for mte in MapTools.mapToolEnums():
            self.assertIsInstance(mte, MapTools)

            args = []
            if mte == MapTools.AddFeature:
                for mode  in [QgsMapToolCapture.CapturePoint,
                              QgsMapToolCapture.CaptureLine,
                              QgsMapToolCapture.CapturePolygon,
                              QgsMapToolCapture.CaptureNone]:
                    mt = MapTools.create(mte, canvas, mode, cadDockWidget)
                    self.assertIsInstance(mt, QgsMapTool)
                    tools.append(mt)
            else:
                mt = MapTools.create(mte, canvas, *args)
                self.assertIsInstance(mt, QgsMapTool)
                tools.append(mt)



        for enum in MapTools.mapToolEnums():
            print('Test MapTool {}...'.format(enum.name))
            mapTool = MapTools.create(name, self.canvas)
            self.assertIsInstance(mapTool, QgsMapTool)
            self.assertEqual(mapTool, self.canvas.mapTool())

            size = self.canvas.size()

            mouseEvent = QMouseEvent(
                            QEvent.MouseButtonPress,
                            QPointF(0.5 * size.width(), 0.5 * size.height()),
                            Qt.LeftButton,
                            Qt.LeftButton,
                            Qt.NoModifier)

            qgsMouseEvent = QgsMapMouseEvent(self.canvas, mouseEvent)


            mapTool.canvasPressEvent(qgsMouseEvent)
            mapTool.canvasReleaseEvent(qgsMouseEvent)


        mt = PixelScaleExtentMapTool(self.canvas)
        self.assertIsInstance(mt, PixelScaleExtentMapTool)

        mt = FullExtentMapTool(self.canvas)
        self.assertIsInstance(mt, FullExtentMapTool)





if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
