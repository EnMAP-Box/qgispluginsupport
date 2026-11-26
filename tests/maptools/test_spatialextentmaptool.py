# -*- coding: utf-8 -*-
"""
Test file for SpatialExtentMapTool
"""

import unittest

from qgis.PyQt.QtCore import QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent

from qps.maptools import SpatialExtentMapTool
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestSpatialExtentMapTool(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.lyr = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(self.lyr)
        self.canvas.setLayers([self.lyr])
        self.canvas.setCurrentLayer(self.lyr)
        self.canvas.setExtent(self.lyr.extent())
        self.canvas.setExtent(self.canvas.fullExtent())

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_creation(self):
        """Test that SpatialExtentMapTool can be created"""
        mt = SpatialExtentMapTool(self.canvas)
        self.assertIsInstance(mt, SpatialExtentMapTool)

    def test_flags(self):
        """Test flags method"""
        mt = SpatialExtentMapTool(self.canvas)
        flags = mt.flags()
        self.assertIsNotNone(flags)

    def test_set_style(self):
        """Test setStyle method - verifies the method can be called without error"""
        mt = SpatialExtentMapTool(self.canvas)

        from qgis.PyQt.QtGui import QColor
        new_color = QColor('blue')
        new_width = 3

        # The setStyle method should be callable
        mt.setStyle(new_color, new_width)

        # Note: QgsRubberBand API may vary - we just verify the method can be called
        self.assertIsNotNone(mt.rubberBand)

    def test_reset(self):
        """Test reset method"""
        mt = SpatialExtentMapTool(self.canvas)
        mt.activate()

        # Set some points
        size = self.canvas.size()
        point1 = QPointF(0.3 * size.width(), 0.3 * size.height())
        # point2 = QPointF(0.7 * size.width(), 0.7 * size.height())

        mouse_event1 = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point1,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event1 = QgsMapMouseEvent(self.canvas, mouse_event1)
        mt.canvasPressEvent(qgs_mouse_event1)

        # Reset should clear the selection
        mt.reset()

        # After reset, rectangle() should return None
        rect = mt.rectangle()
        self.assertIsNone(rect)

    def test_rectangle_after_selection(self):
        """Test rectangle() method after completing selection"""
        mt = SpatialExtentMapTool(self.canvas)
        mt.activate()

        size = self.canvas.size()

        # Click to start
        point1 = QPointF(0.3 * size.width(), 0.3 * size.height())
        mouse_event1 = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point1,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event1 = QgsMapMouseEvent(self.canvas, mouse_event1)
        mt.canvasPressEvent(qgs_mouse_event1)

        # Move to end point
        point2 = QPointF(0.7 * size.width(), 0.7 * size.height())
        mouse_event2 = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            point2,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event2 = QgsMapMouseEvent(self.canvas, mouse_event2)
        mt.canvasMoveEvent(qgs_mouse_event2)

        # The rectangle should be valid during drawing (before release)
        rect = mt.rectangle()
        self.assertIsNotNone(rect)
        self.assertIsInstance(rect, QgsRectangle)
        self.assertGreater(rect.width(), 0)
        self.assertGreater(rect.height(), 0)

        # Release to complete - this will call reset() which clears the rectangle
        mouse_event3 = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point2,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event3 = QgsMapMouseEvent(self.canvas, mouse_event3)
        mt.canvasReleaseEvent(qgs_mouse_event3)

        # After release, rectangle() should return None (reset was called)
        rect = mt.rectangle()
        self.assertIsNone(rect)

    def test_sig_spatial_extent_selected_signal(self):
        """Test sigSpatialExtentSelected signal emission"""
        mt = SpatialExtentMapTool(self.canvas)
        mt.activate()

        received = []

        def on_extent(crs, rect):
            received.append((crs, rect))

        mt.sigSpatialExtentSelected.connect(on_extent)

        size = self.canvas.size()

        # Click to start
        point1 = QPointF(0.3 * size.width(), 0.3 * size.height())
        mouse_event1 = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point1,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event1 = QgsMapMouseEvent(self.canvas, mouse_event1)
        mt.canvasPressEvent(qgs_mouse_event1)

        # Move
        point2 = QPointF(0.7 * size.width(), 0.7 * size.height())
        mouse_event2 = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            point2,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event2 = QgsMapMouseEvent(self.canvas, mouse_event2)
        mt.canvasMoveEvent(qgs_mouse_event2)

        # Release
        mouse_event3 = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point2,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event3 = QgsMapMouseEvent(self.canvas, mouse_event3)
        mt.canvasReleaseEvent(qgs_mouse_event3)

        # Signal should have been emitted
        self.assertEqual(len(received), 1)
        crs, rect = received[0]
        self.assertIsInstance(crs, QgsCoordinateReferenceSystem)
        self.assertIsInstance(rect, QgsRectangle)


if __name__ == '__main__':
    unittest.main(buffer=False)
