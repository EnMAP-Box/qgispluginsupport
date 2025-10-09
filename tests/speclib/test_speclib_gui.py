# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import logging
# noinspection PyPep8Naming
import os
import pathlib
import unittest

from osgeo import gdal, ogr

from qgis.PyQt.QtCore import QMimeData, QPoint, Qt, QUrl
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QDropEvent
from qgis.PyQt.QtWidgets import QAction, QApplication, QComboBox, QDialog, QPushButton, QToolBar, QToolButton, \
    QVBoxLayout, QWidget
from qgis.core import QgsFeature, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsGui, QgsMapCanvas
from qps import registerEditorWidgets
from qps.layerproperties import AddAttributeDialog
from qps.speclib.core import is_spectral_library, profile_field_list
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotWidget
from qps.speclib.gui.spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel
from qps.speclib.gui.spectrallibraryplotwidget import SpectralLibraryPlotWidget
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import start_app, TestCase, TestObjects
from qps.unitmodel import BAND_NUMBER, UnitLookup
from qps.utils import setToolButtonDefaultActionMenu
from qpstestdata import enmap, hymap, speclib_geojson

start_app()


class TestSpeclibWidgets(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:

        super(TestSpeclibWidgets, cls).setUpClass(*args, **kwds)

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
        super().setUp()
        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()
            registerEditorWidgets()

        from qps import registerMapLayerConfigWidgetFactories
        registerMapLayerConfigWidgetFactories()

    def test_SpectralLibraryPlotWidget(self):

        from qps.resources import ResourceBrowser
        w = SpectralLibraryPlotWidget()
        rb = ResourceBrowser()

        self.showGui([w, rb])

    @unittest.skipIf(False, '')
    def test_toolbarStackedActions(self):

        tb = QToolBar()
        a1 = tb.addAction('Action1')
        a2 = tb.addAction('ActionA2')

        a21 = QAction('A2.1')
        a22 = QAction('A2.2')
        a22.setCheckable(True)

        setToolButtonDefaultActionMenu(a2, [a21, a22])

        btn2 = tb.findChildren(QToolButton)[2]
        self.assertIsInstance(btn2, QToolButton)

        self.showGui(tb)

    def test_UnitComboBox(self):

        cb = QComboBox()
        model = SpectralProfilePlotXAxisUnitModel()
        for k in UnitLookup.LENGTH_UNITS.keys():
            model.addUnit(k)

        cb.setModel(model)

        self.showGui(cb)

    @unittest.skipIf(TestCase.runsInCI(), 'Fuzz test (drag and drop)')
    def test_dropping_speclibs(self):

        files = []

        for root, dirs, f in os.walk(pathlib.Path(__file__).parents[1] / 'qpstestdata'):
            for file in f:
                files.append(pathlib.Path(root) / file)

        slw = SpectralLibraryWidget()
        # drop a valid speclib
        md = QMimeData()
        from qpstestdata import envi_sli

        sl = QgsVectorLayer(envi_sli, 'Speclib')

        md.setUrls([QUrl.fromLocalFile(envi_sli)])

        event = QDropEvent(QPoint(0, 0), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
        print('Drop {}'.format(envi_sli), flush=True)
        slw.dropEvent(event)
        self.assertEqual(len(slw.speclib()), len(sl))

        # drop random files
        slw = SpectralLibraryWidget()
        self.assertTrue(len(slw.speclib()) == 0)
        n = 0
        for file in files:
            n += 1
            if n >= 10:
                break
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(file.as_posix())])
            print('# Drop {}'.format(file.name), flush=True)
            event = QDropEvent(QPoint(0, 0), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
            slw.dropEvent(event)
            QApplication.processEvents()
            # delete dropped spectra
            slw.speclib().startEditing()
            slw.speclib().deleteFeatures(slw.speclib().allFeatureIds())
            slw.speclib().commitChanges()
            s = ""

        self.showGui(slw)

    def test_CurrentProfiles(self):

        slw = SpectralLibraryWidget()

        def onClicked(*args):
            sl = TestObjects.createSpectralLibrary(2)
            slw.setCurrentProfiles(sl[:])

        btnAddTempProfiles = QPushButton('Add Temp Profiles')
        btnAddTempProfiles.clicked.connect(onClicked)

        w2 = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(btnAddTempProfiles)
        layout.addWidget(slw)
        w2.setLayout(layout)
        self.showGui(w2)
        slw.project().removeAllMapLayers()
        QgsProject.instance().removeAllMapLayers()

        s = ""

    def test_SpectralLibraryWidget_empty_vectorlayer(self):

        vl = TestObjects.createVectorLayer()

        slw = SpectralLibraryWidget(speclib=vl)
        self.assertTrue(not is_spectral_library(slw.speclib()))
        self.assertIsInstance(slw, SpectralLibraryWidget)
        self.showGui(slw)
        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(TestCase.runsInCI(), 'GUI test only')
    def test_SpectralLibraryWidget_Empty(self):

        slw = SpectralLibraryWidget()
        self.showGui(slw)

    @unittest.skipIf(TestCase.runsInCI(), 'GUI test only')
    def test_SpectralLibraryWidget_Simple(self):
        # QApplication.setStyle("Fusion")

        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)s %(module)s %(funcName)s: %(message)s',
                            handlers=[
                                # logging.FileHandler("debug.log"),  # Log to a file
                                logging.StreamHandler()  # Log to console
                            ])
        sl1 = TestObjects.createSpectralLibrary(n=10)
        sl1.setName('Speclib A')

        sl2 = TestObjects.createSpectralLibrary(n=10)
        sl2.setName('Speclib B')

        rl1 = TestObjects.createRasterLayer(nb=5)

        project = QgsProject()
        project.addMapLayers([sl1, sl2, rl1])
        slw = SpectralLibraryWidget(speclib=sl2, project=project)
        slw.resize(QSize(1000, 600))
        self.assertEqual(project, slw.project())
        self.showGui(slw)
        project.removeAllMapLayers()

    def test_SpectralLibraryWidget(self):

        from qpstestdata import enmap, landcover, enmap_pixel

        l1 = QgsRasterLayer(enmap.as_posix(), 'EnMAP')
        l2 = QgsVectorLayer(landcover.as_posix(), 'LandCover')
        l3 = QgsVectorLayer(enmap_pixel.as_posix(), 'Points of Interest')
        l4 = QgsRasterLayer(enmap.as_posix(), 'EnMAP-2')
        QgsProject.instance().addMapLayers([l1, l2, l3, l4])

        sl1 = TestObjects.createSpectralLibrary(5, n_bands=[177, 6], wlu='Nanometers')
        sl1.setName(' My Speclib')

        sl2 = TestObjects.createSpectralLibrary(3, n_bands=[177, 6], wlu='Nanometers')

        slw = SpectralLibraryWidget(speclib=sl1)

        sl1.startEditing()
        SpectralLibraryUtils.addSpeclib(sl1, sl2)

        profiles = TestObjects.spectralProfiles(4, fields=sl1.fields(), n_bands=[7, 12])
        slw.plotModel().addProfileCandidates({sl1.id(): profiles})
        fids_a = sl1.allFeatureIds()
        # sl1.commitChanges()
        # fids_b = sl1.allFeatureIds()

        QgsProject.instance().addMapLayer(slw.speclib())

        # self.assertEqual(slw.speclib(), sl1)
        # self.assertIsInstance(slw.speclib(), QgsVectorLayer)
        # fieldNames = slw.speclib().fields().names()
        # self.assertIsInstance(fieldNames, list)

        # self.assertTrue(slw.speclib() == sl1)

        self.showGui([slw])

        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(False, '')
    def test_SpectralLibraryWidgetCanvas(self):

        # speclib = self.createSpeclib()

        lyr = QgsRasterLayer(hymap.as_posix())
        h, w = lyr.height(), lyr.width()
        speclib = TestObjects.createSpectralLibrary()
        slw = SpectralLibraryWidget(speclib=speclib)

        QgsProject.instance().addMapLayers([lyr, slw.speclib()])

        canvas = QgsMapCanvas()

        canvas.setLayers([speclib, lyr])
        canvas.setDestinationCrs(speclib.crs())
        canvas.setExtent(speclib.extent())

        def setLayers():
            canvas.mapSettings().setDestinationCrs(slw.mCanvas.mapSettings().destinationCrs())
            canvas.setExtent(slw.canvas().extent())
            canvas.setLayers(slw.canvas().layers())

        slw.sigMapCenterRequested.connect(setLayers)
        slw.sigMapExtentRequested.connect(setLayers)

        self.showGui([canvas, slw])
        QgsProject.instance().removeAllMapLayers()

    def test_delete_speclib(self):

        speclib = TestObjects.createSpectralLibrary(10)
        project = QgsProject()
        project.addMapLayer(speclib)
        w = SpectralLibraryWidget(speclib=speclib, project=project)
        w.show()

        project.removeAllMapLayers()

        speclibs = w.plotModel().spectralLibraries()
        self.assertEqual(0, len(speclibs))

    def test_SpectralProfileImportPointsDialog(self):

        lyrRaster = QgsRasterLayer(enmap.as_posix())
        lyrRaster.setName('EnMAP')
        h, w = lyrRaster.height(), lyrRaster.width()

        pxPositions = [QPoint(0, 0), QPoint(w - 1, h - 1)]

        vl1 = TestObjects.createVectorLayer(QgsWkbTypes.Point)
        vl2 = TestObjects.createVectorLayer(QgsWkbTypes.LineGeometry)
        vl3 = TestObjects.createVectorLayer(QgsWkbTypes.Polygon)

        layers = [vl1,
                  vl2,
                  vl3]
        # layers = [speclib1]

        QgsProject.instance().addMapLayers(layers)
        from qps.speclib.io.rastersources import SpectralProfileImportPointsDialog

        def onFinished(code):
            self.assertTrue(code in [QDialog.Accepted, QDialog.Rejected])

            if code == QDialog.Accepted:
                slib = d.speclib()
                profiles = d.profiles()
                self.assertTrue(d.isFinished())
                self.assertIsInstance(slib, QgsVectorLayer)
                self.assertIsInstance(profiles, list)
                self.assertTrue(len(profiles) > 0)
                if len(profiles) != len(slib):
                    s = ""
                self.assertTrue(len(profiles) == len(slib))

        for vl in layers:
            d = SpectralProfileImportPointsDialog()
            self.assertEqual(d.aggregation(), 'mean')
            d.setAggregation('median')
            d.setWkbType(vl.wkbType())
            self.assertEqual(d.aggregation(), 'median')

            self.assertIsInstance(d, SpectralProfileImportPointsDialog)
            d.setRasterSource(lyrRaster)
            d.setVectorSource(vl)
            self.showGui(d)
            self.assertEqual(lyrRaster, d.rasterSource())
            self.assertEqual(vl, d.vectorSource())

            d.finished.connect(onFinished)
            d.run(run_async=False)
            while not d.isFinished():
                QApplication.processEvents()
            d.hide()
            d.close()

        # self.showGui(d)
        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(TestCase.runsInCI(), 'Opens blocking dialog')
    def test_AttributeDialog(self):

        SLIB = TestObjects.createSpectralLibrary()
        d = AddAttributeDialog(SLIB)
        self.showGui(d)

    def test_SpectralLibraryWidget_loadProfileFields(self):

        # test profile field detection
        lyr = QgsVectorLayer(speclib_geojson.as_posix())
        pfields = profile_field_list(lyr)
        self.assertEqual(1, len(pfields))

        lyr = QgsVectorLayer(speclib_geojson.as_posix(), options=QgsVectorLayer.LayerOptions(loadDefaultStyle=False))
        pfields = profile_field_list(lyr)
        self.assertEqual(0, len(pfields))

        w = SpectralLibraryWidget(speclib=lyr)
        pfields = profile_field_list(lyr)
        self.assertEqual(1, len(pfields))

        self.showGui(w)
        w.plotModel().project().removeAllMapLayers()

    def test_SpectralLibraryWidgetProgressDialog(self):

        slib = TestObjects.createSpectralLibrary(3000)
        self.assertIsInstance(slib, QgsVectorLayer)
        self.assertTrue(slib.isValid())

    def test_SpectralLibraryWidgetCurrentProfilOverlayerXUnit(self):

        sw = SpectralLibraryWidget()
        self.assertIsInstance(sw, SpectralLibraryWidget)
        pw = sw.plotWidget()
        self.assertIsInstance(pw, SpectralProfilePlotWidget)
        self.assertEqual(BAND_NUMBER, pw.xAxis().unit())
        slib = TestObjects.createSpectralLibrary(10)

        pField = profile_field_list(slib)[0]
        xunits = []
        features = list(slib.getFeatures())
        for p in features:
            self.assertIsInstance(p, QgsFeature)
            d = decodeProfileValueDict(p.attribute(pField.name()))
            u = d.get('xUnit', None)
            if u not in xunits:
                xunits.append(u)

        sw = SpectralLibraryWidget(speclib=slib)
        sw.updatePlot()

        sw = SpectralLibraryWidget()
        sw.updatePlot()
        currentProfiles = features[0:2]
        sw.plotModel().addProfileCandidates({slib.id(): currentProfiles})
        sw.updatePlot()
        sw.plotModel().project().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
