import os

from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QMouseEvent
from osgeo import gdal, ogr
from qgis._gui import QgsMapCanvas, QgsDualView

from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget, SpectralProfilePlotWidget
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

        speclib = TestObjects.createSpectralLibrary(n_profile_fields=2)
        canvas = QgsMapCanvas()
        dv = QgsDualView()
        dv.init(speclib, canvas)

        w = SpectralLibraryPlotWidget()
        w.setDualView(dv)

        # add spectral processing models
        spm = TestObjects.createSpectralProcessingModel()
        from qps.speclib.processing import is_spectral_processing_model
        self.assertTrue(is_spectral_processing_model(spm))
        w.addSpectralModel(spm)

        visModel = w.tableView.model()
        self.assertEqual(visModel.rowCount(), 0)
        # add a VIS
        w.btnAddProfileVis.click()
        self.assertEqual(visModel.rowCount(), 1)

        # click into each cell
        for row in range(visModel.rowCount()):
            for col in range(visModel.columnCount()):
                idx = w.tableView.model().index(row, col)
                w.tableView.edit(idx)

        # remove row
        w.tableView.selectRow(0)
        w.btnRemoveProfileVis.click()

        self.assertEqual(visModel.rowCount(), 0)

        w.actionAddProfileVis.trigger()
        self.assertEqual(visModel.rowCount(), 1)

        speclib.startEditing()
        speclib.addSpectralProfileAttribute('profiles3')
        speclib.commitChanges(stopEditing=False)
        speclib.deleteAttribute(speclib.fields().lookupField('profiles3'))
        speclib.commitChanges(stopEditing=False)
        self.showGui([w, dv])
