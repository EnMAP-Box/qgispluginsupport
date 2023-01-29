import re
import unittest

from qgis.PyQt.QtCore import QByteArray
from osgeo import gdal_array

from qgis.core import QgsCoordinateTransform
from qgis.core import QgsExpressionFunction, QgsExpression, QgsExpressionContext, QgsProperty, QgsExpressionContextUtils
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields
from qps.qgsfunctions import SpectralMath, HelpStringMaker, Format_Py, RasterProfile, RasterArray
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

        lyr = TestObjects.createRasterLayer(nb=25)
        lyr.setName('myraster')
        QgsProject.instance().addMapLayer(lyr)

        center = SpatialPoint.fromMapLayerCenter(lyr)

        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(center))
        context = QgsExpressionContextUtils.createFeatureBasedContext(feature, QgsFields())

        exp = QgsExpression("geom_to_wkt($geometry)")
        value = exp.evaluate(context)

        exp = QgsExpression("raster_value('myraster', 1, $geometry)")
        assert exp.prepare(context), exp.parserErrorString()
        b1value = exp.evaluate(context)
        assert exp.evalErrorString() == '', exp.evalErrorString()

        f1 = RasterArray()
        self.assertIsInstance(f1, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f1))
        exp = QgsExpression("raster_array('myraster', $geometry)")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        v_array = exp.evaluate(context)
        self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

        f2 = RasterProfile()
        self.assertIsInstance(f2, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f2))
        exp = QgsExpression("raster_profile('myraster', $geometry)")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        v_profile = exp.evaluate(context)
        self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
        self.assertListEqual(v_array, v_profile['y'])

    def test_RasterArray(self):

        f = RasterArray()
        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        lyrR, lyrV = self.createRasterAndVectorLayers()

        expressions = [
            f"{f.name()}('{lyrR.name()}')",
            f"{f.name()}('{lyrR.id()}')",
            f"{f.name()}('{lyrR.name()}', @geometry)",
            f"{f.name()}('{lyrR.name()}', $geometry)",
        ]

        RASTER_ARRAY = gdal_array.LoadFile(lyrR.source())
        for e in expressions:
            context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))
            exp = QgsExpression(e)
            for i, feature in enumerate(lyrV.getFeatures()):
                self.assertIsInstance(feature, QgsFeature)
                context.setFeature(feature)

                exp.prepare(context)

                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

                profile = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profile, list, msg=exp.expression())
                pt = SpatialPoint(lyrV.crs(), feature.geometry().asPoint())
                px = pt.toPixelPosition(lyrR)

                profile_ref = RASTER_ARRAY[:, px.y(), px.x()]
                for p, pref in zip(profile, profile_ref):
                    self.assertEqual(p, pref)
                s = ""

        self.assertTrue(QgsExpression.unregisterFunction(f.name()))

    def createRasterAndVectorLayers(self):
        lyrR = TestObjects.createRasterLayer(nb=25)
        lyrR.setName('myraster')
        QgsProject.instance().addMapLayer(lyrR)
        uri = "point?crs=epsg:4326&field=id:integer"
        lyrV = QgsVectorLayer(uri, 'myvector', 'memory')
        self.assertTrue(lyrV.isValid())
        self.assertTrue(lyrV.startEditing())
        pt1 = SpatialPoint.fromMapLayerCenter(lyrR).toCrs(lyrV.crs())
        feature1 = QgsFeature(lyrV.fields())
        feature1.setGeometry(QgsGeometry.fromPointXY(pt1))

        pt2 = SpatialPoint.fromPixelPosition(lyrR, 1, 1).toCrs(lyrV.crs())

        pxPos = pt2.toPixelPosition(lyrR)

        feature2 = QgsFeature(lyrV.fields())
        feature2.setGeometry(QgsGeometry.fromPointXY(pt2))
        self.assertTrue(lyrV.addFeature(feature1))
        self.assertTrue(lyrV.addFeature(feature2))
        self.assertTrue(lyrV.commitChanges())

        return lyrR, lyrV

    def test_RasterProfile(self):

        f = RasterProfile()

        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        lyrR, lyrV = self.createRasterAndVectorLayers()

        expressions = [
            f"{f.name()}('{lyrR.name()}')",
            f"{f.name()}('{lyrR.name()}', $geometry)",
            f"{f.name()}('{lyrR.name()}', $geometry, 'bytes')",
            f"{f.name()}('{lyrR.name()}', $geometry, 'json')",
            f"{f.name()}('{lyrR.name()}', $geometry, 'text')",
            f"{f.name()}('{lyrR.name()}', encoding:='text')",
        ]

        for e in expressions:
            context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))
            exp = QgsExpression(e)
            for i, feature in enumerate(lyrV.getFeatures()):
                self.assertIsInstance(feature, QgsFeature)
                context.setFeature(feature)
                # context = QgsExpressionContextUtils.createFeatureBasedContext(feature, QgsFields())
                if i > 0:
                    self.assertIsInstance(context.cachedValue('crs_trans'), QgsCoordinateTransform)
                    self.assertIsInstance(context.cachedValue(f.CACHED_SPECTRAL_PROPERTIES), dict)
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

                profile = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                if re.search(r'(bytes)', exp.expression()):
                    self.assertIsInstance(profile, QByteArray)
                elif re.search(r'(text|json)', exp.expression()):
                    self.assertIsInstance(profile, str)
                else:
                    self.assertIsInstance(profile, dict, msg=exp.expression())

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

    def test_Format_Py(self):
        f = Format_Py()
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())
        self.assertIsInstance(html, str)
        self.assertTrue(QgsExpression.unregisterFunction(f.name()))


if __name__ == '__main__':
    unittest.main(buffer=False)
