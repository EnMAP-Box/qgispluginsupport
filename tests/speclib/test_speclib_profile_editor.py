import unittest
from typing import List

from qgis.PyQt.QtCore import NULL, QSize, Qt, QVariant
from qgis.PyQt.QtWidgets import QCheckBox, QVBoxLayout, QWidget
from qgis.core import QgsActionManager, QgsFeature
from qgis.gui import QgsDualView, QgsGui, QgsMapCanvas, QgsSearchWidgetWrapper
from qps.speclib import EDITOR_WIDGET_REGISTRY_KEY, FIELD_VALUES
from qps.speclib.core import profile_field_list
from qps.speclib.core.spectralprofile import decodeProfileValueDict, prepareProfileValueDict
from qps.speclib.gui.spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel
from qps.speclib.gui.spectralprofileeditor import SpectralProfileEditorConfigWidget, SpectralProfileEditorWidget, \
    SpectralProfileEditorWidgetFactory, spectralProfileEditorWidgetFactory, SpectralProfileEditorWidgetWrapper, \
    SpectralProfileJsonEditor, SpectralProfileTableEditor, SpectralProfileTableModel
from qps.speclib.gui.spectralprofileplotwidget import SpectralProfilePlotWidget
from qps.testing import start_app, TestCase, TestObjects
from qps.unitmodel import BAND_NUMBER

start_app()


def valid_profile_dicts() -> List[dict]:
    examples = [
        dict(y=[1, 2, 3], x=[2, 3, 4], xUnit='foobar'),
        dict(y=[1, 2, 3], bbl=[1, 2, 3]),
        dict(y=[1, 2, 3]),
        dict(y=[1, 2, 3], x=[2, 3, 4]),
        dict(y=[1, 2, 3], x=['2005-02-25', '2005-03-25', '2005-04-25']),
        dict(y=[1, 2, 3], x=[2, 3, 4], xUnit=BAND_NUMBER),

        dict(y=[1, 2, 3], bbl=[1, 1, 0]),
    ]
    for u in SpectralProfilePlotXAxisUnitModel.instance():
        examples.append(
            dict(y=[0, 8, 15], x=[1, 2, 3], xUnit=u.unit)
        )

    examples = [prepareProfileValueDict(prototype=e) for e in examples]
    return examples


class TestSpeclibWidgets(TestCase):

    def valid_profile_dicts(self):
        return valid_profile_dicts()

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
            for i, d1 in enumerate(self.valid_profile_dicts()):
                editor.setProfileDict(d1)
                d2 = editor.profileDict()
                if d1 != d2:
                    editor.setProfileDict(d1)
                    d2 = editor.profileDict()
                    s = ""
                self.assertEqual(d1, d2)
            editor.clear()
            self.assertEqual(editor.profileDict(), dict())

    def test_SpectralProfileEditorWidget(self):
        from qps import initResources
        initResources()
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

        w.setProfile(d)
        # w.setReadOnly(True)
        self.showGui(w)

    def test_SpectralProfilePlotWidget(self):

        w = SpectralProfilePlotWidget()

        p = list(TestObjects.spectralProfiles(1, n_bands=[8]))[0]
        self.assertIsInstance(p, QgsFeature)

        pField = profile_field_list(p)[0]
        profile = decodeProfileValueDict(p.attribute(pField.name()))

        w.setProfile(profile)

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
        spectralProfileEditorWidgetFactory(True)

        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())
        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, SpectralProfileEditorWidgetFactory)

        speclib = TestObjects.createSpectralLibrary(n=5, n_empty=2, n_bands=5)

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


if __name__ == '__main__':
    unittest.main(buffer=False)
