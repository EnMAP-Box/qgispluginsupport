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
import pathlib
import re
import unittest

import xmlrunner
from qgis.core import QgsProcessingFeedback, QgsFields, QgsExpressionContext, QgsFileUtils, QgsFeature

from qgis.core import QgsVectorLayer
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils, SpectralLibrary
from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog, \
    SpectralLibraryIO, SpectralLibraryImportWidget, SpectralLibraryExportWidget
from qps.speclib.io.envi import EnviSpectralLibraryImportWidget, EnviSpectralLibraryIO
from qps.speclib.io.geojson import GeoJsonSpectralLibraryIO
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget
from qps.testing import TestObjects, TestCase
from qps.utils import file_search


class TestIO(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestIO, cls).setUpClass(*args, **kwds)
        cls.registerIO(cls)

    @classmethod
    def tearDownClass(cls):
        super(TestIO, cls).tearDownClass()

    def registerIO(self):

        ios = [GeoJsonSpectralLibraryIO(),
               GeoPackageSpectralLibraryIO(),
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
        for uri in file_search(self.createTestDir(), rx, recursive=True):
            speclib1 = SpectralLibraryIO.readSpeclibFromUri(uri, feedback=feedback)
            speclib2 = SpectralLibrary.readFrom(uri, feedback=feedback)
            if speclib1 is None:
                continue
            self.assertIsInstance(speclib1, QgsVectorLayer)
            self.assertTrue(len(speclib1) > 0)

            self.assertIsInstance(speclib2, QgsVectorLayer)
            self.assertTrue(len(speclib2) == len(speclib1))

    def test_writeTo(self):
        self.registerIO()
        DIR = self.createTestOutputDirectory()

        sl = TestObjects.createSpectralLibrary(n_bands=[[25, 45], [10, 5]])

        COUNTS = SpectralLibraryUtils.countProfiles(sl)

        self.assertIsInstance(sl, QgsVectorLayer)
        for ext in ['geojson', 'sli', 'gpkg']:

            path = DIR / f'test.speclib.{ext}'
            print(f'Test export to {path.name}')
            # SpectralLibrary.write()
            files = SpectralLibraryUtils.writeToSource(sl, path)
            self.assertIsInstance(files, list)
            self.assertTrue(len(files) > 0)
            COUNTS2 = dict()
            for file in files:
                sl2 = SpectralLibrary.readFrom(file)
                CNT = SpectralLibraryUtils.countProfiles(sl2)
                for k, cnt in CNT.items():
                    COUNTS2[k] = COUNTS2.get(k, 0) + cnt
                self.assertIsInstance(sl2, QgsVectorLayer)
                self.assertTrue(len(sl2) > 0)
            self.assertEqual(sum(COUNTS.values()), sum(COUNTS2.values()),
                             msg=f'Not all profiles written automatically: {path}')

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

            testpath = (self.createTestDir() / 'testname').as_posix()

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
            files = io.exportProfiles(testpath, features, settings, feedback)
            self.assertIsInstance(files, list)
            if len(files) == 0:
                s = ""
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

            io.exportProfiles(path, profiles, settings, feedback)

        dialog.accepted.connect(onAccepted)

        self.showGui(dialog)

    @unittest.skipIf(TestCase.runsInCI(), 'Opens blocking dialog')
    def test_ImportDialog2(self):
        self.registerIO()

        speclib = SpectralLibrary()

        results = SpectralLibraryImportDialog.importProfiles(speclib, defaultRoot=self.createTestDir())
        s = ""

    def createTestDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
