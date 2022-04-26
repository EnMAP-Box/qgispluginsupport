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
from test_speclib_core import SpeclibCoreTests


class TestSpeclibWidgets(TestCase):

    def valid_profile_dicts(self):
        return SpeclibCoreTests.valid_profile_dicts()

    def test_SpectralProfileTableModel(self):

        model = SpectralProfileTableModel()
        for p in self.valid_profile_dicts():
            model.setProfileDict(p)
            d1 = {k: v for k, v in p.items() if k in ['x', 'y', 'bbl']}
            d2 = model.profileDict()
            self.assertEqual(d1, d2)

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
        hdr = ['#', 'x', 'y', 'bbl']
        for i, n in enumerate(hdr):
            self.assertEqual(n, m.headerData(i, orientation=Qt.Horizontal, role=Qt.DisplayRole))

        m.setProfileDict(d)
        self.assertTrue(m.rowCount() == len(d.get('x', [])))

        for i, n in enumerate(hdr):
            self.assertEqual(n, m.headerData(i, orientation=Qt.Horizontal, role=Qt.DisplayRole))

    def test_SpectralProfileEditorWidgetFactory(self):

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()
        registerSpectralProfileEditorWidget()

        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, SpectralProfileEditorWidgetFactory)

        speclib = TestObjects.createSpectralLibrary(n=5, n_bands=5, n_empty=2)

        am = speclib.actions()
        self.assertIsInstance(am, QgsActionManager)

        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())

        dv = QgsDualView()
        dv.init(speclib, c)
        dv.setView(QgsDualView.AttributeEditor)
        dv.setAttributeTableConfig(speclib.attributeTableConfig())
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

        parent = QWidget()
        configWidget = factory.configWidget(speclib, look(FIELD_VALUES), parent)
        self.assertIsInstance(configWidget, SpectralProfileEditorConfigWidget)

        self.assertIsInstance(factory.createSearchWidget(speclib, 0, dv), QgsSearchWidgetWrapper)

        parent2 = QWidget()
        eww = factory.create(speclib, 0, None, parent2)
        self.assertIsInstance(eww, SpectralProfileEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), SpectralProfileEditorWidget)

        eww.valueChanged.connect(lambda v: print(f'value changed: {v}'))

        fields = speclib.fields()
        speclib.startEditing()
        value = eww.value()
        f = speclib.getFeature(1)
        self.assertTrue(speclib.updateFeature(f))

        self.showGui([w, configWidget])
        speclib.commitChanges()
