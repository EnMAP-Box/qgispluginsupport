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

import xmlrunner

from qgis.core import QgsFeature, QgsField, QgsVectorLayer, QgsAttributeTableConfig, \
    QgsEditorWidgetSetup, QgsActionManager, QgsAction
from qgis.gui import QgsMapCanvas, QgsDualView, QgsGui, QgsSearchWidgetWrapper
from qps import initResources
from qps.plotstyling.plotstyling import *
from qps.processing.processingalgorithmdialog import ProcessingAlgorithmDialog
from qps.testing import TestCase


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



if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
