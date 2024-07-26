# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 :
    Copyright            : (C) 2021 by Benjamin Jakimow
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
import os.path
import pathlib
import re
# noinspection PyPep8Naming
import unittest
from typing import List

import processing
import qgis.testing
import qgis.utils
from processing import AlgorithmDialog
from processing.ProcessingPlugin import ProcessingPlugin
from qgis.core import edit, QgsApplication, QgsFeature, QgsField, QgsFields, QgsProcessingAlgorithm, \
    QgsProcessingAlgRunnerTask, QgsProcessingOutputRasterLayer, QgsProcessingRegistry, QgsProject, QgsTaskManager, \
    QgsVectorLayer
from qgis.gui import QgsProcessingRecentAlgorithmLog, QgsProcessingToolboxProxyModel
from qgis.PyQt.QtCore import QModelIndex, QObject, Qt
from qgis.PyQt.QtWidgets import QDialog

from qps.processing.processingalgorithmdialog import ProcessingAlgorithmDialog
from qps.qgisenums import QMETATYPE_QSTRING
from qps.qgsfunctions import registerQgsExpressionFunctions
from qps.speclib.core import create_profile_field, profile_field_names, profile_fields
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs, SpectralLibraryIO
from qps.speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, isProfileValueDict, \
    prepareProfileValueDict, ProfileEncoding
from qps.speclib.processing.aggregateprofiles import AggregateProfiles
from qps.speclib.processing.exportspectralprofiles import ExportSpectralProfiles
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import ExampleAlgorithmProvider, start_app, TestCaseBase, TestObjects

start_app()


class MyAlgModel(QgsProcessingToolboxProxyModel):
    """
    This proxy model filters out all QgsProcessingAlgorithms that do not use
    SpectralProcessingProfiles
    """

    def __init__(self,
                 parent: QObject,
                 registry: QgsProcessingRegistry = None,
                 recentLog: QgsProcessingRecentAlgorithmLog = None):
        super().__init__(parent, registry, recentLog)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def is_my_alg(self, alg: QgsProcessingAlgorithm) -> bool:
        for output in alg.outputDefinitions():
            if isinstance(output, QgsProcessingOutputRasterLayer):
                return True
        return False

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex):

        sourceIdx = self.toolboxModel().index(sourceRow, 0, sourceParent)
        if self.toolboxModel().isAlgorithm(sourceIdx):
            alg = self.toolboxModel().algorithmForIndex(sourceIdx)
            return super().filterAcceptsRow(sourceRow, sourceParent) and self.is_my_alg(alg)
        else:
            return super().filterAcceptsRow(sourceRow, sourceParent)


