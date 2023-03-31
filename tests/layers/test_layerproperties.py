# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest

from osgeo import gdal

from qgis.PyQt.QtWidgets import QDialog, QWidget, QGridLayout
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsPalettedRasterRenderer, \
    QgsMultiBandColorRenderer, QgsStyle, QgsSingleBandGrayRenderer, QgsProject
from qgis.gui import QgsRasterLayerProperties, QgsOptionsDialogBase, QgsMapLayerConfigWidgetFactory
from qgis.gui import QgsRendererPropertiesDialog, QgsMapCanvas
from qps import registerMapLayerConfigWidgetFactories, MAPLAYER_CONFIGWIDGET_FACTORIES
from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget
from qps.layerproperties import RemoveAttributeDialog, AttributeTableWidget, CopyAttributesDialog, AddAttributeDialog, \
    showLayerPropertiesDialog, defaultRasterRenderer, equal_styles
from qps.testing import TestObjects, TestCaseBase, start_app
from qps.utils import createQgsField

LAYER_WIDGET_REPS = 5

start_app()
registerMapLayerConfigWidgetFactories()


class LayerPropertyTests(TestCaseBase):

    def test_equal_styles(self):

        lyr1 = TestObjects.createRasterLayer(nb=1, nc=5)
        lyr2 = TestObjects.createRasterLayer(nb=10)

        self.assertTrue(equal_styles(lyr1, lyr1))
        self.assertFalse(equal_styles(lyr1, lyr2))

    def test_subLayerDefinitions(self):

        from qpstestdata import testvectordata, enmap
        from qps.layerproperties import subLayers

        p = enmap
        rl = QgsRasterLayer(p)
        sDefs = subLayers(rl)
        self.assertIsInstance(sDefs, list)
        self.assertTrue(len(sDefs) == 1)

        vl = QgsVectorLayer(testvectordata)
        sLayers = subLayers(vl)
        self.assertIsInstance(sLayers, list)
        self.assertTrue(len(sLayers) == 1)

        QgsProject.instance().removeAllMapLayers()

    def test_defaultRenderer(self):

        # 1 band, byte
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

        QgsProject.instance().removeAllMapLayers()

    def test_enmapboxbug_452(self):
        lyr = TestObjects.createVectorLayer()
        rlr = TestObjects.createRasterLayer()
        style = QgsStyle()
        d = QgsRendererPropertiesDialog(lyr, style, embedded=True)
        self.showGui(d)

        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(TestCaseBase.runsInCI(), 'blocking dialog')
    def test_layer_properties(self):

        rl = TestObjects.createRasterLayer(nb=300)
        showLayerPropertiesDialog(rl)

        vl = TestObjects.createVectorLayer()
        showLayerPropertiesDialog(vl)

    def test_layerPropertiesDialog_RasterBandWidget(self):

        lyr = TestObjects.createRasterLayer(nb=255, eType=gdal.GDT_UInt16)
        QgsProject.instance().addMapLayer(lyr)
        w = QWidget()

        canvas = QgsMapCanvas(parent=w)
        canvas.setLayers([lyr])
        canvas.zoomToFullExtent()
        dialog1 = QgsRasterLayerProperties(lyr, canvas)
        dialog2 = QgsRasterLayerProperties(lyr, canvas)

        panelWidget = RasterBandConfigWidget(lyr, canvas)
        panelWidget.setDockMode(True)
        panelWidget.widgetChanged.connect(panelWidget.apply)

        added = []
        for factory in MAPLAYER_CONFIGWIDGET_FACTORIES:
            factory: QgsMapLayerConfigWidgetFactory
            added.append(factory.title())
            dialog1.addPropertiesPageFactory(factory)
            dialog2.addPropertiesPageFactory(factory)

        grid = QGridLayout()
        grid.addWidget(canvas, 0, 0)
        grid.addWidget(panelWidget, 0, 1)
        grid.addWidget(dialog1, 1, 0)
        grid.addWidget(dialog2, 1, 1)

        w.setWindowTitle('Dialog Test')
        w.setLayout(grid)
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    def test_LayerPropertiesDialog_Raster(self):

        s = ""

        lyr = TestObjects.createRasterLayer(nb=255, eType=gdal.GDT_UInt16)
        QgsProject.instance().addMapLayer(lyr)
        c = QgsMapCanvas()
        c.setLayers([lyr])

        d = QgsRasterLayerProperties(lyr, c)

        if True:
            for factory in MAPLAYER_CONFIGWIDGET_FACTORIES:
                factory: QgsMapLayerConfigWidgetFactory
                d.addPropertiesPageFactory(factory)

        self.showGui(d)
        del d
        QgsProject.instance().removeAllMapLayers()

    def test_LayerProperties(self):

        layers = [TestObjects.createRasterLayer(),
                  TestObjects.createVectorLayer()]
        for lyr in layers:
            dialog = showLayerPropertiesDialog(lyr, modal=False)
            self.assertIsInstance(dialog, QgsOptionsDialogBase)
            self.assertTrue(dialog.isVisible())

            # self.showGui(dialog)
            # dialog.btnCancel.click()
            # self.assertTrue(dialog.result() == QDialog.Rejected)

            # dialog = showLayerPropertiesDialog(lyr, modal=False)
            # dialog.btnOk.click()
            # self.assertTrue(dialog.result() == QDialog.Accepted)
            del dialog

        QgsProject.instance().removeAllMapLayers()

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

    def test_RemoveAttributeDialog(self):
        vl = TestObjects.createVectorLayer()
        d = RemoveAttributeDialog(vl)

        self.showGui(d)

    @unittest.skipIf(TestCaseBase.runsInCI(), 'Blocking dialog')
    def test_CopyAttributesDialog(self):

        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        lyr = TestObjects.createVectorLayer()
        lyr.startEditing()
        lyr.renameAttribute(lyr.fields().lookupField('Name'), 'name')
        lyr.commitChanges()
        d = CopyAttributesDialog(sl, lyr.fields())

        if d.exec_() == QDialog.Accepted:
            sl.startEditing()
            for f in d.selectedFields():
                sl.addAttribute(f)
            self.assertTrue(sl.commitChanges())

    def test_AttributeTableWidget(self):
        vl = TestObjects.createVectorLayer()
        w = AttributeTableWidget(vl)
        vl.startEditing()

        w.mUpdateExpressionText.setField("'dummy'")

        self.showGui(w)


if __name__ == "__main__":
    unittest.main(buffer=False)
