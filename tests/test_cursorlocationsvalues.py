# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import unittest
from qgis import *
from qgis.gui import *

from qgis.core import *
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from enmapbox.testing import initQgisApplication
QGIS_APP = initQgisApplication()
from enmapbox.gui.utils import *
from enmapbox.gui.cursorlocationvalue import *

SHOW_GUI = False

class CursorLocationTest(unittest.TestCase):

    def setUp(self):
        self.wmsUri1 = r'crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'
        self.wmsUri2 = 'referer=OpenStreetMap%20contributors,%20under%20ODbL&type=xyz&url=http://tiles.wmflabs.org/hikebike/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=17&zmin=1'
        self.wfsUri = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' typename=''fis:re_postleit'' url=''http://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' version=''auto'''

    def webLayers(self)->list:
        layers = [QgsRasterLayer(self.wmsUri1, 'XYZ', 'wms'), QgsRasterLayer(self.wmsUri2, 'OSM', 'wms'), QgsVectorLayer(self.wfsUri, 'Berlin', 'WFS')]
        for l in layers:
            self.assertIsInstance(l, QgsMapLayer)
            self.assertTrue(l.isValid())
        return layers

    def test_layertest(self):

        canvas  = QgsMapCanvas()
        layers = self.webLayers()
        center = SpatialPoint.fromMapLayerCenter(layers[0])
        store = QgsMapLayerStore()
        store.addMapLayers(layers)
        canvas.setLayers(layers)
        cldock = CursorLocationInfoDock()
        cldock.show()
        cldock.loadCursorLocation(center, canvas)
        crs, point = cldock.cursorLocation()
        self.assertIsInstance(point, QgsPointXY)
        self.assertIsInstance(crs, QgsCoordinateReferenceSystem)

        if SHOW_GUI:
            QGIS_APP.exec_()
        self.assertIsInstance(cldock, CursorLocationInfoDock)

if __name__ == "__main__":

    #exampleMapLinking()
    unittest.main()



