from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import QgsProject, Qgis, QgsRasterLayer, QgsCoordinateReferenceSystem, QgsRasterRange, QgsMapLayerStore, \
    QgsRasterPipe

from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas, QgsGui

from qps import initResources
from qps.speclib.core import profile_fields
from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider, \
    VectorLayerFieldRasterDataProvider, createRasterLayers
from qps.speclib.core.spectralprofile import SpectralSetting, decodeProfileValueDict
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import TestObjects, TestCase
from qps.utils import rasterArray


class RasterDataProviderTests(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(RasterDataProviderTests, cls).setUpClass(*args, **kwds)
        initResources()
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()
        registerDataProvider()

    def setUp(self):
        super().setUp()
        QgsProject.instance().removeMapLayers(QgsProject.instance().mapLayers().keys())

        self.mapLayerStore = QgsMapLayerStore()
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
        QgsProject.instance().addMapLayer(vl)

        fids = vl.allFeatureIds()
        features = vl.getFeatures()
        layers = []
        dpList = []
        registerDataProvider()
        for field in vl.fields():
            name = f'Test {field.name()}:{field.typeName()}'
            print(name)
            src = f'?lid={{{vl.id()}}}&field={field.name()}'
            layer = QgsRasterLayer(src, name, VectorLayerFieldRasterDataProvider.providerKey())
            dp: VectorLayerFieldRasterDataProvider = layer.dataProvider()

            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)
            self.assertTrue(dp.fields() == vl.fields())
            crs = dp.crs()
            dp.setActiveFeatures(features)
            self.assertIsInstance(crs, QgsCoordinateReferenceSystem)

            nb = dp.bandCount()
            for b in range(1, nb + 1):
                bandName = dp.generateBandName(b)
                displayName = dp.displayBandName(b)

                self.assertIsInstance(bandName, str)
                self.assertTrue(bandName != '')
                self.assertTrue(displayName, str)
                self.assertTrue(displayName != '')

                dt = dp.sourceDataType(b)
                self.assertIsInstance(dt, Qgis.DataType)
                src_nodata = dp.sourceNoDataValue(b)
                self.assertTrue(src_nodata is not None)
                usr_nodata = dp.userNoDataValues(b)
                self.assertIsInstance(usr_nodata, list)
                for nd in usr_nodata:
                    self.assertIsInstance(nd, QgsRasterRange)

            dpList.append(dp)
            layers.append(layer)

        lyr = layers[0]
        c = self.rasterProviderTestSuite(lyr)
        self.showGui(c)
        # print('SHOW GUI')

    def rasterProviderTestSuite(self, layer: QgsRasterLayer) -> QgsMapCanvas:
        self.assertIsInstance(layer, QgsRasterLayer)

        QgsProject.instance().addMapLayer(layer, False)

        pipe = layer.pipe()
        self.assertIsInstance(pipe, QgsRasterPipe)
        cb = QgsMapLayerComboBox()
        cb.setLayer(layer)
        c: QgsMapCanvas = QgsMapCanvas()

        c.setLayers([layer])
        c.zoomToFullExtent()

        vbLayout = QVBoxLayout()
        vbLayout.addWidget(cb)
        vbLayout.addWidget(c)
        w = QWidget()
        w.setLayout(vbLayout)
        w.show()
        return w

        return c

    def test_createExampleLayers(self):

        n_total = 20
        n_empty = 2
        vl = TestObjects.createSpectralLibrary(n_total, n_bands=[[13, 25, 5], [22, None, 42]], n_empty=n_empty)
        fields = profile_fields(vl)
        layers = createRasterLayers(vl, fields.at(1))
        for lyr in layers:
            self.assertIsInstance(lyr, QgsRasterLayer)
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)
            setting = dp.spectralSetting()
            self.assertIsInstance(setting, SpectralSetting)
            self.assertEqual(dp.bandCount(), setting.n_bands())

            # read entire raster image
            array = rasterArray(dp)
            self.assertEqual(array.shape, (setting.n_bands(), 1, n_total))

            # check for each profile its raster band values
            for iPx, fid in enumerate(dp.activeFeatureIds()):
                value = vl.getFeature(fid).attribute(setting.fieldName())
                data = decodeProfileValueDict(value)
                yValues = data['y']
                for y1, y2 in zip(array[:, 0, iPx], yValues):
                    self.assertEqual(y1, y2)

        layers = createRasterLayers(vl)
        for lyr in layers:
            self.assertIsInstance(lyr, QgsRasterLayer)
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)
