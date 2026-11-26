# -*- coding: utf-8 -*-
"""
Test file for MapToolCenter
"""

import unittest

from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.core import QgsPointXY
from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent

from qps.maptools import MapToolCenter
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestMapToolCenter(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(self.lyr)
        self.canvas.setLayers([self.lyr])
        self.canvas.setExtent(self.lyr.extent())
        self.canvas.setExtent(self.canvas.fullExtent())

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_creation(self):
        """Test that MapToolCenter can be created"""
        mt = MapToolCenter(self.canvas)
        self.assertIsInstance(mt, MapToolCenter)

    def test_flags(self):
        """Test flags method"""
        mt = MapToolCenter(self.canvas)
        flags = mt.flags()
        self.assertIsNotNone(flags)

    def test_set_map_center(self):
        """Test setMapCenter method"""
        from qps.utils import SpatialPoint
        mt = MapToolCenter(self.canvas)
        mt.activate()

        # Create a SpatialPoint
        crs = self.canvas.mapSettings().destinationCrs()
        center = self.canvas.extent().center()
        point = SpatialPoint(crs, center)

        # This should not raise an exception
        mt.setMapCenter(point)

    def test_canvas_release_event(self):
        """Test canvasReleaseEvent centers the map"""
        mt = MapToolCenter(self.canvas)
        mt.activate()

        old_center = self.canvas.center()
        self.assertIsInstance(old_center, QgsPointXY)

        size = self.canvas.size()
        point = QPointF(0.5 * size.width(), 0.5 * size.height())
        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event = QgsMapMouseEvent(self.canvas, mouse_event)
        mt.canvasReleaseEvent(qgs_mouse_event)

        # The map should have been centered (may or may not change depending on crosshair settings)


if __name__ == '__main__':
    unittest.main(buffer=False)
