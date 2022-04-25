from typing import List

from qgis.PyQt.QtCore import QSize, Qt, NULL, QVariant
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QCheckBox
from qgis.core import QgsActionManager, QgsFeature
from qgis.gui import QgsGui, QgsMapCanvas, QgsDualView, QgsSearchWidgetWrapper

from qps.speclib import FIELD_VALUES, EDITOR_WIDGET_REGISTRY_KEY
from qps.speclib.core import profile_field_list
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.gui.spectralprofileeditor import SpectralProfileEditorWidgetFactory, SpectralProfileEditorConfigWidget, \
    SpectralProfileEditorWidgetWrapper, SpectralProfileEditorWidget, registerSpectralProfileEditorWidget, \
    SpectralProfileTableModel, SpectralProfileJsonEditor, SpectralProfileTableEditor
from qps.testing import TestCase, TestObjects
from qps.unitmodel import BAND_NUMBER


class TestSpeclibWidgets(TestCase):

    def valid_profile_dicts(self) -> List[dict]:
        examples = [
            dict(),
            dict(y=[1, 2, 3]),
            dict(y=[1, 2, 3], x=[2, 3, 4]),
            dict(y=[1, 2, 3], x=[2, 3, 4], xUnit=BAND_NUMBER),
            dict(y=[1, 2, 3], bbl=[1, 1, 0])
        ]
        return examples

    def test_SpectralProfileTableModel(self):

        model = SpectralProfileTableModel()
        for p in self.valid_profile_dicts():
            model.setProfile(p)
            d = model.profileDict()
            self.assertEqual(p, d)

    def test_SpectralProfileEditors(self):

        editors = [SpectralProfileTableEditor(),
                   SpectralProfileJsonEditor()]

        for editor in editors:
            for profile in self.valid_profile_dicts():
                editor.setProfileDict(profile)
                d = editor.profileDict()
                self.assertEqual(profile, d)
            editor.clear()
            self.assertEqual(editor.profileDict(), dict())

    def test_SpectralProfileEditorWidget(self):
        p = list(TestObjects.spectralProfiles(1, n_bands=[8]))[0]
        self.assertIsInstance(p, QgsFeature)

        pField = profile_field_list(p)[0]
        d = decodeProfileValueDict(p.attribute(pField.name()))

        w = SpectralProfileEditorWidget()
        self.assertIsInstance(w, QWidget)

        not_a_profile = [None,
                         NULL,
                         QVariant(None),
                         dict(),
                         dict(x='not a profile')]
        for p in not_a_profile:
            w.setProfile(p)
            r = w.profile()
            self.assertEqual(r, None)

        self.showGui(w)

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

        speclib = TestObjects.createSpectralLibrary(n_bands=5)

        am = speclib.actions()
        self.assertIsInstance(am, QgsActionManager)

        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())

        print('STOP 1', flush=True)
        dv = QgsDualView()
        print('STOP 2', flush=True)
        dv.init(speclib, c)
        print('STOP 3', flush=True)
        dv.setView(QgsDualView.AttributeEditor)
        print('STOP 4', flush=True)
        dv.setAttributeTableConfig(speclib.attributeTableConfig())
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
        print(speclib.fields().names())
        look = speclib.fields().lookupField
        print('STOP 4', flush=True)

        parent = QWidget()
        configWidget = factory.configWidget(speclib, look(FIELD_VALUES), parent)
        self.assertIsInstance(configWidget, SpectralProfileEditorConfigWidget)

        self.assertIsInstance(factory.createSearchWidget(speclib, 0, dv), QgsSearchWidgetWrapper)

        parent2 = QWidget()
        eww = factory.create(speclib, 0, None, parent2)
        self.assertIsInstance(eww, SpectralProfileEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), SpectralProfileEditorWidget)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))

        fields = speclib.fields()
        speclib.startEditing()
        value = eww.value()
        f = speclib.getFeature(1)
        self.assertTrue(speclib.updateFeature(f))

        self.showGui([w, configWidget])
        speclib.commitChanges()
