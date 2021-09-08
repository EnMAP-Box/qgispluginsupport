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
import unittest
import xmlrunner

import qpstestdata
from qps.speclib.core import profile_field_names
from qps.speclib.core.spectrallibrary import vsiSpeclibs
from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget
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
        n_bands = [[25,75], [50,100]]

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
        self.showGui(dialog)


    def test_importDialog(self):

        self.registerIO()
        n_bands = [25, 50, 34]
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        dialog = SpectralLibraryImportDialog()
        dialog.setSpeclib(speclib)
        self.showGui(dialog)


    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path



    def test_ENVI_Export(self):

        testdir = self.testDir()

        n_bands = [[25, 50],
                   [75, 100]
                   ]
        n_bands = np.asarray(n_bands)
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        w = EnviSpectralLibraryExportWidget()
        w.setSpeclib(speclib)
        self.assertEqual(EnviSpectralLibraryIO.formatName(), w.formatName())
        filter = w.filter()
        self.assertIsInstance(filter, str)
        self.assertTrue('*.sli' in filter)

        settings = {SpectralLibraryExportWidget.EXPORT_PATH: (testdir / 'envi.sli').as_posix(),
                    SpectralLibraryExportWidget.EXPORT_FORMAT: '*.sli',
                    SpectralLibraryExportWidget.EXPORT_LAYERNAME: None,
                    SpectralLibraryExportWidget.EXPORT_FIELDS: profile_field_names(speclib)[0:1]
                    }

        settings = w.exportSettings(settings)
        self.assertIsInstance(settings, dict)
        feedback = QgsProcessingFeedback()
        profiles = list(speclib.getFeatures())
        files = w.exportProfiles(settings, profiles, feedback)
        self.assertIsInstance(files, list)
        self.assertTrue(len(files) == n_bands.shape[0])

    def test_ENVI_Import(self):
        speclib = self.createTestSpeclib()
        path_sli = qpstestdata.speclib
        w = EnviSpectralLibraryImportWidget()
        self.assertIsInstance(w, SpectralLibraryImportWidget)
        w.setSpeclib(speclib)
        self.assertIsInstance(w.sourceFields(), QgsFields)
        w.setSource(path_sli)


        w.importProfiles()
        for f, nb in zip(files, n_bands[:, 0]):
            self.assertTrue(os.path.exists(f))

            importSettings = {SpectralLibraryImportWidget.IMPORT_PATH: f,
                              }

            importSettings = w.importSettings(importSettings)
            self.assertIsInstance(importSettings, dict)

            feedback = QgsProcessingFeedback()
            profiles = w.importProfiles(speclib.fields(), importSettings, feedback)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for profile in profiles:
                self.assertIsInstance(profile, QgsFeature)

        self.showGui([w])

if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
