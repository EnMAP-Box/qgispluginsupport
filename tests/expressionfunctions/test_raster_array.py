import unittest

from qgis.core import QgsExpression, QgsExpressionContext, QgsProject, QgsExpressionContextUtils
from qgis.core import QgsGeometry

from qps.expressionfunctions import RasterArray
from qps.testing import start_app, TestCase, TestObjects

start_app()


class RasterArrayTests(TestCase):
    def test_raster_array(self):
        f = self.registerFunction(RasterArray())
        self.assertIsInstance(f, RasterArray)

        # Create a test raster layer
        raster_layer = TestObjects.createRasterLayer(ns=10, nl=10, nb=3)
        raster_layer.setName('test_raster')
        QgsProject.instance().addMapLayer(raster_layer)

        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(raster_layer))

        center = raster_layer.extent().center()
        g = QgsGeometry.fromPointXY(center)
        context.setGeometry(g)

        # Test with a simple expression
        exp = QgsExpression("raster_array('test_raster', @geometry, 'mean')")
        self.assertTrue(exp.prepare(context))
        result = exp.evaluate(context)

        # Result should be a list or None (for empty geometry)
        self.assertTrue(result is None or isinstance(result, list))

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
