# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
from pathlib import Path

from qgis.core import QgsApplication, QgsLayerTree, QgsLayerTreeModel, QgsProcessingRegistry, QgsProject
from qgis.gui import QgisInterface, QgsGui, QgsLayerTreeView

import qps.testing
from qps.testing import QgsOptionsMockup, start_app, TestCase
from scripts.install_testdata import DIR_REPO

start_app()


class TestCasesClassTesting(TestCase):

    def test_init(self):
        self.assertTrue(qps.testing is not None)

        qgis_app = QgsApplication.instance()
        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)
        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0,
                        msg='Standard QgsEditorWidgetWrapper not initialized')

        # test iface
        import qgis.utils
        iface = qgis.utils.iface

        self.assertIsInstance(iface, QgisInterface)
        self.assertIsInstance(iface, qps.testing.QgisMockup)

        lyr1 = qps.testing.TestObjects.createVectorLayer()
        lyr2 = qps.testing.TestObjects.createVectorLayer()

        self.assertIsInstance(iface.layerTreeView(), QgsLayerTreeView)
        self.assertIsInstance(iface.layerTreeView().layerTreeModel(), QgsLayerTreeModel)
        root = iface.layerTreeView().layerTreeModel().rootGroup()
        self.assertIsInstance(root, QgsLayerTree)
        self.assertEqual(len(root.findLayers()), 0)

        QgsProject.instance().addMapLayer(lyr1, False)
        QgsProject.instance().addMapLayer(lyr2, True)

        QgsApplication.processEvents()

        self.assertTrue(lyr1.id() not in root.findLayerIds())
        self.assertTrue(lyr2.id() in root.findLayerIds())

        app = QgsApplication.instance()
        ENV = app.systemEnvVars()
        for k in sorted(ENV.keys()):
            print('{}={}'.format(k, ENV[k]))

        QgsProject.instance().removeAllMapLayers()

    def test_QgsOptionsMockup(self):
        d = QgsOptionsMockup(None)
        self.showGui(d)

    def test_testfolders(self):
        p = self.createTestOutputDirectory()
        expected = DIR_REPO / 'test-outputs' / __name__ / self.__class__.__name__ / 'test_testfolders'
        self.assertEqual(p, expected)
        self.assertTrue(p.is_dir())

        p = self.createTestOutputDirectory(subdir='my/subdirs')
        self.assertEqual(p, expected / 'my' / 'subdirs')
        self.assertTrue(p.is_dir())

        p = self.createTestOutputDirectory(subdir=Path('my/subdirs2'))
        self.assertEqual(p, expected / 'my' / 'subdirs2')
        self.assertTrue(p.is_dir())

        path_testfile = p / 'testfile.txt'
        with open(path_testfile, 'w') as f:
            f.write('test')
        self.assertTrue(path_testfile.is_file())

        p = self.createTestOutputDirectory(subdir=Path('my/subdirs2'), cleanup=True)
        self.assertFalse(path_testfile.is_file())


if __name__ == "__main__":
    unittest.main(buffer=False)
