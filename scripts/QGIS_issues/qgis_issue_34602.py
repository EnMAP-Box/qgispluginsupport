
import site
import pathlib

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QResizeEvent

DIR_QGIS_REPO = pathlib.Path(r'F:\Repositories\QGIS')
assert DIR_QGIS_REPO.is_dir()

site.addsitedir(DIR_QGIS_REPO / 'tests' / 'src' / 'python')
import unittest
import os
from utilities import unitTestDataPath
from qgis.core import QgsRasterLayer, QgsSingleBandGrayRenderer, QgsProject
from qgis.gui import QgsMapCanvas, QgsRendererRasterPropertiesWidget

from qgis.testing.mocked import get_iface

class TestQgsRasterLayer(unittest.TestCase):

    def setUp(self):
        self.iface = get_iface()
        QgsProject.instance().removeAllMapLayers()

        self.iface.mapCanvas().viewport().resize(400, 400)
        # For some reason the resizeEvent is not delivered, fake it
        self.iface.mapCanvas().resizeEvent(QResizeEvent(QSize(400, 400), self.iface.mapCanvas().size()))

    def multibandRasterLayer(self) -> QgsRasterLayer:

        try:
            from utilities import unitTestDataPath
            path = pathlib.Path(unitTestDataPath()) / 'landsat_4326.tif'
        except ModuleNotFoundError:
            path = pathlib.Path(__file__).parent / 'landsat_4326.tif'

        assert isinstance(path, pathlib.Path) and path.is_file()
        lyr = QgsRasterLayer(path.as_posix())
        lyr.setName(path.name)
        self.assertIsInstance(lyr, QgsRasterLayer)
        self.assertTrue(lyr.isValid())
        self.assertTrue(lyr.bandCount() > 1)

        return lyr

    def test_syncToLayer_SingleBandGray(self):

        lyr = self.multibandRasterLayer()
        lyr.setRenderer(QgsSingleBandGrayRenderer(lyr.dataProvider(), 1))
        c = QgsMapCanvas()
        w = QgsRendererRasterPropertiesWidget(lyr, c)
        assert isinstance(w.currentRenderWidget().renderer(), QgsSingleBandGrayRenderer)
        assert w.currentRenderWidget().renderer().grayBand() == 1
        lyr.renderer().setGrayBand(2)
        w.syncToLayer(lyr)
        assert w.currentRenderWidget().renderer().grayBand() == 2

    def test_renderer(self):
        path = os.path.join(unitTestDataPath(), 'landsat.tif')

        layer = QgsRasterLayer(path)
        layer.setRenderer(QgsSingleBandGrayRenderer(layer.dataProvider(), 1))
        c = QgsMapCanvas()
        w = QgsRendererRasterPropertiesWidget(layer, c)
        w.show()
        self.assertIsInstance(w.currentRenderWidget().renderer(), QgsSingleBandGrayRenderer)
        self.assertEqual(w.currentRenderWidget().renderer().grayBand(), 1)
        layer.renderer().setGrayBand(2)
        w.syncToLayer(layer)
        self.assertEqual(w.currentRenderWidget().renderer().grayBand(), 2)