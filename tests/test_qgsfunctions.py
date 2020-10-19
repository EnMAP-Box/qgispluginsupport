import unittest
import xmlrunner
from qgis.core import QgsExpressionFunction, QgsExpression
from qps.speclib.qgsfunctions import SpectralMath, HelpStringMaker
from qps.testing import TestObjects


class QgsFunctionTests(unittest.TestCase):

    def test_SpectralMath(self):
        slib = TestObjects.createSpectralLibrary(10)
        f = SpectralMath()

        self.assertIsInstance(f, QgsExpressionFunction)
        b = QgsExpression.registerFunction(f)
        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        exp = QgsExpression("SpectralMath('foobar')")
        self.assertTrue(QgsExpression.isFunctionName(f.name()))
        h = QgsExpression.helpText(f.name())
        s = ""


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