class ProcessingToolsTest(TestCaseBase):

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Blocking dialog')
    def test_processingAlgorithmDialog(self):

        d = ProcessingAlgorithmDialog()
        model = MyAlgModel(None)
        d.setAlgorithmModel(model)
        result = d.exec_()
        if result == QDialog.Accepted:
            alg = d.algorithm()
            self.assertIsInstance(alg, QgsProcessingAlgorithm)

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Blocking dialog')
    def test_aggregate_profiles_dialog(self):
        registerQgsExpressionFunctions()
        enc = ProfileEncoding.Json
        sl1: QgsVectorLayer = SpectralLibraryUtils.createSpectralLibrary(
            name='SL', profile_fields=['profiles'], encoding=enc)

        context, feedback = self.createProcessingContextFeedback()

        project = QgsProject.instance()
        project.addMapLayers([sl1])

        sl1.startEditing()
        sl1.renameAttribute(sl1.fields().lookupField('name'), 'group')
        sl1.commitChanges(False)
        content = [
            {'group': 'A', 'profiles': {'y': [1, 1, 1]}},
            {'group': 'A', 'profiles': {'y': [1, 1, 1]}},
            {'group': 'A', 'profiles': {'y': [4, 4, 4]}},
            {'group': 'B', 'profiles': {'y': [0, 8, 15]}},
        ]
        for c in content:
            f = QgsFeature(sl1.fields())
            f.setAttribute('group', c['group'])
            f.setAttribute('profiles', encodeProfileValueDict(c['profiles'], enc))
            self.assertTrue(sl1.addFeature(f))
        self.assertTrue(sl1.commitChanges())

        groups = sl1.uniqueValues(sl1.fields().lookupField('group'))
        self.assertEqual(groups, {'A', 'B'})

        provider = ExampleAlgorithmProvider()
        processingPlugin = qgis.utils.plugins.get('processing', ProcessingPlugin(TestCaseBase.IFACE))

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        reg.addProvider(provider)
        self.assertTrue(provider.addAlgorithm(AggregateProfiles()))
        reg.providerById(ExampleAlgorithmProvider.NAME.lower())

        alg_id = provider.algorithms()[0].id()
        alg = reg.algorithmById(alg_id)
        self.assertIsInstance(alg, AggregateProfiles)

        alg = reg.algorithmById(alg_id)
        d = AlgorithmDialog(alg, False, None)
        d.context = context
        d.exec_()
        processingPlugin.executeAlgorithm(alg_id, None, in_place=False, as_batch=False)

    def test_aggregate_profiles(self):
        registerQgsExpressionFunctions()
        enc = ProfileEncoding.Json
        sl1: QgsVectorLayer = SpectralLibraryUtils.createSpectralLibrary(
            name='SL', profile_fields=['profiles'], encoding=enc)

        context, feedback = self.createProcessingContextFeedback()

        project = QgsProject.instance()
        project.addMapLayers([sl1])

        with edit(sl1):

            sl1.renameAttribute(sl1.fields().lookupField('name'), 'group')
            content = [
                {'group': 'A', 'profiles': {'y': [1, 1, 1], 'x': [100, 200, 300], 'xUnit': 'nm'}},
                {'group': 'A', 'profiles': {'y': [1, 1, 1], 'x': [100, 200, 300], 'xUnit': 'nm'}},
                {'group': 'A', 'profiles': {'y': [4, 4, 4], 'x': [100, 200, 300], 'xUnit': 'nm'}},
                {'group': 'B', 'profiles': {'y': [0, 8, 15], 'x': [100, 200, 300], 'xUnit': 'nm'}},
            ]
            for c in content:
                f = QgsFeature(sl1.fields())
                f.setAttribute('group', c['group'])
                f.setAttribute('profiles', encodeProfileValueDict(c['profiles'], enc))
                self.assertTrue(sl1.addFeature(f))

        groups = sl1.uniqueValues(sl1.fields().lookupField('group'))
        self.assertEqual(groups, {'A', 'B'})

        provider = ExampleAlgorithmProvider()

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        reg.addProvider(provider)
        self.assertTrue(provider.addAlgorithm(AggregateProfiles()))
        reg.providerById(ExampleAlgorithmProvider.NAME.lower())

        alg_id = provider.algorithms()[0].id()
        alg = reg.algorithmById(alg_id)
        self.assertIsInstance(alg, AggregateProfiles)

        parameters = {
            AggregateProfiles.P_INPUT: sl1,
            AggregateProfiles.P_GROUP_BY: 'group',
            AggregateProfiles.P_AGGREGATES: [
                {'aggregate': 'first_value', 'delimiter': ',', 'input': '"group"', 'length': 0,
                 'name': 'group', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'minimum', 'delimiter': ',', 'input': '"profiles"', 'length': -1,
                 'name': 'p_min', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'maximum', 'delimiter': ',', 'input': '"profiles"', 'length': -1,
                 'name': 'p_max', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'mean', 'delimiter': ',', 'input': '"profiles"', 'length': -1,
                 'name': 'p_mean', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'median', 'delimiter': ',', 'input': '"profiles"', 'length': -1,
                 'name': 'p_median', 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'}
            ],
            AggregateProfiles.P_OUTPUT: 'TEMPORARY_OUTPUT'}

        # r1 = alg.prepare(parameters, context, feedback)
        # r2 = alg.processAlgorithm(parameters, context, feedback)

        context, feedback = self.createProcessingContextFeedback()

        def on_complete(ok, results):
            self.assertTrue(ok)
            sl2 = results[AggregateProfiles.P_OUTPUT]
            self.assertIsInstance(sl2, QgsVectorLayer)

            pfields2 = profile_field_names(sl2)
            self.assertEqual(set(pfields2), {'p_min', 'p_max', 'p_mean', 'p_median'})
            self.assertEqual(len(pfields2), 4)
            self.assertEqual(sl1.featureCount(), 4)
            self.assertEqual(sl2.featureCount(), 2)

            fA = list(sl2.getFeatures('"group" = \'A\''))
            self.assertTrue(len(fA) == 1)
            fA = fA[0]
            p_min = decodeProfileValueDict(fA['p_min'])
            p_max = decodeProfileValueDict(fA['p_max'])
            p_mean = decodeProfileValueDict(fA['p_mean'])
            p_median = decodeProfileValueDict(fA['p_median'])

            for pdict in [p_min, p_max, p_mean, p_median]:
                self.assertEqual(pdict['x'], [100, 200, 300])
                self.assertEqual(pdict['xUnit'], 'nm')

            self.assertEqual(p_min['y'], [1, 1, 1])
            self.assertEqual(p_max['y'], [4, 4, 4])
            self.assertEqual(p_median['y'], [1, 1, 1])
            self.assertEqual(p_mean['y'], [2, 2, 2])

            fB = list(sl2.getFeatures('"group" = \'B\''))[0]
            for k in ['p_min', 'p_max', 'p_mean', 'p_median']:
                p = decodeProfileValueDict(fB[k])
                self.assertEqual(p['y'], [0, 8, 15])

        # test alg.run
        conf = {}
        results, success = alg.run(parameters, context, feedback, conf)
        on_complete(success, results)

        # test processing.run
        results = processing.run(alg_id, parameters, context=context)
        on_complete(True, results)

        # test run by task
        task = QgsProcessingAlgRunnerTask(alg, parameters, context, feedback)
        task.executed.connect(on_complete)
        task.run()

        # test run in task manager

        if False:
            # fails if run with other tests for unknown reasons.
            context2, feedback2 = self.createProcessingContextFeedback()
            task2 = QgsProcessingAlgRunnerTask(alg, parameters, context2, feedback2)
            task2.executed.connect(on_complete)
            tm: QgsTaskManager = QgsApplication.taskManager()
            tm.addTask(task2)
            while tm.countActiveTasks() > 0:
                # pass
                QgsApplication.instance().processEvents()
                pass
        pid = provider.id()
        del provider
        reg.removeProvider(pid)
        QgsProject.instance().removeAllMapLayers()
        s = ""

    def test_spectralprofile_import(self):

        provider = ExampleAlgorithmProvider()
        initSpectralLibraryIOs()
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        reg.addProvider(provider)

        self.assertTrue(provider.addAlgorithm(ImportSpectralProfiles()))
        reg.providerById(ExampleAlgorithmProvider.NAME.lower())

        from qpstestdata import envi_sli, DIR_ASD_BIN, DIR_ARTMO, DIR_ECOSIS

        input_files = [
            envi_sli,
            DIR_ASD_BIN,
            DIR_ARTMO,
            DIR_ECOSIS,
        ]

        for f in input_files:
            p = pathlib.Path(f)
            self.assertTrue(p.is_dir() or p.is_file())

        par = {
            ImportSpectralProfiles.P_INPUT: input_files,
            ImportSpectralProfiles.P_OUTPUT: 'TEMPORARY_OUTPUT'
        }

        context, feedback = self.createProcessingContextFeedback()
        conf = {}
        alg = ImportSpectralProfiles()
        alg.initAlgorithm(conf)

        results, success = alg.run(par, context, feedback, conf)
        self.assertTrue(success)

        lyr = results[ImportSpectralProfiles.P_OUTPUT]
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        sfields = profile_fields(lyr)

        self.assertTrue(sfields.count() > 0)

        self.assertTrue(lyr.featureCount() > 0)

        for f in lyr.getFeatures():
            f: QgsFeature
            for n in sfields.names():
                dump = f.attribute(n)
                if dump:
                    d = decodeProfileValueDict(dump)
                    self.assertTrue(isProfileValueDict(d),
                                    msg=f'Not a spectral profile: {dump}')

        reg.removeProvider(provider)
        QgsProject.instance().removeAllMapLayers()

    def test_spectralprofile_export(self):

        provider = ExampleAlgorithmProvider()
        initSpectralLibraryIOs()
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()

        self.assertTrue(provider.addAlgorithm(ExportSpectralProfiles()))
        reg.providerById(ExampleAlgorithmProvider.NAME.lower())
        reg.addProvider(provider)

        alg: QgsProcessingAlgorithm = reg.algorithmById(f'{provider.id()}:{ExportSpectralProfiles.NAME}')
        self.assertIsInstance(alg, ExportSpectralProfiles)

        # create a spectral library with two speclib fields and two features
        pA1 = prepareProfileValueDict(y=[23, 34, 45.5], x=[1, 2, 3], xUnit='nm')
        pA2 = prepareProfileValueDict(y=[34, 35, 23.5], x=[1, 2, 3], xUnit='micrometers')
        pB1 = prepareProfileValueDict(y=[34, 35, 23.5], x=[3, 4, 5], xUnit='nm')
        pB2 = prepareProfileValueDict(y=[34, 35, 23.5], x=[3, 4, 5], xUnit='nm')

        PDICTS = [pA1, pA2, pB1, pB2]
        fields = QgsFields()
        fields.append(create_profile_field('A'))
        fields.append(create_profile_field('B'))
        fields.append(QgsField('notes', QMETATYPE_QSTRING))

        sl = TestObjects.createEmptyMemoryLayer(fields, name='MySpeclib')

        f1 = QgsFeature(sl.fields())
        f2 = QgsFeature(sl.fields())
        SpectralLibraryUtils.setProfileValues(f1, field='A', profileDict=pA1)
        SpectralLibraryUtils.setProfileValues(f1, field='B', profileDict=pB1)
        SpectralLibraryUtils.setProfileValues(f2, field='A', profileDict=pA2)
        SpectralLibraryUtils.setProfileValues(f2, field='B', profileDict=pB2)

        with edit(sl):
            sl.addFeatures([f1, f2])

        vl = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayers([sl, vl])

        # if False:
        #    from processing import createAlgorithmDialog
        #    from qgis.utils import iface
        #    d = AlgorithmDialog(alg, parent=iface.mainWindow())
        #    d.exec_()

        conf = {}
        alg.initAlgorithm(conf)
        par = {ExportSpectralProfiles.P_INPUT: sl,
               # ExportSpectralProfiles.P_FORMAT: 'sli',
               ExportSpectralProfiles.P_OUTPUT: 'TEMPORARY_OUTPUT'}
        context, feedback = self.createProcessingContextFeedback()
        results, success = alg.run(par, context, feedback)
        self.assertTrue(success)

        testDir = self.createTestCaseDirectory()

        rx = re.compile(r'\(\*(?P<extension>\.[^)]+)\)')
        for i, io in enumerate(SpectralLibraryIO.spectralLibraryIOs(write=True)):
            self.assertIsInstance(io, SpectralLibraryIO)
            w = io.createExportWidget()

            outputfiles = []
            for match in rx.findall(w.filter()):
                outputfiles.append(testDir / f'format{i}{match}')

            for output in outputfiles:
                par = {ExportSpectralProfiles.P_INPUT: sl,
                       ExportSpectralProfiles.P_OUTPUT: output.as_posix()}
                results = processing.run(alg, par, feedback=feedback, context=context)

                file = results[ExportSpectralProfiles.P_OUTPUT]
                files = results[ExportSpectralProfiles.P_OUTPUT + 'S']

                self.assertTrue(file in files)

                writtenFeatures = []
                for uri in files:
                    self.assertTrue(os.path.isfile(uri), f'Not a file: {uri}: \nIO: {io}')
                    features = SpectralLibraryIO.readProfilesFromUri(uri)
                    writtenFeatures.extend(features)

                # ensure that each profile has been written into one of the output files
                writtenProfiles: List[dict] = []
                for f in writtenFeatures:
                    for n in profile_field_names(f.fields()):
                        d = decodeProfileValueDict(f.attribute(n))
                        self.assertTrue(d in PDICTS)
                        writtenProfiles.append(d)
                if not len(writtenProfiles) == len(PDICTS):
                    s = ""
                self.assertEqual(len(writtenProfiles), len(PDICTS),
                                 msg=f'{len(writtenProfiles)} of {len(PDICTS)} profiles written\n IO: {io}')
                # todo: compare metadata
                s = ""
                s = ""
        reg.removeProvider(provider)
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
