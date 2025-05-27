import unittest

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import QEvent, QModelIndex, QPointF, Qt
from qgis.PyQt.QtGui import QColor, QMouseEvent
from qgis.PyQt.QtWidgets import QHBoxLayout, QTreeView, QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsCategorizedSymbolRenderer, QgsClassificationRange, QgsEditorWidgetSetup, \
    QgsExpressionContextScope, QgsFeature, QgsField, QgsGraduatedSymbolRenderer, QgsMarkerSymbol, \
    QgsMultiBandColorRenderer, QgsNullSymbolRenderer, QgsProject, QgsProperty, QgsPropertyDefinition, \
    QgsReadWriteContext, QgsRenderContext, QgsRendererCategory, QgsRendererRange, QgsSingleBandGrayRenderer, \
    QgsSingleSymbolRenderer, QgsVectorLayer, edit
from qgis.gui import QgsDualView, QgsMapCanvas
from qps import registerSpectralLibraryPlotFactories, unregisterSpectralLibraryPlotFactories
from qps.pyqtgraph.pyqtgraph import InfiniteLine
from qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from qps.speclib.core import create_profile_field, profile_field_list, profile_field_names, profile_fields
from qps.speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict
from qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotWidget, SpectralXAxis
from qps.speclib.gui.spectrallibraryplotmodelitems import PlotStyleItem, ProfileCandidateItem, \
    ProfileVisualizationGroup, PropertyItem, PropertyItemGroup, QgsPropertyItem, RasterRendererGroup, \
    SpectralProfileColorPropertyWidget
from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget, SpectralProfilePlotModel
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import TestCase, TestObjects, start_app
from qps.unitmodel import BAND_INDEX, BAND_NUMBER
from qps.utils import nextColor, nodeXmlString, parseWavelength, writeAsVectorFormat

