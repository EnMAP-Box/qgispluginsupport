import unittest

from qgis.core import QgsExpression, QgsExpressionContext

from qps.expressionfunctions.helpers import registerQgsExpressionFunctions
from qps.speclib.processing.aggregateprofiles import createSpectralProfileFunctions
from qps.testing import start_app, TestCase

start_app()


class AggregateFunctionsTests(TestCase):
    def test_aggregate_functions_registration(self):
        # Test that aggregate functions can be registered
        functions = createSpectralProfileFunctions()

        self.assertGreater(len(functions), 0)

        # Check that all functions have expected names
        function_names = [f.name() for f in functions]
        self.assertIn('mean_profile', function_names)
        self.assertIn('median_profile', function_names)
        self.assertIn('minimum_profile', function_names)
        self.assertIn('maximum_profile', function_names)

        # Test registration
        for func in functions:
            self.registerFunction(func)

    def test_spectral_profile_functions(self):
        # Test using registerQgsExpressionFunctions helper
        registerQgsExpressionFunctions()

        context = QgsExpressionContext()

        # Test mean_profile function
        exp = QgsExpression("mean_profile(NULL, NULL, NULL, 'map')")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)
        self.assertTrue(result is None or result is None)


if __name__ == '__main__':
    unittest.main()
