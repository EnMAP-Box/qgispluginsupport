import os
import pathlib
import re
import xml.etree.ElementTree as ElementTree
from PyQt5.QtXml import QDomDocument

from qgis.core import QgsVectorLayerExporter, QgsVectorLayer, QgsEditorWidgetSetup
from qgis.gui import QgsEditorWidgetRegistry, QgsEditorWidgetFactory, QgsEditorConfigWidget, QgsGui
from qgis.testing import start_app, TestCase

qgis_app = start_app()


class TestQgsRangeWidgetSetup(TestCase):

    @classmethod
    def setUpClass(cls):
        QgsGui.editorWidgetRegistry().initEditors()
        cls.TMP_DIR = pathlib.Path(__file__).parent

    def localLayerSourcePath(self) -> pathlib.Path:

        path_lyr = self.TMP_DIR / 'example.gpkg'
        if not path_lyr.is_file():
            # create a local *.gpkg
            uri = "point?crs=epsg:4326&field=number:integer"
            lyr = QgsVectorLayer(uri, 'scratch layer', 'memory')
            result, msg = QgsVectorLayerExporter.exportLayer(lyr, path_lyr.as_posix(), 'ogr',
                                                     lyr.crs(), options={'overwrite': True})
            if not result == QgsVectorLayerExporter.NoError:
                raise Exception(msg)

        return path_lyr

    def test_range_widget(self):
        path_lyr = self.localLayerSourcePath()
        path_qml = path_lyr.parent / re.sub(r'[^.]+$', 'qml', path_lyr.name)
        if path_qml.is_file():
            os.remove(path_qml)
        self.assertFalse(path_qml.is_file(), msg='qml file already exists')

        # open layer and assign a Range widget to field "number" with range [1, 256]
        lyr = QgsVectorLayer(path_lyr.as_posix())
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())

        factory: QgsEditorWidgetFactory = QgsGui.editorWidgetRegistry().factories()['Range']
        configWidget: QgsEditorConfigWidget = factory.configWidget(lyr, lyr.fields().lookupField('number'), None)
        config = configWidget.config()
        config['Max'] = 256
        config['Min'] = 1

        setup = QgsEditorWidgetSetup('range', config)
        # lyr.fields().field('number').setEditorWidgetSetup(setup)
        lyr.setEditorWidgetSetup(lyr.fields().lookupField('number'), setup)
        lyr.saveDefaultStyle()

        # check QML
        self.assertTrue(path_qml.is_file(), msg=f'{path_qml} has not been written')

        tree = ElementTree.parse(path_qml)
        root = tree.getroot()
        nodeMax = root.find(
            'fieldConfiguration/field[@name="number"]/editWidget[@type="range"]/config/Option/Option[@name="Max"]')
        nodeMin = root.find(
            'fieldConfiguration/field[@name="number"]/editWidget[@type="range"]/config/Option/Option[@name="Min"]')
        self.assertIsInstance(nodeMax, ElementTree.Element)
        self.assertIsInstance(nodeMin, ElementTree.Element)
        self.assertEqual(int(nodeMax.attrib['value']), 256)
        self.assertEqual(int(nodeMin.attrib['value']), 1)

        # re-load layer
        lyr2 = QgsVectorLayer(path_lyr.as_posix())
        # lyr2.loadDefaultStyle()

        # test loaded QgsEditorWidgetSetup
        setup: QgsEditorWidgetSetup = lyr2.fields().field('number').editorWidgetSetup()
        configA = setup.config()
        self.assertEqual(configA['Max'], 256)
        self.assertEqual(configA['Min'], 1)

        # test loaded QgsEditorConfigWidget
        cw: QgsEditorConfigWidget = factory.configWidget(lyr2, lyr2.fields().lookupField('number'), None)
        configB = cw.config()
        self.assertEqual(configB['Max'], 256)
        self.assertEqual(configB['Min'], 1)


