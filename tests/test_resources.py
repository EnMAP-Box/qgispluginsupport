import os
import shutil
import unittest
from pathlib import Path

import defusedxml.ElementTree as ET
from qgis.PyQt.QtCore import PYQT_VERSION_STR
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget

from qps import QPS_RESOURCE_FILE
from qps import initResources
from qps.resources import (
    ResourceBrowser, ResourceTableModel, compileResourceFiles, find_rcc, scanResources
)
from qps.testing import start_app, TestCase

start_app()
initResources()


class ResourceTests(TestCase):

    def _create_resource_test_tree(self):
        root = self.createTestOutputDirectory(cleanup=True)
        icons = root / 'icons'
        icons.mkdir()
        (icons / 'testicon.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
        )

        qrc = root / 'test_resources.qrc'
        qrc.write_text(
            '<RCC><qresource prefix="qpstest"><file>icons/testicon.svg</file></qresource></RCC>'
        )

        subdir = root / 'sub'
        sub_icons = subdir / 'icons'
        sub_icons.mkdir(parents=True)
        (sub_icons / 'testicon.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
        )
        (subdir / 'test_resources.qrc').write_text(
            '<RCC><qresource prefix="qpstest2"><file>icons/testicon.svg</file></qresource></RCC>'
        )
        (root / 'test.ui').write_text(
            '<ui version="4.0"><class>Form</class><widget class="QWidget" name="Form"/>'
            '<resources><include location="test_resources.qrc"/></resources><connections/></ui>'
        )
        return root

    def _skip_if_rcc_unavailable(self):
        if PYQT_VERSION_STR.startswith('6') and not (
            os.environ.get('RCC_PATH') or shutil.which('rcc') or find_rcc()
        ):
            self.skipTest('Qt 6 resource compiler rcc is not available')

    def test_compile_resource_files(self):
        self._skip_if_rcc_unavailable()
        root = self._create_resource_test_tree()
        target_dir = root / 'compiled'
        target_dir.mkdir()

        py_files = compileResourceFiles(root, targetDir=target_dir)

        self.assertEqual(len(py_files), 2)
        self.assertTrue(all(path.is_file() for path in py_files))
        self.assertEqual(
            {path.name for path in py_files},
            {'test_resources_rc.py', 'test_resources2_rc.py'}
        )

        empty_dir = root / 'empty'
        empty_dir.mkdir()
        self.assertEqual(compileResourceFiles(empty_dir), [])

    def test_qrc(self):

        pathQRC = Path(__file__).parents[1] / 'qps' / 'qpsresources.qrc'
        qrcDir = pathQRC.parent
        self.assertTrue(pathQRC.is_file())

        tree = ET.parse(pathQRC)
        root = tree.getroot()
        self.assertEqual(root.tag, 'RCC')
        for child in root:
            if child.tag == 'qresource':
                # prefix = child.attrib['prefix']
                for fileTag in child:
                    if fileTag.tag == 'file':
                        resource_path = qrcDir / Path(fileTag.text)
                        # resource_uri = ':{}/{}'.format(prefix, fileTag.text)
                        self.assertTrue(resource_path.is_file(), msg='File does not exist: {}'.format(resource_path))

    @unittest.skipIf(not QPS_RESOURCE_FILE.is_file(), '{} does not exist'.format(QPS_RESOURCE_FILE))
    def test_rc(self):

        r = ':/qps/ui/icons/speclib.svg'
        self.assertIsInstance(r, str)
        resources = list(scanResources())

        self.assertTrue(r in resources, '"{}" not loaded to resource system'.format(r))
        self.assertFalse(QIcon(r).isNull())

    def test_resource_browser(self):

        B = ResourceBrowser()
        B.tbFilter.setText('qps*.svg')
        B.updateFilter()
        B.optionUseRegex.setChecked(False)
        B.updateFilter()
        B.optionUseRegex.setChecked(True)
        B.updateFilter()

        B.optionCaseSensitive.setChecked(False)
        B.updateFilter()
        B.optionCaseSensitive.setChecked(True)
        B.updateFilter()

        self.assertIsInstance(B, QWidget)
        self.showGui(B)

        self.assertIsInstance(B.resourceModel, ResourceTableModel)


if __name__ == '__main__':
    unittest.main(buffer=False)
