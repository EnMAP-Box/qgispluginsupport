import json
import re
import unittest

import numpy as np
from osgeo import gdal_array

from qgis.PyQt.QtCore import QByteArray
from qgis.core import edit, Qgis, QgsCoordinateTransform, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsExpressionFunction, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsMapLayerStore, \
    QgsPointXY, QgsProject, QgsProperty, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsFieldCalculator
from qps.qgisenums import QGIS_WKBTYPE, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from qps.qgsfunctions import ExpressionFunctionUtils, Format_Py, HelpStringMaker, RasterArray, RasterProfile, \
    ReadSpectralProfile, SpectralData, SpectralEncoding, SpectralMath
from qps.speclib.core import profile_fields
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import decodeProfileValueDict, isProfileValueDict, ProfileEncoding, \
    encodeProfileValueDict
from qps.speclib.processing.aggregateprofiles import createSpectralProfileFunctions
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import file_search, SpatialExtent, SpatialPoint
from qpstestdata import DIR_SED, enmap, enmap_multipolygon, enmap_pixel

start_app()


def createAggregateTestLayer():
    sl = QgsVectorLayer('point?crs=epsg:4326&', 'speclib',
                        'memory')
    data = [{'class': 'a', 'num': 1, 't_mean': 1.5, 't_min': 1, 't_max': 2},
            {'class': 'a', 'num': 2, 't_mean': 1.5, 't_min': 1, 't_max': 2},
            {'class': 'b', 'num': 3, 't_mean': 4.0, 't_min': 3, 't_max': 5},
            {'class': 'b', 'num': 5, 't_mean': 4.0, 't_min': 3, 't_max': 5},
            ]
    fields = [QgsField('class', QMETATYPE_QSTRING),
              QgsField('num', QMETATYPE_INT),
              QgsField('t_mean', QMETATYPE_DOUBLE),
              QgsField('t_min', QMETATYPE_DOUBLE),
              QgsField('t_max', QMETATYPE_DOUBLE)
              ]
    with edit(sl):
        for f in fields:
            assert sl.addAttribute(f)

        # add features
        for d in data:
            f = QgsFeature(sl.fields())
            for name, value in d.items():
                f.setAttribute(name, value)
            assert sl.addFeature(f)

    for i, f in enumerate(sl.getFeatures()):
        f: QgsFeature
        d1: dict = data[i]
        d2: dict = f.attributeMap()
        assert d1 == d2

    return sl


def createAggregateTestProfileLayer():
    sl = createAggregateTestLayer()
    with edit(sl):
        assert SpectralLibraryUtils.addSpectralProfileField(sl, 'profile', encoding=ProfileEncoding.Json)
        assert sl.fields()['profile'].editorWidgetSetup().type() == 'SpectralProfile'
        idx = sl.fields().indexOf('profile')
        for f in sl.getFeatures():
            f: QgsFeature
            d: dict = f.attributeMap()
            num = d['num']

            yvec = [i * num for i in range(1, 4)]
            profile = {'y': yvec}
            assert sl.changeAttributeValue(f.id(), idx, profile)
            s = ""

    return sl


