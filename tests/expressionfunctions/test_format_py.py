import unittest

from qgis.core import QgsExpression, QgsExpressionContext

from qps.expressionfunctions import Format_Py
from qps.testing import start_app, TestCase

start_app()


class FormatPyTests(TestCase):
    def test_format_py(self):
        f = Format_Py()

        if not QgsExpression.isFunctionName(f.name()):
            self.assertTrue(QgsExpression.registerFunction(f))

        context = QgsExpressionContext()

        exp = QgsExpression("format_py('Hello {}', 'World')")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)
        self.assertEqual(result, 'Hello World')

        exp = QgsExpression("format_py('{} + {} = {}', 2, 2, 4)")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)
        self.assertEqual(result, '2 + 2 = 4')


if __name__ == '__main__':
    unittest.main()
