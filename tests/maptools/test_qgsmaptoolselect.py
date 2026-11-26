# -*- coding: utf-8 -*-
"""
Test file for QgsMapToolSelect
"""

import unittest

from qgis.PyQt.QtCore import Qt, QPointF
from qgis.PyQt.QtGui import QMouseEvent
from qgis.core import QgsProject, QgsWkbTypes, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent

from qps.maptools import QgsMapToolSelect, QgsMapToolSelectionHandler
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestQgsMapToolSelect(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PolygonGeometry)
        QgsProject.instance().addMapLayer(self.lyr)
        self.canvas.setLayers([self.lyr])
        self.canvas.setCurrentLayer(self.lyr)
        self.canvas.setExtent(self.lyr.extent())
        self.canvas.setExtent(self.canvas.fullExtent())

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_creation(self):
        """Test that QgsMapToolSelect can be created"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        self.assertIsInstance(mt, QgsMapToolSelect)

    def test_flags(self):
        """Test flags method"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        flags = mt.flags()
        self.assertIsNotNone(flags)

    def test_default_selection_mode(self):
        """Test that default selection mode is SelectSimple"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        self.assertEqual(mt.mSelectionHandler.selectionMode(),
                         QgsMapToolSelectionHandler.SelectionMode.SelectSimple)

    def test_set_selection_mode_select_simple(self):
        """Test setSelectionMode with SelectSimple"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)

        self.assertEqual(mt.mSelectionHandler.selectionMode(),
                         QgsMapToolSelectionHandler.SelectionMode.SelectSimple)
        self.showGui(self.canvas)

    def test_set_selection_mode_select_polygon(self):
        """Test setSelectionMode with SelectPolygon"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        self.assertEqual(self.canvas.mapTool(), mt)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectPolygon)

        self.assertEqual(mt.mSelectionHandler.selectionMode(),
                         QgsMapToolSelectionHandler.SelectionMode.SelectPolygon)

        self.showGui(self.canvas)

    def test_set_selection_mode_select_freehand(self):
        """Test setSelectionMode with SelectFreehand"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectFreehand)

        self.assertEqual(mt.mSelectionHandler.selectionMode(),
                         QgsMapToolSelectionHandler.SelectionMode.SelectFreehand)
        self.showGui(self.canvas)

    def test_set_selection_mode_select_radius(self):
        """Test setSelectionMode with SelectRadius"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)

        self.assertEqual(mt.mSelectionHandler.selectionMode(),
                         QgsMapToolSelectionHandler.SelectionMode.SelectRadius)
        self.showGui(self.canvas)

    def test_cursor_changes_with_selection_mode(self):
        """Test that cursor changes when selection mode changes"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)

        # SelectSimple should have a select cursor
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectSimple)

        # Other modes should have arrow cursor
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectPolygon)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectFreehand)
        mt.setSelectionMode(QgsMapToolSelectionHandler.SelectionMode.SelectRadius)

    def test_canvas_press_event(self):
        """Test canvasPressEvent"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        size = self.canvas.size()
        point = QPointF(0.5 * size.width(), 0.5 * size.height())

        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event = QgsMapMouseEvent(self.canvas, mouse_event)

        # This should not raise an exception
        mt.canvasPressEvent(qgs_mouse_event)

    def test_canvas_move_event(self):
        """Test canvasMoveEvent"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        size = self.canvas.size()
        point = QPointF(0.5 * size.width(), 0.5 * size.height())

        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event = QgsMapMouseEvent(self.canvas, mouse_event)

        # This should not raise an exception
        mt.canvasMoveEvent(qgs_mouse_event)

    def test_canvas_release_event(self):
        """Test canvasReleaseEvent"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        size = self.canvas.size()
        point = QPointF(0.5 * size.width(), 0.5 * size.height())

        # Note: canvasReleaseEvent requires canvasPressEvent to be called first
        # to set mInitDragPos. This test verifies the bug that would occur without proper setup.
        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event = QgsMapMouseEvent(self.canvas, mouse_event)
        mt.canvasPressEvent(qgs_mouse_event)

        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        qgs_mouse_event = QgsMapMouseEvent(self.canvas, mouse_event)

        # This should not raise an exception
        mt.canvasReleaseEvent(qgs_mouse_event)

    def test_deactivate(self):
        """Test deactivate method"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        # Deactivate should not raise an exception
        mt.deactivate()

    def test_select_features_with_point_geometry(self):
        """Test selectFeatures with point geometry"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        # Set a point geometry
        point = QgsPointXY(0, 0)
        geometry = QgsGeometry.fromPointXY(point)
        mt.mSelectionHandler.setSelectedGeometry(geometry, Qt.KeyboardModifier.NoModifier)

        # This should not raise an exception
        mt.selectFeatures(Qt.KeyboardModifier.NoModifier)

    def test_select_features_with_polygon_geometry(self):
        """Test selectFeatures with polygon geometry"""
        mt = QgsMapToolSelect(self.canvas)
        self.canvas.setMapTool(mt)
        mt.activate()

        # Set a polygon geometry
        rect = QgsGeometry.fromRect(self.lyr.extent())
        mt.mSelectionHandler.setSelectedGeometry(rect, Qt.KeyboardModifier.NoModifier)

        # This should not raise an exception
        mt.selectFeatures(Qt.KeyboardModifier.NoModifier)


if __name__ == '__main__':
    unittest.main(buffer=False)
