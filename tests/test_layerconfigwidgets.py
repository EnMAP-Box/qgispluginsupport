# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest

import xmlrunner
from osgeo import gdal

from qgis.PyQt.QtCore import QSortFilterProxyModel, Qt, QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget, QTableView, QGridLayout, QPushButton, QHBoxLayout
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsField, QgsAbstractVectorLayerLabeling
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, \
    QgsMapLayerComboBox, QgsRasterBandComboBox, QgsRasterTransparencyWidget, QgsMapLayerConfigWidgetFactory
from qps.layerconfigwidgets.rasterbands import RasterBandComboBox
from qps.resources import initQtResources
from qps.testing import TestObjects, TestCase, StartOptions

LAYER_WIDGET_REPS = 5


class LayerConfigWidgetsTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.EditorWidgets, resources=[]) -> None:
        super(LayerConfigWidgetsTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        initQtResources()

    def canvasWithLayer(self, lyr) -> QgsMapCanvas:
        c = QgsMapCanvas()
        c.setLayers([lyr])
        c.setDestinationCrs(lyr.crs())
        c.setExtent(lyr.extent())
        return c

    def test_metadata(self):
        from qps.layerconfigwidgets.core import MetadataConfigWidgetFactory, MetadataConfigWidget
        lyrR = TestObjects.createRasterLayer(nb=100)
        lyrV = TestObjects.createVectorLayer()
        c = QgsMapCanvas()

        f = MetadataConfigWidgetFactory()

        for lyr in [lyrR, lyrV]:
            c.setLayers([lyr])
            c.setDestinationCrs(lyr.crs())
            c.setExtent(lyr.extent())
            self.assertTrue(f.supportsLayer(lyr))
            w = f.createWidget(lyr, c)
            self.assertIsInstance(w, MetadataConfigWidget)
            w.syncToLayer()
            w.apply()

            self.showGui([c, w])

    def test_source(self):
        from qps.layerconfigwidgets.core import SourceConfigWidget, SourceConfigWidgetFactory
        lyrR = TestObjects.createRasterLayer(nb=100)
        lyrV = TestObjects.createVectorLayer()
        c = QgsMapCanvas()

        f = SourceConfigWidgetFactory()

        for lyr in [lyrR, lyrV]:
            c.setLayers([lyr])
            c.setDestinationCrs(lyr.crs())
            c.setExtent(lyr.extent())
            self.assertTrue(f.supportsLayer(lyr))
            w = f.createWidget(lyr, c)
            self.assertIsInstance(w, SourceConfigWidget)
            w.syncToLayer()
            w.apply()

            self.showGui([c, w])

    def test_labels(self):

        from qps.layerconfigwidgets.vectorlabeling import LabelingConfigWidgetFactory, LabelingConfigWidget

        lyrV = TestObjects.createVectorLayer()
        lyrR = TestObjects.createRasterLayer()
        canvas = self.canvasWithLayer(lyrV)

        f = LabelingConfigWidgetFactory()
        self.assertTrue(f.supportsLayer(lyrV))
        self.assertFalse(f.supportsLayer(lyrR))

        w = f.createWidget(lyrV, canvas)
        self.assertIsInstance(w, LabelingConfigWidget)
        self.assertIsInstance(lyrV, QgsVectorLayer)

        self.assertTrue(w.mapLayer() == lyrV)
        for i in range(w.comboBox.count()):
            w.comboBox.setCurrentIndex(i)
            if i == 0:
                self.assertTrue(w.labeling() is None)
                w.apply()
                self.assertFalse(lyrV.labelsEnabled())
                self.assertEqual(lyrV.labeling(), None)
            else:
                if not w.labeling() is None:
                    self.assertIsInstance(w.labeling(), QgsAbstractVectorLayerLabeling)
                    w.apply()
                    self.assertTrue(lyrV.labelsEnabled())
                    self.assertEqual(type(lyrV.labeling()), type(w.labeling()))

            labeling = w.labeling()
            w.setLabeling(labeling)

        self.showGui(w)

    def test_transparency(self):

        lyr = TestObjects.createRasterLayer()
        c = QgsMapCanvas()
        c.setLayers([lyr])

        w1 = QgsRasterTransparencyWidget(lyr, c)

        btnApply = QPushButton('Apply')
        btnSync = QPushButton('Sync')

        def onApply():
            ndv1 = [n.min() for n in lyr.dataProvider().userNoDataValues(1)]
            w1.apply()
            ndv2 = [n.min() for n in lyr.dataProvider().userNoDataValues(1)]

            s = ""

        def onSync():
            ndv1 = [n.min() for n in lyr.dataProvider().userNoDataValues(1)]
            w1.apply()
            ndv2 = [n.min() for n in lyr.dataProvider().userNoDataValues(1)]
            w1.syncToLayer()
            ndv3 = [n.min() for n in lyr.dataProvider().userNoDataValues(1)]

            s = ""

        btnApply.clicked.connect(onApply)
        btnSync.clicked.connect(onSync)

        w = QWidget()
        vbLayout = QVBoxLayout()
        lh = QHBoxLayout()
        lh.addWidget(btnApply)
        lh.addWidget(btnSync)
        vbLayout.addLayout(lh)
        vbLayout.addWidget(w1)
        w.setLayout(vbLayout)
        self.showGui(w)

    def test_histogram(self):
        pass

    def test_rendering(self):
        pass

    def test_pyramids(self):
        pass

    def test_fields_and_forms(self):
        from qps.layerconfigwidgets.vectorlayerfields import \
            LayerFieldsConfigWidgetFactory, LayerAttributeFormConfigWidgetFactory, \
            LayerFieldsConfigWidget, LayerAttributeFormConfigWidget

        lyr = TestObjects.createVectorLayer()
        c = self.canvasWithLayer(lyr)
        fFields = LayerFieldsConfigWidgetFactory()
        fForms = LayerAttributeFormConfigWidgetFactory()

        wFields = fFields.createWidget(lyr, c)
        wForms = fForms.createWidget(lyr, c)

        self.assertIsInstance(wFields, QgsMapLayerConfigWidget)
        self.assertIsInstance(wForms, QgsMapLayerConfigWidget)

        self.assertIsInstance(wFields, LayerFieldsConfigWidget)
        self.assertIsInstance(wForms, LayerAttributeFormConfigWidget)
        self.showGui([wFields, wForms])

    def test_rasterbandselection2(self):
        from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget, RasterBandConfigWidgetFactory

        from qpstestdata import ndvi_ts
        ndvi_ts = self.createImageCopy(ndvi_ts)
        lyrR = QgsRasterLayer(ndvi_ts)
        self.assertTrue(lyrR.isValid())
        cR = self.canvasWithLayer(lyrR)

        f = RasterBandConfigWidgetFactory()
        self.assertIsInstance(f, QgsMapLayerConfigWidgetFactory)
        self.assertTrue(f.supportsLayer(lyrR))
        w = f.createWidget(lyrR, cR, dockWidget=False)
        self.assertIsInstance(w, RasterBandConfigWidget)

        w = f.createWidget(lyrR, None, False, None)
        self.assertIsInstance(w, RasterBandConfigWidget)

        self.showGui([cR, w])

    def test_rasterbandComboBox(self):
        lyr = TestObjects.createRasterLayer(nb=255)
        cb = RasterBandComboBox()
        cb.setLayer(lyr)

        self.showGui(cb)

    def test_rasterbandselection(self):
        from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget, RasterBandConfigWidgetFactory

        lyrR = TestObjects.createRasterLayer(nb=200)
        lyrV = TestObjects.createVectorLayer()
        cR = self.canvasWithLayer(lyrR)

        f = RasterBandConfigWidgetFactory()
        self.assertIsInstance(f, QgsMapLayerConfigWidgetFactory)
        self.assertTrue(f.supportsLayer(lyrR))
        self.assertFalse(f.supportsLayer(lyrV))
        w = f.createWidget(lyrR, cR, dockWidget=False)
        self.assertIsInstance(w, RasterBandConfigWidget)

        self.showGui([cR, w])

    def test_empty_gdalmetadata(self):

        lyrR = TestObjects.createRasterLayer(nb=100, eType=gdal.GDT_Byte)
        lyrV = TestObjects.createVectorLayer()
        lyrE = QgsRasterLayer()

        QgsProject.instance().addMapLayers([lyrR, lyrV, lyrE])
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget
        cb = QgsMapLayerComboBox()
        c = QgsMapCanvas()
        md = GDALMetadataModelConfigWidget()
        cb.layerChanged.connect(md.setLayer)
        vbLayout = QVBoxLayout()
        vbLayout.addWidget(cb)
        vbLayout.addWidget(md)
        w = QWidget()
        w.setLayout(vbLayout)
        self.showGui(w)

    def test_GDALBandNameModel(self):

        from qpstestdata import enmap
        enmap2 = self.createImageCopy(enmap)

        ds: gdal.Dataset = gdal.Open(enmap2)
        old_name = ds.GetRasterBand(1).GetDescription()
        del ds

        lyrR = QgsRasterLayer(enmap2)
        from qps.layerconfigwidgets.gdalmetadata import GDALBandMetadataModel
        bandModel = GDALBandMetadataModel()
        bandModel.setLayer(lyrR)

        self.assertEqual(bandModel.rowCount(), lyrR.bandCount())

        fm = QSortFilterProxyModel()
        fm.setSourceModel(bandModel)

        tv = QTableView()
        tv.setSortingEnabled(True)
        tv.setModel(fm)

        new_name = old_name + 'XYZ'
        changed = bandModel.setData(bandModel.index(0, 0), new_name, role=Qt.EditRole)
        self.assertTrue(changed)
        bandModel.applyToLayer()
        bandModel.syncToLayer()
        self.assertEqual(bandModel.data(bandModel.index(0, 0), role=Qt.DisplayRole), new_name)

        ds: gdal.Dataset = gdal.Open(enmap2)
        new_name2 = ds.GetRasterBand(1).GetDescription()
        del ds
        self.assertEqual(new_name, new_name2)

        self.showGui(tv)

    def test_GDALMetadataModel(self):
        from qpstestdata import landcover
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModel

        c = QgsMapCanvas()
        # lyr = QgsRasterLayer(enmap)
        lyr = QgsVectorLayer(landcover)
        model = GDALMetadataModel()
        model.setIsEditable(True)
        fm = QSortFilterProxyModel()
        fm.setSourceModel(model)

        tv = QTableView()
        tv.setSortingEnabled(True)
        tv.setModel(fm)
        model.setLayer(lyr)

        self.showGui(tv)

    def test_GDALMetadataModelItemWidget(self):

        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataItemDialog, GDALMetadataItem

        items = ['dataset', 'band1', 'band2']
        domains = ['Domains 1', 'domains2', 'MyDomain']
        d = GDALMetadataItemDialog(major_objects=items, domains=domains)
        d.setKey('MyKey')
        d.setValue('MyValue')
        d.setDomain('MyDomain')
        d.setMajorObject('band1')

        item = d.metadataItem()
        self.assertIsInstance(item, GDALMetadataItem)
        self.assertEqual(item.major_object, 'band1')
        self.assertEqual(item.domain, 'MyDomain')
        self.assertEqual(item.key, 'MyKey')
        self.assertEqual(item.value, 'MyValue')

        self.showGui(d)

    def test_GDALMetadataModelConfigWidget(self):
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget
        from qpstestdata import envi_bsq

        envi_bsq = self.createImageCopy(envi_bsq)

        lyrR = QgsRasterLayer(envi_bsq)

        canvas = QgsMapCanvas()
        w = GDALMetadataModelConfigWidget(lyrR, canvas)
        w.metadataModel.setIsEditable(True)
        w.widgetChanged.connect(lambda: print('Changed'))
        self.assertIsInstance(w, QWidget)

        QgsProject.instance().addMapLayer(w.mapLayer())
        canvas.setLayers([w.mapLayer()])
        canvas.mapSettings().setDestinationCrs(w.mapLayer().crs())
        canvas.zoomToFullExtent()
        btnApply = QPushButton('Apply')
        btnApply.clicked.connect(w.apply)
        btnZoom = QPushButton('Center')
        btnZoom.clicked.connect(canvas.zoomToFullExtent)
        btnReload = QPushButton('Reload')
        btnReload.clicked.connect(w.syncToLayer)
        cb = QgsRasterBandComboBox()
        cb.setLayer(w.mapLayer())

        gridLayout = QGridLayout()
        gridLayout.addWidget(btnApply, 0, 0)
        gridLayout.addWidget(btnReload, 0, 1)
        gridLayout.addWidget(btnZoom, 0, 2)
        gridLayout.addWidget(cb, 0, 3, 1, 2)
        gridLayout.addWidget(w, 1, 0, 2, 3)
        gridLayout.addWidget(canvas, 1, 4, 3, 2)
        m = QWidget()
        m.setLayout(gridLayout)

        if isinstance(w.mapLayer(), QgsVectorLayer):
            from qps.layerconfigwidgets.gdalmetadata import GDALMetadataItem
            item = GDALMetadataItem('DataSource', '', 'MyKey', 'MyValue')
            item.initialValue = ''
            w.metadataModel.addItem(item)

            item = GDALMetadataItem('DataSource', 'MyDomain', 'MyKey1', 'MyValue1')
            item.initialValue = ''
            w.metadataModel.addItem(item)

            item = GDALMetadataItem('Layer1', '', 'MyKey1', 'MyValue1')
            item.initialValue = ''
            w.metadataModel.addItem(item)

            item = GDALMetadataItem('Layer1', 'MyDomain', 'MyKey1', 'MyValue1')
            item.initialValue = ''
            w.metadataModel.addItem(item)

            w.apply()
        self.showGui(m)

    def test_gdalmetadata(self):

        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget, GDALMetadataConfigWidgetFactory

        lyrR = TestObjects.createRasterLayer(nb=100, eType=gdal.GDT_Byte)
        from qpstestdata import enmap
        lyrR = QgsRasterLayer(enmap)
        self.assertTrue(lyrR.isValid())
        lyrV = TestObjects.createVectorLayer()

        cR = self.canvasWithLayer(lyrR)
        cV = self.canvasWithLayer(lyrV)

        # no layer
        c = QgsMapCanvas()
        lyr = QgsRasterLayer()
        w = GDALMetadataModelConfigWidget(lyr, c)
        self.assertIsInstance(w, GDALMetadataModelConfigWidget)
        w = GDALMetadataModelConfigWidget(lyrR, cR)
        w.setLayer(lyrR)

        f = GDALMetadataConfigWidgetFactory()
        self.assertIsInstance(f, GDALMetadataConfigWidgetFactory)
        self.assertTrue(f.supportsLayer(lyrR))
        self.assertTrue(f.supportsLayer(lyrV))
        wR = f.createWidget(lyrR, cR, dockWidget=False)
        self.assertIsInstance(wR, GDALMetadataModelConfigWidget)
        self.assertTrue(wR.metadataModel.rowCount(None) > 0)
        wV = f.createWidget(lyrV, cV, dockWidget=False)
        self.assertTrue(wR.metadataModel.rowCount(None) > 0)
        self.assertIsInstance(wR, GDALMetadataModelConfigWidget)

        lyrC = TestObjects.createRasterLayer(nc=5)
        canvas = self.canvasWithLayer(lyrC)
        wC = f.createWidget(lyrC, canvas)

        self.showGui([w, wC])

    def test_vectorfieldmodels(self):

        lyr = TestObjects.createVectorLayer()
        v = QTableView()
        from qps.layerconfigwidgets.vectorlayerfields import LayerFieldsTableModel
        m = LayerFieldsTableModel()
        m.setLayer(lyr)
        v.setModel(m)

        self.assertTrue(lyr.startEditing())
        f = QgsField('newField', QVariant.String, 'String')
        lyr.addAttribute(f)
        self.assertTrue(lyr.commitChanges())
        self.showGui(v)


if __name__ == "__main__":

    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
