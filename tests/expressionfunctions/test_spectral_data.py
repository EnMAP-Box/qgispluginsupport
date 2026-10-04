import datetime
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
from qps.utils import BAND_INDEX_CACHE, band_index, band_shortcut_descriptions

start_app()


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

    def test_band_values(self):

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
