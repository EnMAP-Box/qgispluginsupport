import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qgis._core import QgsMapLayerModel, QgsProject, Qgis, QgsRasterLayer, QgsCoordinateReferenceSystem, QgsRectangle, \
    QgsField, QgsFields, QgsRasterDataProvider, QgsRasterInterface

from qgis._gui import QgsMapLayerComboBox, QgsMapCanvas, QgsGui

from qps import initResources
from qps.speclib.core.spectrallibraryrasterdataprovider import SpectralLibraryRasterDataProvider, registerDataProvider, \
    VectorLayerFieldRasterDataProvider
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import TestObjects, TestCase


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestCore, cls).setUpClass(*args, **kwds)
        initResources()
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        registerSpectralProfileEditorWidget()
        from qps import registerEditorWidgets
        registerEditorWidgets()

        from qps import registerMapLayerConfigWidgetFactories
        registerMapLayerConfigWidgetFactories()

    def test_VectorLayerRasterDataProvider(self):
        vl = TestObjects.createVectorLayer()
        registerDataProvider()
        for field in vl.fields():
            print(f'Test {field.name()}:{field.typeName()}')
            src = f'?lid={{{vl.id()}}}&field={field.name()}'
            layer = QgsRasterLayer(src, 'Test', VectorLayerFieldRasterDataProvider.providerKey())
            dp = layer.dataProvider()

            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)

    def test_SpectralLibraryRasterDataProvider(self):
        n_bands = [[256, 2500],
                   [123, 42]]
        n_features = 500

        registerDataProvider()

        SLIB = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
        # SLIB = TestObjects.createSpectralLibrary()

        dp = SpectralLibraryRasterDataProvider()

        self.assertIsInstance(dp, QgsRasterInterface)
        self.assertIsInstance(dp, QgsRasterDataProvider)

        dp.initData(SLIB)

        pfields = dp.profileFields()

        self.assertIsInstance(pfields, QgsFields)
        self.assertTrue(pfields.count() > 0)

        settingsList = dp.profileSettingsList()
        self.assertTrue(len(settingsList) > 0)
        layers = []
        for settings in settingsList:
            self.assertEqual(len(settings), pfields.count())
            dp.setActiveProfileSettings(settings)

            fids = dp.profileFIDs(settings)
            self.assertIsInstance(fids, np.ndarray)
            self.assertEqual(len(fids), n_features)

            for iField, pfield in enumerate(pfields):
                self.assertIsInstance(pfield, QgsField)
                setting = settings[iField]
                dp.setActiveProfileField(pfield)

                array = dp.profileArray()

                self.assertIsInstance(array, np.ndarray)
                self.assertEqual(array.ndim, 2)
                self.assertEqual(array.shape[0], setting.n_bands())
                self.assertEqual(array.shape[1], n_features)

                self.assertEqual(dp.xSize(), n_features)
                self.assertEqual(dp.ySize(), 1)
                self.assertEqual(dp.bandCount(), setting.n_bands())
                self.assertIsInstance(dp.dataType(1), Qgis.DataType)
                self.assertTrue(dp.dataType(1) != Qgis.DataType.UnknownDataType)

                layer = QgsRasterLayer('source', 'Test', SpectralLibraryRasterDataProvider.providerKey())
                dp2 = layer.dataProvider()
                self.assertIsInstance(dp2, SpectralLibraryRasterDataProvider)

                dp2.linkProvider(dp)
                self.assertTrue(dp2.isValid())

                dp2.setActiveProfileField(dp.activeProfileField())
                dp2.setActiveProfileSettings(dp.activeProfileSettings())
                layers.append(layer)

        for layer in layers:
            self.assertIsInstance(layer, QgsRasterLayer)
            self.assertTrue(layer.isValid())
            self.assertTrue(layer.bandCount() > 0)
            self.assertTrue(layer.dataProvider().description() == SpectralLibraryRasterDataProvider.description())
            self.assertIsInstance(layer.crs(), QgsCoordinateReferenceSystem)
            self.assertIsInstance(layer.extent(), QgsRectangle)

            for b in range(layer.bandCount()):
                bn = layer.bandName(b + 1)
                self.assertIsInstance(bn, str)
                self.assertTrue(bn != '')
                self.assertTrue(layer.dataProvider().dataType(b) != Qgis.DataType.UnknownDataType)

        model = QgsMapLayerModel(layers)
        cb = QgsMapLayerComboBox()
        cb.setModel(model)
        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayers(layers)
        canvas.setLayers(layers)
        canvas.zoomToFullExtent()

        l = QVBoxLayout()
        l.addWidget(cb)
        l.addWidget(canvas)
        w = QWidget()
        w.setLayout(l)
        self.showGui(w)
        s = ""
