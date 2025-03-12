import os.path
import unittest

from qgis._core import QgsMapLayer

from qgis.core import QgsRasterLayer
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties, QgsRasterLayerSpectralPropertiesTable, \
    QgsRasterLayerSpectralPropertiesTableWidget, SpectralPropertyKeys, SpectralPropertyOrigin, stringToType
from qps.testing import start_app, TestCase, TestObjects
from qpstestdata import DIR_WAVELENGTH, envi_bsq

start_app()


class TestQgsRasterLayerProperties(TestCase):

    def test_stringToType(self):
        self.assertEqual(stringToType(3.24), 3.24)
        self.assertEqual(stringToType('3.24'), 3.24)

        self.assertEqual(stringToType(3), 3)
        self.assertEqual(stringToType('3'), 3)

        self.assertEqual(stringToType('3foobar'), '3foobar')

    def test_wavelength(self):

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'gdal_no_info.tif')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual(prop.wavelengths(), [None, None])
        self.assertEqual(prop.wavelengthUnits(), [None, None])
        self.assertEqual(prop.fwhm(), [None, None])

        lyr = QgsRasterLayer((DIR_WAVELENGTH / 'gdal_wl_only.tif').as_posix())
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(lyr.bandCount(), prop.bandCount())
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())
        self.assertEqual([None, None], prop.badBands())
        self.assertEqual([1, 1], prop.badBands(default=1))
        self.assertEqual([None, None], prop.fwhm(), )
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'gdal_wl_fwhm.tif')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())
        self.assertEqual([None, None], prop.badBands())
        self.assertEqual([0.01, 0.02], prop.fwhm(), )
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'envi_wl_fwhm.bsq')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())
        self.assertEqual([0, 1], prop.badBands())
        self.assertEqual([0.01, 0.02], prop.fwhm(), )
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'envi_wl_implicit_nm.bsq')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual([400, 500], prop.wavelengths())
        self.assertEqual(['nm', 'nm'], prop.wavelengthUnits())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'envi_wl_implicit_um.bsq')
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())

    def test_QgsRasterLayerSpectralProperties(self):

        lyr = TestObjects.createRasterLayer()
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(prop.badBands(), [None])
        self.assertEqual(prop.badBands(default=1), [1])

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

        self.assertEqual(properties.itemKey('BBL'), 'bbl')

        lyr2 = TestObjects.createRasterLayer(nb=2, add_wl=False)
        # QgsRasterLayer((DIR_WAVELENGTH / 'gdal_no_info.tif').as_posix())
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr2)
        self.assertEqual([None, None], prop.wavelengths())
        self.assertEqual([None, None], prop.wavelengthUnits())
        self.assertEqual([None, None], prop.fwhm())

        # read wavelength from custom layer properties
        lyr2.setCustomProperty('wavelengths', [300, 400])
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr2)
        self.assertEqual([300, 400], prop.wavelengths())
        self.assertEqual(['nm', 'nm'], prop.wavelengthUnits())

        # are custom properties cloned as well?
        lyr3 = lyr2.clone()
        prop3 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr3)
        self.assertEqual([300, 400], prop3.wavelengths())
        self.assertEqual(['nm', 'nm'], prop3.wavelengthUnits())

        lyr4 = TestObjects.createRasterLayer(nb=2, add_wl=False)
        self.assertTrue(prop3.writeToLayer(lyr4))

        prop4 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr4)
        self.assertEqual([300, 400], prop4.wavelengths())
        self.assertEqual(['nm', 'nm'], prop4.wavelengthUnits())
        self.assertEqual(prop3, prop4)

        # write into layer properties
        DIR_TMP = self.createTestOutputDirectory()
        path_img = DIR_TMP / 'example.tif'

        lyr = TestObjects.createRasterLayer(nb=2, add_wl=False, path=path_img)
        self.assertTrue(os.path.isfile(path_img))

        prop1 = QgsRasterLayerSpectralProperties.fromRasterLayer(path_img)
        prop2 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(prop1, prop2)
        self.assertEqual([None, None], prop1.wavelengths())

        prop1.setBandValues('*', 'wavelength', [355, 455])
        prop1.writeToLayer(lyr)
        self.assertTrue(lyr.saveDefaultStyle(categories=QgsMapLayer.StyleCategory.CustomProperties))

        del lyr
        lyr = QgsRasterLayer(path_img.as_posix())
        prop3 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        if prop1 != prop3:
            s = ""
        self.assertEqual(prop1, prop3)
        self.assertEqual(prop3.value(SpectralPropertyKeys.Wavelength)['_origin_'],
                         SpectralPropertyOrigin.LayerProperties)

        del lyr

        prop1.writeToSource(lyr)

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
