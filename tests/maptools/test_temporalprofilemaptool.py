# -*- coding: utf-8 -*-
"""
Test file for TemporalProfileMapTool
"""

import unittest

from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas

from qps.maptools import TemporalProfileMapTool
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestTemporalProfileMapTool(TestCase):

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
        """Test that TemporalProfileMapTool can be created"""
        mt = TemporalProfileMapTool(self.canvas)
        self.assertIsInstance(mt, TemporalProfileMapTool)
        self.assertIsInstance(mt, TemporalProfileMapTool.__bases__[0])  # Check inheritance from CursorLocationMapTool


if __name__ == '__main__':
    unittest.main(buffer=False)
