import unittest

from qgis.core import QgsRasterLayer
from qgis.gui import QgsGui
from qgis.testing import start_app
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralPropertiesTable, \
    QgsRasterLayerSpectralPropertiesTableWidget, QgsRasterLayerSpectralProperties, stringToType
from qps.testing import TestObjects, TestCase


class TestQgsRasterLayerProperties(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        start_app()
        QgsGui.editorWidgetRegistry().initEditors()

    def test_stringToType(self):
        self.assertEqual(stringToType(3.24), 3.24)
        self.assertEqual(stringToType('3.24'), 3.24)

        self.assertEqual(stringToType(3), 3)
        self.assertEqual(stringToType('3'), 3)

        self.assertEqual(stringToType('3foobar'), '3foobar')

    def test_QgsRasterLayerSpectralProperties(self):
        from qpstestdata import envi_bsq

        lyr = QgsRasterLayer(envi_bsq)
        properties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        p2 = QgsRasterLayerSpectralProperties.fromRasterLayer(envi_bsq)
        self.assertEqual(properties, p2)

        self.assertEqual(properties.itemKey('wl'), 'wl')
        self.assertEqual(properties.itemKey('WL'), 'wl')
        self.assertEqual(properties.itemKey('Wavelength'), 'wl')
        self.assertEqual(properties.itemKey('Wavelengths'), 'wl')

        self.assertEqual(properties.itemKey('WLU'), 'wlu')
        self.assertEqual(properties.itemKey('WavelengthUnits'), 'wlu')
        self.assertEqual(properties.itemKey('Wavelength unit'), 'wlu')
        self.assertEqual(properties.itemKey('Wavelength Units'), 'wlu')

        self.assertEqual(properties.itemKey('FWHM'), 'fwhm')
        self.assertEqual(properties.itemKey('FWHM/BBL'), 'FWHM/bbl')

        lyr.setCustomProperty('band_3/wavelength', 350)
        properties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        wl = properties.wavelengths()
        self.assertEqual(wl[2], 350)

        wlu = properties.wavelengthUnits()
        for v in wlu:
            self.assertEqual(v, 'nm')
        properties.setBandValues('all', 'wavelength_unit', 'm')
        wlu2 = properties.wavelengthUnits()
        self.assertEqual(len(wlu), len(wlu2))
        for v in wlu2:
            self.assertEqual(v, 'm')

    def test_QgsRasterLayerSpectralPropertiesTable(self):
        rasterLayer = TestObjects.createRasterLayer()
        properties = QgsRasterLayerSpectralPropertiesTable()
        properties._readBandProperties(rasterLayer)

        properties.setValues('BBL', [1, 2], [False, False])
        badBands1 = properties.values('BBL')
        print(badBands1)

    def test_QgsRasterLayerSpectralPropertiesTableWidget(self):
        rasterLayer = TestObjects.createRasterLayer(nb=24)
        properties = QgsRasterLayerSpectralPropertiesTable()
        properties._readBandProperties(rasterLayer)
        properties.initDefaultFields()
        properties.startEditing()
        w = QgsRasterLayerSpectralPropertiesTableWidget(properties)
        self.showGui(w)


if __name__ == '__main__':
    unittest.main()
