from qgis.core import QgsProject, QgsRasterLayer

from qps.layerfielddialog import LayerFieldDialog, LayerFieldWidget
from qps.speclib.core import is_spectral_library, is_profile_field
from qps.testing import TestCase, start_app, TestObjects

start_app()


class LayerFieldDialogTests(TestCase):

    def test_layer_field_dialog(self):
        sl1 = TestObjects.createSpectralLibrary(n=20, n_bands=[10, 14],
                                                profile_field_names=['profilesA1', 'profilesA2'])
        sl1.setName('Speclib A')
        sl2 = TestObjects.createSpectralLibrary(profile_field_names=['profilesB1', 'profilesB2'])
        sl2.setName('Speclib B')

        layers = [
            TestObjects.createVectorLayer(),
            TestObjects.createRasterLayer(),
            sl1, sl2,
        ]

        project = QgsProject()
        project.addMapLayers(layers)

        lyrFunc = lambda lyr: is_spectral_library(lyr)
        fieldFunc = lambda field: is_profile_field(field)

        d = LayerFieldDialog()
        d.setLayerFilter(lyrFunc)
        d.setFieldFilter(fieldFunc)
        d.setProject(project)

        self.assertNotEqual(d.layer(), sl2)

        d.setLayer(sl2.name())
        self.assertEqual(d.layer(), sl2)
        d.setLayer(sl1.id())
        self.assertEqual(d.layer(), sl1)

        d.setLayer(sl2)
        self.assertEqual(d.layer(), sl2)

        self.assertTrue(d.setLayer('Speclib B'), msg='Layer not found: Speclib B')
        self.assertTrue(d.setField('profilesB1'), msg='Field not found: profilesB1')

        self.assertTrue(d.setField('profilesB2'))
        self.assertEqual(d.field(), 'profilesB2')

        # change layer
        d.setLayer(sl1)
        field = d.field()
        self.assertEqual(field, 'profilesA1')
        # reset to the previous layer. restore previous field selection
        d.setLayer(sl2)

        field = d.field()
        self.assertEqual(field, 'profilesB2')

        self.showGui(d)

    def test_select_raster(self):
        layers = [
            TestObjects.createVectorLayer(name='sl'),
            TestObjects.createRasterLayer(name='r1', nb=1),
            TestObjects.createRasterLayer(name='r200', nb=200),
        ]
        project = QgsProject()
        project.addMapLayers(layers)

        lyrFunc = lambda lyr: isinstance(lyr, QgsRasterLayer) and lyr.bandCount() > 3

        d = LayerFieldDialog()
        d.setProject(project)
        d.setLayerFilter(lyrFunc)

        # this should hide the field filter widgets
        d.setFieldFilter(None)
        self.assertFalse(d.mLabelField.isVisible())
        self.assertFalse(d.mFieldComboBox.isVisible())
        d.setWindowTitle('Select Raster Layer')

        if TestCase.runsInCI():
            self.showGui(d)

        else:

            if d.exec() == d.Accepted:
                print(f'Accepted: {d.layer()} {d.field()}')
            else:
                print(f'Canceled: {d.layer()} {d.field()}')

    def test_layerfield_widget(self):

        layers = [
            TestObjects.createVectorLayer(name='vl'),
            TestObjects.createRasterLayer(name='r1', nb=1),
            TestObjects.createRasterLayer(name='r200', nb=200),
            TestObjects.createSpectralLibrary(name='sl1', profile_field_names=['profilesA1', 'profilesA2']),
            TestObjects.createSpectralLibrary(name='sl2', profile_field_names=['profilesB1', 'profilesB2']),

        ]
        project = QgsProject()
        project.addMapLayers(layers)

        w = LayerFieldWidget()
        w.setLayerFilter(lambda lyr: is_spectral_library(lyr))
        w.setFieldFilter(lambda field: is_profile_field(field))
        w.setProject(project)

        self.showGui(w)
