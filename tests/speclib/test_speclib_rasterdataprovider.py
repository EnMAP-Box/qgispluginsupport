import unittest

import numpy as np
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer, QgsRasterPipe, QgsRasterRange, edit
)
from qgis.core import QgsField
from qgis.core import QgsRasterBandStats
from qgis.gui import QgsMapCanvas, QgsMapLayerComboBox

from qps import initResources
from qps.speclib.core import is_profile_field
from qps.speclib.core.spectrallibraryrasterdataprovider import createRasterLayers, registerDataProvider, \
    VectorLayerFieldRasterDataProvider
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import rasterArray

start_app()


class RasterDataProviderTests(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(RasterDataProviderTests, cls).setUpClass(*args, **kwds)
        initResources()
        registerDataProvider()

    def test_empty_provider(self):

        layer = QgsRasterLayer('?', 'MyName', VectorLayerFieldRasterDataProvider.providerKey())
        self.assertIsInstance(layer, QgsRasterLayer)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.name(), 'MyName')
        self.assertEqual(layer.bandCount(), 0)
        self.assertEqual(layer.width(), 0)
        self.assertEqual(layer.height(), 0)

    def test_VectorLayerRasterDataProvider(self):
        vl = TestObjects.createVectorLayer()
        QgsProject.instance().addMapLayer(vl)

        _ = vl.allFeatureIds()
        features = list(vl.getFeatures())
        layers = []
        dpList = []
        registerDataProvider()
        for field in vl.fields():
            name = f'Test {field.name()}:{field.typeName()}'
            print(name)
            src = f'?lid={{{vl.id()}}}&field={field.name()}'
            layer = QgsRasterLayer(src, name, VectorLayerFieldRasterDataProvider.providerKey())
            dp = layer.dataProvider()

            # lid = QgsProcessingUtils.layerToStringIdentifier(layer)
            # ns = QgsProcessingUtils.normalizeLayerSource(layer.source())
            # dp.setParent(None)
            self.assertIsInstance(dp, VectorLayerFieldRasterDataProvider)
            self.assertTrue(dp.fields() == vl.fields())

            caps = dp.capabilities()
            self.assertIsInstance(caps, Qgis.RasterInterfaceCapabilities)

            crs = dp.crs()
            dp.setActiveFeatures(features, field.name())
            self.assertIsInstance(crs, QgsCoordinateReferenceSystem)

            src2 = layer.source()
            self.assertEqual(src2, src)

            nb = dp.bandCount()
            for b in range(1, nb + 1):
                bandName = dp.generateBandName(b)
                displayName = dp.displayBandName(b)

                self.assertIsInstance(bandName, str)
                self.assertTrue(bandName != '')
                self.assertTrue(displayName, str)
                self.assertTrue(displayName != '')

                stats = dp.bandStatistics(b, Qgis.RasterBandStatistic.All)
                self.assertIsInstance(stats, QgsRasterBandStats)
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
        dp = None
        dpList.clear()
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
        vl = TestObjects.createSpectralLibrary(
            n_total,
            n_empty=n_empty,
            n_bands=[[13, 25, 5], [22, None, 42]]
        )

        with edit(vl):
            vl.addAttribute(QgsField('class', QMetaType.QString))
            for f in vl.getFeatures():
                if f.id() % 3 == 0:
                    class_name = None
                elif f.id() % 2 == 0:
                    class_name = 'Class B'
                else:
                    class_name = 'Class A'
                f['class'] = class_name
                vl.updateFeature(f)

        # fields = profile_fields(vl)
        QgsProject.instance().addMapLayer(vl, addToLegend=False)
        layers = createRasterLayers(vl)
        for lyr1 in layers:
            self.assertIsInstance(lyr1, QgsRasterLayer)
            dp1: VectorLayerFieldRasterDataProvider = lyr1.dataProvider()
            self.assertIsInstance(dp1, VectorLayerFieldRasterDataProvider)

            field = dp1.fields()[dp1.activeField()]
            self.assertIsInstance(field, QgsField)
            self.assertTrue(field.name() in vl.fields().names())

            is_prof = is_profile_field(field)

            rmd = dp1.rasterMetaData()
            self.assertIsInstance(rmd, dict)
            nb = rmd['band_count']
            self.assertEqual(dp1.bandCount(), nb)
            array1 = rasterArray(dp1)
            self.assertIsInstance(array1, np.ndarray)

            if not is_profile_field(field):
                mArray = dp1.mRasterData
                self.assertIsInstance(mArray, np.ndarray)
                self.assertEqual(mArray.shape, array1.shape)
                self.assertTrue(np.array_equal(mArray, array1))

            # check for each profile its raster band values
            vector_values = []
            for iPx, fid in enumerate(dp1.activeFeatureIds()):
                vector_value = vl.getFeature(fid).attribute(field.name())
                vector_values.append(vector_value)
                if is_prof:
                    data = decodeProfileValueDict(vector_value)
                    yValues = data['y']
                    for y1, y2 in zip(array1[:, 0, iPx], yValues):
                        self.assertEqual(y1, y2)
                elif field.isNumeric():
                    self.assertEqual(vector_value, array1[:, 0, iPx])
                elif field.type() == QMetaType.QString:
                    pass

            # create second data provider from same url
            lyrA = lyr1.clone()
            lyrA.setName('layerA')
            lyrB = QgsRasterLayer(lyr1.source(), 'layerB', VectorLayerFieldRasterDataProvider.providerKey())

            for lyr2 in [lyrA, lyrB]:
                self.assertTrue(lyr2.isValid())
                self.assertEqual(lyr2.source(), lyr1.source())
                dp2 = lyr2.dataProvider()

                source = lyr2.source()
                self.assertIsInstance(source, str)

                self.assertIsInstance(dp2, VectorLayerFieldRasterDataProvider)
                self.assertEqual(dp1.featureSourceId(), dp2.featureSourceId())

                if False:
                    # todo: ensure correct cloning including feature subsets
                    self.assertDictEqual(dp2.rasterMetaData(), dp1.rasterMetaData())
                    self.assertTrue(np.array_equal(dp1.mRasterData, dp2.mRasterData))
                    self.assertListEqual(dp1.activeFeatureIds(), dp2.activeFeatureIds())

                    # read entire raster image
                    array2 = rasterArray(dp1)
                    self.assertTrue(np.array_equal(array1, array2))

        layers = createRasterLayers(vl)
        for lyr1 in layers:
            self.assertIsInstance(lyr1, QgsRasterLayer)
            dp1: VectorLayerFieldRasterDataProvider = lyr1.dataProvider()
            self.assertIsInstance(dp1, VectorLayerFieldRasterDataProvider)

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
