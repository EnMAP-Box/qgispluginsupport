from qgis._core import QgsProject

from qps.layerfielddialog import SelectLayerFieldDialog
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

        d = SelectLayerFieldDialog()
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

        d.setField('profilesB2')
        self.assertEqual(d.field(), 'profilesB2')

        # change layer
        d.setLayer(sl1)
        field = d.field()
        self.assertEqual(field, 'profilesA1')
        # reset to previous layer. restore previous field selection
        d.setLayer(sl2)

        field = d.field()
        self.assertEqual(field, 'profilesB2')

        self.showGui(d)
