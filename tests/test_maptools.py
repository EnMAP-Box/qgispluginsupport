# coding=utf-8
"""

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__copyright__ = 'Copyright 2019, Benjamin Jakimow'

import unittest, pickle
from qgis import *
from qgis.core import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from osgeo import gdal, ogr, osr
from qps.testing import initQgisApplication, TestObjects
SHOW_GUI = True and os.environ.get('CI') is None
QGIS_APP = initQgisApplication()
from qps.utils import *
from qps.maptools import *

class TestMapTools(unittest.TestCase):

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
        return canvas

    def tearDown(self):
        self.canvas.close()
        QgsProject.instance().removeMapLayer(self.lyr)


    def test_MapToolDigitizeFeatures(self):

        lyrR = TestObjects.createRasterLayer()
        lyrV_Point = TestObjects.createVectorLayer(QgsWkbTypes.PointGeometry)
        lyrV_Poly = TestObjects.createVectorLayer(QgsWkbTypes.PolygonGeometry)
        lyrV_Line = TestObjects.createVectorLayer(QgsWkbTypes.LineGeometry)
        layers = [lyrR, lyrV_Point, lyrV_Line, lyrV_Poly]
        QgsProject.instance().addMapLayers(layers)

        c = QgsMapCanvas()
        d = QgsAdvancedDigitizingDockWidget(c)
        d.setVisible(False)
        c.show()
        c.setLayers(layers)
        c.setDestinationCrs(lyrV_Poly.crs())
        c.setExtent(c.fullExtent())

        mt = MapToolAddFeature(c, d, QgsMapToolCapture.CapturePolygon)
        self.assertIsInstance(mt, MapToolAddFeature)
        c.setMapTool(mt)
        #mt = QgsMapToolCapture(c, d, QgsMapToolCapture.CapturePolygon)

        mts = QgsMapToolSelect(c)
        mts.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        c.setMapTool(mts)
        c.setCurrentLayer(lyrV_Poly)

        #QMouseEvent(QEvent::Type type, const QPointF &localPos, Qt::MouseButton button, Qt::MouseButtons buttons, Qt::KeyboardModifiers modifiers)
        
        w,h = c.size().width(), c.size().height()
        me1 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0,0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me2 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0, w), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me3 = QMouseEvent(QEvent.MouseButtonPress, QPointF(h, w), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        me4 = QMouseEvent(QEvent.MouseButtonPress, QPointF(0.5*h, 0.5*w), Qt.RightButton, Qt.RightButton, Qt.NoModifier)
        c.mousePressEvent(me1)
        c.mousePressEvent(me2)
        c.mousePressEvent(me3)
        c.mousePressEvent(me4)

        if SHOW_GUI:
            QGIS_APP.exec_()


    def test_MapTools(self):

        keys = MapTools.mapToolKeys()
        for k in keys:
            self.assertIsInstance(k, str)
        self.assertIsInstance(keys, list)
        self.assertTrue(len(keys) > 0)


        for key in keys:
            print('Test MapTool {}...'.format(key))
            mapTool = MapTools.create(key, self.canvas)
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

            if SHOW_GUI:
                d = QDialog(None)
                d.setWindowTitle('Cursor "{}"'.format(mapTool.__class__.__name__))
                d.setLayout(QVBoxLayout())
                canvas = self.createCanvas()
                mapTool = MapTools.create(key, canvas)
                d.layout().addWidget(canvas)
                self.assertEqual(mapTool, canvas.mapTool())
                btn1 = QPushButton('Ok', d)
                btn2 = QPushButton('Failed', d)

                btn1.clicked.connect(d.accept)
                btn2.clicked.connect(d.reject)
                d.layout().addWidget(btn1)
                d.layout().addWidget(btn2)

                if d.exec_() == QDialog.Rejected:
                    self.fail('Wrong/none cursor for maptool {}'.format(mapTool.__class__.__name__))


        mt = PixelScaleExtentMapTool(self.canvas)
        self.assertIsInstance(mt, PixelScaleExtentMapTool)
#        self.assertFalse(mt.canvas().cursor().pixmap().isNull())

        mt = FullExtentMapTool(self.canvas)
        self.assertIsInstance(mt, FullExtentMapTool)
 #       self.assertFalse(mt.canvas().cursor().pixmap().isNull())




if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



QGIS_APP.quit()