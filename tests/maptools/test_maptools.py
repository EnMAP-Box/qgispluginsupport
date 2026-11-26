# -*- coding: utf-8 -*-
"""
Test file for MapTools enum
"""

import unittest

from qgis.core import QgsProject, QgsWkbTypes
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapTool
from qps.maptools import MapTools
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestMapTools(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.cad_dock_widget = QgsAdvancedDigitizingDockWidget(self.canvas)
        # Note: Tests in this file don't use a current layer by default, they set it as needed

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_maptools_enum_values(self):
        """Test that MapTools enum has all expected values"""
        expected_values = [
            'ZOOM_IN', 'ZOOM_OUT', 'ZOOM_FULL', 'PAN',
            'ZOOM_PIXEL_SCALE', 'CURSOR_LOCATION', 'SPECTRAL_PROFILE',
            'TEMPORAL_PROFILE', 'MOVE_CENTER', 'ADD_FEATURE',
            'SELECT_FEATURE', 'SELECT_FEATURE_POLYGON',
            'SELECT_FEATURE_FREEHAND', 'SELECT_FEATURE_RADIUS'
        ]

        actual_values = [mt.value for mt in MapTools]

        for expected in expected_values:
            self.assertIn(expected, actual_values)

    def test_maptools_map_tool_names(self):
        """Test mapToolNames method"""
        names = MapTools.mapToolNames()
        self.assertIsInstance(names, list)
        self.assertGreater(len(names), 0)

    def test_maptools_map_tool_values(self):
        """Test mapToolValues method"""
        values = MapTools.mapToolValues()
        self.assertIsInstance(values, list)
        self.assertGreater(len(values), 0)

    def test_maptools_map_tool_enums(self):
        """Test mapToolEnums method"""
        enums = MapTools.mapToolEnums()
        self.assertIsInstance(enums, list)
        self.assertGreater(len(enums), 0)

        for enum in enums:
            self.assertIsInstance(enum, MapTools)

    def test_to_map_tool_enum_from_string(self):
        """Test toMapToolEnum with string argument"""
        for name in MapTools.mapToolNames():
            result = MapTools.toMapToolEnum(name)
            self.assertIsInstance(result, MapTools)
            self.assertEqual(result.name, name)

    def test_to_map_tool_enum_from_value(self):
        """Test toMapToolEnum with value argument"""
        for value in MapTools.mapToolValues():
            result = MapTools.toMapToolEnum(value)
            self.assertIsInstance(result, MapTools)
            self.assertEqual(result.value, value)

    def test_to_map_tool_enum_from_enum(self):
        """Test toMapToolEnum with MapTools enum argument"""
        for enum in MapTools:
            result = MapTools.toMapToolEnum(enum)
            self.assertIsInstance(result, MapTools)
            self.assertEqual(result, enum)

    def test_to_map_tool_enum_invalid(self):
        """Test toMapToolEnum with invalid argument"""
        with self.assertRaises(AssertionError):
            MapTools.toMapToolEnum("INVALID_NAME")

        with self.assertRaises(AssertionError):
            MapTools.toMapToolEnum(12345)  # Invalid type

    def test_to_map_tool_enum_deprecated_keys(self):
        """Test deprecated mapToolKeys method"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = MapTools.mapToolKeys()
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
            self.assertIn("Deprecated", str(w[0].message))

    def test_create_map_tool_zoom_in(self):
        """Test create method with ZoomIn"""
        mt = MapTools.create(MapTools.ZoomIn, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_zoom_out(self):
        """Test create method with ZoomOut"""
        mt = MapTools.create(MapTools.ZoomOut, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_pan(self):
        """Test create method with Pan"""
        mt = MapTools.create(MapTools.Pan, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_zoom_pixel_scale(self):
        """Test create method with ZoomPixelScale"""
        mt = MapTools.create(MapTools.ZoomPixelScale, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_cursor_location(self):
        """Test create method with CursorLocation"""
        mt = MapTools.create(MapTools.CursorLocation, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_move_to_center(self):
        """Test create method with MoveToCenter"""
        mt = MapTools.create(MapTools.MoveToCenter, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_spectral_profile(self):
        """Test create method with SpectralProfile"""
        mt = MapTools.create(MapTools.SpectralProfile, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_temporal_profile(self):
        """Test create method with TemporalProfile"""
        mt = MapTools.create(MapTools.TemporalProfile, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_add_feature(self):
        """Test create method with AddFeature"""
        lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        QgsProject.instance().addMapLayer(lyr)
        self.canvas.setLayers([lyr])

        mt = MapTools.create(MapTools.AddFeature, self.canvas, cadDockWidget=self.cad_dock_widget)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_select_feature(self):
        """Test create method with SelectFeature"""
        lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        QgsProject.instance().addMapLayer(lyr)
        self.canvas.setLayers([lyr])

        mt = MapTools.create(MapTools.SelectFeature, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_select_feature_by_polygon(self):
        """Test create method with SelectFeatureByPolygon"""
        lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        QgsProject.instance().addMapLayer(lyr)
        self.canvas.setLayers([lyr])

        mt = MapTools.create(MapTools.SelectFeatureByPolygon, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)

    def test_create_map_tool_select_feature_by_freehand(self):
        """Test create method with SelectFeatureByFreehand"""
        lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        QgsProject.instance().addMapLayer(lyr)
        self.canvas.setLayers([lyr])

        mt = MapTools.create(MapTools.SelectFeatureByFreehand, self.canvas)
        self.assertIsInstance(mt, QgsMapTool)


if __name__ == '__main__':
    unittest.main(buffer=False)
