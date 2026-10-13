import datetime
import importlib
import random
import unittest

from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsExpression, QgsExpressionContext, QgsProject, QgsExpressionContextUtils
from qgis.core import QgsFields, QgsField, QgsFeature
from qgis.core import QgsRasterLayer

from qps.expressionfunctions import SpectralData
from qps.externals.spyindex.definitions import BANDS
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import ProfileEncoding
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import BAND_INDEX_CACHE, band_index, band_shortcut_descriptions, band_values

start_app()

has_spyndex = importlib.util.find_spec('spyndex')


class SpectralDataTests(TestCase):
    def test_spectral_data(self):
        f = SpectralData()
        self.registerFunction(f)

        # Create a spectral library with test profiles
        sl = TestObjects.createSpectralLibrary(profile_field_names=['profile1', 'profile2'])
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        # Test spectral_data without field name (should get first profile field)
        for feature in sl.getFeatures():
            context.setFeature(feature)
            exp = QgsExpression("spectral_data()")
            self.assertTrue(exp.prepare(context))
            result = exp.evaluate(context)
            # Should return a profile dict or None if no profile
            if result is not None:
                from qps.speclib.core.spectralprofile import decodeProfileValueDict
                profile = decodeProfileValueDict(result)
                self.assertIsInstance(profile, dict)

        QgsProject.instance().removeAllMapLayers()

    def test_spectral_data2(self):

        self.registerFunction(SpectralData())

        fields = QgsFields()
        fields.append(QgsField("name", QMetaType.Type.QString))
        fields.append(SpectralLibraryUtils.createProfileField('p1', encoding=ProfileEncoding.Json))
        fields.append(SpectralLibraryUtils.createProfileField('p2', encoding=ProfileEncoding.Json))

        f = QgsFeature(fields)

        d1 = {
            'x': [400, 500, 600, 700, 800, 900, 1000],
            'y': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            'xUnit': 'nm'
        }

        d2 = {
            'x': [0.4, 0.5, 0.6, ],
            'y': [2, 5, 10],
            'xUnit': 'um'
        }

        f.setAttribute('p1', d1)
        f.setAttribute('p2', d2)

        context = QgsExpressionContext()
        context.setFeature(f)
        context.setFields(f.fields())

        # return the band-index if band name has a `_` prefix
        exp = QgsExpression("spectral_data(\"p1\", band:='NDVI', indices:=True)")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, {'R620', 2}, )

        exp = QgsExpression("spectral_data()")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertDictEqual(result, d1)

        exp = QgsExpression("spectral_data(\"p1\")")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertDictEqual(result, d1)

        exp = QgsExpression("spectral_data(\"p2\")")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertDictEqual(result, d2)

        exp = QgsExpression("spectral_data(\"p1\", band:='R620')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 0.3)

        exp = QgsExpression("spectral_data(band:='R620')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 0.3)

        exp = QgsExpression("spectral_data(band:='nir')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 0.5)

        exp = QgsExpression("spectral_data(\"p2\", band:='R620')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 10)

        exp = QgsExpression("spectral_data(band:='R400_600')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 0.2)

    def test_required_bands(self):

        # R = 620 - 690
        wl_nm = [400, 610, 650, 690, 700]
        bands = ['R450', 'R650_800', 'R', 'R100_200']
        wl_i = [0, 4, 2, None]
        wl_um = [v / 1000 for v in wl_nm]

        for expected_index, band in zip(wl_i, bands):
            i0 = band_index(band, wl_nm)
            i1 = band_index(band, wl_um, 'micrometers')

            self.assertEqual(
                expected_index, i0,
                msg=f'Expected band index {expected_index}, got {i0} to get index for band "{band}"'
            )

            self.assertEqual(i0, i1)

    @unittest.skipIf(not has_spyndex, 'spyndex package is not installed')
    def test_required_band_values(self):

        d = list(TestObjects.spectralProfileData(1))[0]
        x = d['x']
        y = d['y']
        wlu = d['xUnit']
        # test band identifiers
        bands = ['R450', 'R650_800', 'R', 'G', 'N']
        b_values = band_values(bands, x, y, wavelength_unit=wlu)
        b_indices = band_values(bands, x, y, wavelength_unit=wlu, return_band_indices=True)
        self.assertIsInstance(b_values, dict)
        self.assertIsInstance(b_indices, dict)
        for i, b in enumerate(bands):
            self.assertTrue(b in b_values)
            b_value = b_values[b]
            b_index = b_indices[b]
            self.assertEqual(b_value, y[b_index])

    @unittest.skipIf(not has_spyndex, 'spyndex package is not installed')
    def test_spectral_index(self):

        d = list(TestObjects.spectralProfileData(1))[0]
        x = d['x']
        y = d['y']
        wlu = d['xUnit']

        values = band_values('NDVI', x, y, wavelength_unit=wlu)
        self.assertIsInstance(values, dict)
        self.assertTrue('NDVI' in values)
        self.assertIsInstance(values['NDVI'], float)

        b_indices = band_values('EVI', x, y, wavelength_unit=wlu, return_band_indices=True)
        b_values = band_values('EVI', x, y, wavelength_unit=wlu, return_band_indices=False, compute=False)

        for b in ['B', 'N', 'R']:
            self.assertTrue(b in b_indices)
            self.assertTrue(b in b_values)
            b_idx = b_indices[b]
            b_val = b_values[b]

            self.assertIsInstance(b_idx, int)
            self.assertEqual(y[b_idx], b_val)

        s = ""
        index_names = ['EVI', 'NDVI']
        from spyndex.axioms import indices, SpectralIndex

        for n in index_names:
            sidx: SpectralIndex = indices[n]
            b_values = band_values(sidx.bands, x, y, wavelength_unit=wlu)
            b_indices = band_values(sidx.bands, x, y, wavelength_unit=wlu, return_band_indices=True)
            self.assertIsInstance(b_indices, dict)
            self.assertIsInstance(b_values, dict)
            self.assertListEqual(list(b_values.keys()), list(b_indices.keys()))

            for b_name, b_idx in b_indices.items():
                if b_idx is not None:
                    b_value = b_values[b_name]
                    self.assertEqual(y[b_idx], b_value)

            value = sidx.compute(b_values)

            self.assertTrue(isinstance(value, (int, float)))

    @unittest.skipIf(not has_spyndex, 'spyndex package is missing')
    def test_spectral_index_function(self):

        self.registerFunction(SpectralData())

        fields = QgsFields()
        fields.append(QgsField("name", QMetaType.Type.QString))
        fields.append(SpectralLibraryUtils.createProfileField('p1', encoding=ProfileEncoding.Json))
        fields.append(SpectralLibraryUtils.createProfileField('p2', encoding=ProfileEncoding.Json))

        f = QgsFeature(fields)

        d1 = {
            'x': [400, 500, 600, 700, 800, 900, 1000],
            'y': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            'xUnit': 'nm'
        }
        f.setAttribute('p1', d1)
        context = QgsExpressionContext()
        context.setFeature(f)
        context.setFields(f.fields())

        exp = QgsExpression("spectral_data(\"p1\", band:='NDVI')")
        self.assertTrue(exp.prepare(context), msg=f"Failed to prepare expression: {exp.parserErrorString()}")
        result = exp.evaluate(context)
        self.assertEqual(result, 10)

    def test_required_bands_benchmark(self):
        n = 1000

        from qpstestdata import enmap
        lyr = QgsRasterLayer(str(enmap))
        sp = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        wl = sp.wavelengths()
        wlu = sp.wavelengthUnits()[0]
        band_names = list(BANDS.keys())
        n_bands = len(wl)

        BAND_INDEX_CACHE.clear()
        choices = random.choices(band_names, k=n)  # nosec: B311
        t0 = datetime.datetime.now()
        for b in choices:
            bi = band_index(b, wl, wlu=wlu, use_cache=False)
            self.assertTrue(bi is None or 0 <= bi < n_bands, msg=f'Failed to get index for band "{b}. Got {bi}"')
        t1 = datetime.datetime.now()
        for b in choices:
            bi = band_index(b, wl, wlu=wlu, use_cache=True)
            self.assertTrue(bi is None or 0 <= bi < n_bands)
        t2 = datetime.datetime.now()

        print(f'Sampling: {n}')
        print(f'No cache: {t1 - t0}')
        print(f'With cache: {t2 - t1}')

    def test_band_shortcut_descriptions(self):

        wl_nm = [400, 610, 650, 690, 700]
        results = band_shortcut_descriptions(wl_nm)
        self.assertIsInstance(results, list)

        def check_band(b: dict, wl: list, wlu: str = 'nm'):
            self.assertIsInstance(b, dict)
            for k in ['max_wavelength', 'min_wavelength', 'short_name', 'long_name']:
                self.assertTrue(k in b)

        for b in results:
            check_band(b, wl_nm)


if __name__ == '__main__':
    unittest.main()
