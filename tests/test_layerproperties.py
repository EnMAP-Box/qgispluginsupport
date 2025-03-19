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
from qgis.PyQt.QtWidgets import QDialog, QGridLayout, QWidget
from qgis.core import QgsMapLayer
from qgis.core import QgsMultiBandColorRenderer, QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, \
    QgsSingleBandGrayRenderer, QgsStyle, QgsVectorLayer
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidgetFactory, QgsOptionsDialogBase, QgsRasterLayerProperties, \
    QgsRendererPropertiesDialog

from qps import MAPLAYER_CONFIGWIDGET_FACTORIES
from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget
from qps.layerproperties import AddAttributeDialog, AttributeTableWidget, CopyAttributesDialog, defaultRasterRenderer, \
    equal_styles, RemoveAttributeDialog, showLayerPropertiesDialog, pasteStyleToClipboard, pasteStyleFromClipboard
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import createQgsField

LAYER_WIDGET_REPS = 5

start_app()


class LayerPropertyTests(TestCase):

    def test_equal_styles(self):

        lyr1 = TestObjects.createRasterLayer(nb=1, nc=5)
        lyr2 = TestObjects.createRasterLayer(nb=10)

        self.assertTrue(equal_styles(lyr1, lyr1))
        self.assertFalse(equal_styles(lyr1, lyr2))

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
        del r
        QgsProject.instance().removeAllMapLayers()

    def test_enmapboxbug_452(self):
        lyr = TestObjects.createVectorLayer()
        rlr = TestObjects.createRasterLayer()
        style = QgsStyle()
        d = QgsRendererPropertiesDialog(lyr, style, embedded=True)
        self.showGui(d)
        del d
        QgsProject.instance().removeAllMapLayers()

    @unittest.skipIf(TestCase.runsInCI(), 'blocking dialog')
    def test_layer_properties1(self):

        rl = TestObjects.createRasterLayer(nb=300)
        showLayerPropertiesDialog(rl)

        vl = TestObjects.createVectorLayer()
        showLayerPropertiesDialog(vl)

    @unittest.skip('Crashes CI, unknown reason')
    def test_layerPropertiesDialog_RasterBandWidget(self):

        lyr = TestObjects.createRasterLayer(nb=255, eType=gdal.GDT_UInt16)
        self.assertTrue(lyr.isValid())
        QgsProject.instance().addMapLayer(lyr)
        w = QWidget()

        canvas = QgsMapCanvas(parent=w)
        canvas.setLayers([lyr])
        canvas.zoomToFullExtent()

        dialog1 = QgsRasterLayerProperties(lyr, canvas, parent=w)

        dialog2 = QgsRasterLayerProperties(lyr, canvas, parent=w)

        panelWidget = RasterBandConfigWidget(lyr, canvas, parent=w)
        panelWidget.setDockMode(True)
        panelWidget.widgetChanged.connect(panelWidget.apply)

        added = []
        if False:
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
        w.close()
        # del dialog1, dialog2, canvas, w
        QgsProject.instance().removeAllMapLayers()

    @unittest.skip
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

    @unittest.skip
    def test_layer_properties2(self):

        layers = [TestObjects.createRasterLayer(),
                  TestObjects.createVectorLayer()]
        QgsProject.instance().addMapLayers(layers)
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

    def test_paste_style_to_clipboard(self):

        layer = TestObjects.createRasterLayer(nb=10)

        layer.renderer().setRedBand(5)
        layer.renderer().setGreenBand(6)
        layer.renderer().setBlueBand(9)
        bands = layer.renderer().usesBands()
        self.assertEqual(layer.renderer().usesBands(), [5, 6, 9])
        pasteStyleToClipboard(layer)

        layer2 = TestObjects.createRasterLayer(nb=10)
        self.assertNotEqual(layer2.renderer().usesBands(), bands)

        pasteStyleFromClipboard(layer2)
        self.assertEqual(layer2.renderer().usesBands(), bands)

        layer3 = TestObjects.createRasterLayer(nb=10)

        # copy MapTip style only. This should not change the used bands
        # I honestly don't know why this test does not work in GH CI
        if False:
            uses_bands = layer3.renderer().usesBands()
            pasteStyleFromClipboard(layer3, categories=QgsMapLayer.StyleCategory.Notes)
            self.assertEqual(layer3.renderer().usesBands(), uses_bands)

    def test_RemoveAttributeDialog(self):
        vl = TestObjects.createVectorLayer()
        d = RemoveAttributeDialog(vl)

        self.showGui(d)

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
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
        assert vl.isSpatial()
        w = AttributeTableWidget(vl)
        vl.startEditing()

        def onAction(*args):
            s = ""

        w.mActionZoomMapToSelectedRows.triggered.connect(onAction)
        w.mUpdateExpressionText.setField("'dummy'")

        self.showGui(w)
        w.close()
        QgsProject.instance().removeAllMapLayers()


if __name__ == "__main__":
    unittest.main(buffer=False)
