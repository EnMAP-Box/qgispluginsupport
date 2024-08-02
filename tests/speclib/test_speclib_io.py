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

from qgis.core import edit, QgsExpressionContext, QgsExpressionContextScope, QgsFeature, QgsField, QgsFields, \
    QgsFileUtils, QgsProcessingFeedback, QgsProject, QgsProperty, QgsRemappingSinkDefinition, QgsVectorLayer

from qps.qgisenums import QMETATYPE_QSTRING
from qps.speclib.core import create_profile_field
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs, SpectralLibraryExportDialog, \
    SpectralLibraryExportWidget, SpectralLibraryImportDialog, SpectralLibraryImportFeatureSink, \
    SpectralLibraryImportWidget, SpectralLibraryIO
from qps.speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict
from qps.speclib.io.envi import EnviSpectralLibraryImportWidget, EnviSpectralLibraryIO
from qps.speclib.io.geojson import GeoJsonSpectralLibraryIO
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryImportWidget, GeoPackageSpectralLibraryIO
from qps.testing import start_app, TestCaseBase, TestObjects
from qps.utils import file_search

start_app()


class TestIO(TestCaseBase):
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
            EnviSpectralLibraryImportWidget.__name__: qpstestdata.envi_sli,
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
            if speclib1 is None:
                continue
            self.assertIsInstance(speclib1, QgsVectorLayer)
            self.assertTrue(len(speclib1) > 0)

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
                sl2 = SpectralLibraryUtils.readFromSource(file)
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

    def test_SpectralLibraryIO(self):

        initSpectralLibraryIOs()

        importFormats = SpectralLibraryIO.spectralLibraryIOs(read=True)
        self.assertTrue(len(importFormats) > 0)
        for fmt in importFormats:
            self.assertIsInstance(fmt.createImportWidget(), SpectralLibraryImportWidget)

        exportFormats = SpectralLibraryIO.spectralLibraryIOs(write=True)
        self.assertTrue(len(exportFormats) > 0)
        for fmt in exportFormats:
            self.assertIsInstance(fmt.createExportWidget(), SpectralLibraryExportWidget)

    def test_SpectralLibraryImportFeatureSink(self):

        srcFields = QgsFields()
        srcFields.append(QgsField('srcName', QMETATYPE_QSTRING))
        srcFields.append(create_profile_field('srcProfiles', encoding='bytes'))

        dstFields = QgsFields()
        dstFields.append(QgsField('dstName', QMETATYPE_QSTRING))
        dstFields.append(create_profile_field('dstProfilesB', encoding='bytes'))
        dstFields.append(create_profile_field('dstProfilesS', encoding='text'))
        dstFields.append(create_profile_field('dstProfilesJ', encoding='json'))

        d = prepareProfileValueDict(x=[1, 2, 3], y=[14, 15, 16], xUnit='nm', yUnit='ukn')

        f = QgsFeature(srcFields)
        f.setAttribute('srcName', 'myname')
        f.setAttribute('srcProfiles', encodeProfileValueDict(d, encoding=srcFields.field('srcProfiles')))

        profiles = [f]

        propertyMap = {
            'dstName': QgsProperty.fromField('srcName'),
            'dstProfilesB': QgsProperty.fromField('srcProfiles'),
            'dstProfilesS': QgsProperty.fromField('srcProfiles'),
            'dstProfilesJ': QgsProperty.fromField('srcProfiles')
        }

        speclib: QgsVectorLayer = TestObjects.createEmptyMemoryLayer(dstFields)

        srcCrs = dstSrc = speclib.crs()
        sinkDefinition = QgsRemappingSinkDefinition()
        sinkDefinition.setDestinationFields(speclib.fields())
        sinkDefinition.setSourceCrs(srcCrs)
        sinkDefinition.setDestinationCrs(dstSrc)
        sinkDefinition.setDestinationWkbType(speclib.wkbType())
        sinkDefinition.setFieldMap(propertyMap)

        feedback: QgsProcessingFeedback = QgsProcessingFeedback()
        context = QgsExpressionContext()
        context.setFields(srcFields)
        context.setFeedback(feedback)

        scope = QgsExpressionContextScope()
        scope.setFields(srcFields)
        context.appendScope(scope)

        # sink = QgsRemappingProxyFeatureSink(sinkDefinition, speclib)
        sink = SpectralLibraryImportFeatureSink(sinkDefinition, speclib)
        sink.setExpressionContext(context)
        sink.setTransformContext(QgsProject.instance().transformContext())

        with edit(speclib):
            speclib.beginEditCommand('Import profiles')
            self.assertTrue(sink.addFeatures(profiles))
            speclib.endEditCommand()

        for f in speclib.getFeatures():
            f: QgsFeature

            name: str = f.attribute('dstName')

            dumpB = f.attribute('dstProfilesB')
            dumpS = f.attribute('dstProfilesS')
            dumpJ = f.attribute('dstProfilesJ')

            self.assertTrue(dumpB is not None)
            self.assertTrue(dumpS is not None)
            self.assertTrue(dumpJ is not None)

            dB = decodeProfileValueDict(dumpB)
            dS = decodeProfileValueDict(dumpS)
            dJ = decodeProfileValueDict(dumpJ)

            self.assertEqual(d, dB)
            self.assertEqual(d, dS)
            self.assertEqual(d, dJ)

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

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Opens blocking dialog')
    def test_ImportDialog2(self):
        self.registerIO()

        speclib = TestObjects.createSpectralLibrary()

        results = SpectralLibraryImportDialog.importProfiles(speclib, defaultRoot=self.createTestDir())
        s = ""

    def createTestDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path


if __name__ == '__main__':
    unittest.main(buffer=False)
