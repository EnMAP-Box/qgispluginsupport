import unittest

import xmlrunner
from osgeo import gdal, ogr

from qgis.PyQt.QtCore import QEvent, QPointF, Qt, QVariant
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtGui import QMouseEvent, QColor
from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget
from qgis.PyQt.QtWidgets import QTreeView
from qgis.PyQt.QtWidgets import QVBoxLayout
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsPropertyDefinition
from qgis.core import QgsSingleBandGrayRenderer, QgsMultiBandColorRenderer
from qgis.core import QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsProject, QgsProperty, QgsFeature, \
    QgsRenderContext
from qgis.gui import QgsMapCanvas, QgsDualView
from qps.pyqtgraph.pyqtgraph import InfiniteLine
from qps.speclib.core import create_profile_field, profile_fields
from qps.speclib.gui.spectrallibraryplotitems import SpectralXAxis, SpectralProfilePlotWidget
from qps.speclib.gui.spectrallibraryplotmodelitems import RasterRendererGroup, ProfileVisualizationGroup, \
    SpectralProfileColorPropertyWidget, PropertyItemGroup, PlotStyleItem, ProfileCandidateItem, PropertyItem, \
    QgsPropertyItem
from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget, SpectralProfilePlotModel
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import StartOptions, TestCase, TestObjects
from qps.unitmodel import BAND_INDEX, BAND_NUMBER
from qps.utils import nextColor, parseWavelength


class TestSpeclibPlotting(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        options = StartOptions.All

        super(TestSpeclibPlotting, cls).setUpClass(*args, options=options)

        from qps import initAll
        initAll()

        gdal.UseExceptions()
        gdal.PushErrorHandler(TestSpeclibPlotting.gdal_error_handler)
        ogr.UseExceptions()

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
        registerSpectralProfileEditorWidget()
        super().setUp()

    def test_SpectralProfilePlotVisualization(self):

        sl1 = TestObjects.createSpectralLibrary()
        sl2 = TestObjects.createSpectralLibrary()

        vis0 = ProfileVisualizationGroup()
        vis1 = ProfileVisualizationGroup()
        vis1.setSpeclib(sl1)

        vis2 = ProfileVisualizationGroup()
        vis2.setSpeclib(sl2)

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

    @unittest.skipIf(True, '')
    def test_SpectralProfileColorProperty(self):
        speclib: QgsVectorLayer = TestObjects.createSpectralLibrary()
        speclib.startEditing()
        colorField = QgsField('color', type=QVariant.String)
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
        context = speclib.createExpressionContext()

        profile = speclib[0]
        context.setFeature(profile)

        renderer = speclib.renderer().clone()
        renderer.startRender(renderContext, speclib.fields())
        symbol = renderer.symbolForFeature(profile, renderContext)
        context.appendScope(symbol.symbolRenderContext().expressionContextScope())
        color1 = symbol.color()
        print(color1.name())
        self.assertIsInstance(p, QgsProperty)
        color2, success = p.valueAsColor(context, defaultColor=QColor('black'))
        print(color2.name())
        renderer.stopRender(renderContext)
        self.assertEqual(color1, color2)
        del renderer
        # self.showGui(w)

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

    def test_SpectralProfilePlotControlModel(self):
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

        self.assertEqual(model.rowCount(), 3)

        indices = [model.createIndex(2, 0),
                   model.createIndex(1, 0), model.createIndex(1, 1)]
        mimeData = model.mimeData(indices)
        grps = PropertyItemGroup.fromMimeData(mimeData)
        self.assertEqual(len(grps), 2)
        self.assertTrue(model.canDropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))
        self.assertTrue(model.dropMimeData(mimeData, Qt.CopyAction, 0, 0, QModelIndex()))

        self.showGui(tv)

    def test_QgsPropertyItems(self):

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
            item1.writeXml(node, doc)

            item2 = QgsPropertyItem(item1.key())
            item2.setDefinition(item1.definition())
            item2.readXml(node)

            self.assertEqual(item1, item2)

    def test_plotitems_xml(self):

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

        doc = QDomDocument()
        root = doc.createElement('TESTGROUP')
        for item in items:

            self.assertIsInstance(item, PropertyItem)
            self.assertEqual(item, item.data(Qt.UserRole),
                             msg='data(Qt.UserRole) should return self-reference to PropertyItem')

            nodeA = doc.createElement('nodeA')
            nodeB = doc.createElement('nodeB')
            item.writeXml(nodeA, doc, attribute=False)
            item.writeXml(nodeB, doc, attribute=True)

            cls = item.__class__
            itemA = cls(item.key())
            itemB = cls(item.key())
            self.assertIsInstance(itemA, PropertyItem)
            if isinstance(item, QgsPropertyItem):
                self.assertIsInstance(itemA, QgsPropertyItem)
                itemA.setDefinition(item.definition())
                itemB.setDefinition(item.definition())

            itemA.readXml(nodeA, attribute=False)
            itemB.readXml(nodeB, attribute=True)

            for item2 in [itemA, itemB]:
                self.assertEqual(item2.key(), item.key())
                self.assertEqual(item2.firstColumnSpanned(), item.firstColumnSpanned())
                self.assertEqual(item2.label().text(), item.label().text())
                self.assertEqual(item2.columnCount(), item.columnCount())
                for role in [Qt.DisplayRole, Qt.DecorationRole]:
                    self.assertEqual(item2.data(role), item.data(role))

        mimeData = PropertyItemGroup.toMimeData([grp])

        grp1 = PropertyItemGroup.fromMimeData(mimeData)

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
        proj.addMapLayers([rl1, rl2])
        w.setProject(proj)

        speclib.startEditing()
        speclib.addSpectralProfileField('profiles3')
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


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
