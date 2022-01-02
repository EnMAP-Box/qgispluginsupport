import os
import unittest
import xmlrunner
from PyQt5.QtCore import QEvent, QPointF, Qt, QVariant
from PyQt5.QtGui import QMouseEvent, QColor
from PyQt5.QtWidgets import QHBoxLayout, QWidget
from PyQt5.QtXml import QDomDocument
from osgeo import gdal, ogr

from qgis.core import QgsVectorLayer, QgsField, QgsEditorWidgetSetup, QgsProject, QgsProperty, QgsFeature, \
    QgsRenderContext
from qgis.gui import QgsMapCanvas, QgsDualView
from qps.speclib.core import create_profile_field, profile_fields

from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget, SpectralProfilePlotWidget, \
    SpectralProfilePlotVisualization, SpectralProfileColorPropertyWidget
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import StartOptions, TestCase, TestObjects
from qps.utils import nextColor


class TestSpeclibWidgets(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        options = StartOptions.All

        super(TestSpeclibWidgets, cls).setUpClass(*args, options=options)

        from qps import initAll
        initAll()

        gdal.UseExceptions()
        gdal.PushErrorHandler(TestSpeclibWidgets.gdal_error_handler)
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

        vis0 = SpectralProfilePlotVisualization()
        vis1 = SpectralProfilePlotVisualization()
        vis1.setSpeclib(sl1)

        vis2 = SpectralProfilePlotVisualization()
        vis2.setSpeclib(sl2)

        model1 = TestObjects.createSpectralProcessingModel('model1')
        model2 = TestObjects.createSpectralProcessingModel('model2')

        vis1.setModelId(model1)
        vis2.setModelId(model2)

        doc = QDomDocument()
        root = doc.createElement('root')

        visList = [vis0, vis1, vis2]
        for v in visList:
            v.writeXml(root, doc)

        available_speclibs = [sl1, sl2]
        visList2 = SpectralProfilePlotVisualization.fromXml(root,
                                                            available_speclibs=available_speclibs)

        self.assertTrue(len(visList) == len(visList2))

        for v1, v2 in zip(visList, visList2):
            self.assertIsInstance(v1, SpectralProfilePlotVisualization)
            self.assertIsInstance(v2, SpectralProfilePlotVisualization)

            self.assertEqual(v1.name(), v2.name())
            self.assertEqual(v1.labelProperty(), v2.labelProperty())
            self.assertEqual(v1.plotStyle(), v2.plotStyle())
            self.assertEqual(v1.speclib(), v2.speclib())
            # speclib and model instances need to be restored differently

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

    def test_SpectralLibraryPlotWidget(self):

        speclib = TestObjects.createSpectralLibrary(n_bands=[-1, 12])
        canvas = QgsMapCanvas()
        dv = QgsDualView()
        dv.init(speclib, canvas)

        w = SpectralLibraryPlotWidget()
        w.setDualView(dv)

        visModel = w.treeView.model().sourceModel()
        self.assertEqual(visModel.rowCount(), 1)

        # add a VIS
        w.btnAddProfileVis.click()
        self.assertEqual(visModel.rowCount(), 2)

        # click into each cell
        for row in range(visModel.rowCount()):
            for col in range(visModel.columnCount()):
                idx = w.treeView.model().index(row, col)
                w.treeView.edit(idx)

        # remove vis

        w.treeView.selectVisualizations(visModel[0])
        w.btnRemoveProfileVis.click()

        speclib.startEditing()
        speclib.addSpectralProfileField('profiles3')
        speclib.commitChanges(stopEditing=False)
        speclib.deleteAttribute(speclib.fields().lookupField('profiles3'))
        speclib.commitChanges(stopEditing=False)
        self.showGui([w])

    def test_rendering(self):



        speclib = TestObjects.createSpectralLibrary()
        QgsProject.instance().addMapLayers([speclib], False)
        slw = SpectralLibraryWidget(speclib=speclib)

        canvas = QgsMapCanvas()

        canvas.setLayers([speclib])
        canvas.zoomToFullExtent()

        l = QHBoxLayout()
        l.addWidget(canvas)
        l.addWidget(slw)

        w = QWidget()
        w.setLayout(l)
        self.showGui(w)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
