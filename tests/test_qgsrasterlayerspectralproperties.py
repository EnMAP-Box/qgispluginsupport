import unittest

from qgis.core import QgsRasterLayer

from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties, QgsRasterLayerSpectralPropertiesTable, \
    QgsRasterLayerSpectralPropertiesTableWidget, stringToType
from qps.testing import start_app, TestCase, TestObjects
from qpstestdata import envi_bsq, DIR_WAVELENGTH

start_app()


class TestQgsRasterLayerProperties(TestCase):

    def test_stringToType(self):
        self.assertEqual(stringToType(3.24), 3.24)
        self.assertEqual(stringToType('3.24'), 3.24)

        self.assertEqual(stringToType(3), 3)
        self.assertEqual(stringToType('3'), 3)

        self.assertEqual(stringToType('3foobar'), '3foobar')

    def test_wavelength(self):

        if False:
            prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'gdal_no_info.tif')
            self.assertEqual(prop.bandCount(), 2)
            self.assertEqual(prop.wavelengths(), [None, None])
            self.assertEqual(prop.wavelengthUnits(), [None, None])
            self.assertEqual(prop.fwhm(), [None, None])

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'gdal_wl_only.tif')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual(prop.wavelengths(), [None, None])
        s = ""

    def test_QgsRasterLayerSpectralProperties(self):

        lyr = QgsRasterLayer(envi_bsq.as_posix())
        self.assertIsInstance(lyr, QgsRasterLayer)
        properties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertIsInstance(properties, QgsRasterLayerSpectralProperties)
        p2 = QgsRasterLayerSpectralProperties.fromRasterLayer(envi_bsq)
        self.assertEqual(properties, p2)

        for name in ['wl', 'Wl', 'WaVeLength', 'WaVelengths']:
            self.assertEqual(properties.itemKey(name), 'wavelength')

        for name in ['WLU', 'wlu', 'WavelengthUnits', 'Wavelength unit', 'Wavelength Units']:
            self.assertEqual(properties.itemKey(name), 'wavelength_unit')

        for name in ['fwHm', 'FWHM']:
            self.assertEqual(properties.itemKey(name), 'fwhm')

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
