"""
see https://github.com/qgis/QGIS/issues/47127
"""
import unittest

from qgis.PyQt.QtXml import QDomDocument
from qgis._core import QgsExpressionContext
from qgis.core import QgsProperty, QgsXmlUtils, QgsExpression
from qgis.testing import start_app, TestCase

p = QgsProperty()

s = ""
start_app()


class TestCase(TestCase):
    def test_QgsProperty_XML(self):
        p1 = QgsProperty()
        p1.setExpressionString('')
        self.assertEqual(p1.propertyType(), QgsProperty.ExpressionBasedProperty)
        self.assertTrue(p1.isActive())

        doc = QDomDocument()
        node = QgsXmlUtils.writeVariant(p1, doc)

        # check what is read from XML
        p2 = QgsXmlUtils.readVariant(node)
        self.assertIsInstance(p2, QgsProperty)
        self.assertEqual(p2.expressionString(), p1.expressionString())
        self.assertEqual(p2.propertyType(), p1.propertyType())

        # this evaluates to false
        self.assertEqual(p2.isActive(), p1.isActive())
        self.assertEqual(p2, p1)


if __name__ == '__main__':
    unittest.main()
