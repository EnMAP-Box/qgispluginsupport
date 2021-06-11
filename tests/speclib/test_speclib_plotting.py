import os

from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtXml import QDomDocument
from osgeo import gdal, ogr
from qgis.gui import QgsMapCanvas, QgsDualView

from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget, SpectralProfilePlotWidget, \
    SpectralProfilePlotVisualization
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import StartOptions, TestCase, TestObjects


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
            self.assertEqual(v1.labelExpression(), v2.labelExpression())
            self.assertEqual(v1.plotStyle(), v2.plotStyle())
            self.assertEqual(v1.speclib(), v2.speclib())
            # speclib and model instances need to be restored differently

    def test_SpectralProfilePlotWidget(self):

        speclib = TestObjects.createSpectralLibrary()

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

        # add spectral processing models
        spm = TestObjects.createSpectralProcessingModel()
        from qps.speclib.processing import is_spectral_processing_model
        self.assertTrue(is_spectral_processing_model(spm))
        # w.addSpectralModel(spm)

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
