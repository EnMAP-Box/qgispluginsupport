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
# noinspection PyPep8Naming
import os
import re
import unittest
import xmlrunner


from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget
from qps.testing import TestObjects, TestCase

from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsEditorWidgetSetup, QgsField

from qpstestdata import enmap, landcover
from qpstestdata import speclib as speclibpath

from qps.speclib.io.vectorsources import *
from qps.speclib.io.csvdata import *
from qps.speclib.io.envi import *
from qps.speclib.io.rastersources import *

from qps.utils import *


class TestIO(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestIO, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestIO, cls).tearDownClass()

    def registerIO(self):

        ios = [GeoPackageSpectralLibraryIO(),
               EnviSpectralLibraryIO(),
               ]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_importWidgets(self):

        widgets = [EnviSpectralLibraryImportWidget(),
                   GeoPackageSpectralLibraryImportWidget()]
        import qpstestdata
        gpkg = TestObjects.createSpectralLibrary(n_bands=[75, 75])
        EXAMPLES = {
            EnviSpectralLibraryImportWidget.__name__: qpstestdata.speclib,
            GeoPackageSpectralLibraryImportWidget.__name__: gpkg.source()
        }
        n_bands = [[25, 75], [50, 100]]

        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        for w in widgets:
            self.assertIsInstance(w, SpectralLibraryImportWidget)
            print(f'Test {w.__class__.__name__}: "{w.formatName()}"')

            w.setSpeclib(speclib)

            filter = w.filter()
            self.assertIsInstance(filter, str)
            self.assertTrue(len(filter) > 0)

            context = w.createExpressionContext()
            self.assertIsInstance(context, QgsExpressionContext)

            source = EXAMPLES[w.__class__.__name__]

            fields = w.sourceFields()
            self.assertIsInstance(fields, QgsFields)
            w.setSource(source)

            fields = w.sourceFields()
            self.assertIsInstance(fields, QgsFields)

    def test_readFrom(self):
        self.registerIO()

        feedback = QgsProcessingFeedback()
        rx = re.compile(r'\.(sli|asd|gpkg|csv)$')
        for uri in file_search(self.testDir(), rx, recursive=True):
            speclib1 = SpectralLibraryIO.readSpeclibFromUri(uri, feedback=feedback)
            speclib2 = SpectralLibrary.readFrom(uri, feedback=feedback)
            if speclib1 is None:
                continue
            self.assertIsInstance(speclib1, SpectralLibrary)
            self.assertTrue(len(speclib1) > 0)

            self.assertIsInstance(speclib2, SpectralLibrary)
            self.assertTrue(len(speclib2) == len(speclib1))

    def test_exportWidgets(self):
        self.registerIO()

        widgets = []
        for io in SpectralLibraryIO.spectralLibraryIOs():
            w = io.createExportWidget()
            if isinstance(w, SpectralLibraryExportWidget):
                widgets.append(w)

        speclib = self.createTestSpeclib()

        layername = 'testlayer'
        for w in widgets:
            print(f'Test {w.__class__.__name__}')
            self.assertIsInstance(w, SpectralLibraryExportWidget)

            testpath = (self.testDir() / 'testname').as_posix()

            extensions = QgsFileUtils.extensionsFromFilter(w.filter())
            testpath = QgsFileUtils.ensureFileNameHasExtension(testpath, extensions)
            w.setSpeclib(speclib)

            settings = w.exportSettings({})

            if w.supportsLayerName():
                settings['layer_name'] = layername

            feedback = QgsProcessingFeedback()

            features = list(speclib.getFeatures())

            io: SpectralLibraryIO = w.spectralLibraryIO()
            self.assertIsInstance(io, SpectralLibraryIO)
            files = io.exportProfiles(testpath, settings, features, feedback)
            self.assertIsInstance(files, list)
            self.assertTrue(len(files) > 0)
            wImport = io.createImportWidget()
            speclibImport = None
            if isinstance(wImport, SpectralLibraryImportWidget):
                speclibImport = self.createTestSpeclib()
                wImport.setSpeclib(speclib)

            for f in files:
                self.assertTrue(os.path.isfile(f))
                if isinstance(wImport, SpectralLibraryImportWidget):
                    wImport.setSource(f)
                    importSettings = wImport.importSettings({})
                    sourceFields = wImport.sourceFields()
                    importedProfiles = list(io.importProfiles(f, importSettings, feedback))
                    self.assertTrue(len(importedProfiles) > 0)
                    for p in importedProfiles:
                        self.assertIsInstance(p, QgsFeature)

    def createTestSpeclib(self) -> QgsVectorLayer:
        n_bands = [1025, 240, 8]
        profile_field_names = ['ASD', 'EnMAP', 'Landsat']
        return TestObjects.createSpectralLibrary(n_bands=n_bands, profile_field_names=profile_field_names)

    def test_exportDialog(self):
        self.registerIO()
        speclib = self.createTestSpeclib()
        speclib.selectByIds([1, 3, 5, 7])

        dialog = SpectralLibraryExportDialog()
        dialog.setSpeclib(speclib)

        def onAccepted():
            w = dialog.currentExportWidget()
            self.assertIsInstance(w, SpectralLibraryExportWidget)

            settings = dialog.exportSettings()
            self.assertIsInstance(settings, dict)
            feedback = QgsProcessingFeedback()
            path = dialog.exportPath()
            self.assertIsInstance(path, str)

            io = dialog.exportIO()
            self.assertIsInstance(io, SpectralLibraryIO)

            if dialog.saveSelectedFeaturesOnly():
                profiles = speclib.getSelectedFeatures()
            else:
                profiles = speclib.getFeatures()

            io.exportProfiles(path, settings, profiles, feedback)

        dialog.accepted.connect(onAccepted)

        self.showGui(dialog)

    @unittest.skipIf(TestCase.runsInCI(), 'Opens blocking dialog')
    def test_ImportDialog2(self):
        self.registerIO()

        speclib = SpectralLibrary()

        results = SpectralLibraryImportDialog.importProfiles(speclib, defaultRoot=self.testDir())
        s = ""

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path



if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
