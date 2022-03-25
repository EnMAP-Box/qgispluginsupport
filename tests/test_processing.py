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
# noinspection PyPep8Naming
import unittest

import qgis.utils
from processing import AlgorithmDialog
from processing.ProcessingPlugin import ProcessingPlugin
from processing.algs import qgis
from qgis.PyQt.QtCore import QObject, Qt, QModelIndex
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsApplication, QgsVectorLayer, QgsField
from qgis.core import QgsProcessingFeedback, QgsProcessingContext
from qgis.core import QgsProject, QgsProcessingRegistry, QgsProcessingAlgorithm, QgsProcessingOutputRasterLayer
from qgis.gui import QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog

from qps import initResources
from qps.processing.processingalgorithmdialog import ProcessingAlgorithmDialog
from qps.speclib.processing.aggregateprofiles import AggregateProfiles
from qps.testing import TestCase, TestObjects, ExampleAlgorithmProvider


class ProcessingToolsTest(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(ProcessingToolsTest, cls).setUpClass(*args, **kwds)
        initResources()

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
    def test_processingAlgorithmDialog(self):

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

        d = ProcessingAlgorithmDialog()
        model = MyAlgModel(None)
        d.setAlgorithmModel(model)
        result = d.exec_()
        if result == QDialog.Accepted:
            alg = d.algorithm()
            self.assertIsInstance(alg, QgsProcessingAlgorithm)

    def test_aggregate_profiles(self):
        provider = ExampleAlgorithmProvider()
        processingPlugin = qgis.utils.plugins.get('processing', ProcessingPlugin(TestCase.IFACE))
        vl = TestObjects.createVectorLayer()
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        sl.startEditing()
        sl.addAttribute(QgsField('group', type=QVariant.String))
        sl.commitChanges(False)
        i_name = sl.fields().lookupField('name')
        i_group = sl.fields().lookupField('group')
        for i, p in enumerate(sl.getFeatures()):
            sl.changeAttributeValue(p.id(), i_name, f'Profile {i + 1}')
            sl.changeAttributeValue(p.id(), i_group, str(i % 2 == 0))
        self.assertTrue(sl.commitChanges())
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        reg.addProvider(provider)
        self.assertTrue(provider.addAlgorithm(AggregateProfiles()))
        reg.providerById(ExampleAlgorithmProvider.NAME.lower())

        alg_id = provider.algorithms()[0].id()
        # alg_id = 'native:aggregate'
        conf = {}
        project = QgsProject()
        project = QgsProject.instance()
        project.addMapLayers([vl, sl])
        context = QgsProcessingContext()
        context.setProject(project)
        feedback = QgsProcessingFeedback()
        context.setFeedback(feedback)

        if False:
            alg = reg.algorithmById(alg_id)
            d = AlgorithmDialog(alg, False, None)
            d.context = context
            d.exec_()
            processingPlugin.executeAlgorithm(alg_id, None, in_place=False, as_batch=False)

        alg = reg.algorithmById(alg_id)
        # self.assertIsInstance(alg, AggregateProfiles)
        # alg.initAlgorithm(conf)
        if False:
            parameters = {AggregateProfiles.P_AGGREGATES: [
                {'aggregate': 'mean', 'delimiter': ',', 'input': '"fid"', 'length': 0, 'name': 'mean_id',
                 'precision': 0,
                 'sub_type': 0, 'type': 4, 'type_name': 'int8'},
                {'aggregate': 'first_value', 'delimiter': ',', 'input': '"level_1_id"', 'length': 0,
                 'name': 'level_1_id',
                 'precision': 0, 'sub_type': 0, 'type': 2, 'type_name': 'integer'},
                {'aggregate': 'concatenate', 'delimiter': ',', 'input': '"level_1"', 'length': 0, 'name': 'level_1',
                 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'}],
                AggregateProfiles.P_GROUP_BY: '"level_1"',
                AggregateProfiles.P_INPUT: vl,
                AggregateProfiles.P_OUTPUT: 'TEMPORARY_OUTPUT'}
        else:
            parameters = {AggregateProfiles.P_AGGREGATES: [
                {'aggregate': 'concatenate', 'delimiter': ',', 'input': '"name"', 'length': 0, 'name': 'name',
                 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'aggregate': 'mean', 'delimiter': ',', 'input': '"profiles0"', 'length': 0, 'name': 'profiles0',
                 'precision': 0, 'sub_type': 0, 'type': 12, 'type_name': 'binary'},
                {'aggregate': 'concatenate', 'delimiter': ',', 'input': '"group"', 'length': 0, 'name': 'group',
                 'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'}],
                AggregateProfiles.P_GROUP_BY: 'group',
                AggregateProfiles.P_INPUT: sl,
                AggregateProfiles.P_OUTPUT: './temputput.gpkg'}
        self.assertTrue(alg.prepare(parameters, context, feedback), msg=feedback.textLog())
        result2 = alg.processAlgorithm(parameters, context, feedback)
        result3, success = alg.run(parameters, context, feedback)
        self.assertTrue(success, msg=feedback.textLog())
        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
