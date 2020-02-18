# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, time
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from osgeo import gdal, ogr, osr
from qps.testing import TestObjects, TestCase, StartOptions, initQtResources
from qps.layerproperties import *

LAYER_WIDGET_REPS = 5

class LayerRendererTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.EditorWidgets, resources=[]) -> None:
        super(LayerRendererTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        initQtResources()


    def test_SubLayerSelection(self):

        p = r'F:\Temp\Hajo\S3A_OL_2_EFR____20160614T082507_20160614T082707_20170930T190837_0119_005_178______MR1_R_NT_002_vical_c2rcc015nets20170704.nc'

        #d = QgsSublayersDialog(QgsSublayersDialog.Gdal, )




    def test_subLayerDefinitions(self):


        from qpstestdata import testvectordata, landcover, enmap
        from qps.layerproperties import subLayers, subLayerDefinitions

        p = enmap
        sDefs = subLayers(QgsRasterLayer(p))
        self.assertIsInstance(sDefs, list)
        self.assertTrue(len(sDefs) == 1)

        vl = QgsVectorLayer(testvectordata)
        sLayers = subLayers(vl)
        self.assertIsInstance(sLayers, list)
        self.assertTrue(len(sLayers) == 2)

        p = r'F:\Temp\Hajo\S3A_OL_2_EFR____20160614T082507_20160614T082707_20170930T190837_0119_005_178______MR1_R_NT_002_vical_c2rcc015nets20170704.nc'

        if os.path.isfile(p):
            rl = QgsRasterLayer(p)
            sDefs = subLayerDefinitions(rl)
            self.assertTrue(sDefs, list)
            self.assertTrue(len(sDefs) > 0)

            sLayers = subLayers(rl)

            self.assertTrue(sLayers, list)
            self.assertTrue(len(sLayers) > 0)



    def test_defaultRenderer(self):

        #1 band, byte
        ds = TestObjects.createRasterDataset(nb=1, eType=gdal.GDT_Byte)
        lyr = QgsRasterLayer(ds.GetDescription())
        r = defaultRasterRenderer(lyr)
        self.assertIsInstance(r, QgsSingleBandGrayRenderer)

        # 1 band, classification
        ds = TestObjects.createRasterDataset(nc=3)
        lyr = QgsRasterLayer(ds.GetDescription())
        r = defaultRasterRenderer(lyr)
        self.assertIsInstance(r, QgsPalettedRasterRenderer)

        # 3 bands, byte
        ds = TestObjects.createRasterDataset(nb=3, eType=gdal.GDT_Byte)
        lyr = QgsRasterLayer(ds.GetDescription())
        r = defaultRasterRenderer(lyr)
        self.assertIsInstance(r, QgsMultiBandColorRenderer)

        # 10 bands, int
        ds = TestObjects.createRasterDataset(nb=10, eType=gdal.GDT_Int16)
        lyr = QgsRasterLayer(ds.GetDescription())
        r = defaultRasterRenderer(lyr)
        self.assertIsInstance(r, QgsMultiBandColorRenderer)

    def test_QgsMapLayerConfigWidget(self):

        lyr = TestObjects.createRasterLayer(nb=3)
        QgsProject.instance().addMapLayer(lyr)
        canvas = QgsMapCanvas()
        canvas.setLayers([lyr])
        canvas.setExtent(canvas.fullExtent())

        w1 = QgsRendererRasterPropertiesWidget(lyr, canvas, None)

        self.showGui(([canvas, w1]))


    def test_metadatatable(self):

        lyr = TestObjects.createVectorLayer()
        #lyr = TestObjects.createRasterLayer()
        model = GDALMetadataModel()
        tv = QTableView()
        tv.setModel(model)
        model.setLayer(lyr)

        self.showGui(tv)


    def test_LayerPropertiesDialog_Vector(self):
        lyr = TestObjects.createVectorLayer()
        d = LayerPropertiesDialog(lyr)
        self.assertIsInstance(d, LayerPropertiesDialog)
        d.show()
        d.sync()

        w = QWidget()
        w.setLayout(QHBoxLayout())
        w.layout().addWidget(d.canvas())
        w.layout().addWidget(d)
        self.showGui(w)

    def test_LayerPropertiesDialog_Raster(self):
        lyr = TestObjects.createRasterLayer()
        d = LayerPropertiesDialog(lyr)
        self.assertIsInstance(d, LayerPropertiesDialog)
        d.show()
        d.sync()

        w = QWidget()
        w.setLayout(QHBoxLayout())
        w.layout().addWidget(d.canvas())
        w.layout().addWidget(d)
        self.showGui(w)

    def test_LayerProperties(self):

        layers = [TestObjects.createRasterLayer(),
                  TestObjects.createVectorLayer()]
        for lyr in layers:
            dialog = showLayerPropertiesDialog(lyr, modal=False)
            self.assertIsInstance(dialog, LayerPropertiesDialog)
            self.assertTrue(dialog.isVisible())

            dialog.btnCancel.click()
            self.assertTrue(dialog.result() == QDialog.Rejected)

            dialog = showLayerPropertiesDialog(lyr, modal=False)
            dialog.btnOk.click()
            self.assertTrue(dialog.result() == QDialog.Accepted)


    def test_p(self):

        rl = TestObjects.createRasterLayer()
        vl = TestObjects.createVectorLayer()
        vd = QgsRendererPropertiesDialog(vl, QgsStyle(), True, None)
        canvas = QgsMapCanvas()
        rd = QgsRendererRasterPropertiesWidget(rl, canvas, None)
        wtrans = QgsRasterTransparencyWidget(rl, canvas, None)

        style = QgsMapLayerStyleManagerWidget(rl, canvas, None)
        self.showGui([vd, rd, wtrans,style])




if __name__ == "__main__":
    unittest.main()

