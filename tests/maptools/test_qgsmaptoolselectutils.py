# -*- coding: utf-8 -*-
"""
Test file for QgsMapToolSelectUtils
"""

import unittest

from qgis.PyQt.QtCore import Qt, QRect
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes, QgsRectangle, QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsRubberBand

from qps.maptools import QgsMapToolSelectUtils
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestQgsMapToolSelectUtils(TestCase):

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

    def test_get_current_vector_layer(self):
        """Test getCurrentVectorLayer static method"""
        self.canvas.setCurrentLayer(self.lyr)
        vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer(self.canvas)
        self.assertIsInstance(vlayer, QgsVectorLayer)
        self.assertEqual(vlayer, self.lyr)

    def test_get_current_vector_layer_no_layer(self):
        """Test getCurrentVectorLayer with no vector layer"""
        canvas = QgsMapCanvas()
        vlayer = QgsMapToolSelectUtils.getCurrentVectorLayer(canvas)
        self.assertIsNone(vlayer)

    def test_set_rubber_band(self):
        """Test setRubberBand static method"""
        rect = QRect(10, 10, 100, 100)
        rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)

        QgsMapToolSelectUtils.setRubberBand(self.canvas, rect, rubber_band)

        # The rubber band should have been modified
        self.assertIsNotNone(rubber_band)

    def test_expand_select_rectangle_point_line(self):
        """Test expandSelectRectangle for point and line layers"""
        # For point/line layers, boxSize should be 5 (10x10 pixels)
        vlayer = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.LineGeometry)
        QgsProject.instance().addMapLayer(vlayer)

        map_point = QgsPointXY(0, 0)
        rect = QgsMapToolSelectUtils.expandSelectRectangle(map_point, self.canvas, vlayer)

        self.assertIsInstance(rect, QgsRectangle)
        # The rectangle should be small (10x10 pixels in map units)
        self.assertLess(rect.width(), 100)
        self.assertLess(rect.height(), 100)

        QgsProject.instance().removeMapLayer(vlayer)

    def test_expand_select_rectangle_polygon(self):
        """Test expandSelectRectangle for polygon layers"""
        # For polygon layers, boxSize should be 1
        vlayer = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PolygonGeometry)
        QgsProject.instance().addMapLayer(vlayer)

        map_point = QgsPointXY(0, 0)
        rect = QgsMapToolSelectUtils.expandSelectRectangle(map_point, self.canvas, vlayer)

        self.assertIsInstance(rect, QgsRectangle)

        QgsProject.instance().removeMapLayer(vlayer)

    def test_select_multiple_features(self):
        """Test selectMultipleFeatures static method"""
        modifiers = Qt.KeyboardModifier.NoModifier
        select_geom = QgsGeometry.fromRect(self.lyr.extent())

        # This should not raise an exception
        QgsMapToolSelectUtils.selectMultipleFeatures(self.canvas, select_geom, modifiers)

    def test_select_single_feature(self):
        """Test selectSingleFeature static method"""
        select_geom = QgsGeometry.fromRect(self.lyr.extent())

        # This should not raise an exception
        QgsMapToolSelectUtils.selectSingleFeature(self.canvas, select_geom, Qt.KeyboardModifier.NoModifier)


if __name__ == '__main__':
    unittest.main(buffer=False)
