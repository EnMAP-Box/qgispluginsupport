import json
import unittest

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, \
    QgsExpressionContext, QgsExpressionContextUtils, QgsExpressionContextScope, \
    QgsGeometry, QgsProject
from qgis.core import QgsPointXY

from qps.expressionfunctions.helpers import ExpressionFunctionUtils
from qps.speclib.core.spectralprofile import ProfileEncoding
from qps.testing import start_app, TestCase, TestObjects

start_app()


class ExpressionFunctionUtilsTests(TestCase):

    def setUp(self):
        self.mRasterLayer = TestObjects.createRasterLayer(ns=10, nl=10, nb=3)
        self.mRasterLayer.setName('test_raster')
        QgsProject.instance().addMapLayer(self.mRasterLayer)

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        super().tearDown()

    def test_parameter(self):
        from qps.expressionfunctions.raster_profile import RasterProfile

        f = RasterProfile()
        param = ExpressionFunctionUtils.parameter(f, 'layer')
        self.assertIsNotNone(param)
        self.assertEqual(param.name(), 'layer')

        with self.assertRaises(NotImplementedError):
            ExpressionFunctionUtils.parameter(f, 'nonexistent_parameter')

    def test_cachedSpectralPropertiesKey(self):
        key = ExpressionFunctionUtils.cachedSpectralPropertiesKey(self.mRasterLayer)
        self.assertIn('spectralproperties_', key)
        self.assertIn(self.mRasterLayer.id(), key)

    def test_cachedNoDataValues(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        nodata1 = ExpressionFunctionUtils.cachedNoDataValues(context, self.mRasterLayer)
        self.assertIsInstance(nodata1, dict)

        nodata2 = ExpressionFunctionUtils.cachedNoDataValues(context, self.mRasterLayer)
        self.assertEqual(nodata1, nodata2)

    def test_cachedScaleValues(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        scales1 = ExpressionFunctionUtils.cachedScaleValues(context, self.mRasterLayer)
        self.assertIsInstance(scales1, dict)
        self.assertGreater(len(scales1), 0)

        for band, (offset, scale) in scales1.items():
            self.assertIsInstance(band, int)
            self.assertIsInstance(offset, float)
            self.assertIsInstance(scale, float)

        scales2 = ExpressionFunctionUtils.cachedScaleValues(context, self.mRasterLayer)
        self.assertEqual(list(scales1), list(scales2))

    def test_cachedSpectralProperties(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        props1 = ExpressionFunctionUtils.cachedSpectralProperties(context, self.mRasterLayer)
        self.assertIsInstance(props1, dict)
        self.assertIn('bbl', props1)
        self.assertIn('wl', props1)
        self.assertIn('wlu', props1)

        props2 = ExpressionFunctionUtils.cachedSpectralProperties(context, self.mRasterLayer)
        self.assertEqual(props1, props2)

    def test_cachedCrsTransformationKey(self):
        context = QgsExpressionContext()
        scope = QgsExpressionContextScope()
        scope.setVariable('layer_id', 'test_layer_id')
        context.appendScope(scope)

        source_layer = TestObjects.createVectorLayer(0)
        key = ExpressionFunctionUtils.cachedCrsTransformationKey(context, source_layer)
        self.assertIn('test_layer_id', key)
        self.assertIn(source_layer.id(), key)

    def test_cachedCrsTransformation_with_same_crs(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        transform = ExpressionFunctionUtils.cachedCrsTransformation(context, self.mRasterLayer)
        self.assertIsInstance(transform, QgsCoordinateTransform)
        self.assertTrue(transform.sourceCrs().isValid())
        self.assertTrue(transform.destinationCrs().isValid())

    def test_cachedCrsTransformation_with_different_crs(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))

        layer_4326 = TestObjects.createRasterLayer(ns=10, nl=10, nb=1)
        layer_4326.setName('test_raster_4326')
        layer_4326.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        QgsProject.instance().addMapLayer(layer_4326)

        context.appendScope(QgsExpressionContextUtils.layerScope(layer_4326))

        transform = ExpressionFunctionUtils.cachedCrsTransformation(context, layer_4326)
        self.assertIsInstance(transform, QgsCoordinateTransform)

        QgsProject.instance().removeMapLayer(layer_4326)

    def test_extractSpectralProfileEncoding(self):
        param = None
        context = QgsExpressionContext()

        encoding1 = ExpressionFunctionUtils.extractSpectralProfileEncoding(param, 'bytes', context)
        self.assertEqual(encoding1, ProfileEncoding.Bytes)

        encoding2 = ExpressionFunctionUtils.extractSpectralProfileEncoding(param, 'json', context)
        self.assertEqual(encoding2, ProfileEncoding.Json)

        encoding3 = ExpressionFunctionUtils.extractSpectralProfileEncoding(param, 'text', context)
        self.assertEqual(encoding3, ProfileEncoding.Text)

    def test_extractRasterLayer(self):
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        param = None

        lyr1 = ExpressionFunctionUtils.extractRasterLayer(param, self.mRasterLayer.name(), context)
        self.assertEqual(lyr1, self.mRasterLayer)

        lyr2 = ExpressionFunctionUtils.extractRasterLayer(param, self.mRasterLayer.id(), context)
        self.assertEqual(lyr2, self.mRasterLayer)

        lyr3 = ExpressionFunctionUtils.extractRasterLayer(param, self.mRasterLayer, context)
        self.assertEqual(lyr3, self.mRasterLayer)

        lyr4 = ExpressionFunctionUtils.extractRasterLayer(param, 'nonexistent_layer', context)
        self.assertIsNone(lyr4)

        lyr5 = ExpressionFunctionUtils.extractRasterLayer(param, 123, context)
        self.assertIsNone(lyr5)

    def test_extractSpectralProfile(self):
        context = QgsExpressionContext()

        param = None

        profile_dict = {'x': [1, 2, 3], 'y': [10, 20, 30]}
        profile1 = ExpressionFunctionUtils.extractSpectralProfile(param, profile_dict, context)
        self.assertEqual(profile1, profile_dict)

        profile_json = json.dumps({'x': [1, 2, 3], 'y': [10, 20, 30]})
        profile2 = ExpressionFunctionUtils.extractSpectralProfile(param, profile_json, context)
        self.assertIsNotNone(profile2)
        self.assertIn('x', profile2)
        self.assertIn('y', profile2)

        profile3 = ExpressionFunctionUtils.extractSpectralProfile(param, None, context)
        self.assertIsNone(profile3)

        profile4 = ExpressionFunctionUtils.extractSpectralProfile(param, '{}', context)
        self.assertIsNone(profile4)

        profile5 = ExpressionFunctionUtils.extractSpectralProfile(param, {}, context)
        self.assertIsNone(profile5)

    def test_extractGeometry_with_at_geometry_variable(self):

        for g1 in [
            QgsGeometry.fromPointXY(QgsPointXY(1.0, 2.0)),
            QgsExpression('make_point(0, 0)').evaluate(QgsExpressionContext())
        ]:
            param = None
            context = QgsExpressionContext()
            context.setGeometry(g1)
            geom2 = ExpressionFunctionUtils.extractGeometry(param, '@geometry', context)
            self.assertIsInstance(geom2, QgsGeometry)
            self.assertGeometriesEqual(geom2, g1)

            geom3 = ExpressionFunctionUtils.extractGeometry(param, '$geometry', context)
            self.assertIsInstance(geom3, QgsGeometry)
            self.assertGeometriesEqual(geom3, g1)

            geom4 = ExpressionFunctionUtils.extractGeometry(param, g1, context)
            self.assertIsInstance(geom4, QgsGeometry)
            self.assertGeometriesEqual(geom4, g1)

    def test_extractGeometry_with_feature(self):
        context = QgsExpressionContext()

        param = None
        feature = TestObjects.createVectorLayer(0).getFeatures().__next__()
        scope = QgsExpressionContextScope()
        scope.setFeature(feature)
        context.appendScope(scope)

        geom4 = ExpressionFunctionUtils.extractGeometry(param, None, context)
        self.assertIsInstance(geom4, QgsGeometry)

    def test_extractGeometry_with_empty_geometry(self):
        context = QgsExpressionContext()

        param = None
        geom5 = ExpressionFunctionUtils.extractGeometry(param, None, context)
        self.assertIsInstance(geom5, QgsGeometry)

    def test_extractValues(self):
        from qps.expressionfunctions.raster_profile import RasterProfile

        f = RasterProfile()
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mRasterLayer))

        values = (self.mRasterLayer.name(), QgsGeometry(), 'bytes', 'mean')
        results = ExpressionFunctionUtils.extractValues(f, values, context)

        self.assertEqual(len(results), len(values))


if __name__ == '__main__':
    unittest.main()
