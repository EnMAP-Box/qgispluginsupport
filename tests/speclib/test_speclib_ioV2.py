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

from qps.speclib.core import profile_field_names
from qps.speclib.core.spectrallibrary import vsiSpeclibs
from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
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

    def test_exportDialog(self):
        SpectralLibraryExportDialog.registerExportWidget(EnviSpectralLibraryExportWidget())
        self.assertTrue(len(SpectralLibraryExportDialog.EXPORT_WIDGETS) == 1)
        SpectralLibraryExportDialog.registerExportWidget(EnviSpectralLibraryExportWidget())
        self.assertTrue(len(SpectralLibraryExportDialog.EXPORT_WIDGETS) == 1)

        dialog = SpectralLibraryExportDialog()

        self.showGui(dialog)

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path

    def test_ENVI(self):

        testdir = self.testDir()

        n_bands = [[25, 50],
                   [75, 100]
                   ]
        n_bands = np.asarray(n_bands)
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        w = EnviSpectralLibraryExportWidget()
        w.setSpeclib(speclib)
        self.assertEqual('Envi Spectral Library', w.formatName())
        filter = w.filter()
        self.assertIsInstance(filter, str)
        self.assertTrue('*.sli' in filter)

        settings = {AbstractSpectralLibraryExportWidget.EXPORT_PATH: (testdir / 'envi.sli').as_posix(),
                    AbstractSpectralLibraryExportWidget.EXPORT_FORMAT: '*.sli',
                    AbstractSpectralLibraryExportWidget.EXPORT_LAYERNAME: None,
                    AbstractSpectralLibraryExportWidget.EXPORT_FIELDS: profile_field_names(speclib)[0:1]
        }

        settings = w.exportSettings(settings)
        self.assertIsInstance(settings, dict)
        feedback = QgsProcessingFeedback()
        profiles = list(speclib.getFeatures())
        files = w.exportProfiles(settings, profiles, feedback)
        self.assertIsInstance(files, list)
        self.assertTrue(len(files) == n_bands.shape[0])

        speclib2 = TestObjects.createSpectralLibrary()

        importWidget = EnviSpectralLibraryImportWidget()
        self.assertIsInstance(importWidget, AbstractSpectralLibraryImportWidget)
        importWidget.setSpeclib(speclib2)

        for f, nb in zip(files, n_bands[:, 0]):
            self.assertTrue(os.path.exists(f))

            importSettings = {AbstractSpectralLibraryImportWidget.IMPORT_PATH: f,
                              AbstractSpectralLibraryImportWidget.IMPORT_FIELDS:  profile_field_names(speclib2)[0:1]
                              }

            importSettings = importWidget.importSettings(importSettings)
            self.assertIsInstance(importSettings, dict)

            feedback = QgsProcessingFeedback()
            profiles = importWidget.importProfiles(importSettings, feedback)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for profile in profiles:
                self.assertIsInstance(profile, QgsFeature)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
