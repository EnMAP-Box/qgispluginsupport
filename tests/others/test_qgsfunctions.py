import unittest

from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields
from qgis.core import QgsExpressionFunction, QgsExpression, QgsExpressionContext, QgsProperty, QgsExpressionContextUtils
from qps.qgsfunctions import SpectralMath, HelpStringMaker, Format_Py, RasterProfile
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.testing import TestObjects, TestCase
from qps.utils import SpatialPoint


# from qgis.testing import start_app

# start_app()
class QgsFunctionTests(TestCase):
    """
    Tests for functions in the Field Calculator
    """

    def test_eval_geometry(self):

        # app = start_app()
        # app.initQgis()

        lyr = TestObjects.createRasterLayer(nb=25)
        lyr.setName('myraster')
        QgsProject.instance().addMapLayer(lyr)

        center = SpatialPoint.fromMapLayerCenter(lyr)

        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(center))
        context = QgsExpressionContextUtils.createFeatureBasedContext(f, QgsFields())
        exp = QgsExpression("geom_to_wkt($geometry)")
        value = exp.evaluate(context)

        exp = QgsExpression("raster_value('myraster', 1, $geometry)")
        assert exp.prepare(context), exp.parserErrorString()
        value = exp.evaluate(context)
        assert exp.evalErrorString() == '', exp.evalErrorString()

        f = RasterProfile()
        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        exp = QgsExpression("raster_profile('myraster', $geometry)")
        assert exp.prepare(context), exp.parserErrorString()
        value = exp.evaluate(context)
        assert exp.evalErrorString() == '', exp.evalErrorString()
        s = ""

    def test_raster_profile(self):

        f = RasterProfile()
        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        lyrR = TestObjects.createRasterLayer(nb=25)
        lyrR.setName('myraster')
        QgsProject.instance().addMapLayer(lyrR)

        uri = 'Point?'
        mem = QgsVectorLayer(uri, 'myvector', 'memory')
        mem.setCrs(lyrR.crs())
        self.assertTrue(mem.isValid())
        self.assertTrue(mem.startEditing())
        pt = SpatialPoint.fromMapLayerCenter(lyrR)
        feature = QgsFeature(mem.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(pt))
        self.assertTrue(mem.addFeature(feature))
        self.assertTrue(mem.commitChanges())

        expressions = [
            "raster_profile('myraster', $geometry)",
            "raster_profile('myraster', $geometry, 'bytes')",
            "raster_profile('myraster', $geometry, 'json')",
            "raster_profile('myraster', $geometry, 'text')",
        ]

        for e in expressions:
            exp = QgsExpression(e)
            feature = list(mem.getFeatures())[0]
            context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(mem))
            context.setFeature(feature)
            # context = QgsExpressionContextUtils.createFeatureBasedContext(feature, QgsFields())

            exp.prepare(context)
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

            result = exp.evaluate(context)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

            d = decodeProfileValueDict(result)
            self.assertIsInstance(d, dict)
            self.assertTrue(len(d) > 0)

        self.assertTrue(QgsExpression.unregisterFunction(f.name()))

    def test_SpectralMath(self):

        slib = TestObjects.createSpectralLibrary(10)
        f = SpectralMath()

        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)
        sl = TestObjects.createSpectralLibrary(1, n_bands=[20, 20], profile_field_names=['p1', 'p2'])
        profileFeature = list(sl.getFeatures())[0]
        context = QgsExpressionContext()
        context.setFeature(profileFeature)
        context = QgsExpressionContextUtils.createFeatureBasedContext(profileFeature, profileFeature.fields())

        expressions = [
            'SpectralMath(\'y=[1,2,3]\')',
            'SpectralMath("p1", \'\')',
            'SpectralMath("p1", \'\', \'text\')',
            'SpectralMath("p1", \'\', \'map\')',
            'SpectralMath("p1", \'\', \'bytes\')',
            'SpectralMath("p1", "p2", \'y=y1/y2\')',
        ]

        for e in expressions:
            exp = QgsExpression(e)
            exp.prepare(context)
            self.assertEqual(exp.parserErrorString(), '', msg=exp.parserErrorString())
            result = exp.evaluate(context)
            d = decodeProfileValueDict(result)
            self.assertIsInstance(d, dict)
            self.assertTrue(len(d) > 0)
            self.assertEqual(exp.evalErrorString(), '', msg=exp.evalErrorString())

            prop = QgsProperty.fromExpression(exp.expression())
            result, success = prop.value(context, None)
            self.assertTrue(success)

        self.assertTrue(QgsExpression.isFunctionName(f.name()))

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
    unittest.main(buffer=False)
