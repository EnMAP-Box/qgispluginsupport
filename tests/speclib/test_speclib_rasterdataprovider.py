import numpy as np
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qgis._core import QgsMapLayerModel, QgsProject, Qgis, QgsRasterLayer, QgsCoordinateReferenceSystem, QgsRectangle, \
    QgsField, QgsFields, QgsRasterDataProvider, QgsRasterInterface, QgsRasterRange, QgsMapLayerStore, QgsRasterPipe

from qgis._gui import QgsMapLayerComboBox, QgsMapCanvas, QgsGui

from qps import initResources
from qps.speclib.core import profile_fields
from qps.speclib.core.spectrallibraryrasterdataprovider import SpectralLibraryRasterDataProvider, registerDataProvider, \
    VectorLayerFieldRasterDataProvider, createExampleLayers
from qps.speclib.gui.spectralprofileeditor import registerSpectralProfileEditorWidget
from qps.testing import TestObjects, TestCase


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
            for b in range(1, nb+1):
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
        #print('SHOW GUI')


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

        l = QVBoxLayout()
        l.addWidget(cb)
        l.addWidget(c)
        w = QWidget()
        w.setLayout(l)
        w.show()
        return w


        return c

    def test_createExampleLayers(self):

        vl = TestObjects.createSpectralLibrary(20, n_bands=[[13, 25, 5], [22, None, 42]], n_empty=2)
        fields = profile_fields(vl)
        layers = createExampleLayers(vl, fields.at(1))
        for lyr in layers:
            self.assertIsInstance(lyr, QgsRasterLayer)
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)
            self.assertTrue(len(dp.activeFeatureIds()) == 20)

        layers = createExampleLayers(vl)
        for lyr in layers:
            self.assertIsInstance(lyr, QgsRasterLayer)
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)

        s = ""
