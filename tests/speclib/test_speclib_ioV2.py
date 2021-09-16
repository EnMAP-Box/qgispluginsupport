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

import qpstestdata
from qps.speclib.core import profile_field_names
from qps.speclib.core.spectrallibrary import vsiSpeclibs
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

    def test_Mapping(self):

        speclib1 = TestObjects.createSpectralLibrary()
        speclib2 = TestObjects.createSpectralLibrary(n_bands=[24,25,36])
        # w = QgsAggregateMappingWidget()
        w = QgsFieldMappingWidget()
        w.setSourceLayer(speclib1)
        w.setDestinationFields(speclib2.fields())


        self.showGui(w)


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


        import qpstestdata
        speclib = self.createTestSpeclib()
        filewidget = QgsFileWidget()

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


    def test_importDialog(self):

        self.registerIO()
        n_bands = [25, 50, 34]
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        dialog = SpectralLibraryImportDialog()
        dialog.setSpeclib(speclib)

        src = self.testDir() / 'envi.sli'
        self.assertTrue(os.path.isfile(src))
        dialog.setSource(src)
        self.assertTrue(dialog.findMatchingFormat())

        self.assertIsInstance(dialog.currentImportWidget(), EnviSpectralLibraryImportWidget)
        source = dialog.source()
        format = dialog.currentImportWidget()
        io = format.spectralLibraryIO()

        feedback = QgsProcessingFeedback()
        coreProfiles = io.importProfiles(source, format.sourceFields(), format.importSettings({}), feedback)

        mappingWidget = dialog.fieldMappingWidget

        mapping = mappingWidget.mapping()
        propertyMap = mappingWidget.fieldPropertyMap()

        sinkDefinition = QgsRemappingSinkDefinition()
        sinkDefinition.setDestinationFields(speclib.fields())
        sinkDefinition.setSourceCrs(format.sourceCrs())
        sinkDefinition.setDestinationWkbType(speclib.wkbType())
        sinkDefinition.setFieldMap(mappingWidget.fieldPropertyMap())
        sink = QgsRemappingProxyFeatureSink(sinkDefinition, speclib)
        n = speclib.featureCount()

        self.assertTrue(speclib.startEditing())
        sink.addFeatures(coreProfiles)
        self.assertTrue(speclib.commitChanges())
        n2 = speclib.featureCount()
        self.assertEqual(n2, n + len(coreProfiles))

        self.showGui(dialog)

    def test_ImportDialog2(self):
        self.registerIO()

        speclib = SpectralLibrary()

        results = SpectralLibraryImportDialog.importProfiles(speclib, defaultRoot=self.testDir())
        s = ""

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path



    def test_ENVI_IO(self):

        testdir = self.testDir()

        n_bands = [[25, 50],
                   [75, 100]
                   ]
        n_bands = np.asarray(n_bands)
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        ENVI_IO = EnviSpectralLibraryIO()
        wExport = ENVI_IO.createExportWidget()
        self.assertIsInstance(wExport, SpectralLibraryExportWidget)
        self.assertIsInstance(wExport, EnviSpectralLibraryExportWidget)
        wExport.setSpeclib(speclib)
        self.assertEqual(EnviSpectralLibraryIO.formatName(), wExport.formatName())
        filter = wExport.filter()
        self.assertIsInstance(filter, str)
        self.assertTrue('*.sli' in filter)

        settings = dict()
        settings = wExport.exportSettings(settings)

        self.assertIsInstance(settings, dict)
        feedback = QgsProcessingFeedback()
        profiles = list(speclib.getFeatures())
        path = self.testDir() / 'exampleENVI.sli'
        files = ENVI_IO.exportProfiles(path.as_posix(), settings, profiles, feedback)
        self.assertIsInstance(files, list)
        self.assertTrue(len(files) == n_bands.shape[0])

        speclib2 = SpectralLibrary()
        wImport = ENVI_IO.createImportWidget()
        self.assertIsInstance(wImport, SpectralLibraryImportWidget)
        self.assertIsInstance(wImport, EnviSpectralLibraryImportWidget)

        for path, nb in zip(files, n_bands[:, 0]):
            self.assertTrue(os.path.exists(path))

            wImport.setSpeclib(speclib2)
            wImport.setSource(path)
            importSettings = wImport.importSettings({})
            self.assertIsInstance(importSettings, dict)
            feedback = QgsProcessingFeedback()
            fields = wImport.sourceFields()
            self.assertIsInstance(fields, QgsFields)
            self.assertTrue(fields.count() > 0)
            self.assertTrue(len(profile_field_list(fields)) > 0)
            ENVI_IO.importProfiles(path, fields, importSettings, feedback)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for profile in profiles:
                self.assertIsInstance(profile, QgsFeature)

        self.showGui([wImport])

if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
