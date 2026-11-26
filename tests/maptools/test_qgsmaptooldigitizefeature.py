# -*- coding: utf-8 -*-
"""
Test file for QgsMapToolDigitizeFeature
"""

import unittest

from qgis.core import QgsProject, QgsWkbTypes
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas
from qgis.gui import QgsMapTool

from qps.maptools import QgsMapToolDigitizeFeature
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestQgsMapToolDigitizeFeature(TestCase):

    def setUp(self):
        self.canvas = QgsMapCanvas()
        self.cad_dock_widget = QgsAdvancedDigitizingDockWidget(self.canvas)
        self.lyr = TestObjects.createVectorLayer(QgsWkbTypes.GeometryType.PointGeometry)
        QgsProject.instance().addMapLayer(self.lyr)
        self.canvas.setLayers([self.lyr])
        self.canvas.setExtent(self.lyr.extent())
        self.canvas.setExtent(self.canvas.fullExtent())
        self.canvas.setCurrentLayer(self.lyr)
        self.lyr.startEditing()

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()

    def test_creation(self):
        """Test that QgsMapToolDigitizeFeature can be created"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        self.assertIsInstance(mt, QgsMapToolDigitizeFeature)
        self.showGui(self.canvas)

    def test_creation_with_vector_layer_tools(self):
        """Test that QgsMapToolDigitizeFeature can be created with vectorLayerTools parameter"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget,
                                       vectorLayerTools=None)
        self.canvas.setMapTool(mt)
        self.assertIsInstance(mt, QgsMapToolDigitizeFeature)

    def test_set_vector_layer_tools(self):
        """Test setVectorLayerTools method"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        mt.setVectorLayerTools(None)
        self.assertIsNone(mt.mVectorLayerTools)

    def test_check_geometry_type(self):
        """Test checkGeometryType and setCheckGeometryType methods"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget)
        self.canvas.setMapTool(mt)

        # Default should be True
        self.assertTrue(mt.checkGeometryType())

        # Set to False
        mt.setCheckGeometryType(False)
        self.assertFalse(mt.checkGeometryType())

    def test_digitizing_completed_signal(self):
        """Test digitizingCompleted signal emission"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        mt.activate()

        received = []

        def on_digitized(feature):
            received.append(feature)

        mt.digitizingCompleted.connect(on_digitized)

        # Verify the signal exists and can be connected
        self.assertIsNotNone(mt.digitizingCompleted)

    def test_flags(self):
        """Test flags method"""
        mt = QgsMapToolDigitizeFeature(self.canvas, self.lyr, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        flags = mt.flags()
        self.assertIsInstance(flags, QgsMapTool.Flag)


if __name__ == '__main__':
    unittest.main(buffer=False)
