# coding=utf-8
"""

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__copyright__ = 'Copyright 2019, Benjamin Jakimow'

import gc
import unittest

from qgis.PyQt.QtCore import QEvent, QPointF, Qt, pyqtSlot
from qgis.PyQt.QtGui import QMouseEvent
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapMouseEvent, QgsMapTool, QgsMapToolCapture, \
    QgsMapToolZoom
from qps.maptools import FullExtentMapTool, MapToolCenter, MapTools, PixelScaleExtentMapTool, QgsMapToolAddFeature, \
    QgsMapToolSelect, QgsMapToolSelectionHandler, SpatialExtentMapTool
from qps.testing import TestCase, TestObjects, start_app
from qps.utils import SpatialExtent

start_app()


class TestMapTools(TestCase):

    def createCanvas(self) -> [QgsMapCanvas, QgsVectorLayer]:
        canvas = QgsMapCanvas()
        lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(lyr)
        canvas.setLayers([lyr])
        canvas.setExtent(lyr.extent())
        canvas.setExtent(canvas.fullExtent())
        return canvas, lyr

    # @unittest.skip('')
    def test_QgsMapTools(self):

        lyrR = TestObjects.createRasterLayer()
        lyrV_Point = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        lyrV_Poly = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PolygonGeometry)
        lyrV_Line = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.LineGeometry)
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
        mt1 = QgsMapToolAddFeature(canvas, cadDockWidget, QgsMapToolCapture.CaptureMode.CapturePoint)
        self.assertIsInstance(mt1, QgsMapToolAddFeature)
        canvas.setMapTool(mt1)
        mt1.activate()
        me1 = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0.5 * w, 0.5 * h), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
        canvas.mousePressEvent(me1)
        # mt = QgsMapToolCapture(c, d, QgsMapToolCapture.CapturePolygon)

        mts = QgsMapToolSelect(canvas)
        mts.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        canvas.setMapTool(mts)
        canvas.setCurrentLayer(lyrV_Poly)

        # QMouseEvent(QEvent::Type type, const QPointF &localPos, Qt::MouseButton button, Qt::MouseButtons buttons, Qt::KeyboardModifiers modifiers)

        me1 = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        me2 = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, w), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        me3 = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(h, w), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

        canvas.mousePressEvent(me1)
        canvas.mousePressEvent(me2)
        canvas.mousePressEvent(me3)
        # if not self.runsInCI():
        #   me4 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0.5 * h, 0.5 * w), Qt.RightButton, Qt.RightButton,
        #                    Qt.NoModifier)
        # canvas.mousePressEvent(me4)

        mt2 = SpatialExtentMapTool(canvas)

        @pyqtSlot(QgsCoordinateReferenceSystem, QgsRectangle)
        def onEmit(crs, rect):
            print('# onEmit2')
            self.assertIsInstance(crs, QgsCoordinateReferenceSystem)
            self.assertIsInstance(rect, QgsRectangle)

        mt2.sigSpatialExtentSelected[QgsCoordinateReferenceSystem, QgsRectangle].connect(onEmit)

        @pyqtSlot()
        def doEmit():
            print('#doEmit')
            ext = SpatialExtent.fromMapCanvas(canvas)
            mt2.sigSpatialExtentSelected[QgsCoordinateReferenceSystem, QgsRectangle].emit(ext.crs(), canvas.extent())

        # QTimer.singleShot(2, doEmit)
        # doEmit()
        # import time
        # time.sleep(2)

        self.showGui(canvas)

        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('')
    def test_PixelScaleExtentMapTool(self):

        canvas = QgsMapCanvas()
        lyr30 = TestObjects.createRasterLayer(pixel_size=30)
        lyr12_5 = TestObjects.createRasterLayer(pixel_size=12.5)
        mt = PixelScaleExtentMapTool(canvas)
        canvas.setLayers([lyr30, lyr12_5])
        canvas.setDestinationCrs(lyr30.crs())
        canvas.setCenter(lyr12_5.extent().center())
        canvas.zoomToFullExtent()
        canvas.setMapTool(mt)
        mt.setRasterLayer(lyr30)
        self.assertAlmostEqual(canvas.mapUnitsPerPixel(), lyr30.rasterUnitsPerPixelX(), 4)
        mt.setRasterLayer(lyr12_5)
        self.assertAlmostEqual(canvas.mapUnitsPerPixel(), lyr12_5.rasterUnitsPerPixelX(), 4)

        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('')
    def test_CenterMapCanvasMapTool(self):

        canvas, lyr = self.createCanvas()
        canvas.show()
        mt = MapToolCenter(canvas)
        canvas.setMapTool(mt)

        self.showGui(canvas)
        QgsProject.instance().removeAllMapLayers()
        del canvas

    # @unittest.skip('')
    def test_SpatialExtentMapTool(self):

        canvas, lyr = self.createCanvas()
        canvas.show()
        canvas.setCurrentLayer(canvas.layers()[0])
        mt = SpatialExtentMapTool(canvas)
        canvas.setMapTool(mt)

        spatialExtent = None

        def onExtentReceived(crs: QgsCoordinateReferenceSystem, rect: QgsRectangle):
            nonlocal spatialExtent
            spatialExtent = SpatialExtent(crs, rect)
            self.assertIsInstance(spatialExtent, SpatialExtent)

        mt.sigSpatialExtentSelected.connect(onExtentReceived)

        size = canvas.size()
        point = QPointF(0.3 * size.width(), 0.3 * size.height())
        event = QMouseEvent(QEvent.Type.MouseButtonPress, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        canvas.mousePressEvent(event)

        point = QPointF(0.4 * size.width(), 0.4 * size.height())
        event = QMouseEvent(QEvent.Type.MouseMove, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(event)

        point = QPointF(0.6 * size.width(), 0.6 * size.height())
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        canvas.mouseReleaseEvent(event)

        self.assertIsInstance(spatialExtent, SpatialExtent)

        del canvas, mt
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('')
    def test_QgsFeatureSelectByRadius(self):

        canvas, lyr = self.createCanvas()
        canvas.show()
        canvas.setCurrentLayer(canvas.layers()[0])
        mt1 = QgsMapToolSelect(canvas)
        mt1.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        canvas.setMapTool(mt1)

        size = canvas.size()

        mouseEvent = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(0.5 * size.width(), 0.5 * size.height()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)

        qgsMouseEvent = QgsMapMouseEvent(canvas, mouseEvent)
        mt1.canvasPressEvent(qgsMouseEvent)

        mouseEvent2 = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(0.5 * size.width(), 0.5 * size.height()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)

        qgsMouseEvent2 = QgsMapMouseEvent(canvas, mouseEvent2)
        mt1.canvasReleaseEvent(qgsMouseEvent2)
        mt1.deactivate()
        self.showGui(canvas)
        # del mt1, canvas, lyr
        gc.collect()
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('')
    def test_QgsFeatureSelectTool(self):

        canvas, lyr = self.createCanvas()
        canvas.show()
        canvas.setCurrentLayer(canvas.layers()[0])
        mt1 = QgsMapToolSelect(canvas)
        mt1.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        canvas.setMapTool(mt1)

        mt2 = QgsMapToolZoom(canvas, True)
        canvas.setMapTool(mt2)

        canvas.setMapTool(mt1)

        self.showGui(canvas)
        del canvas, mt1, mt2, lyr
        QgsProject.instance().removeAllMapLayers()

    # @unittest.skip('')
    def test_AddFeature(self):

        canvas, lyr = self.createCanvas()
        canvas.show()
        cadDockWidget = QgsAdvancedDigitizingDockWidget(canvas)
        for lyr in canvas.layers():
            if isinstance(lyr, QgsVectorLayer):
                canvas.setCurrentLayer(lyr)
                lyr.startEditing()
                break
        from qps.maptools import QgsMapToolDigitizeFeature
        mt = QgsMapToolAddFeature(canvas, cadDockWidget, QgsMapToolDigitizeFeature.CaptureMode.CaptureNone)
        canvas.setMapTool(mt)
        self.showGui(canvas)
        mt.deactivate()
        del mt
        del cadDockWidget
        del canvas
        del lyr

        QgsProject.instance().removeAllMapLayers()
        s = ""

    # @unittest.skip('')
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

                for mode in [QgsMapToolCapture.CaptureMode.CapturePoint,
                             QgsMapToolCapture.CaptureMode.CaptureLine,
                             QgsMapToolCapture.CaptureMode.CapturePolygon,
                             QgsMapToolCapture.CaptureMode.CaptureNone]:
                    mt = MapTools.create(mte, canvas, mode=mode, cadDockWidget=cadDockWidget)
                    self.assertIsInstance(mt, QgsMapTool)
                    tools.append(mt)
            else:
                mt = MapTools.create(mte, canvas, *args)
                self.assertIsInstance(mt, QgsMapTool)
                tools.append(mt)

        mt_enums = [enum for enum in MapTools.mapToolEnums()]
        mt_enums = [
            MapTools.ZoomIn,
            MapTools.ZoomOut,
            MapTools.ZoomFull,
            MapTools.Pan,
            MapTools.ZoomPixelScale,
            MapTools.CursorLocation,
            MapTools.SpectralProfile,
            MapTools.TemporalProfile,
            MapTools.AddFeature,
            MapTools.SelectFeature,
            MapTools.SelectFeatureByPolygon,
            MapTools.SelectFeatureByFreehand,
            # MapTools.SelectFeatureByRadius
        ]
        for enum in mt_enums:
            print('Test MapTool {}...'.format(enum.name))
            if enum.name in [MapTools.AddFeature.name]:
                mapTool = MapTools.create(enum.name, canvas, cadDockWidget)
            else:
                mapTool = MapTools.create(enum.name, canvas)
            self.assertIsInstance(mapTool, QgsMapTool)
            self.assertEqual(mapTool, canvas.mapTool())

            size = canvas.size()

            mouseEvent = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(0.5 * size.width(), 0.5 * size.height()),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier)

            qgsMouseEvent = QgsMapMouseEvent(canvas, mouseEvent)
            mapTool.canvasPressEvent(qgsMouseEvent)

            mouseEvent2 = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(0.5 * size.width(), 0.5 * size.height()),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier)

            qgsMouseEvent2 = QgsMapMouseEvent(canvas, mouseEvent2)
            mapTool.canvasReleaseEvent(qgsMouseEvent2)

        mt = PixelScaleExtentMapTool(canvas)
        self.assertIsInstance(mt, PixelScaleExtentMapTool)

        mt = FullExtentMapTool(canvas)
        self.assertIsInstance(mt, FullExtentMapTool)

        QgsProject.instance().removeAllMapLayers()


if __name__ == "__main__":
    unittest.main(buffer=False)
