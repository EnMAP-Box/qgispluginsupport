from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QCheckBox
from qgis.core import QgsActionManager, QgsFeature
from qgis.gui import QgsGui, QgsMapCanvas, QgsDualView, QgsSearchWidgetWrapper

from qps.speclib import FIELD_VALUES, EDITOR_WIDGET_REGISTRY_KEY
from qps.speclib.core import profile_field_list
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.gui.spectralprofileeditor import SpectralProfileEditorWidgetFactory, SpectralProfileEditorConfigWidget, \
    SpectralProfileEditorWidgetWrapper, SpectralProfileEditorWidget, registerSpectralProfileEditorWidget, \
    SpectralProfileTableModel
from qps.testing import TestCase, TestObjects


class TestSpeclibWidgets(TestCase):

    def test_SpectralProfileEditorWidget(self):
        p = list(TestObjects.spectralProfiles(1, n_bands=[8]))[0]
        self.assertIsInstance(p, QgsFeature)

        pField = profile_field_list(p)[0]
        d = decodeProfileValueDict(p.attribute(pField.name()))

        w = SpectralProfileEditorWidget()
        self.assertIsInstance(w, QWidget)

        w.setProfile(d)

        self.showGui(w)
        self.assertTrue(True)

    def test_SpectralProfileValueTableModel(self):

        p = list(TestObjects.spectralProfiles(1, n_bands=[255]))[0]
        pField = profile_field_list(p)[0]
        d = decodeProfileValueDict(p.attribute(pField.name()))
        self.assertIsInstance(d, dict)

        m = SpectralProfileTableModel()

        self.assertIsInstance(m, SpectralProfileTableModel)
        self.assertTrue(m.rowCount() == 0)
        # self.assertTrue(m.columnCount() == 2)
        self.assertEqual('x', m.headerData(0, orientation=Qt.Horizontal, role=Qt.DisplayRole))
        self.assertEqual('y', m.headerData(1, orientation=Qt.Horizontal, role=Qt.DisplayRole))

        m.setProfile(d)
        self.assertTrue(m.rowCount() == len(d.get('x', [])))
        self.assertEqual('x', m.headerData(0, orientation=Qt.Horizontal, role=Qt.DisplayRole))
        self.assertEqual('y', m.headerData(1, orientation=Qt.Horizontal, role=Qt.DisplayRole))

        # m.setColumnValueUnit(0, '')

    def test_SpectralProfileEditorWidgetFactory(self):

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()
        registerSpectralProfileEditorWidget()

        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, SpectralProfileEditorWidgetFactory)

        vl = TestObjects.createSpectralLibrary()

        am = vl.actions()
        self.assertIsInstance(am, QgsActionManager)

        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())

        print('STOP 1', flush=True)
        dv = QgsDualView()
        print('STOP 2', flush=True)
        dv.init(vl, c)
        print('STOP 3', flush=True)
        dv.setView(QgsDualView.AttributeTable)
        print('STOP 4', flush=True)
        dv.setAttributeTableConfig(vl.attributeTableConfig())
        print('STOP 5', flush=True)
        cb = QCheckBox()
        cb.setText('Show Editor')

        def onClicked(b: bool):
            if b:
                dv.setView(QgsDualView.AttributeEditor)
            else:
                dv.setView(QgsDualView.AttributeTable)

        cb.clicked.connect(onClicked)
        w.layout().addWidget(dv)
        w.layout().addWidget(cb)

        w.resize(QSize(300, 250))
        print(vl.fields().names())
        look = vl.fields().lookupField
        print('STOP 4', flush=True)
        parent = QWidget()
        configWidget = factory.configWidget(vl, look(FIELD_VALUES), None)
        self.assertIsInstance(configWidget, SpectralProfileEditorConfigWidget)

        self.assertIsInstance(factory.createSearchWidget(vl, 0, dv), QgsSearchWidgetWrapper)

        eww = factory.create(vl, 0, None, dv)
        self.assertIsInstance(eww, SpectralProfileEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), SpectralProfileEditorWidget)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))

        fields = vl.fields()
        vl.startEditing()
        value = eww.value()
        f = vl.getFeature(1)
        self.assertTrue(vl.updateFeature(f))

        self.showGui([w, configWidget])
        vl.commitChanges()
