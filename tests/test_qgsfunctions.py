import unittest
import xmlrunner
from qgis.core import QgsExpressionFunction, QgsExpression
from qps.qgsfunctions import SpectralMath, HelpStringMaker, Format_Py
from qps.testing import TestObjects


class QgsFunctionTests(unittest.TestCase):

    def test_SpectralMath(self):
        slib = TestObjects.createSpectralLibrary(10)
        f = SpectralMath()

        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        exp = QgsExpression("SpectralMath('foobar')")
        self.assertTrue(QgsExpression.isFunctionName(f.name()))
        h = QgsExpression.helpText(f.name())
        self.assertTrue(QgsExpression.unregisterFunction(f.name()))

    def test_format_py(self):
        f = Format_Py()
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())
        self.assertIsInstance(html, str)
        self.assertTrue(QgsExpression.unregisterFunction(f.name()))


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
