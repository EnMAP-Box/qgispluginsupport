# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 3 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import typing
import unittest

import xmlrunner
from osgeo import gdal

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget, QTableView, QPushButton, QHBoxLayout
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsField, QgsAbstractVectorLayerLabeling
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsMapLayerComboBox, QgsRasterTransparencyWidget, \
    QgsMapLayerConfigWidgetFactory
from qps.layerconfigwidgets.gdalmetadata import RX_OGR_URI
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

    def test_rx_ogr_uri(self):

        match = RX_OGR_URI.search('qps/testvectordata.kml|layername=landcover|layerid=3')
        self.assertIsInstance(match, typing.Match)
        D = match.groupdict()
        self.assertEqual(D.get('path'), 'qps/testvectordata.kml')
        self.assertEqual(D.get('layername'), 'landcover')
        self.assertEqual(D.get('layerid'), '3')

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
