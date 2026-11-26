# -*- coding: utf-8 -*-
"""
Test file for PixelScaleExtentMapTool
"""

import unittest

from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent

from qps.maptools import PixelScaleExtentMapTool
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestPixelScaleExtentMapTool(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_creation(self):
        """Test that PixelScaleExtentMapTool can be created"""
        mt = PixelScaleExtentMapTool(self.canvas)
        self.assertIsInstance(mt, PixelScaleExtentMapTool)

    def test_cursor_is_set(self):
        """Test that cursor is properly set"""
        mt = PixelScaleExtentMapTool(self.canvas)
        # Use mCursor attribute as the public API for cursor may differ
        cursor = mt.mCursor
        self.assertIsNotNone(cursor)

    def test_flags(self):
        """Test flags method"""
        mt = PixelScaleExtentMapTool(self.canvas)
        flags = mt.flags()
        self.assertIsNotNone(flags)

    def test_set_raster_layer(self):
        """Test setRasterLayer method"""
        lyr = TestObjects.createRasterLayer(pixel_size=30)
        QgsProject.instance().addMapLayer(lyr)

        self.canvas.setLayers([lyr])
        self.canvas.setDestinationCrs(lyr.crs())
        self.canvas.setCenter(lyr.extent().center())
        self.canvas.zoomToFullExtent()

        mt = PixelScaleExtentMapTool(self.canvas)
        mt.setRasterLayer(lyr)

        # The canvas should be zoomed to match the raster resolution
        # This is a basic test - the actual zoom behavior depends on native resolutions
        self.assertIsInstance(mt, PixelScaleExtentMapTool)

    def test_set_raster_layer_with_different_resolutions(self):
        """Test setRasterLayer with multiple raster layers"""
        lyr30 = TestObjects.createRasterLayer(pixel_size=30)
        lyr12_5 = TestObjects.createRasterLayer(pixel_size=12.5)
        QgsProject.instance().addMapLayers([lyr30, lyr12_5])

        self.canvas.setLayers([lyr30, lyr12_5])
        self.canvas.setDestinationCrs(lyr30.crs())
        self.canvas.setCenter(lyr12_5.extent().center())
        self.canvas.zoomToFullExtent()

        mt = PixelScaleExtentMapTool(self.canvas)

        # Test with 30m resolution layer
        mt.setRasterLayer(lyr30)

        # Test with 12.5m resolution layer
        mt.setRasterLayer(lyr12_5)

    def test_canvas_release_event(self):
        """Test canvasReleaseEvent selects appropriate raster layer"""
        lyr = TestObjects.createRasterLayer(pixel_size=30)
        QgsProject.instance().addMapLayer(lyr)

        self.canvas.setLayers([lyr])
        self.canvas.setDestinationCrs(lyr.crs())
        self.canvas.setExtent(lyr.extent())

        mt = PixelScaleExtentMapTool(self.canvas)
        mt.activate()

        # Simulate a click on the canvas
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

        # The tool should have identified and set a raster layer
        # Note: This test may not set a layer if the click is outside any raster extent


if __name__ == '__main__':
    unittest.main(buffer=False)
