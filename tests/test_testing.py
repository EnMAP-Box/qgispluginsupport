# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
from pathlib import Path
from typing import List

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QGroupBox, QLabel, QLineEdit, QVBoxLayout, QWidget
from qgis.gui import QgisInterface, QgsGui, QgsLayerTreeView, QgsOptionsPageWidget, QgsOptionsWidgetFactory
from qgis.core import QgsApplication, QgsLayerTree, QgsLayerTreeModel, QgsProcessingRegistry, QgsProject
import qps.testing
from qps.testing import QgsOptionsMockup, start_app, TestCase
from scripts.install_testdata import DIR_REPO

start_app()


class ExampleOptionsPageWidget(QgsOptionsPageWidget):
    """Settings form embedded into QGIS 'options' menu."""

    last_value = 'default text'
    applyCalled = pyqtSignal(str)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.setLayout(QVBoxLayout())
        gb = QGroupBox('My Group')

        gb.setLayout(QVBoxLayout())
        gb.layout().addWidget(QLabel('My Label'))
        self.lineEdit = QLineEdit('My Values')
        self.lineEdit.setText(self.last_value)
        gb.layout().addWidget(self.lineEdit)
        self.layout().addWidget(gb)

    def setObjectName(self, name):
        super().setObjectName(name)
        self.lineEdit.setText(name)

    def apply(self):
        """
        Called to permanently apply the settings shown in the options page (e.g. \
        save them to QgsSettings objects). This is usually called when the options \
        dialog is accepted.
        """

        self.last_value = self.lineEdit.text()
        self.applyCalled.emit(self.objectName())


class ExampleOptionsWidgetFactory(QgsOptionsWidgetFactory):
    """Factory for options widget."""

    applyCalled = pyqtSignal(str)

    def __init__(self, pageName: str):
        """Constructor."""
        super().__init__()
        self.pageName = pageName

    def icon(self) -> QIcon:
        """Returns plugin icon, used to as tab icon in QGIS options tab widget.

        :return: _description_
        :rtype: QIcon
        """
        return QIcon(':/qt-project.org/styles/commonstyle/images/floppy-128.png')

    def createWidget(self, parent) -> ExampleOptionsPageWidget:
        """Create settings widget.

        :param parent: Qt parent where to include the options page.
        :type parent: QObject

        :return: options page for tab widget
        :rtype: ConfigOptionsPage
        """
        page = ExampleOptionsPageWidget(parent)
        page.applyCalled.connect(self.applyCalled)
        page.setObjectName(self.pageName)
        return page

    def title(self) -> str:
        """Returns plugin title, used to name the tab in QGIS options tab widget.

        :return: plugin title from about module
        :rtype: str
        """
        return self.pageName

    def key(self):
        return self.pageName

    def path(self) -> List[str]:
        return []

    def helpId(self) -> str:
        """Returns plugin help URL.

        :return: plugin homepage url from about module
        :rtype: str
        """
        return 'Example Help'


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

    def test_init_factory(self):
        f1 = ExampleOptionsWidgetFactory('mOptionsPageExample1')
        f2 = ExampleOptionsWidgetFactory('mOptionsPageExample2')

        apply_called = []

        def onApply(name):
            nonlocal apply_called
            apply_called.append(name)

        from qgis.utils import iface
        for factory in [f1, f2]:
            factory.applyCalled.connect(onApply)
            iface.registerOptionsWidgetFactory(factory)
        d = iface.showOptionsDialog(currentPage='mOptionsPageExample1')
        self.assertIsInstance(d, QgsOptionsMockup)
        d.buttonBox.accepted.emit()
        self.assertTrue('mOptionsPageExample1' in apply_called)
        self.assertTrue('mOptionsPageExample2' in apply_called)

        for factory in [f1, f2]:
            iface.unregisterOptionsWidgetFactory(factory)

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