start_app()
s = ""


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

    def test_SpectralProfilePlotVisualization(self):

        sl1 = TestObjects.createSpectralLibrary()
        sl2 = TestObjects.createSpectralLibrary()

        vis0 = ProfileVisualizationGroup()
        vis1 = ProfileVisualizationGroup()
        vis1.setSpeclib(sl1)

        vis2 = ProfileVisualizationGroup()
        vis2.setSpeclib(sl2)

        doc = QDomDocument('test')
        root = doc.createElement('root')
        doc.appendChild(root)

        context = QgsReadWriteContext()

        # restore visualization settings from XML
        vis0b: ProfileVisualizationGroup = vis0.clone()
        for p0, p1 in zip(vis0.propertyItems(), vis0b.propertyItems()):
            self.assertEqual(p0, p1)
        self.assertEqual(vis0, vis0b)
        vis0.setColor('red')
        self.assertNotEqual(vis0, vis0b)
        vis0.writeXml(root, context)
        vis0b.readXml(root, context)
        print(nodeXmlString(root))
        for p0, p1 in zip(vis0.propertyItems(), vis0b.propertyItems()):
            if p0 != p1:
                b = p0 == p1
                s = ""
        self.assertEqual(vis0, vis0b)

    def test_SpectralLibraryWidget_deleteFeatures(self):
        speclib = TestObjects.createSpectralLibrary(10)
        slw = SpectralLibraryWidget(speclib=speclib)
        speclib = slw.speclib()
        speclib.startEditing()
        speclib.selectAll()
        speclib.deleteSelectedFeatures()
        speclib.commitChanges()

        self.showGui(slw)

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
        vis0: ProfileVisualizationGroup = slw.plotControl().visualizations()[0]
        self.assertEqual(vis0.colorProperty().asExpression(), '@symbol_color')

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

        fnames = ['profilesA', 'profilesB']

        tmpDir = self.createTestOutputDirectory()
        path_sl = tmpDir / 'TestSpeclib.gpkg'
        speclib = TestObjects.createSpectralLibrary(n_bands=[25, 50], profile_field_names=fnames)

        speclib2 = writeAsVectorFormat(speclib, path_sl)
        self.assertIsInstance(speclib2, QgsVectorLayer)
        self.assertTrue(speclib2.isValid())
        self.assertTrue(path_sl.is_file())

        self.assertListEqual(fnames, profile_field_names(speclib2))
        p = QgsProject()
        p.addMapLayer(speclib2)

        slw = SpectralLibraryWidget(speclib=speclib2)
        spw: SpectralProfilePlotWidget = slw.spectralLibraryPlotWidget()
        m: SpectralProfilePlotModel = slw.plotControl()

        vis0 = slw.plotControl().visualizations()
        for i, vis in enumerate(vis0):
            self.assertEqual(vis.field().name(), fnames[i])

        doc = QDomDocument()
        n: QDomElement = doc.createElement('root')
        doc.appendChild(n)
        context = QgsReadWriteContext()
        slw.writeXml(n, context)
        slw.plotControl().readXml(n.elementsByTagName('Visualizations').item(0).toElement(), context)

        vis1 = slw.plotControl().visualizations()

        self.assertListEqual(vis0, vis1)

        # slw.plotControl().removePropertyItemGroups()
        # reload, with existing speclib instance
        slw2 = SpectralLibraryWidget.fromXml(n, context, project=p)
        self.assertIsInstance(slw2, SpectralLibraryWidget)
        self.assertEqual(slw.speclib(), slw2.speclib())
        vis1b, vis2 = slw.plotControl().visualizations(), slw2.plotControl().visualizations()
        self.assertListEqual(vis1, vis1b)
        self.assertListEqual(vis1, vis2)

        # reload, without existing speclib instance
        slw2 = SpectralLibraryWidget.fromXml(n, context)
        self.assertIsInstance(slw2, SpectralLibraryWidget)
        self.assertNotEqual(slw.speclib(), slw2.speclib())
        vis1b, vis2 = slw.plotControl().visualizations(), slw2.plotControl().visualizations()
        self.assertListEqual(vis1, vis1b)
        self.assertListEqual(vis1, vis2)

        s = ""

        p.removeAllMapLayers()
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

    def test_LayerRendererVisualization(self):

        vis = RasterRendererGroup()

        for p in vis.bandPlotItems():
            self.assertIsInstance(p, InfiniteLine)
            self.assertFalse(p.isVisible())

        barR, barG, barB, barA = vis.bandPlotItems()

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

        vis.setLayer(lyrA)
        self.assertEqual(vis.mXUnit, BAND_NUMBER)
        renderer = lyrA.renderer()
        mb_renderer = renderer.clone()
        self.assertIsInstance(renderer, QgsMultiBandColorRenderer)
        self.assertEqual(barR.name(), f'{lyrA.name()} red band {renderer.redBand()}')
        self.assertEqual(barG.name(), f'{lyrA.name()} green band {renderer.greenBand()}')
        self.assertEqual(barB.name(), f'{lyrA.name()} blue band {renderer.blueBand()}')

        self.assertEqual(vis.bandToXValue(renderer.redBand()), renderer.redBand())
        self.assertEqual(vis.bandToXValue(renderer.greenBand()), renderer.greenBand())
        self.assertEqual(vis.bandToXValue(renderer.blueBand()), renderer.blueBand())

        vis.setXUnit(BAND_INDEX)
        self.assertEqual(vis.bandToXValue(renderer.redBand()), renderer.redBand() - 1)
        self.assertEqual(vis.bandToXValue(renderer.greenBand()), renderer.greenBand() - 1)
        self.assertEqual(vis.bandToXValue(renderer.blueBand()), renderer.blueBand() - 1)

        wl, wlu = parseWavelength(lyrA)
        vis.setXUnit(wlu)
        self.assertAlmostEqual(vis.bandToXValue(renderer.redBand()), wl[renderer.redBand() - 1], 4)
        self.assertAlmostEqual(vis.bandToXValue(renderer.greenBand()), wl[renderer.greenBand() - 1], 4)
        self.assertAlmostEqual(vis.bandToXValue(renderer.blueBand()), wl[renderer.blueBand() - 1], 4)

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
        xAxis.setUnit(vis.mXUnit)
        for bar in vis.bandPlotItems():
            w.plotItem.addItem(bar)

        lyrA.setRenderer(mb_renderer)
        self.showGui(w)

        is_removed = False

        def onRemoval(*args):
            nonlocal is_removed
            is_removed = True

        vis.signals().requestRemoval.connect(onRemoval)

        # delete layer and destroy its reference.
        # this should trigger the requestRemoval signal

        # del lyrA
        proj.removeAllMapLayers()

        self.assertTrue(is_removed)
        self.assertTrue(vis.mLayer is None)
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
        model = slw.plotControl()
        self.assertIsInstance(model, SpectralProfilePlotModel)

        idx = sl.fields().lookupField(pfield.name())
        f1 = list(sl.getFeatures())[0]
        data = model.rawData(f1, idx)
        self.assertListEqual(data['x'], x)
        self.assertListEqual(data['y'], y2)

    def test_SpectralProfilePlotModel(self):

        registerSpectralLibraryPlotFactories()
        model = SpectralProfilePlotModel()
        speclib = TestObjects.createSpectralLibrary()
        canvas = QgsMapCanvas()
        dv = QgsDualView()
        dv.init(speclib, canvas)
        pw = SpectralProfilePlotWidget()
        model.setPlotWidget(pw)
        model.setDualView(dv)

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

        mimeData = model.mimeData(indices)
        grps = PropertyItemGroup.fromMimeData(mimeData)
        self.assertTrue(len(grps) > 0)
        self.assertTrue(model.canDropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))
        self.assertTrue(model.dropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))

        self.showGui(tv)

        unregisterSpectralLibraryPlotFactories()
        QgsProject.instance().removeAllMapLayers()

    def test_QgsPropertyItems(self):
        context = QgsReadWriteContext()
        itemLabel = QgsPropertyItem('Label')
        itemLabel.setDefinition(QgsPropertyDefinition(
            'Label',
            'A label to describe the plotted profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        itemLabel.setProperty(QgsProperty.fromExpression('$id'))

        itemField = QgsPropertyItem('Field')
        itemField.setIsProfileFieldProperty(True)
        itemField.setDefinition(QgsPropertyDefinition(
            'Field',
            'A field to load the plotted profiles from',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        itemField.setProperty(QgsProperty.fromField('fieldname'))

        itemFilter = QgsPropertyItem('Filter')
        itemFilter.setDefinition(QgsPropertyDefinition(
            'Filter',
            'Filter for feature rows',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        itemFilter.setProperty(QgsProperty.fromExpression(''))

        itemColor = QgsPropertyItem('Color')
        itemColor.setDefinition(QgsPropertyDefinition(
            'Color',
            'Color of spectral profile',
            QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        itemColor.setProperty(QgsProperty.fromValue(QColor('white')))

        items = [itemFilter, itemField, itemLabel, itemColor]

        doc = QDomDocument()
        root = doc.createElement('TESTGROUP')

        for item1 in items:
            self.assertIsInstance(item1, PropertyItem)
            node = doc.createElement('testnode')
            item1.writeXml(node, context)

            item2 = QgsPropertyItem(item1.key())
            item2.setDefinition(item1.definition())
            item2.readXml(node, context)

            self.assertEqual(item1, item2)

    def test_PlotStyleItem(self):

        item1 = PlotStyleItem('key')
        item1.plotStyle().setLineColor('red')
        item2 = item1.clone()
        self.assertIsInstance(item2, PlotStyleItem)
        self.assertEqual(item1, item2)

        item2.plotStyle().setLineColor('blue')
        self.assertNotEqual(item1, item2)

    def test_plotitems_xml(self):

        registerSpectralLibraryPlotFactories()

        grp = PropertyItemGroup()

        item1 = QgsPropertyItem('Field')
        item1.setIsProfileFieldProperty(True)
        item1.setDefinition(QgsPropertyDefinition(
            'Field',
            'A field to load the plotted profiles from',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        item1.setProperty(QgsProperty.fromField('fieldname'))

        item2 = PlotStyleItem('KEY')
        item2.plotStyle().setLineColor('red')

        item3 = ProfileCandidateItem('KEY')
        item3.setCellKey(1, 'testfield')
        items = [item1, item2, item3]

        context = QgsReadWriteContext()
        doc = QDomDocument()
        root = doc.createElement('TESTGROUP')
        doc.appendChild(root)

        for item in items:

            self.assertIsInstance(item, PropertyItem)
            self.assertEqual(item, item.data(Qt.UserRole),
                             msg='data(Qt.UserRole) should return self-reference to PropertyItem')

            nodeA = doc.createElement('nodeA')
            nodeB = doc.createElement('nodeB')

            item.writeXml(nodeA, context, attribute=False)
            item.writeXml(nodeB, context, attribute=True)

            cls = item.__class__
            itemA = cls(item.key())
            itemB = cls(item.key())
            self.assertIsInstance(itemA, PropertyItem)
            if isinstance(item, QgsPropertyItem):
                self.assertIsInstance(itemA, QgsPropertyItem)
                itemA.setDefinition(item.definition())
                itemB.setDefinition(item.definition())

                itemA.readXml(nodeA, context, attribute=False)
                itemB.readXml(nodeB, context, attribute=True)

                for item2 in [itemA, itemB]:
                    self.assertEqual(item2.key(), item.key())
                    self.assertEqual(item2.firstColumnSpanned(), item.firstColumnSpanned())
                    self.assertEqual(item2.label().text(), item.label().text())
                    self.assertEqual(item2.columnCount(), item.columnCount())
                    for role in [Qt.DisplayRole, Qt.DecorationRole]:
                        self.assertEqual(item2.data(role), item.data(role))

        groupsA = [grp]
        mimeData = PropertyItemGroup.toMimeData([grp])

        groupsB = PropertyItemGroup.fromMimeData(mimeData)

        self.assertListEqual(groupsA, groupsB)
        s = ""

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

    def test_SpectralLibraryPlotWidget(self):
        registerSpectralLibraryPlotFactories()
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
        proj.addMapLayers([rl1, rl2])
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
