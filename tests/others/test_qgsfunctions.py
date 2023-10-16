import json
import re
import unittest

 import numpy as np
from osgeo import gdal_array

from qgis.PyQt.QtCore import QByteArray, QVariant
from qgis.core import QgsRasterLayer, QgsPointXY
from qgis.core import Qgis
from qgis.core import QgsCoordinateTransform
from qgis.core import QgsExpressionFunction, QgsExpression, QgsExpressionContext, QgsProperty, QgsExpressionContextUtils
from qgis.core import QgsField
from qgis.core import QgsMapLayerStore
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsFields
from qgis.core import QgsWkbTypes
from qgis.gui import QgsFieldCalculator
from qps.qgsfunctions import SpectralMath, HelpStringMaker, Format_Py, RasterProfile, RasterArray, SpectralData, \
    SpectralEncoding, ExpressionFunctionUtils
from qps.speclib.core import profile_fields
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import decodeProfileValueDict, isProfileValueDict
from qps.testing import TestObjects, TestCaseBase, start_app
from qps.utils import SpatialExtent
from qps.utils import SpatialPoint
from qpstestdata import enmap, enmap_multipolygon, enmap_pixel

start_app()


class QgsFunctionTests(TestCaseBase):
    """
    Tests for functions in the Field Calculator
    """
    FUNC_REFS = []

    def test_eval_geometry(self):

        lyr = TestObjects.createRasterLayer(nb=25)
        lyr.setName('myraster')
        QgsProject.instance().addMapLayer(lyr)

        center = SpatialPoint.fromMapLayerCenter(lyr)

        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(center))
        context = QgsExpressionContextUtils.createFeatureBasedContext(feature, QgsFields())
        # context.setLoadedLayerStore(QgsProject.instance().layerStore())

        exp = QgsExpression("geom_to_wkt($geometry)")
        value = exp.evaluate(context)

        exp = QgsExpression("raster_value('myraster', 1, $geometry)")
        assert exp.prepare(context), exp.parserErrorString()
        b1value = exp.evaluate(context)
        assert exp.evalErrorString() == '', exp.evalErrorString()

        f1 = RasterArray()
        self.registerFunction(f1)
        exp = QgsExpression(f"{f1.NAME}('myraster', $geometry)")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        v_array = exp.evaluate(context)
        self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

        f2 = RasterProfile()
        self.registerFunction(f2)
        exp = QgsExpression(f"{f2.NAME}('myraster', $geometry, encoding:='map')")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        v_profile = exp.evaluate(context)
        self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
        self.assertListEqual(v_array, v_profile['y'])
        QgsProject.instance().removeAllMapLayers()

    def test_SpectralEncoding(self):

        f = SpectralEncoding()
        self.registerFunction(f)

        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24, 255], profile_field_names=['p1', 'p2'])
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

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
        QgsProject.instance().removeAllMapLayers()

    def test_SpectralData(self):

        f = SpectralData()
        self.registerFunction(f)

        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24, 255], profile_field_names=['p1', 'p2'])
        sfields = profile_fields(sl)

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))
        QgsProject.instance().addMapLayer(sl)
        for n in sfields.names():
            exp = QgsExpression(f'{f.name()}("{n}")')
            for feature in sl.getFeatures():
                context.setFeature(feature)
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                profileDict = decodeProfileValueDict(profile)
                self.assertTrue(isProfileValueDict(profileDict))
        QgsProject.instance().removeAllMapLayers()

    def test_RasterArray(self):

        f = RasterArray()
        self.registerFunction(f)

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        lyrR = QgsRasterLayer(enmap, 'EnMAP')
        lyrSP = QgsVectorLayer(enmap_pixel, 'SinglePoint')
        lyrMP = QgsVectorLayer(enmap_multipolygon, 'MultiPoly')
        QgsProject.instance().addMapLayers([lyrR, lyrMP])

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrMP))
        for i, feature in enumerate(lyrMP.getFeatures()):
            self.assertIsInstance(feature, QgsFeature)
            context.setFeature(feature)

            gPoly = feature.geometry()
            bb = gPoly.boundingBox()
            p1 = bb.center()
            p2 = QgsPointXY(bb.xMinimum(), bb.yMaximum())
            gSPoint = QgsGeometry.fromPointXY(p1)
            gMPoint = QgsGeometry.fromMultiPointXY([p1])
            gLine = QgsGeometry.fromPolylineXY([p1, p2])

            values = [lyrR, gSPoint, 'none', False]
            a = np.asarray(f.func(values, context, None, None))
            self.assertEqual(a.ndim, 1)
            self.assertEqual(len(a), lyrR.bandCount())

            for g in [gMPoint, gLine, gPoly]:
                values = [lyrR, QgsGeometry(g), 'none', False]
                a = np.asarray(f.func(values, context, None, None))
                self.assertEqual(a.ndim, 2, msg=f'ndim != 2 for geometry {g}')
                self.assertEqual(a.shape[0], lyrR.bandCount())

                values = [lyrR, QgsGeometry(g), 'mean', False]
                a = np.asarray(f.func(values, context, None, None))
                self.assertEqual(a.ndim, 1, msg=f'ndim != 1 for aggregated geometry {g}')
                self.assertEqual(len(a), lyrR.bandCount())

        expressions = [
            f"{f.name()}('{lyrR.name()}')",
            f"{f.name()}('{lyrR.id()}')",
            f"{f.name()}('{lyrR.name()}', @geometry)",
            f"{f.name()}('{lyrR.name()}', $geometry)",
        ]

        RASTER_ARRAY = gdal_array.LoadFile(lyrR.source())
        for e in expressions:
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrMP))
            exp = QgsExpression(e)
            for i, feature in enumerate(lyrSP.getFeatures()):
                self.assertIsInstance(feature, QgsFeature)
                context.setFeature(feature)

                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

                profile = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profile, list, msg=exp.expression())
                pt = SpatialPoint(lyrSP.crs(), feature.geometry().asPoint())
                px = pt.toPixelPosition(lyrR)

                profile_ref = RASTER_ARRAY[:, px.y(), px.x()]
                for p, pref in zip(profile, profile_ref):
                    self.assertEqual(p, pref)
                s = ""

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrMP))

        for feature in lyrMP.getFeatures():
            context.setFeature(feature)
            exp = QgsExpression(f"{f.name()}('EnMAP', aggregate:='none')")
            exp.prepare(context)
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
            array = np.asarray(exp.evaluate(context))
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertIsInstance(array, np.ndarray)
            self.assertEqual(array.ndim, 2)
            self.assertEqual(array.shape[0], lyrR.bandCount())
            self.assertTrue(array.shape[1] > 0)

            exp = QgsExpression(f"{f.name()}('EnMAP', aggregate:='none', t:=true)")
            exp.prepare(context)
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
            arr1 = np.asarray(exp.evaluate(context))
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

            exp = QgsExpression(f"{f.name()}('EnMAP', aggregate:='none', t:=false)")
            exp.prepare(context)
            arr2 = np.asarray(exp.evaluate(context))
            self.assertEqual(arr1.ndim, 2)
            self.assertTrue(np.array_equal(arr2, arr1.transpose()))

            exp = QgsExpression(f"{f.name()}('EnMAP', aggregate:='median')")
            exp.prepare(context)
            array = np.asarray(exp.evaluate(context))
            self.assertEqual(array.shape, (lyrR.bandCount(),))

            exp = QgsExpression(f"{f.name()}('EnMAP', aggregate:='median', t:=true)")
            exp.prepare(context)
            array = np.asarray(exp.evaluate(context))
            self.assertEqual(array.shape, (lyrR.bandCount(),))

        self.assertTrue(QgsExpression.unregisterFunction(f.name()))
        QgsProject.instance().removeAllMapLayers()

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
        self.registerFunction(f)

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        if Qgis.versionInt() >= 33000:
            store = QgsMapLayerStore()
        else:
            store = QgsProject.instance().layerStore()

        self.assertIsInstance(html, str)

        lyrE = QgsRasterLayer(enmap)

        lyrV = QgsVectorLayer(enmap_multipolygon)
        lyrV.setName('MyMultiPoly')
        store.addMapLayers([lyrV, lyrE])
        context = QgsExpressionContext()
        if Qgis.versionInt() >= 33000:
            context.setLoadedLayerStore(store)
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))
        for feat in lyrV.getFeatures():
            n_px_nat = feat.attribute('n_px_nat')
            n_px = feat.attribute('n_px')

            if isinstance(n_px_nat, int) and isinstance(n_px, int):
                feat.attribute('n_px_nat')
                context.setFeature(feat)
                c1 = QgsExpressionContext(context)

                values = [lyrE, feat.geometry(), 'none', False, 'dict']
                exp = QgsExpression()
                profiles_nat = f.func(values, QgsExpressionContext(context), exp, None)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profiles_nat, list)
                self.assertEqual(len(profiles_nat), n_px_nat)

                values = [lyrE, feat.geometry(), 'none', True, 'dict']
                exp = QgsExpression()
                profiles_at = f.func(values, QgsExpressionContext(context), exp, None)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profiles_at, list)
                self.assertEqual(len(profiles_at), n_px)

                exp1 = QgsExpression(f"raster_profile('{lyrE.name()}', at:=False, aggregate:='none', encoding:='dict')")
                exp1.prepare(c1)
                self.assertTrue(exp1.parserErrorString() == '', msg=exp1.parserErrorString())
                profiles1 = exp1.evaluate(context)
                self.assertTrue(exp1.evalErrorString() == '', msg=exp1.evalErrorString())


                c2 = QgsExpressionContext(context)
                exp2 = QgsExpression(f"raster_profile('{lyrE.name()}', at:=True, aggregate:='none', encoding:='dict')")
                exp2.prepare(c2)
                self.assertTrue(exp2.parserErrorString() == '', msg=exp2.parserErrorString())
                profiles2 = exp2.evaluate(context)
                self.assertTrue(exp2.evalErrorString() == '', msg=exp2.evalErrorString())

                self.assertEqual(len(profiles1), n_px_nat)
                self.assertEqual(len(profiles2), n_px)

                s = ""

        vectorLayers = [QgsVectorLayer(enmap_multipolygon),
                        QgsVectorLayer(enmap_pixel)]
        for lyrV in vectorLayers:
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))

            for feature in lyrV.getFeatures():
                values = [lyrE, QgsGeometry(feature.geometry())]
                for p in f.parameters()[2:]:
                    values.append(p.defaultValue())
                exp = QgsExpression()

                values[2] = 'none'
                values[-1] = 'binary'  # return multiple profiles
                results = f.func(values, context, exp, None)

                self.assertEqual(exp.parserErrorString(), '', msg=exp.parserErrorString())
                self.assertEqual(exp.evalErrorString(), '', msg=exp.evalErrorString())
                if lyrV.wkbType() == Qgis.WkbType.Point:
                    self.assertIsInstance(results, QByteArray)
                else:
                    self.assertIsInstance(results, list)
                    for d in results:
                        self.assertIsInstance(d, QByteArray)

                values[1] = QgsGeometry(feature.geometry())
                values[2] = 'mean'
                values[-1] = 'dict'  # return multiple profiles
                results = f.func(values, context, exp, None)

                self.assertEqual(exp.parserErrorString(), '', msg=exp.parserErrorString())
                self.assertEqual(exp.evalErrorString(), '', msg=exp.evalErrorString())
                self.assertIsInstance(results, dict)
                s = ""

        lyrR, lyrV = self.createRasterAndVectorLayers()

        expressions = [
            f"{f.name()}('{lyrR.name()}')",
            f"{f.name()}('{lyrR.name()}', $geometry)",
            f"{f.name()}('{lyrR.name()}', $geometry, encoding:='bytes')",
            f"{f.name()}('{lyrR.name()}', $geometry, encoding:='json')",
            f"{f.name()}('{lyrR.name()}', $geometry, encoding:='text')",
            f"{f.name()}('{lyrR.name()}', $geometry, encoding:='dict')",
            f"{f.name()}('{lyrR.name()}', $geometry, encoding:='map')",
            f"{f.name()}('{lyrR.name()}', encoding:='text')",
        ]


        store.addMapLayers([lyrR, lyrV])

        for e in expressions:
            context = QgsExpressionContext()
            context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))
            if Qgis.versionInt() >= 33000:
                context.setLoadedLayerStore(store)

            exp = QgsExpression(e)
            for i, feature in enumerate(lyrV.getFeatures()):
                self.assertIsInstance(feature, QgsFeature)
                context.setFeature(feature)
                # context = QgsExpressionContextUtils.createFeatureBasedContext(feature, QgsFields())
                if i > 0:
                    if False:
                        k = ExpressionFunctionUtils.cachedCrsTransformationKey(context, lyrR)
                        cached = context.cachedValue(k)
                        if not isinstance(cached, QgsCoordinateTransform):
                            s = ""
                        self.assertIsInstance(context.cachedValue(k), QgsCoordinateTransform)
                    k = ExpressionFunctionUtils.cachedSpectralPropertiesKey(lyrR)
                    dump = context.cachedValue(k)
                    cached = json.loads(dump)
                    self.assertIsInstance(cached, dict)
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

                profile = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

                if re.search(r'(bytes)', exp.expression()):
                    self.assertIsInstance(profile, QByteArray)
                elif re.search(r'(text|json)', exp.expression()):
                    self.assertIsInstance(profile, str)
                elif re.search(r'(dict|map)', exp.expression()):
                    self.assertIsInstance(profile, dict)
                else:
                    self.assertIsInstance(profile, str, msg=exp.expression())

        self.assertTrue(QgsExpression.unregisterFunction(f.name()))
        QgsProject.instance().removeAllMapLayers()

    def registerFunction(self, f: QgsExpressionFunction):
        self.assertIsInstance(f, QgsExpressionFunction)
        if QgsExpression.isFunctionName(f.name()):
            self.assertTrue(QgsExpression.unregisterFunction(f.name()))

        self.assertTrue(QgsExpression.registerFunction(f))
        self.assertTrue(QgsExpression.isFunctionName(f.name()))
        self.FUNC_REFS.append(f)

    def test_RasterProfile2(self):

        f = RasterProfile()
        self.registerFunction(f)

        lyrRaster = TestObjects.createRasterLayer(nb=100)
        lyrRaster.setName('EnMAP')
        lyrPoints = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.GeometryType.PointGeometry, n_features=3)

        extR = SpatialExtent.fromLayer(lyrRaster)
        extP = SpatialExtent.fromLayer(lyrPoints).toCrs(lyrRaster.crs())
        self.assertTrue(extR.contains(extP))
        s = ""

        QgsProject.instance().addMapLayers([lyrRaster, lyrPoints])
        import processing
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
        QgsProject.instance().removeAllMapLayers()

    def test_SpectralMath(self):
        f = SpectralMath()
        self.registerFunction(f)

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)
        sl = TestObjects.createSpectralLibrary(1, n_bands=[20, 20], profile_field_names=['p1', 'p2'])

        profileFeature = list(sl.getFeatures())[0]
        context = QgsExpressionContext()
        context.setFeature(profileFeature)
        context = QgsExpressionContextUtils.createFeatureBasedContext(profileFeature, profileFeature.fields())

        expressions = [
            f'{f.NAME}(\'y=[1,2,3]\')',
            f'{f.NAME}("p1", \'\')',
            f'{f.NAME}("p1", \'\', \'text\')',
            f'{f.NAME}("p1", \'\', \'map\')',
            f'{f.NAME}("p1", \'\', \'bytes\')',
            f'{f.NAME}("p1", "p2", \'y=y1/y2\')',
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
        QgsProject.instance().removeAllMapLayers()

    def test_Format_Py(self):
        f = Format_Py()
        self.registerFunction(f)

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())
        self.assertIsInstance(html, str)
        self.assertTrue(QgsExpression.unregisterFunction(f.name()))

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Blocking dialog')
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
            self.registerFunction(f)

        # sl = TestObjects.createSpectralLibrary()
        lyr1 = QgsRasterLayer(enmap, 'EnMAP')
        lyr2 = QgsVectorLayer(enmap_multipolygon, 'Poly')
        QgsProject.instance().addMapLayers([lyr1, lyr2])

        gui = QgsFieldCalculator(lyr2, None)
        gui.exec_()

    def test_aggragation_functions(self):
        from qps.speclib.processing.aggregateprofiles import createSpectralProfileFunctions
        afuncs = createSpectralProfileFunctions()
        for f in afuncs:
            self.registerFunction(f)

        sl = TestObjects.createSpectralLibrary(n=10, n_bands=[25, 50], profile_field_names=['P1', 'P2'])
        sl.setName('speclib')
        sl.startEditing()
        sl.addAttribute(QgsField('class', QVariant.String))
        sl.commitChanges(False)

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

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
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
