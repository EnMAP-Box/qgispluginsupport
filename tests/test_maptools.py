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
SHOW_GUI = False and os.environ.get('CI') is None
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