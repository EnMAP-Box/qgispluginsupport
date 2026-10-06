import unittest

from qgis.PyQt.QtCore import QByteArray
from qgis.core import QgsExpression, QgsExpressionContext, QgsProject, QgsExpressionContextUtils

from qps.expressionfunctions import SpectralEncoding
from qps.speclib.core import profile_fields
from qps.testing import start_app, TestCase, TestObjects

start_app()


class SpectralEncodingTests(TestCase):
    def test_spectral_encoding(self):

        f = self.registerFunction(SpectralEncoding())
        self.assertIsInstance(f, SpectralEncoding)

        # Test 2: Test function directly with a profile dict
        profileDict = {'x': [1, 2, 3], 'y': [10, 20, 30], 'xUnit': 'nm'}
        test_context = QgsExpressionContext()

        # Test with different encodings using the function directly
        for encoding in ['text', 'json', 'map', 'bytes']:
            encoding_param = encoding if encoding != 'map' else 'dict'
            result = f.func([profileDict, encoding_param], test_context, None, None)
            self.assertIsNotNone(result, f"Direct function call failed for encoding {encoding}")
            if encoding == 'text':
                self.assertIsInstance(result, str)
            elif encoding in ['json', 'map', 'dict']:
                self.assertIsInstance(result, dict)
            elif encoding == 'bytes':
                self.assertIsInstance(result, QByteArray)

        # Test 3: Test with expression
        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24], profile_field_names=['p1'])
        QgsProject.instance().addMapLayer(sl)
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        for feature in sl.getFeatures():
            context.setFeature(feature)
            for sfield in profile_fields(sl).names():
                profile_value = feature.attribute(sfield)
                # The profile value should be encoded (string, bytes, etc.)
                self.assertIsNotNone(profile_value)

                # Test text encoding
                exp1 = QgsExpression(f'{f.name()}("{sfield}", \'text\')')
                self.assertTrue(exp1.prepare(context))
                result = exp1.evaluate(context)
                self.assertIsInstance(result, str)

                exp2 = QgsExpression(f'{f.name()}("{sfield}", \'map\')')
                self.assertTrue(exp2.prepare(context))
                result = exp2.evaluate(context)
                self.assertIsInstance(result, dict)
                self.assertTrue(result != {})

                # The function might return None if profile value is not valid
                # This is okay - we're just testing that the function works
                break
            break

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
