import unittest

from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer, QgsRasterPipe, QgsRasterRange
from qgis.gui import QgsMapCanvas, QgsMapLayerComboBox
from qps import initResources
from qps.speclib.core import profile_fields
from qps.speclib.core.spectrallibraryrasterdataprovider import VectorLayerFieldRasterDataProvider, createRasterLayers, \
    registerDataProvider
from qps.speclib.core.spectralprofile import SpectralSetting, decodeProfileValueDict
from qps.testing import TestCase, TestObjects, start_app
from qps.utils import rasterArray

start_app()


class RasterDataProviderTests(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(RasterDataProviderTests, cls).setUpClass(*args, **kwds)
        initResources()
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()
        registerDataProvider()

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
        QgsProject.instance().removeAllMapLayers()
        # print('SHOW GUI')

    def rasterProviderTestSuite(self, layer: QgsRasterLayer) -> QgsMapCanvas:
        self.assertIsInstance(layer, QgsRasterLayer)

        QgsProject.instance().addMapLayer(layer)

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

    def test_createExampleLayers(self):

        n_total = 20
        n_empty = 2
        vl = TestObjects.createSpectralLibrary(n_total, n_empty=n_empty, n_bands=[[13, 25, 5], [22, None, 42]])
        fields = profile_fields(vl)
        QgsProject.instance().addMapLayer(vl, addToLegend=False)
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
            self.assertEqual(array.shape, (setting.n_bands(), 1, n_total - n_empty))

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

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
