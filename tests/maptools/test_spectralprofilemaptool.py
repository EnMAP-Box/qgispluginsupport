# -*- coding: utf-8 -*-
"""
Test file for SpectralProfileMapTool
"""

import unittest

from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas

from qps.maptools import SpectralProfileMapTool
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestSpectralProfileMapTool(TestCase):

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
        """Test that SpectralProfileMapTool can be created"""
        mt = SpectralProfileMapTool(self.canvas)
        self.assertIsInstance(mt, SpectralProfileMapTool)
        self.assertIsInstance(mt, SpectralProfileMapTool.__bases__[0])  # Check inheritance from CursorLocationMapTool


if __name__ == '__main__':
    unittest.main(buffer=False)
