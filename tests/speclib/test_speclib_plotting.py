import json
import os.path
import unittest

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import QEvent, QPointF, Qt
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtGui import QColor, QMouseEvent
from qgis.PyQt.QtGui import QPen
from qgis.PyQt.QtWidgets import QHBoxLayout, QTreeView, QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsApplication
from qgis.core import edit, QgsCategorizedSymbolRenderer, QgsClassificationRange, QgsEditorWidgetSetup, \
    QgsExpressionContextScope, QgsFeature, QgsField, QgsGraduatedSymbolRenderer, QgsMarkerSymbol, \
    QgsMultiBandColorRenderer, QgsNullSymbolRenderer, QgsProject, QgsProperty, QgsReadWriteContext, QgsRenderContext, \
    QgsRendererCategory, QgsRendererRange, QgsSingleBandGrayRenderer, \
    QgsSingleSymbolRenderer, QgsVectorLayer
from qgis.gui import QgsDualView, QgsMapCanvas
from qps import DIR_REPO, initAll
from qps.plotstyling.plotstyling import PlotStyle, MarkerSymbol
from qps.pyqtgraph.pyqtgraph import InfiniteLine
from qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from qps.speclib.core import create_profile_field, profile_field_list, profile_field_names, profile_fields
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict
from qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotWidget, SpectralXAxis, \
    SpectralProfilePlotDataItem
from qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, ProfileVisualizationGroup, RasterRendererGroup, \
    SpectralProfileColorPropertyWidget
from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprofileplotmodel import SpectralProfilePlotModel, copy_items
from qps.testing import start_app, TestCase, TestObjects
from qps.unitmodel import BAND_INDEX, BAND_NUMBER
from qps.utils import file_search, nextColor, parseWavelength, writeAsVectorFormat

start_app()
initAll()


