import unittest

from qgis.core import QgsExpression, QgsExpressionContext

from qps.expressionfunctions import StaticExpressionFunction
from qps.testing import start_app, TestCase

start_app()


class StaticExpressionFunctionTests(TestCase):
    def test_static_expression_function(self):
        # Create a simple function
        def test_func(values, context, parent, node):
            return 'test_result'

        f = StaticExpressionFunction(
            fnname='test_static_func',
            params=[],
            fcn=test_func,
            group='Test Group'
        )

        self.registerFunction(f)

        context = QgsExpressionContext()

        # Test the function
        exp = QgsExpression("test_static_func()")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)
        self.assertEqual(result, 'test_result')


if __name__ == '__main__':
    unittest.main()