class QgsFunctionTests(TestCase):
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

    def test_SpectralProfile(self):

        context = QgsExpressionContext()
        f = ReadSpectralProfile()
        self.registerFunction(f)
        from qpstestdata import DIR_SVC, DIR_ASD_BIN

        asd_files = list(file_search(DIR_ASD_BIN, '*.asd'))
        svc_files = list(file_search(DIR_SVC, '*.sig'))
        sed_files = list(file_search(DIR_SED, '*.sed'))

        for file in [asd_files[0], svc_files[0], sed_files[0]]:
            exp = QgsExpression(f"{f.NAME}('{file}')")
            self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
            data = exp.evaluate(context)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertIsInstance(data, dict)
        s = ""

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
                self.assertIsInstance(profile, dict)

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

        sl = TestObjects.createSpectralLibrary(profile_field_names=['profile1', 'profile2'])

        with edit(sl):
            for feature in sl.getFeatures():

                if feature.id() % 2 == 0:
                    feature.setAttribute('profile1', None)
                elif feature.id() % 3 == 0:
                    feature.setAttribute('profile2', None)
                sl.updateFeature(feature)

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        for feature in sl.getFeatures():
            # print(feature.attributeMap())
            context.setFeature(feature)

            expected = [
                ('spectral_data()', feature.attribute('profile1')),
                ('spectral_data("profile1")', feature.attribute('profile1')),
                ('spectral_data("profile2")', feature.attribute('profile2')),
            ]

            for (exp_string, expected_result) in expected:
                exp = QgsExpression(exp_string)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                dump = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertEqual(dump, expected_result)

        sl = TestObjects.createSpectralLibrary(n_empty=0, n_bands=[24, 255],
                                               profile_field_names=['profile1', 'profile2'])
        sfields = profile_fields(sl)
        self.assertTrue(len(sfields) == 2)

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))
        QgsProject.instance().addMapLayer(sl)
        for i, n in enumerate(sfields.names()):
            exp = QgsExpression(f'{f.name()}("{n}")')

            for feature in sl.getFeatures():
                context.setFeature(feature)
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
                profile = exp.evaluate(context)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                profileDict = decodeProfileValueDict(profile)
                self.assertTrue(isProfileValueDict(profileDict))

        QgsProject.instance().removeAllMapLayers()

    def test_RasterArray(self):

        f = RasterArray()
        self.registerFunction(f)

        HM = HelpStringMaker()
        html = HM.helpText(f.name(), f.parameters())

        self.assertIsInstance(html, str)

        lyrR = QgsRasterLayer(enmap.as_posix(), 'EnMAP')
        lyrSP = QgsVectorLayer(enmap_pixel.as_posix(), 'SinglePoint')
        lyrMP = QgsVectorLayer(enmap_multipolygon.as_posix(), 'MultiPoly')
        QgsProject.instance().addMapLayers([lyrR, lyrMP])

        if True:
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
                # layer, geometry, aggregate, t, at
                values = [lyrR, gSPoint, 'none', False, True]
                a = np.asarray(f.func(values, context, None, None))
                self.assertEqual(a.ndim, 1, 'Single-Point geometry should return 1-d array profile')
                self.assertEqual(len(a), lyrR.bandCount())

                for g in [gMPoint, gLine, gPoly]:
                    values = [lyrR, QgsGeometry(g), 'none', False, True]
                    a = np.asarray(f.func(values, context, None, None))
                    self.assertEqual(a.ndim, 2, msg=f'ndim != 2 for geometry {g}')
                    self.assertEqual(a.shape[0], lyrR.bandCount())

                    values = [lyrR, QgsGeometry(g), 'mean', False, True]
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
                px_x, px_y = feature.attribute('px_x'), feature.attribute('px_y')
                exp.prepare(context)
                self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())

                values = [lyrR, feature.geometry(), 'mean', True, True]
                exp0 = QgsExpression()
                profile0 = f.func(values, context, exp0, None)
                profile1 = exp.evaluate(context)

                self.assertListEqual(profile0, profile1)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profile1, list, msg=exp.expression())
                pt = SpatialPoint(lyrSP.crs(), feature.geometry().asPoint())
                px = pt.toPixelPosition(lyrR)
                self.assertEqual(px.x(), px_x)
                self.assertEqual(px.y(), px_y)
                profile_ref = RASTER_ARRAY[:, px.y(), px.x()].tolist()
                self.assertListEqual(profile1, profile_ref)

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

        lyrE = QgsRasterLayer(enmap.as_posix())

        lyrV = QgsVectorLayer(enmap_multipolygon.as_posix())
        lyrV.setName('MyMultiPoly')
        store.addMapLayers([lyrV, lyrE])
        context = QgsExpressionContext()
        if Qgis.versionInt() >= 33000:
            context.setLoadedLayerStore(store)
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyrV))
        for feat in lyrV.getFeatures():
            n_px_nat = feat.attribute('n_px_nat')
            n_px_at = feat.attribute('n_px')

            if isinstance(n_px_nat, int) and isinstance(n_px_at, int):
                context.setFeature(feat)
                all_touched = True
                values = [lyrE, feat.geometry(), 'none', all_touched, 'dict']
                exp = QgsExpression()
                profiles_at = f.func(values, QgsExpressionContext(context), exp, None)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())

                self.assertIsInstance(profiles_at, list)
                n_px_returned = len(profiles_at)
                self.assertEqual(len(profiles_at), n_px_returned,
                                 msg=f'Expected {n_px_at} but got {n_px_returned} pixel with ALL_TOUCHED=TRUE')

                values = [lyrE, feat.geometry(), 'none', False, 'dict']
                exp = QgsExpression()
                profiles_nat = f.func(values, QgsExpressionContext(context), exp, None)
                self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
                self.assertIsInstance(profiles_nat, list)
                self.assertEqual(len(profiles_nat), n_px_nat,
                                 msg=f'Expected {n_px_at} but got {len(profiles_nat)} pixel with ALL_TOUCHED=FALSE')

                c1 = QgsExpressionContext(context)
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
                self.assertEqual(len(profiles2), n_px_at)

                s = ""

        vectorLayers = [QgsVectorLayer(enmap_multipolygon.as_posix()),
                        QgsVectorLayer(enmap_pixel.as_posix())]
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
                if lyrV.wkbType() == QGIS_WKBTYPE.Point:
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
                elif re.search(r'(text)', exp.expression()):
                    self.assertIsInstance(profile, str)
                elif re.search(r'(dict|map|json)', exp.expression()):
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
        assert SpectralLibraryUtils.makeToProfileField(lyrSpeclib, 'profiles')

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

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
    def test_functiondialog(self):
        functions = [
            Format_Py(),
            RasterArray(),
            RasterProfile(),
            SpectralMath(),
            SpectralData(),
            SpectralEncoding(),
            ReadSpectralProfile()
        ]

        functions.extend(createSpectralProfileFunctions())

        for f in functions:
            self.registerFunction(f)

        # sl = TestObjects.createSpectralLibrary()
        lyr = createAggregateTestProfileLayer()
        QgsProject.instance().addMapLayers([lyr])

        gui = QgsFieldCalculator(lyr, None)
        gui.exec()

        QgsProject.instance().removeAllMapLayers()

    def test_aggregation_functions(self):

        afuncs = createSpectralProfileFunctions()
        for feature in afuncs:
            text = feature.helpText()
            self.assertTrue(feature.name() in text)
            self.registerFunction(feature)

        aggrFuncs = ['mean', 'median', 'minimum', 'maximum']
        for feature in aggrFuncs:
            fname = f'{feature}_profile'
            self.assertTrue(QgsExpression.isFunctionName(fname))

        sl = createAggregateTestProfileLayer()

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(sl))

        def checkProfileAggr(context: QgsExpressionContext, f: QgsFeature, funcString: str) -> list:
            c = QgsExpressionContext(context)
            c.setFeature(f)
            c.setGeometry(f.geometry())

            exp = QgsExpression(funcString)
            exp.prepare(c)
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
            profile = exp.evaluate(c)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertIsInstance(profile, dict)
            values = profile.get('y')
            self.assertIsInstance(values, list)
            return values

        ALL_PROFILES = dict()

        all_arrays = []
        all_classes = []
        for feature in sl.getFeatures():
            c = feature.attribute('class')
            p = np.array(feature.attribute('profile')['y'])
            ALL_PROFILES[c] = ALL_PROFILES.get(c, []) + [p]
            all_classes.append(c)
            all_arrays.extend([p])

        ALL_PROFILES['mean'] = np.mean(all_arrays, axis=0).tolist()
        ALL_PROFILES['median'] = np.median(all_arrays, axis=0).tolist()
        ALL_PROFILES['minimum'] = np.min(all_arrays, axis=0).tolist()
        ALL_PROFILES['maximum'] = np.max(all_arrays, axis=0).tolist()

        for className in all_classes:
            ALL_PROFILES[className + '_mean'] = np.mean(ALL_PROFILES[className], axis=0).tolist()
            ALL_PROFILES[className + '_median'] = np.median(ALL_PROFILES[className], axis=0).tolist()
            ALL_PROFILES[className + '_minimum'] = np.min(ALL_PROFILES[className], axis=0).tolist()
            ALL_PROFILES[className + '_maximum'] = np.max(ALL_PROFILES[className], axis=0).tolist()

        for feature in sl.getFeatures():

            classname = feature.attribute('class')
            d = feature.attributeMap()
            c = QgsExpressionContext(context)
            c.setFeature(feature)
            c.setGeometry(feature.geometry())

            # reference aggregation on single number
            exp = QgsExpression('mean("num",  group_by:="class")')
            self.assertTrue(exp.parserErrorString() == '', msg=exp.parserErrorString())
            # exp.prepare(c)
            mean_value = exp.evaluate(c)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertEqual(mean_value, d['t_mean'])

            for func in aggrFuncs:
                # aggregate over all
                expected = ALL_PROFILES[func]
                funcString = f'{func}_profile()'
                context = QgsExpressionContext(c)
                profile = checkProfileAggr(context, feature, funcString)
                self.assertListEqual(profile, expected)

                # grouped aggregation, aggregate per class
                expected = ALL_PROFILES[f'{classname}_{func}']

                context = QgsExpressionContext(c)
                funcString = f'{func}_profile(group_by:="class")'
                profile = checkProfileAggr(context, feature, funcString)
                self.assertListEqual(profile, expected)

                funcString = f'{func}_profile("profile", group_by:="class")'
                context = QgsExpressionContext(c)
                profile = checkProfileAggr(context, feature, funcString)
                self.assertListEqual(profile, expected)

    @unittest.skipIf(TestCase.runsInCI(), 'blocking dialog')
    def test_aggregation_differingArrays(self):

        afuncs = createSpectralProfileFunctions()
        for f in afuncs:
            text = f.helpText()
            self.assertTrue(f.name() in text)
            self.registerFunction(f)

        sl = SpectralLibraryUtils.createSpectralLibrary(['profile'])

        expected = {
            'A': [2.5, 4.0, 3.5],
            'B': [1, 1, 1],
            'C': [2.5, 3, 3.5, 5.5]

        }

        data = [
            {'x': [1, 2, 3], 'y': [2, 2, 2], 'class': 'A'},  # A should average t 2.5, 4.0, 3.5
            {'x': [1, 2, 3], 'y': [3, 4, 5], 'class': 'A'},
            {'x': [1, 2, 3], 'y': [1, 1, 1], 'class': 'B'},  # B should average to 1 1 1
            # {'x': [4, 5, 6, 7], 'y': [2, 2, 2, 5], 'class': 'C'},  # C should average to 2.5, 3, 3.5, 5.5
            # {'x': [4, 5, 6, 7], 'y': [3, 4, 5, 6], 'class': 'C'},
            # {'x': [1, 2, 3, 4], 'y': [5, 4, 3, 4], 'class': 'D'},  # D should fail, because arrays have different values
            # {'x': [1, 2], 'y': [5, 4], 'class': 'D'},
            #
        ]
        QgsProject.instance().addMapLayer(sl)
        with edit(sl):
            sl.addAttribute(QgsField('class', QMETATYPE_QSTRING))
            for item in data:
                f = QgsFeature(sl.fields())

                data = {'x': item['x'], 'y': item['y']}
                dump = encodeProfileValueDict(data, sl.fields()['profile'])
                f.setAttribute('profile', dump)
                f.setAttribute('class', item['class'])
                assert sl.addFeature(f)

            gui = QgsFieldCalculator(sl, None)
            # create new field: agr with type map
            # entry expression: mean_profile("profile", "class")

            gui.exec()

        for f in sl.getFeatures():
            f: QgsFeature
            cName = f.attribute('class')

            print(f.attributeMap())
        s = ""

        QgsProject.instance().removeMapLayer(sl)


if __name__ == '__main__':
    unittest.main(buffer=False)
