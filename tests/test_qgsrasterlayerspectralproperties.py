import datetime
import json
import os.path
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal

from qgis.core import QgsMapLayer, QgsRasterLayer
from qps import DIR_REPO
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties, QgsRasterLayerSpectralPropertiesTable, \
    QgsRasterLayerSpectralPropertiesTableWidget, SpectralPropertyKeys, SpectralPropertyOrigin, stringToType
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import bandClosestToWavelength, file_search
from qpstestdata import DIR_WAVELENGTH, envi_bsq

start_app()


class TestQgsRasterLayerProperties(TestCase):

    def setUp(self):

        self.tempDir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempDir.cleanup)

    def assertEqualProperties(self,
                              p1: QgsRasterLayerSpectralProperties,
                              p2: QgsRasterLayerSpectralProperties,
                              skip_keys=['_origin_']):

        self.assertEqual(set(p1.keys()), set(p2.keys()))

        if SpectralPropertyKeys.Wavelength in p1.keys():
            self.assertWavelengthsEqual(p1.wavelengths(), p1.wavelengthUnits(),
                                        p2.wavelengths(), p2.wavelengthUnits())

        if SpectralPropertyKeys.FWHM in p1.keys():
            self.assertWavelengthsEqual(p1.fwhm(), p1.wavelengthUnits(),
                                        p2.fwhm(), p2.wavelengthUnits())

        if SpectralPropertyKeys.BadBand in p1.keys():
            self.assertEqual(p1.badBands(), p1.badBands())

        other_keys = [
            SpectralPropertyKeys.BadBand,
            SpectralPropertyKeys.DataOffset,
            SpectralPropertyKeys.DataGain,
            SpectralPropertyKeys.DataReflectanceGain,
            SpectralPropertyKeys.DataReflectanceOffset,
        ]
        for k in other_keys:
            values1 = p1.bandValues('*', k)
            values2 = p2.bandValues('*', k)
            self.assertEqual(values1, values2)

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
        self.assertWavelengthsEqual([0.4, 0.5], 'μm',
                                    prop.wavelengths(), prop.wavelengthUnits())
        self.assertEqual([0, 1], prop.badBands())
        self.assertWavelengthsEqual([0.01, 0.02], 'μm',
                                    prop.fwhm(), prop.wavelengthUnits())
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'envi_wl_implicit_nm.bsq')
        self.assertEqual(prop.bandCount(), 2)
        self.assertWavelengthsEqual([400, 500], 'nm',
                                    prop.wavelengths(), prop.wavelengthUnits())

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(DIR_WAVELENGTH / 'envi_wl_implicit_um.bsq')
        self.assertEqual(prop.bandCount(), 2)
        self.assertWavelengthsEqual([0.4, 0.5], 'μm',
                                    prop.wavelengths(), prop.wavelengthUnits())

    def test_fromGDALDataset(self):

        path = DIR_WAVELENGTH / 'gdal_wl_only.tif'
        prop = QgsRasterLayerSpectralProperties.fromGDALDataset(path)
        ds: gdal.Dataset = gdal.Open(path.as_posix())
        self.assertEqual(ds.RasterCount, prop.bandCount())
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())
        self.assertEqual([None, None], prop.badBands())
        self.assertEqual([1, 1], prop.badBands(default=1))
        self.assertEqual([None, None], prop.fwhm(), )
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        path = DIR_WAVELENGTH / 'gdal_wl_fwhm.tif'
        prop = QgsRasterLayerSpectralProperties.fromGDALDataset(path)
        self.assertEqual(prop.bandCount(), 2)
        self.assertEqual([0.4, 0.5], prop.wavelengths())
        self.assertEqual(['μm', 'μm'], prop.wavelengthUnits())
        self.assertEqual([None, None], prop.badBands())
        self.assertEqual([0.01, 0.02], prop.fwhm(), )
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        path = DIR_WAVELENGTH / 'envi_wl_fwhm.bsq'
        prop = QgsRasterLayerSpectralProperties.fromGDALDataset(path)
        self.assertEqual(prop.bandCount(), 2)
        self.assertWavelengthsEqual([0.4, 0.5], 'μm',
                                    prop.wavelengths(), prop.wavelengthUnits())
        self.assertEqual([0, 1], prop.badBands())
        self.assertWavelengthsEqual([0.01, 0.02], 'μm',
                                    prop.fwhm(), prop.wavelengthUnits())
        self.assertEqual([None, None], prop.dataGains())
        self.assertEqual([None, None], prop.dataOffsets())

        path = DIR_WAVELENGTH / 'envi_wl_implicit_nm.bsq'
        prop = QgsRasterLayerSpectralProperties.fromGDALDataset(path)
        self.assertEqual(prop.bandCount(), 2)
        self.assertWavelengthsEqual([400, 500], 'nm',
                                    prop.wavelengths(), prop.wavelengthUnits())

        path = DIR_WAVELENGTH / 'envi_wl_implicit_um.bsq'
        prop = QgsRasterLayerSpectralProperties.fromGDALDataset(path)
        self.assertEqual(prop.bandCount(), 2)
        self.assertWavelengthsEqual([0.4, 0.5], 'μm',
                                    prop.wavelengths(), prop.wavelengthUnits())

    def test_benchmark(self):

        path_benchmark = DIR_REPO / 'benchmark/spectralpropertyloading.json'
        os.makedirs(path_benchmark.parent, exist_ok=True)

        DIR_SOURCES = Path(r'X:\dc\deu\ard\mosaic')

        if not DIR_SOURCES.is_dir():
            return

        n_max = 100
        files = []
        for i, f in enumerate(file_search(DIR_SOURCES, re.compile(r'.*_BOA.vrt$'))):
            files.append(f)
            if len(files) == n_max:
                break

        def t1_read_layer(path):
            t = datetime.datetime.now()
            QgsRasterLayerSpectralProperties.fromRasterLayer(path)
            return (datetime.datetime.now() - t).total_seconds()

        def t2_read_gdal(path):
            t = datetime.datetime.now()
            QgsRasterLayerSpectralProperties.fromGDALDataset(path)
            return (datetime.datetime.now() - t).total_seconds()

        dur_lyr = []
        dur_gdal = []
        for file in files:
            dur_lyr.append(t1_read_layer(file))
            dur_gdal.append(t2_read_gdal(file))

        if path_benchmark.is_file():
            with open(path_benchmark, 'r') as f:

                JSON = json.load(f)
        else:
            JSON = dict()

        dur_lyr = np.asarray(dur_lyr)
        dur_gdal = np.asarray(dur_gdal)
        results = {
            'n_files': len(files),
            't_lyr_total': dur_lyr.sum(),
            't_lyr_mean': dur_lyr.mean(),
            't_lyr_std': dur_lyr.std(),
            't_lyr_min': dur_lyr.min(),
            't_lyr_max': dur_lyr.max(),
            't_gdal_total': dur_gdal.sum(),
            't_gdal_mean': dur_gdal.mean(),
            't_gdal_std': dur_gdal.std(),
            't_gdal_min': dur_gdal.min(),
            't_gdal_max': dur_gdal.max(),
        }

        JSON[str(DIR_SOURCES)] = results

        with open(path_benchmark, 'w') as f:
            json.dump(JSON, f, indent=2, ensure_ascii=False)

    def test_serialization(self):

        lyr = TestObjects.createRasterLayer(nb=10)
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)

        data = prop.asMap()
        self.assertIsInstance(data, dict)

        def equalProps(p1: QgsRasterLayerSpectralProperties, p2: QgsRasterLayerSpectralProperties):
            self.assertEqual(p1.bandCount(), p2.bandCount())
            self.assertEqual(p1.keys(), p2.keys())
            for k in p1.keys():
                self.assertEqual(p1.bandValues('*', k), p2.bandValues('*', k))

        dump = json.dumps(data)
        prop2 = QgsRasterLayerSpectralProperties.fromMap(json.loads(dump))

        equalProps(prop, prop2)

        data2 = data.copy()
        data2.pop('band_count')
        data2['x'] = data2.pop('wavelength')
        data2['xUnit'] = data2.pop('wavelength_unit')[0]

        prop3 = QgsRasterLayerSpectralProperties.fromMap(data2)
        equalProps(prop, prop3)

    def test_bandClosestToWavelength(self):
        with tempfile.TemporaryDirectory() as tdir:
            path = Path(tdir) / 'example.bsq'
            ds = TestObjects.createRasterDataset(2, 2, nb=5, drv='ENVI', path=path, add_wl=False)
            self.assertEqual(ds.GetDriver().ShortName, 'ENVI')
            # set B,G,R,NIR,SWIR bands, but no wavelength unit
            ds.SetMetadataItem('wavelength', '{450,550,650,800,1600}', 'ENVI')
            del ds

            props = QgsRasterLayerSpectralProperties.fromRasterLayer(path)
            assert props.wavelengthUnits()[0] == 'nm'

            lyr = QgsRasterLayer(path.as_posix())
            self.assertTrue(lyr.isValid())
            bandsRGB = [bandClosestToWavelength(lyr, s) for s in 'R,G,B'.split(',')]
            self.assertEqual(bandsRGB, [2, 1, 0])
            del lyr

    def test_QgsRasterLayerSpectralProperties(self):

        self.assertTrue(SpectralPropertyKeys.DataGain in SpectralPropertyKeys)

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
        self.assertTrue(prop3.equalBandValues(prop4))

        # write into layer properties

        path_img = Path(self.tempDir.name) / 'example.tif'

        lyr = TestObjects.createRasterLayer(nb=2, add_wl=False, path=path_img)
        self.assertTrue(os.path.isfile(path_img))

        prop1 = QgsRasterLayerSpectralProperties.fromRasterLayer(path_img)
        prop2 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(prop1, prop2)
        self.assertEqual([None, None], prop1.wavelengths())

        prop1.setBandValues('*', 'wavelength', [355, 455])
        prop1.setBandValues('*', 'wavelength unit', 'nm')
        prop1.writeToLayer(lyr)
        self.assertTrue(lyr.saveDefaultStyle(categories=QgsMapLayer.StyleCategory.CustomProperties))

        del lyr
        lyr = QgsRasterLayer(path_img.as_posix())
        assert lyr.isValid()
        prop3 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)

        self.assertEqualProperties(prop1, prop3)

        self.assertEqual(prop3.value(SpectralPropertyKeys.Wavelength)['_origin_'],
                         SpectralPropertyOrigin.LayerProperties)

        prop1.writeToSource(lyr)
        del lyr

        # restore saved properties from raster image
        lyr = QgsRasterLayer(path_img.as_posix())
        prop3 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqualProperties(prop1, prop3)
        self.assertEqual(prop3.fwhm(), [None, None])

        # change properties at layer custom properties
        lyr.setCustomProperty('wavelengths', [222, 333])
        lyr.setCustomProperty('wavelength units', ['nm', 'nm'])
        lyr.setCustomProperty('fwhm', [0.22, 0.44])
        prop4 = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(prop4.wavelengthUnits(), ['nm', 'nm'])
        self.assertEqual(prop4.wavelengths(), [222, 333])
        self.assertEqual(prop4.fwhm(), [0.22, 0.44])

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
