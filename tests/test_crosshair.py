# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
from enmapboxtestdata import enmap
from qps.testing import initQgisApplication, TestObjects
QGIS_APP = initQgisApplication()
SHOW_GUI = False
from qps.crosshair.crosshair import *



class CrosshairTests(unittest.TestCase):

    def test_crosshair(self):
        # add site-packages to sys.path as done by enmapboxplugin.py

        TestObjects.createVectorDataSet()
        lyr = QgsRasterLayer(enmap)
        QgsProject.instance().addMapLayer(lyr)
        refCanvas = QgsMapCanvas()
        refCanvas.setLayers([lyr])
        refCanvas.setExtent(lyr.extent())
        refCanvas.setDestinationCrs(lyr.crs())


        style = CrosshairStyle()
        self.assertIsInstance(style, CrosshairStyle)

        if SHOW_GUI:
            style = CrosshairDialog.getCrosshairStyle(mapCanvas=refCanvas)
            if style is not None:
                self.assertIsInstance(style, CrosshairStyle)

            refCanvas.show()
            QGIS_APP.exec_()

if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



