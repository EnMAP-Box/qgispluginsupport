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

from osgeo import gdal

from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QTreeView
from qgis.core import QgsMapLayer, QgsPointXY, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsMapLayerStore, \
    QgsProject, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas
from qps.cursorlocationvalue import CursorLocationInfoDock
from qps.testing import TestObjects, TestCaseBase, start_app
from qps.utils import SpatialPoint

start_app()


class CursorLocationTest(TestCaseBase):

    def test_maptool(self):

        lyrR = TestObjects.createRasterLayer(ns=50, nl=50, no_data_rectangle=40)
        lyrR = TestObjects.createMultiMaskExample(nb=3, ns=50, nl=50)
        lyrV = TestObjects.createVectorLayer()
        layers = [lyrR, lyrV]
        QgsProject.instance().addMapLayers(layers)
        c = QgsMapCanvas()
        c.setLayers(layers)
        c.setDestinationCrs(layers[0].crs())
        c.zoomToFullExtent()

        center = SpatialPoint.fromMapCanvasCenter(c)
        dock = CursorLocationInfoDock()

        dock.setCanvas(c)
        dock.loadCursorLocation(center, c)

        from qps.maptools import CursorLocationMapTool
        mt = CursorLocationMapTool(c)
        # mt.setFlags(QgsMapTool.ShowContextMenu)
        c.setMapTool(mt)

        def onLocationRequest(crs: QgsCoordinateReferenceSystem, pt: QgsPointXY):
            canvas: QgsMapCanvas = mt.canvas()
            spt = SpatialPoint(canvas.mapSettings().destinationCrs(), pt)
            dock.loadCursorLocation(spt, canvas)

        mt.sigLocationRequest.connect(onLocationRequest)
        tv2 = QTreeView()
        tv2.setModel(dock.mLocationInfoModel)
        w = QWidget()
        hboxLayout = QHBoxLayout()
        hboxLayout.addWidget(dock)
        hboxLayout.addWidget(c)
        hboxLayout.addWidget(tv2)
        w.setLayout(hboxLayout)
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    def test_locallayers(self):

        canvas = QgsMapCanvas()

        layers = [  # TestObjects.createRasterLayer(nc=3),
            TestObjects.createRasterLayer(nb=5, eType=gdal.GDT_Int16),
            # TestObjects.createVectorLayer()
        ]

        for lyr in layers:
            self.assertIsInstance(lyr, QgsMapLayer)
            self.assertTrue(lyr.isValid())

            if isinstance(lyr, QgsRasterLayer):
                center = SpatialPoint.fromMapLayerCenter(lyr)

            elif isinstance(lyr, QgsVectorLayer):
                for feature in lyr.getFeatures():
                    assert isinstance(feature, QgsFeature)
                    if not feature.geometry().isNull():
                        center = feature.geometry().centroid().asPoint()
                        center = SpatialPoint(lyr.crs(), center)
                        break

            store = QgsMapLayerStore()
            store.addMapLayer(lyr)
            canvas.setLayers([lyr])
            cldock = CursorLocationInfoDock()

            self.assertIsInstance(cldock, CursorLocationInfoDock)
            cldock.cursorLocation() == center
            cldock.loadCursorLocation(center, canvas)
            point = cldock.cursorLocation()
            self.assertIsInstance(point, SpatialPoint)

        self.showGui(cldock)


if __name__ == "__main__":
    unittest.main(buffer=False)
