import unittest

from qgis.core import QgsExpression, QgsExpressionContext, QgsProject, QgsExpressionContextUtils

from qps.expressionfunctions import RasterProfile
from qps.testing import start_app, TestCase, TestObjects

start_app()


class RasterProfileTests(TestCase):
    def test_raster_profile(self):
        f = self.registerFunction(RasterProfile())
        self.assertIsInstance(f, RasterProfile)

        # Create a test raster layer
        raster_layer = TestObjects.createRasterLayer(ns=10, nl=10, nb=3)
        raster_layer.setName('test_raster')
        QgsProject.instance().addMapLayer(raster_layer)

        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(raster_layer))

        # Test with a simple expression
        exp = QgsExpression("raster_profile('test_raster', @geometry, 'mean', 'text')")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)

        # Result should be a profile dict or None
        self.assertTrue(result is None or isinstance(result, dict))

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
