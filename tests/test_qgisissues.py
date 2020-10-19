# -*- coding: utf-8 -*-
"""Unit tests to test issues in the QGIS API

"""
__author__ = 'Benjamin Jakimow'
__date__ = '2019/01/21'
# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

import xmlrunner
from osgeo import gdal
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.testing import start_app, unittest, stop_app


class TestQgsFeature(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        start_app()

    @classmethod
    def tearDownClass(cls) -> None:
        stop_app()

    def test_QgsMapMouseEvent(self):
        canvas = QgsMapCanvas()
        canvas.setFixedSize(300, 300)

        pos = QPointF(0.5 * canvas.width(), 0.5 * canvas.height())
        # this works
        mouseEvent = QMouseEvent(QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

        qgsMouseEvent1 = QgsMapMouseEvent(canvas, mouseEvent)
        self.assertIsInstance(qgsMouseEvent1, QgsMapMouseEvent)

        # fails
        qgsMouseEvent2 = QgsMapMouseEvent(
            canvas,
            QEvent.MouseButtonPress,
            QPointF(0.5 * canvas.width(), 0.5 * canvas.height()).toPoint(),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier)
        self.assertIsInstance(qgsMouseEvent2, QgsMapMouseEvent)

    def test_vsimem(self):

        # create an 2x2x1 in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        self.assertIsInstance(driver, gdal.Driver)
        path = '/vsimem/inmemorytestraster.tif'

        dataSet = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
        self.assertIsInstance(dataSet, gdal.Dataset)
        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, dataSet.RasterYSize, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        self.assertIsInstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        self.assertIsInstance(layer, QgsRasterLayer)
        result = layer.isValid()


if __name__ == '__main__':

    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
