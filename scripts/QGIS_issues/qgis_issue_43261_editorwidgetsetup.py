import site
import pathlib

from qgis.PyQt.QtCore import QSize, QVariant
from qgis.PyQt.QtGui import QResizeEvent

DIR_QGIS_REPO = pathlib.Path(r'F:\Repositories\QGIS')
assert DIR_QGIS_REPO.is_dir()

site.addsitedir(DIR_QGIS_REPO / 'tests' / 'src' / 'python')
import unittest
import os
from utilities import unitTestDataPath
from qgis._core import QgsRasterLayer, QgsSingleBandGrayRenderer, QgsProject, QgsVectorLayer, QgsVectorLayerExporter, \
    QgsField, QgsEditorWidgetSetup, Qgis
from qgis._gui import QgsMapCanvas, QgsRendererRasterPropertiesWidget, QgsGui

from qgis.testing.mocked import get_iface


class PyQgsOGRProvider(unittest.TestCase):

    def setUp(self):
        self.iface = get_iface()
        QgsProject.instance().removeAllMapLayers()

    def test_provider_editorWidgets(self):
        if len(QgsGui.editorWidgetRegistry().factories()) == 0:
            QgsGui.editorWidgetRegistry().initEditors()

        editor_widget_type = 'Color'
        factory = QgsGui.instance().editorWidgetRegistry().factory(editor_widget_type)
        assert factory.name() == editor_widget_type

        # 1. create a vector
        uri = "point?crs=epsg:4326&field=id:integer"
        layer = QgsVectorLayer(uri, "Scratch point layer", "memory")

        path = '/vsimem/test.gpkg'
        result, msg = QgsVectorLayerExporter.exportLayer(layer, path, 'ogr', layer.crs())
        self.assertTrue(result == Qgis.VectorExportResult.Success, msg=msg)
        layer = QgsVectorLayer(path)
        self.assertTrue(layer.isValid())
        self.assertTrue(layer.providerType() == 'ogr')

        field1 = QgsField(name='field1', type=QVariant.String)
        field2 = QgsField(name='field2', type=QVariant.String)
        setup1 = QgsEditorWidgetSetup(editor_widget_type, {})
        setup2 = QgsEditorWidgetSetup(editor_widget_type, {})

        # 2. Add field, set editor widget after commitChanges()
        assert layer.startEditing()
        layer.addAttribute(field1)
        assert layer.commitChanges(stopEditing=False)
        i = layer.fields().lookupField(field1.name())
        layer.setEditorWidgetSetup(i, setup1)

        # 3. Add field, set editor widget before commitChanges()
        field2.setEditorWidgetSetup(setup2)
        layer.addAttribute(field2)
        i = layer.fields().lookupField(field2.name())

        # this is a workaround:
        # layer.setEditorWidgetSetup(i, field2.editorWidgetSetup())
        self.assertEqual(layer.editorWidgetSetup(i).type(), editor_widget_type)
        self.assertTrue(layer.commitChanges())

        # editor widget should not change by commitChanges
        self.assertEqual(layer.editorWidgetSetup(i).type(),
                         editor_widget_type,
                         msg='QgsVectorLayer::commitChanged() changed QgsEditorWidgetSetup' + \
                             f'\nDriver: {layer.dataProvider().name()}')
