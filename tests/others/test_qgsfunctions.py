import re
import unittest
from osgeo import gdal_array

import processing
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.utils import SpatialExtent
from qgis.PyQt.QtCore import QByteArray, QVariant
from qgis.core import QgsWkbTypes
from qgis.core import QgsField
from qgis.core import QgsCoordinateTransform
from qgis.core import QgsExpressionFunction, QgsExpression, QgsExpressionContext, QgsProperty, QgsExpressionContextUtils
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields
from qgis.gui import QgsFieldCalculator
from qps.qgsfunctions import SpectralMath, HelpStringMaker, Format_Py, RasterProfile, RasterArray, SpectralData, \
    SpectralEncoding, registerQgsExpressionFunctions
from qps.speclib.core import profile_fields
from qps.speclib.core.spectralprofile import decodeProfileValueDict, isProfileValueDict
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

    def test_SpectralEncoding(self):

        f = SpectralEncoding()
        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24, 255], profile_field_names=['p1', 'p2'])
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        for sfield in profile_fields(sl).names():
            # 'text', 'json', 'map' or 'bytes'

            for feature in sl.getFeatures():
                context.setFeature(feature)
                exp = QgsExpression(f'{f.name()}("{sfield}", \'text\')')
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertIsInstance(profile, str)

                exp = QgsExpression(f'{f.name()}("{sfield}", \'json\')')
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertIsInstance(profile, str)

                exp = QgsExpression(f'{f.name()}("{sfield}", \'map\')')
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertIsInstance(profile, dict)

                exp = QgsExpression(f'{f.name()}("{sfield}", \'bytes\')')
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertIsInstance(profile, QByteArray)

    def test_SpectralData(self):

        f = SpectralData()
        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))

        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24, 255], profile_field_names=['p1', 'p2'])
        sfields = profile_fields(sl)

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(sl))
        for n in sfields.names():
            exp = QgsExpression(f'{f.name()}("{n}")')
            for feature in sl.getFeatures():
                context.setFeature(feature)
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertTrue(isProfileValueDict(profile))

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
                    k = f'crstrans_{context.variable("layer_id")}->{lyrR.id()}'
                    self.assertIsInstance(context.cachedValue(k), QgsCoordinateTransform)
                    k = f'spectralproperties_{lyrR.id()}'
                    self.assertIsInstance(context.cachedValue(k), dict)
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

    def test_RasterProfile2(self):

        f = RasterProfile()

        self.assertIsInstance(f, QgsExpressionFunction)
        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))
        lyrRaster = TestObjects.createRasterLayer(nb=100)
        lyrRaster.setName('EnMAP')
        lyrPoints = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.GeometryType.PointGeometry, n_features=3)

        extR = SpatialExtent.fromLayer(lyrRaster)
        extP = SpatialExtent.fromLayer(lyrPoints).toCrs(lyrRaster.crs())
        self.assertTrue(extR.contains(extP))
        s = ""

        QgsProject.instance().addMapLayers([lyrRaster, lyrPoints])
        results = processing.run("native:fieldcalculator",
                                 {'INPUT': lyrPoints,
                                  'FIELD_NAME': 'profiles', 'FIELD_TYPE': 2, 'FIELD_LENGTH': 0, 'FIELD_PRECISION': 0,
                                  'FORMULA': " raster_profile('EnMAP')", 'OUTPUT': 'TEMPORARY_OUTPUT'},
                                 )
        lyrSpeclib: QgsVectorLayer = results['OUTPUT']
        lyrSpeclib.setName('Spectral Library')
        SpectralLibraryUtils.setAsProfileField(lyrSpeclib, 'profiles')

        for f in lyrSpeclib.getFeatures():
            f: QgsFeature
            jsonStr = f.attribute('profiles')

            d = decodeProfileValueDict(jsonStr)
            self.assertTrue(isProfileValueDict(d))
            self.assertTrue(len(d['y']) == lyrRaster.bandCount())
            s = ""

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

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
    def test_functiondialog(self):
        functions = [
            Format_Py(),
            RasterArray(),
            RasterProfile(),
            SpectralMath(),
            SpectralData(),
            SpectralEncoding(),
        ]
        for f in functions:
            self.assertTrue(QgsExpression.registerFunction(f))
            self.assertTrue(QgsExpression.isFunctionName(f.name()))

        sl = TestObjects.createSpectralLibrary()

        gui = QgsFieldCalculator(sl, None)
        gui.exec_()

    def test_aggragation_functions(self):

        registerQgsExpressionFunctions()

        sl = TestObjects.createSpectralLibrary(n=10, n_bands=[25, 50], profile_field_names=['P1', 'P2'])
        sl.setName('speclib')
        sl.startEditing()
        sl.addAttribute(QgsField('class', QVariant.String))
        sl.commitChanges(False)

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        idx = sl.fields().lookupField('class')
        for i, f in enumerate(sl.getFeatures()):
            name = 'A'
            if i > 3:
                name = 'B'
            sl.changeAttributeValue(f.id(), idx, name)

        sl.commitChanges()
        fname = profile_fields(sl.fields())[0].name()
        classes = sl.uniqueValues(idx)
        """
        mean_profile("profiles0",group_by:="state") → mean population value, grouped by state field
        """
        exp = QgsExpression(f'mean_profile("{fname}", group_by:=\'class\')')
        exp.prepare(context)
        self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

        profile = exp.evaluate(context)
        self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
