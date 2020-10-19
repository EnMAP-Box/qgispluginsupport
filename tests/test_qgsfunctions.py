import unittest, pathlib
import xml.etree.ElementTree as ET
from qgis.core import QgsExpressionFunction, QgsExpression
from qps.testing import TestObjects
from qps.resources import *
from qps import QPS_RESOURCE_FILE
from qps.speclib.qgsfunctions import SpectralMath, HelpStringMaker

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
