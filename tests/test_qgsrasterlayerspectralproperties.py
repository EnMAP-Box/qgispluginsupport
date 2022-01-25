from qgis._core import QgsApplication
from qgis._gui import QgsGui

from qgis.testing import start_app, stop_app, TestCase
import unittest

from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties, QgsRasterLayerSpectralPropertiesWidget
from qps.testing import TestObjects


class TestQgsRasterLayerProperties(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        start_app()
        QgsGui.editorWidgetRegistry().initEditors()

    def test_QgsRasterLayerSpectralProperties(self):
        rasterLayer = TestObjects.createRasterLayer()
        properties = QgsRasterLayerSpectralProperties()
        properties._readBandProperties(rasterLayer)

        properties.setValues('BBL', [1, 2], [False, False])
        badBands1 = properties.values('BBL')
        print(badBands1)

        # test convenience functions
        badBands2 = properties.bandBands()[0 - 2]
        self.assertListEqual(badBands1, badBands2)

    def test_QgsRasterLayerSpectralPropertiesWidget(self):
        rasterLayer = TestObjects.createRasterLayer(nb=24)
        properties = QgsRasterLayerSpectralProperties()
        properties._readBandProperties(rasterLayer)
        properties.initDefaultFields()
        properties.startEditing()
        w = QgsRasterLayerSpectralPropertiesWidget(properties)
        w.show()
        QgsApplication.instance().exec_()
        pass


if __name__ == '__main__':
    unittest.main()
