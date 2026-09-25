import unittest

from qgis.core import QgsExpression, QgsExpressionContext, QgsProject, QgsExpressionContextUtils


from qps.expressionfunctions import SpectralData
from qps.testing import start_app, TestCase, TestObjects

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


if __name__ == '__main__':
    unittest.main()
