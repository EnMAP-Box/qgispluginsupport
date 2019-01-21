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
SHOW_GUI = False
QGIS_APP = initQgisApplication()
from qps.utils import *
from qps.maptools import *

class TestMapTools(unittest.TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(self.lyr)

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



if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



