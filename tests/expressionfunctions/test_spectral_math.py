import unittest

from qgis.core import QgsExpression, QgsExpressionContext

from qps.expressionfunctions import SpectralMath
from qps.testing import start_app, TestCase

start_app()


class SpectralMathTests(TestCase):
    def test_spectral_math(self):
        f = self.registerFunction(SpectralMath())
        self.assertIsInstance(f, SpectralMath)

        context = QgsExpressionContext()

        # Test with NULL values
        exp = QgsExpression("spectral_math(NULL, NULL, 'y1')")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)
        self.assertTrue(result is None or result is None)


if __name__ == '__main__':
    unittest.main()
