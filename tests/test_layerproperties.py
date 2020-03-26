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
from qps import registerMapLayerConfigWidgetFactories
from qps.resources import findQGISResourceFiles
LAYER_WIDGET_REPS = 5

class LayerPropertyTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.EditorWidgets, resources=[]) -> None:
        resources += findQGISResourceFiles()
        super(LayerPropertyTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
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

    def test_LayerPropertiesDialog_Vector(self):
        registerMapLayerConfigWidgetFactories()
        lyr = TestObjects.createVectorLayer()
        d = LayerPropertiesDialog(lyr)
        self.assertIsInstance(d, LayerPropertiesDialog)
        d.show()
        d.sync()
        for p in d.pages():
            self.assertIsInstance(p, QgsMapLayerConfigWidget)
            p.apply()
            d.setPage(p)

        w2 = QgsTextFormatPanelWidget(QgsTextFormat(), d.canvas(), None, lyr)
        w2.show()

        w = QWidget()
        w.setLayout(QHBoxLayout())
        w.layout().addWidget(d.canvas())
        w.layout().addWidget(d)

        self.showGui([w])


    def test_LayerPropertiesDialog_Raster(self):

        registerMapLayerConfigWidgetFactories()
        lyr = TestObjects.createRasterLayer(nb=1, eType=gdal.GDT_UInt16)
        d = LayerPropertiesDialog(lyr)
        d.sync()
        self.assertIsInstance(d, LayerPropertiesDialog)
        for p in d.pages():
            self.assertIsInstance(p, QgsMapLayerConfigWidget)

            p.apply()
            d.setPage(p)

        d.show()

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

    def test_add_attributes(self):

        vl = TestObjects.createVectorLayer()
        vl.startEditing()
        vl.addAttribute(createQgsField('test', 42))
        self.assertTrue(vl.commitChanges())

        d = AddAttributeDialog(vl, case_sensitive=False)
        self.assertIsInstance(d, AddAttributeDialog)
        d.setName('Test')
        is_valid, errors = d.validate()
        self.assertFalse(is_valid)
        self.assertIsInstance(errors, str)
        self.assertTrue(len(errors) > 0)

        d.setCaseSensitive(True)
        is_valid, errors = d.validate()
        self.assertTrue(is_valid)
        self.assertIsInstance(errors, str)
        self.assertTrue(len(errors) == 0)

        d.setName('test')
        self.showGui(d)

    def test_p(self):

        rl = TestObjects.createRasterLayer()
        vl = TestObjects.createVectorLayer()
        vd = QgsRendererPropertiesDialog(vl, QgsStyle(), True, None)
        canvas = QgsMapCanvas()
        rd = QgsRendererRasterPropertiesWidget(rl, canvas, None)
        wtrans = QgsRasterTransparencyWidget(rl, canvas, None)

        style = QgsMapLayerStyleManagerWidget(rl, canvas, None)
        self.showGui([vd, rd, wtrans,style])


    def test_RemoveAttributeDialog(self):
        vl = TestObjects.createVectorLayer()
        d = RemoveAttributeDialog(vl)
        d.tvFieldNames.selectAll()
        self.assertListEqual(d.fieldNames(), vl.fields().names())
        d.tvFieldNames.clearSelection()
        self.assertListEqual(d.fieldNames(), [])
        self.showGui(d)


    def test_AttributeTableWidget(self):
        vl = TestObjects.createVectorLayer()
        w = AttributeTableWidget(vl)
        vl.startEditing()


        w.mUpdateExpressionText.setExpression("'dummy'")

        self.showGui(w)


if __name__ == "__main__":
    unittest.main()

