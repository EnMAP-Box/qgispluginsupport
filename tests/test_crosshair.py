# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, os
from qps.testing import initQgisApplication, TestObjects
QGIS_APP = initQgisApplication()
SHOW_GUI = False and os.environ.get('CI') is None
from qps.crosshair.crosshair import *



class CrosshairTests(unittest.TestCase):

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

        if SHOW_GUI:
            #style = CrosshairDialog.getCrosshairStyle(mapCanvas=refCanvas)
            #if style is not None:
            #    self.assertIsInstance(style, CrosshairStyle)

            refCanvas.show()

            QGIS_APP.exec_()

    def test_noCRS(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setExtent(QgsRectangle(-1,-1,1,1))
        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)
        item = CrosshairMapCanvasItem(refCanvas)
        self.assertIsInstance(item, CrosshairMapCanvasItem)
        item.setCrosshairStyle(style)
        item.setPosition(refCanvas.center())

        if SHOW_GUI:
            refCanvas.show()
            QGIS_APP.exec_()

    def test_CRS(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32721'))
        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)
        item = CrosshairMapCanvasItem(refCanvas)
        self.assertIsInstance(item, CrosshairMapCanvasItem)
        item.setCrosshairStyle(style)
        item.setPosition(refCanvas.center())

        if SHOW_GUI:
            refCanvas.show()
            QGIS_APP.exec_()

    def test_dialog(self):

        refCanvas = QgsMapCanvas()
        refCanvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32721'))

        style = getCrosshairStyle(mapCanvas=refCanvas)

        if SHOW_GUI:
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



QGIS_APP.quit()