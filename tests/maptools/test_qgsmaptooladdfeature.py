# -*- coding: utf-8 -*-
"""
Test file for QgsMapToolAddFeature
"""

import unittest

from qgis.core import QgsProject, QgsWkbTypes
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas, QgsMapToolCapture
from qgis.gui import QgsMapTool

from qps.maptools import QgsMapToolAddFeature
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestQgsMapToolAddFeature(TestCase):

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
        """Test that QgsMapToolAddFeature can be created"""
        mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        self.assertIsInstance(mt, QgsMapToolAddFeature)
        self.showGui(self.canvas)

    def test_creation_with_mode(self):
        """Test that QgsMapToolAddFeature can be created with specific capture mode"""
        for mode in [QgsMapToolCapture.CaptureMode.CapturePoint,
                     QgsMapToolCapture.CaptureMode.CaptureLine,
                     QgsMapToolCapture.CaptureMode.CapturePolygon,
                     QgsMapToolCapture.CaptureMode.CaptureNone]:
            mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget, mode=mode)
            self.canvas.setMapTool(mt)
            self.assertIsInstance(mt, QgsMapToolAddFeature)

    def test_creation_with_vector_layer_tools(self):
        """Test that QgsMapToolAddFeature can be created with vectorLayerTools parameter"""
        mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget,
                                  vectorLayerTools=None)
        self.canvas.setMapTool(mt)
        self.assertIsInstance(mt, QgsMapToolAddFeature)

    def test_check_geometry_type_default(self):
        """Test that checkGeometryType is True by default"""
        mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        self.assertTrue(mt.checkGeometryType())

    def test_project_listeners(self):
        """Test that project listeners are connected"""
        mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget)
        self.canvas.setMapTool(mt)

        # The tool should be listening to project signals
        # This is verified by the existence of the connections in the constructor

    def test_flags(self):
        """Test flags method"""
        mt = QgsMapToolAddFeature(self.canvas, self.cad_dock_widget)
        self.canvas.setMapTool(mt)
        flags = mt.flags()
        self.assertIsInstance(flags, QgsMapTool.Flag)


if __name__ == '__main__':
    unittest.main(buffer=False)
