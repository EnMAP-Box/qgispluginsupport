from qgis.testing import start_app, stop_app, TestCase
import unittest

from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.testing import TestObjects


class TestQgsRasterLayerProperties(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        start_app()

    def test_QgsRasterLayerSpectralProperties(self):
        rasterLayer = TestObjects.createRasterLayer()
        properties = QgsRasterLayerSpectralProperties()
        properties._readFromLayer(rasterLayer)
        properties.setValues('BBL', [1, 2], [False, False])
        badBands = properties.values('BBL')
        print(badBands)


if __name__ == '__main__':
    unittest.main()