class TestSpeclibPlotting(TestCase):

    @staticmethod
    def gdal_error_handler(err_class, err_num, err_msg):
        errtype = {
            gdal.CE_None: 'None',
            gdal.CE_Debug: 'Debug',
            gdal.CE_Warning: 'Warning',
            gdal.CE_Failure: 'Failure',
            gdal.CE_Fatal: 'Fatal'
        }
        err_msg = err_msg.replace('\n', ' ')
        err_class = errtype.get(err_class, 'None')
        print('Error Number: %s' % (err_num))
        print('Error Type: %s' % (err_class))
        print('Error Message: %s' % (err_msg))

    def setUp(self):
        # spectralProfileEditorWidgetFactory(True)
        super().setUp()

    def test_SpectralLibraryWidget_deleteFeatures(self):
        speclib = TestObjects.createSpectralLibrary(10)
        slw = SpectralLibraryWidget(speclib=speclib, project=QgsProject())
        speclib = slw.speclib()
        speclib.startEditing()
        speclib.selectAll()
        speclib.deleteSelectedFeatures()
        speclib.commitChanges()
        slw.project().removeAllMapLayers()
        self.showGui(slw)

    def test_SpectralLibraryWidget_large(self):
        l_dir = DIR_REPO / 'tmp/largespeclib'
        p_large = None
        if l_dir.is_dir():
            for f in file_search(l_dir, '*.gpkg'):
                p_large = f
                break
        if not (p_large and os.path.isfile(p_large)):
            return

        speclib = QgsVectorLayer(p_large)

        self.assertTrue(SpectralLibraryUtils.isSpectralLibrary(speclib))

        slw = SpectralLibraryWidget(speclib=speclib)

        self.showGui(slw)
        slw.project().removeAllMapLayers()

    def test_SpectralLibraryWidget_addField(self):
        speclib = TestObjects.createSpectralLibrary(10)
        slw = SpectralLibraryWidget(speclib=speclib)
        speclib: QgsVectorLayer = slw.speclib()
        slw.show()
        speclib.startEditing()
        pfields = profile_fields(speclib)
        speclib.beginEditCommand('Add profile field')
        new_field = create_profile_field('new_field')
        speclib.addAttribute(new_field)
        speclib.endEditCommand()
        speclib.commitChanges(False)
        i0 = speclib.fields().lookupField(pfields.names()[0])
        i1 = speclib.fields().lookupField(new_field.name())
        self.assertTrue(i0 >= 0)
        self.assertTrue(i1 >= 0 and i0 != i1)

        speclib.beginEditCommand('Modify profiles')
        for i, f in enumerate(speclib.getFeatures()):
            ba = f.attribute(i0)
            if i % 2 == 0:
                f.setAttribute(i1, ba)
                speclib.updateFeature(f)
        speclib.endEditCommand()

        self.showGui(slw)

        slw.project().removeAllMapLayers()

    def test_vectorenderers(self):

        speclib = TestObjects.createSpectralLibrary()
        with edit(speclib):
            n = speclib.featureCount()
            speclib.addAttribute(QgsField('class', QMETATYPE_QSTRING))
            speclib.addAttribute(QgsField('float', QMETATYPE_DOUBLE))
            speclib.addAttribute(QgsField('int', QMETATYPE_INT))
            for i, feature in enumerate(speclib.getFeatures()):
                vclass = 'cat1' if i % 2 else 'cat2'
                vfloat = (i + 1) / n
                vint = i
                feature.setAttribute('class', vclass)
                feature.setAttribute('float', vfloat)
                feature.setAttribute('int', vint)
                speclib.updateFeature(feature)

        slw = SpectralLibraryWidget(speclib=speclib)
        vis0: ProfileVisualizationGroup = slw.plotModel().visualizations()[0]
        self.assertEqual(vis0.colorExpression(), '@symbol_color')

        # change the vector renderers
        symbolRed = QgsMarkerSymbol.createSimple({'name': 'square', 'color': 'red'})
        symbolOrange = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': 'orange'})
        r1 = QgsSingleSymbolRenderer(symbolRed)

        r2 = QgsCategorizedSymbolRenderer()
        r2.setClassAttribute('class')
        cat1 = QgsRendererCategory('cat1', symbolOrange.clone(), 'cat 1')
        cat2 = QgsRendererCategory('cat2', symbolRed.clone(), 'cat 2')
        r2.addCategory(cat1)
        r2.addCategory(cat2)

        r3 = QgsNullSymbolRenderer()

        r4 = QgsGraduatedSymbolRenderer()
        r4.setClassAttribute('float')
        r4.addClassRange(QgsRendererRange(QgsClassificationRange('class 0-0.5', 0, 0.5), symbolRed.clone()))
        r4.addClassRange(QgsRendererRange(QgsClassificationRange('class 0.5-1.0', 0.5, 1.0), symbolOrange.clone()))

        for r in [r1, r2, r3, r4]:
            speclib.setRenderer(r.clone())
        # change color
        vis0.setColor(QColor('green'))
        self.showGui(slw)

        QgsProject.instance().removeAllMapLayers()
        s = ""

    def test_SpectralProfileColorProperty(self):
        speclib: QgsVectorLayer = TestObjects.createSpectralLibrary()
        speclib.startEditing()
        colorField = QgsField('color', type=QMETATYPE_QSTRING)
        colorField.setEditorWidgetSetup(QgsEditorWidgetSetup('color', {}))
        speclib.addAttribute(colorField)
        speclib.commitChanges(False)

        color = QColor('green')
        for i in range(5):
            f = QgsFeature(speclib.fields())
            f.setAttribute('color', color.name())
            color = nextColor(color)
            speclib.addFeature(f)
        speclib.commitChanges(True)

        prop = QgsProperty()
        prop.setExpressionString('@symbol_color')

        w = SpectralProfileColorPropertyWidget()
        w.setLayer(speclib)
        w.setToProperty(prop)

        p = w.toProperty()
        renderContext = QgsRenderContext()
        expressionContext = speclib.createExpressionContext()

        profile = list(speclib.getFeatures())[0]
        expressionContext.setFeature(profile)

        renderer = speclib.renderer().clone()
        renderer.startRender(renderContext, speclib.fields())

        symbol = renderer.symbolForFeature(profile, renderContext)

        renderContext2 = symbol.symbolRenderContext()
        scope2 = renderContext2.expressionContextScope()
        # THIS is important! create a copy of the scope2
        expressionContext.appendScope(QgsExpressionContextScope(scope2))

        color1 = symbol.color()

        print(color1.name())
        self.assertIsInstance(p, QgsProperty)
        color2, success = p.valueAsColor(expressionContext, defaultColor=QColor('black'))
        print(color2.name())
        renderer.stopRender(renderContext)
        self.assertEqual(color1, color2)

        self.showGui(w)

    # @unittest.skip('test')
    def test_speclib_plotsettings_restore(self):
        "write and restore spectral library settings from XML / QgsProject"
        fnames = ['profilesA', 'profilesB']

        tmpDir = self.createTestOutputDirectory()
        path_sl = tmpDir / 'TestSpeclib.gpkg'
        speclib = TestObjects.createSpectralLibrary(name='Speclib1', n_bands=[25, 50], profile_field_names=fnames)

        speclib2 = writeAsVectorFormat(speclib, path_sl)
        self.assertIsInstance(speclib2, QgsVectorLayer)
        self.assertTrue(speclib2.isValid())
        self.assertTrue(path_sl.is_file())
        speclib2.setName('Speclib2')

        self.assertListEqual(fnames, profile_field_names(speclib2))
        self.assertEqual(speclib.featureCount(), speclib2.featureCount())

        p = QgsProject()
        p.addMapLayer(speclib2)

        slw = SpectralLibraryWidget(speclib=speclib2)

        self.assertEqual(slw.speclib(), speclib2)
        doc = QDomDocument()
        root_node: QDomElement = doc.createElement('root')
        doc.appendChild(root_node)
        context = QgsReadWriteContext()
        slw.writeXml(root_node, context)

        # slw.plotControl().removePropertyItemGroups()
        # reload, with existing speclib instance
        slw2 = SpectralLibraryWidget.fromXml(root_node, context, project=p)[0]
        self.assertIsInstance(slw2, SpectralLibraryWidget)
        self.assertEqual(slw2.speclib(), speclib2)
        self.assertEqual(slw.windowTitle(), slw2.windowTitle())

        for vis1, vis2 in zip(slw.plotModel().visualizations(), slw.plotModel().visualizations()):
            self.assertEqual(vis1, vis2)

        QgsProject.instance().removeAllMapLayers()

    def test_SpectralProfilePlotWidget(self):

        pw = SpectralProfilePlotWidget()
        self.assertIsInstance(pw, SpectralProfilePlotWidget)
        pw.show()
        w, h = pw.width(), pw.height()
        # event = QDropEvent(QPoint(0, 0), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
        event = QMouseEvent(QEvent.MouseMove, QPointF(0.5 * w, 0.5 * h), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        pw.mouseMoveEvent(event)

        event = QMouseEvent(QEvent.MouseButtonPress, QPointF(0.5 * w, 0.5 * h), Qt.RightButton, Qt.RightButton,
                            Qt.NoModifier)
        pw.mouseReleaseEvent(event)

        self.showGui(pw)
        QgsProject.instance().removeAllMapLayers()

    def test_LayerRendererVisualization(self):

        rrGrp = RasterRendererGroup()

        for p in rrGrp.bandPlotItems():
            self.assertIsInstance(p, InfiniteLine)
            self.assertFalse(p.isVisible())

        barR, barG, barB, barA = rrGrp.bandPlotItems()

        barR: InfiniteLine
        barG: InfiniteLine
        barB: InfiniteLine
        barA: InfiniteLine

        lyrA = TestObjects.createRasterLayer(nb=20)
        lyrB = TestObjects.createRasterLayer(nb=1)
        lyrB.setName('B')
        lyrC = TestObjects.createRasterLayer(nb=255)

        proj = QgsProject.instance()
        proj.addMapLayers([lyrA, lyrB, lyrC])

        rrGrp.setLayer(lyrA)
        self.assertEqual(rrGrp.mXUnit, BAND_NUMBER)
        renderer = lyrA.renderer()
        mb_renderer = renderer.clone()
        self.assertIsInstance(renderer, QgsMultiBandColorRenderer)
        self.assertEqual(barR.name(), f'{lyrA.name()} red band {renderer.redBand()}')
        self.assertEqual(barG.name(), f'{lyrA.name()} green band {renderer.greenBand()}')
        self.assertEqual(barB.name(), f'{lyrA.name()} blue band {renderer.blueBand()}')

        self.assertEqual(rrGrp.bandToXValue(renderer.redBand()), renderer.redBand())
        self.assertEqual(rrGrp.bandToXValue(renderer.greenBand()), renderer.greenBand())
        self.assertEqual(rrGrp.bandToXValue(renderer.blueBand()), renderer.blueBand())

        rrGrp.setXUnit(BAND_INDEX)
        self.assertEqual(rrGrp.bandToXValue(renderer.redBand()), renderer.redBand() - 1)
        self.assertEqual(rrGrp.bandToXValue(renderer.greenBand()), renderer.greenBand() - 1)
        self.assertEqual(rrGrp.bandToXValue(renderer.blueBand()), renderer.blueBand() - 1)

        wl, wlu = parseWavelength(lyrA)
        rrGrp.setXUnit(wlu)
        self.assertAlmostEqual(rrGrp.bandToXValue(renderer.redBand()), wl[renderer.redBand() - 1], 4)
        self.assertAlmostEqual(rrGrp.bandToXValue(renderer.greenBand()), wl[renderer.greenBand() - 1], 4)
        self.assertAlmostEqual(rrGrp.bandToXValue(renderer.blueBand()), wl[renderer.blueBand() - 1], 4)

        # test single-band grey renderer
        # 1st band bar is used for grey band
        render = QgsSingleBandGrayRenderer(lyrA.dataProvider(), 1)
        lyrA.setRenderer(render)
        self.assertTrue(barR.isVisible())
        self.assertFalse(barG.isVisible())
        self.assertFalse(barB.isVisible())

        # test multi-band renderer
        w = SpectralProfilePlotWidget()
        xAxis = w.xAxis()
        self.assertIsInstance(xAxis, SpectralXAxis)
        xAxis.setUnit(rrGrp.mXUnit)
        for bar in rrGrp.bandPlotItems():
            w.plotItem.addItem(bar)

        lyrA.setRenderer(mb_renderer)

        self.showGui(w)

        QgsProject.instance().removeAllMapLayers()

    def test_plot_NaN_values(self):

        x = [1, 2, 3, 4, 5, 6, 7]
        y = [0, 1, 2, None, np.nan, float('nan'), 7]
        y2 = [0, 1, 2, np.nan, np.nan, np.nan, 7]
        d = prepareProfileValueDict(x=x, y=y)

        sl = TestObjects.createSpectralLibrary(n=0)

        pfield = profile_field_list(sl)[0]
        with edit(sl):
            f = QgsFeature(sl.fields())
            dump = encodeProfileValueDict(d, encoding=pfield)
            p2 = decodeProfileValueDict(dump)
            f.setAttribute(pfield.name(), dump)
            p3 = decodeProfileValueDict(f.attribute(pfield.name()))
            sl.addFeature(f)

        p4 = decodeProfileValueDict(list(sl.getFeatures())[0].attribute(pfield.name()))

        slw = SpectralLibraryWidget(speclib=sl)
        model = slw.plotModel()
        self.assertIsInstance(model, SpectralProfilePlotModel)

        idx = sl.fields().lookupField(pfield.name())
        f1 = list(sl.getFeatures())[0]
        data = model.rawData(sl.id(), f1.id(), idx)
        self.assertListEqual(data['x'], x)
        self.assertListEqual(data['y'], y2)
        slw.project().removeAllMapLayers()

    def test_SpectralProfilePlotModel_add_current_profiles(self):

        sl1 = TestObjects.createSpectralLibrary(n=2, name='speclib1', profile_field_names=['p1'])
        sl2 = TestObjects.createSpectralLibrary(n=4, name='speclib2',
                                                n_bands=[10, 20], profile_field_names=['p1', 'p2'])

        model = SpectralProfilePlotModel()
        model.project().addMapLayers([sl1, sl2])

        vis1 = ProfileVisualizationGroup()
        vis1.setLayerField(sl1, 'p1')
        vis2 = ProfileVisualizationGroup()
        vis2.setLayerField(sl2, 'p2')

        model.insertPropertyGroup(-1, [vis1, vis2])

        f1 = QgsFeature(sl1.fields())
        profile1 = prepareProfileValueDict(x=[400, 500, 600, 700], y=[1, 2, 3, 4], xUnit='nm')
        a = sl1.fields().lookupField('p1')
        f1.setAttribute(a, encodeProfileValueDict(profile1, sl1.fields()['p1']))

        f2 = QgsFeature(sl2.fields())

        current1 = {sl1.id(): [f1],
                    sl2.id(): [f1, f2]
                    }

        n1_1 = sl1.featureCount()
        n1_2 = sl2.featureCount()

        result1 = model.addProfileCandidates(current1)

        self.assertEqual(sl1.featureCount(), n1_1 + 1)
        self.assertEqual(sl2.featureCount(), n1_2 + 2)

        # without adding the current profiles to the vector layer sources,
        # the previous profiles will be deleted
        model.addProfileCandidates({})
        self.assertEqual(sl1.featureCount(), n1_1)
        self.assertEqual(sl2.featureCount(), n1_2)

        result1 = model.addProfileCandidates(current1)
        self.assertEqual(sl1.featureCount(), n1_1 + 1)
        self.assertEqual(sl2.featureCount(), n1_2 + 2)

        self.assertTrue(len(model.mPROFILE_CANDIDATES) > 0)
        # model.clearProfileCandidates()
        # self.assertEqual(sl1.featureCount(), n1_1)
        # self.assertEqual(sl2.featureCount(), n1_2)

        w = SpectralLibraryWidget(sl1, plot_model=model)

        self.showGui(w)
        w.project().removeAllMapLayers()

    def test_SpectralProfilePlotModel(self):

        model = SpectralProfilePlotModel()
        speclib = TestObjects.createSpectralLibrary()
        canvas = QgsMapCanvas()
        dv = QgsDualView()
        dv.init(speclib, canvas)
        pw = SpectralProfilePlotWidget()
        model.setPlotWidget(pw)
        model.setDualView(dv)

        self.assertIsInstance(json.dumps(model.settingsMap(), ensure_ascii=False), str)

        tv = QTreeView()

        tv.setModel(model)

        lyr1 = TestObjects.createRasterLayer(nb=1)
        lyr2 = TestObjects.createRasterLayer(nb=10)
        vis1 = RasterRendererGroup(layer=lyr1)
        vis2 = RasterRendererGroup(layer=lyr2)

        vis3 = ProfileVisualizationGroup()
        model.insertPropertyGroup(0, vis1)
        model.insertPropertyGroup(1, vis2)
        model.insertPropertyGroup(2, vis3)

        vis1.setLayer(lyr2)
        vis2.setLayer(lyr1)

        indices = []
        for grp in model.visualizations():
            indices.append(grp.index())

        settings1 = model.settingsMap()
        jsonDump = json.dumps(settings1, ensure_ascii=False)
        settings2 = json.loads(jsonDump)
        self.assertIsInstance(settings1, dict)
        self.assertEqual(settings1, settings2)

        # restore mode
        project2 = QgsProject()
        model2 = SpectralProfilePlotModel.fromSettingsMap(settings1, project=project2)
        self.assertIsInstance(model2, SpectralProfilePlotModel)
        for vis1, vis2 in zip(model.visualizations(), model2.visualizations()):
            self.assertEqual(vis1.name(), vis2.name())
            self.assertEqual(vis1.fieldName(), vis2.fieldName())
            self.assertEqual(vis1.layer().source(), vis2.layer().source())
            self.assertEqual(vis1.filterExpression(), vis2.filterExpression())
            self.assertEqual(vis1.colorExpression(), vis2.colorExpression())
            self.assertEqual(vis1.labelExpression(), vis2.labelExpression())
            self.assertEqual(vis1.isVisible(), vis2.isVisible())

        # mimeData = model.mimeData(indices)
        # grps = PropertyItemGroup.fromMimeData(mimeData)
        # self.assertTrue(len(grps) > 0)
        # self.assertTrue(model.canDropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))
        # self.assertTrue(model.dropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))

        self.showGui([tv, pw])

        QgsProject.instance().removeAllMapLayers()

    def test_PlotStyleItem(self):

        item1 = PlotStyleItem('key')
        item1.plotStyle().setLineColor('red')
        item2 = item1.clone()
        self.assertIsInstance(item2, PlotStyleItem)
        self.assertEqual(item1, item2)

        item2.plotStyle().setLineColor('blue')
        self.assertNotEqual(item1, item2)

    def test_sortBands(self):

        d = prepareProfileValueDict(y=[1, 2, 3, 4, 4, 3, 2, 3, 3, 4],
                                    x=[0, 1, 2, 6, 5, 4, 3, 7, 8, 9],
                                    xUnit='Band Number')

        slw = SpectralLibraryWidget()

        speclib = slw.speclib()

        feature = QgsFeature(speclib.fields())
        for field in profile_fields(feature):
            idx = feature.fields().lookupField(field.name())
            feature.setAttribute(idx, encodeProfileValueDict(d, field))
        self.assertTrue(speclib.startEditing())
        speclib.addFeature(feature)
        self.assertTrue(speclib.commitChanges())
        self.showGui(slw)
        QgsProject.instance().removeAllMapLayers()

    def test_badBands(self):

        d = prepareProfileValueDict(y=[1, 2, 3, 4, 4, 3, 2, 3, 3, 4],
                                    bbl=[1, 1, 0, 1, 0, 1, 0, 1, 1, 1])

        slw = SpectralLibraryWidget()

        speclib = slw.speclib()

        feature = QgsFeature(speclib.fields())
        for field in profile_fields(feature):
            idx = feature.fields().lookupField(field.name())
            feature.setAttribute(idx, encodeProfileValueDict(d, field))
        self.assertTrue(speclib.startEditing())
        speclib.addFeature(feature)
        self.assertTrue(speclib.commitChanges())
        self.showGui(slw)
        QgsProject.instance().removeAllMapLayers()

    def test_SpectralLibraryPlotWidget_simpled(self):

        sl1 = TestObjects.createSpectralLibrary(n=10, n_bands=[5, 12],
                                                name='Speclib A', profile_field_names=['A1', 'A2'])
        with edit(sl1):
            sl1.addAttribute(QgsField('color', QMetaType.QString))

        sl2 = TestObjects.createSpectralLibrary(n=3, n_bands=[50, 200],
                                                name='Speclib B', profile_field_names=['B1', 'B2'])

        vl1 = TestObjects.createVectorLayer(name='Vector Layer 1')
        vl2 = TestObjects.createVectorLayer(name='Vector Layer - no geometry')
        rl1 = TestObjects.createRasterLayer(name='Raster Layer 1-band', nb=1)
        rl2 = TestObjects.createRasterLayer(name='Raster Layer 3-band', nb=10)

        style = PlotStyle()
        style.setLinePen(QPen(QColor('red')))
        style.setMarkerSymbol(MarkerSymbol.Circle)

        QgsProject.instance().addMapLayers([sl1, sl2, vl1, vl2, rl1, rl2])

        w = SpectralLibraryWidget(speclib=sl1, default_style=style)
        VT = SpectralLibraryWidget.ViewType
        w.setViewVisibility(VT.ProfileView | VT.ProfileViewSettings)  # | VT.AttributeTable)
        w.plotModel()
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    def test_copy_plotdataitems(self):

        x1 = [1, 2, 3]
        y1 = [4, 5, 6]

        x2 = [0, 1, 3, 5]
        y2 = [3.4, 2.3, 3, np.nan]

        item1 = SpectralProfilePlotDataItem()
        item1.setData(x=x1, y=y1)
        item2 = SpectralProfilePlotDataItem()
        item2.setData(x=x2, y=y2)
        items = [
            item1, item2
        ]

        copy_items(items, 'JSON')

        dump = QgsApplication.instance().clipboard().mimeData().text()
        data = json.loads(dump)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertTrue(np.array_equal(data[0]['x'], x1, equal_nan=True))
        self.assertTrue(np.array_equal(data[0]['y'], y1, equal_nan=True))
        self.assertTrue(np.array_equal(data[1]['x'], x2, equal_nan=True))
        self.assertTrue(np.array_equal(data[1]['y'], y2, equal_nan=True))

        copy_items(items, 'CSV')
        data = QgsApplication.instance().clipboard().mimeData().text()
        print(data)

    def test_SpectralLibraryPlotWidget(self):

        speclib = TestObjects.createSpectralLibrary(n_bands=[-1, 12])
        canvas = QgsMapCanvas()
        dv = QgsDualView()
        dv.init(speclib, canvas)

        w = SpectralLibraryPlotWidget()
        w.setDualView(dv)

        visModel = w.treeView.model().sourceModel()
        cnt = visModel.rowCount()
        self.assertIsInstance(visModel, SpectralProfilePlotModel)

        # add a VIS
        w.btnAddProfileVis.click()
        self.assertEqual(visModel.rowCount(), cnt + 1)

        # click into each cell
        for row in range(visModel.rowCount()):
            for col in range(visModel.columnCount()):
                idx = w.treeView.model().index(row, col)
                w.treeView.edit(idx)

        # remove vis

        w.treeView.selectPropertyGroups(visModel.visualizations()[0])
        w.btnRemoveProfileVis.click()

        rl1 = TestObjects.createRasterLayer(nb=255)
        rl2 = TestObjects.createRasterLayer(nb=1)
        rl1.setName('MultiBand')
        rl2.setName('SingleBand')

        proj = QgsProject()
        proj.addMapLayers([rl1, rl2, speclib])
        w.setProject(proj)

        speclib.startEditing()
        speclib.addAttribute(create_profile_field('profiles3'))
        speclib.commitChanges(stopEditing=False)
        speclib.deleteAttribute(speclib.fields().lookupField('profiles3'))
        speclib.commitChanges(stopEditing=False)

        canvas = QgsMapCanvas()
        canvas.setLayers([rl1, rl2])
        canvas.zoomToFullExtent()
        layout = QVBoxLayout()
        layout.addWidget(canvas)
        layout.addWidget(w)

        major = QWidget()
        major.setLayout(layout)

        self.showGui(major)
        QgsProject.instance().removeAllMapLayers()

    def test_rendering(self):

        speclib = TestObjects.createSpectralLibrary()
        QgsProject.instance().addMapLayers([speclib], False)
        slw = SpectralLibraryWidget(speclib=speclib)

        canvas = QgsMapCanvas()

        canvas.setLayers([speclib])
        canvas.zoomToFullExtent()

        layout = QHBoxLayout()
        layout.addWidget(canvas)
        layout.addWidget(slw)

        w = QWidget()
        w.setLayout(layout)
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
