# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest
import time
import tempfile
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from osgeo import gdal, ogr, osr
from qps.testing import TestObjects, TestCase, StartOptions, initQtResources
from qps.layerproperties import *
from qps import registerMapLayerConfigWidgetFactories
LAYER_WIDGET_REPS = 5


class LayerConfigWidgetsTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.EditorWidgets, resources=[]) -> None:
        super(LayerConfigWidgetsTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        initQtResources()

    def canvasWithLayer(self, lyr)->QgsMapCanvas:
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

    def test_symbology(self):
        from qps.layerconfigwidgets.core import SymbologyConfigWidget, SymbologyConfigWidgetFactory
        lyrR = TestObjects.createRasterLayer(nb=100)
        lyrV = TestObjects.createVectorLayer()
        c = QgsMapCanvas()

        f = SymbologyConfigWidgetFactory()
        style_file = (pathlib.Path(tempfile.gettempdir()) / 'stylefile.qml').as_posix()
        for lyr in [lyrV]:
            c.setLayers([lyr])
            c.setDestinationCrs(lyr.crs())
            c.setExtent(lyr.extent())
            self.assertTrue(f.supportsLayer(lyr))
            w = f.createWidget(lyr, c)
            w.show()
            self.assertIsInstance(w, SymbologyConfigWidget)
            w.apply()

            if isinstance(lyr, QgsRasterLayer):
                l2 = TestObjects.createRasterLayer(nb=1)
                r2 = l2.renderer().clone()
                r2.setInput(lyr.dataProvider())
                lyr.setRenderer(r2)
            w.syncToLayer()
            w.saveStyleAsDefault()
            w.loadDefaultStyle()
            w.saveStyle(style_file)
            w.loadStyle(style_file)

            self.showGui([c, w])
        pass

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
                self.assertTrue(w.labeling() == None)
                w.apply()
                self.assertFalse(lyrV.labelsEnabled())
                self.assertEqual(lyrV.labeling(), None)
            else:
                if not w.labeling() is None:
                    self.assertIsInstance(w.labeling(), QgsAbstractVectorLayerLabeling)
                    w.apply()
                    self.assertTrue(lyrV.labelsEnabled())
                    self.assertEquals(type(lyrV.labeling()), type(w.labeling()))

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


        w  = QWidget()
        l = QVBoxLayout()
        lh = QHBoxLayout()
        lh.addWidget(btnApply)
        lh.addWidget(btnSync)
        l.addLayout(lh)
        l.addWidget(w1)
        w.setLayout(l)
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


    def test_legend(self):
        pass

    #

    def test_rasterbandselection2(self):
        from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget, RasterBandConfigWidgetFactory

        from qpstestdata import timestack
        lyrR = QgsRasterLayer(timestack)
        cR = self.canvasWithLayer(lyrR)

        f = RasterBandConfigWidgetFactory()
        self.assertIsInstance(f, QgsMapLayerConfigWidgetFactory)
        self.assertTrue(f.supportsLayer(lyrR))
        w = f.createWidget(lyrR, cR, dockWidget=False)
        self.assertIsInstance(w, RasterBandConfigWidget)

        self.showGui([cR, w])


    def test_rasterbandselection(self):
        from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidget, RasterBandConfigWidgetFactory

        from qpstestdata import enmap
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
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget, GDALMetadataConfigWidgetFactory
        cb= QgsMapLayerComboBox()
        c = QgsMapCanvas()
        md = GDALMetadataModelConfigWidget()
        cb.layerChanged.connect(md.setLayer)
        l = QVBoxLayout()
        l.addWidget(cb)
        l.addWidget(md)
        w = QWidget()
        w.setLayout(l)
        self.showGui(w)

    def test_GDALBandNameModel(self):

        from qpstestdata import enmap
        path = enmap

        ds:gdal.Dataset = gdal.Open(path)
        old_name = ds.GetRasterBand(1).GetDescription()
        del ds

        lyrR = QgsRasterLayer(path)
        from qps.layerconfigwidgets.gdalmetadata import GDALBandNameModel
        model = GDALBandNameModel()
        model.setLayer(lyrR)

        self.assertEqual(model.rowCount(), lyrR.bandCount())

        fm = QSortFilterProxyModel()
        fm.setSourceModel(model)

        tv = QTableView()
        tv.setSortingEnabled(True)
        tv.setModel(fm)

        new_name = old_name + 'XYZ'
        changed = model.setData(model.index(0, 1), new_name, role=Qt.EditRole)
        self.assertTrue(changed)
        model.applyToLayer()
        model.syncToLayer()
        self.assertEqual(model.data(model.index(0, 1), role=Qt.DisplayRole), new_name)

        ds: gdal.Dataset = gdal.Open(path)
        new_name2 = ds.GetRasterBand(1).GetDescription()
        del ds
        self.assertEqual(new_name, new_name2)


        self.showGui(tv)


    def test_GDALMetadataModel(self):
        from qpstestdata import enmap, landcover
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModel

        c = QgsMapCanvas()
        lyr = QgsRasterLayer(enmap)
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
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget, GDALMetadataConfigWidgetFactory
        from qpstestdata import enmap, landcover

        lyrR = QgsRasterLayer(enmap)
        lyrV = QgsVectorLayer(landcover)
        canvas = QgsMapCanvas()
        w = GDALMetadataModelConfigWidget(lyrV, canvas)
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

        l = QGridLayout()
        l.addWidget(btnApply, 0, 0)
        l.addWidget(btnReload, 0, 1)
        l.addWidget(btnZoom, 0, 2)
        l.addWidget(cb, 0, 3, 1, 2)
        l.addWidget(w, 1, 0, 2, 3)
        l.addWidget(canvas, 1, 4, 3, 2)
        m = QWidget()
        m.setLayout(l)

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
        l = QgsRasterLayer()
        w = GDALMetadataModelConfigWidget(l, c)
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
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)

