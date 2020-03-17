# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, os
from qps.testing import TestObjects, TestCase
from qps.crosshair.crosshair import *

os.environ['CI'] = '1' # un-comment or set to 'False' to popup GUIs


class CrosshairTests(TestCase):

    def test_crosshair(self):
        # add site-packages to sys.path as done by enmapboxplugin.py

        lyr = TestObjects.createRasterLayer()
        lyr2 = TestObjects.createRasterLayer(ns=2000, nl=3000, nb=3)
        layers = [lyr, lyr2]
        QgsProject.instance().addMapLayers(layers)
        refCanvas = QgsMapCanvas()
        refCanvas.setLayers([lyr2])
        refCanvas.setDestinationCrs(lyr.crs())
        refCanvas.setExtent(refCanvas.fullExtent())
        item = CrosshairMapCanvasItem(refCanvas)

        self.assertIsInstance(item, CrosshairMapCanvasItem)
        item.setRasterGridLayer(lyr)
        item.setPosition(SpatialPoint.fromMapLayerCenter(lyr2))
        item.setVisibility(True)
        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)

        style.setVisibility(True)
        style.setShowPixelBorder(True)
        item.setCrosshairStyle(style)

        self.showGui(refCanvas)

    def test_noCRS(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setExtent(QgsRectangle(-1,-1,1,1))
        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)
        item = CrosshairMapCanvasItem(refCanvas)
        self.assertIsInstance(item, CrosshairMapCanvasItem)
        item.setCrosshairStyle(style)
        item.setPosition(refCanvas.center())

        self.showGui(refCanvas)

    def test_CRS(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32721'))
        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)
        item = CrosshairMapCanvasItem(refCanvas)
        self.assertIsInstance(item, CrosshairMapCanvasItem)
        item.setCrosshairStyle(style)
        item.setPosition(refCanvas.center())

        self.showGui(refCanvas)

    def test_dialog(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32721'))
        QTimer.singleShot(500, QApplication.closeAllWindows)
        style = getCrosshairStyle(mapCanvas=refCanvas)


    def test_crosshair_maplayer(self):

        canvas = QgsMapCanvas()
        mc = CrosshairMapCanvasItem(canvas)

        lyr = TestObjects.createRasterLayer()

        lyr2 = TestObjects.createRasterLayer()
        mc.setRasterGridLayer(lyr)
        self.assertEqual(mc.rasterGridLayer(), lyr)
        mc.setRasterGridLayer(lyr2)
        self.assertEqual(mc.rasterGridLayer(), lyr2)

        lyr.willBeDeleted.emit()
        lyr2.willBeDeleted.emit()
        self.assertTrue(mc.rasterGridLayer() == None)

if __name__ == "__main__":
    unittest.main()


