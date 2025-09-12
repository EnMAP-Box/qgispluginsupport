# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import pathlib
import re
import unittest

from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsEditorWidgetRegistry, QgsGui
from qps import registerEditorWidgets
from qps.classification.classificationscheme import ClassificationSchemeWidgetFactory
from qps.plotstyling.plotstyling import PlotStyleEditorWidgetFactory
from qps.resources import initQtResources
from qps.speclib.gui.spectralprofileeditor import SpectralProfileEditorWidgetFactory
from qps.testing import start_app, TestCase
from qps.utils import file_search, scanResources
from scripts.create_resourcefile import create_resource_files

start_app()


class TestsCases_Init(TestCase):

    def test_init(self):

        create_resource_files()
        initQtResources()
        paths = [p for p in scanResources() if p.startswith(':/qps/')]
        self.assertTrue(len(paths) > 0, msg='missing resources')
        for p in paths:
            icon = QIcon(p)
            self.assertFalse((icon.isNull()))

        registerEditorWidgets()
        from qps.speclib import EDITOR_WIDGET_REGISTRY_KEY as keyProfiles
        reg: QgsEditorWidgetRegistry = QgsGui.editorWidgetRegistry()
        self.assertIsInstance(reg.factory(keyProfiles), SpectralProfileEditorWidgetFactory)

        from qps.plotstyling.plotstyling import EDITOR_WIDGET_REGISTRY_KEY as keyPlotStyling
        self.assertIsInstance(reg.factory(keyPlotStyling), PlotStyleEditorWidgetFactory)

        from qps.classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as keyClassScheme
        self.assertIsInstance(reg.factory(keyClassScheme), ClassificationSchemeWidgetFactory)

    def test_crs(self):

        from qgis.core import QgsCoordinateReferenceSystem

        crs1 = QgsCoordinateReferenceSystem('EPSG:4326')
        assert crs1.isValid()
        crs2 = QgsCoordinateReferenceSystem.fromWkt(crs1.toWkt())
        assert crs1.toWkt() == crs2.toWkt()
        assert crs2.isValid()

    def test_relative_imports(self):

        root = pathlib.Path(__file__).parents[1]

        re1 = re.compile(r'^\w*import qps')
        re2 = re.compile(r'^\w*from qps')
        for path in file_search(root / 'qps', '*.py', recursive=True):
            with open(path, encoding='utf-8') as f:
                lines = f.read()
                self.assertTrue(re1.search(lines) is None, msg='non-relative "import qps" in {}'.format(path))
                self.assertTrue(re2.search(lines) is None, msg='non-relative "from qps" in {}'.format(path))


if __name__ == "__main__":
    unittest.main(buffer=False)
