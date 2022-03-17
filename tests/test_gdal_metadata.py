from osgeo import gdal, ogr

from qgis.PyQt.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsMapLayer
from qgis.gui import QgsMapCanvas, QgsDualView, QgsRasterBandComboBox, QgsMapLayerComboBox
from qps.layerconfigwidgets.gdalmetadata import GDALBandMetadataModel, GDALMetadataItemDialog, GDALMetadataModel
from qps.testing import TestCase, TestObjects
from qpstestdata import enmap


class TestsGdalMetadata(TestCase):

    def test_GDALBandMetadataModel(self):
        from qpstestdata import enmap
        img_path = self.createImageCopy(enmap)
        lyr = QgsRasterLayer(img_path)
        model2 = GDALBandMetadataModel()
        c = QgsMapCanvas()
        view = QgsDualView()
        view.init(model2, c)
        model2.setLayer(lyr)
        model2.syncToLayer()
        model2.startEditing()
        model2.applyToLayer()
        self.showGui(view)

    def test_GDALMetadataModelConfigWidget(self):
        from qps.layerconfigwidgets.gdalmetadata import GDALMetadataModelConfigWidget
        from qpstestdata import envi_bsq, enmap_polygon

        envi_bsq = self.createImageCopy(envi_bsq)

        lyrR = QgsRasterLayer(envi_bsq, 'ENVI')
        lyrV = QgsVectorLayer(enmap_polygon, 'Vector')

        layers = [QgsRasterLayer(enmap, 'EnMAP'),
                  lyrR,
                  lyrV,
                  TestObjects.createRasterLayer(),
                  TestObjects.createSpectralLibrary(),
                  TestObjects.createSpectralLibrary()]

        canvas = QgsMapCanvas()
        w = GDALMetadataModelConfigWidget(lyrR, canvas)
        w.setEditable(True)
        w.widgetChanged.connect(lambda: print('Changed'))
        self.assertIsInstance(w, QWidget)

        QgsProject.instance().addMapLayer(w.mapLayer())
        canvas.setLayers([w.mapLayer()])
        canvas.mapSettings().setDestinationCrs(w.mapLayer().crs())
        canvas.zoomToFullExtent()
        btnEdit = QPushButton('Edit')
        btnEdit.setCheckable(True)
        btnEdit.toggled.connect(w.setEditable)
        btnApply = QPushButton('Apply')
        btnApply.clicked.connect(w.apply)
        btnZoom = QPushButton('Center')
        btnZoom.clicked.connect(canvas.zoomToFullExtent)
        btnReload = QPushButton('Reload')
        btnReload.clicked.connect(w.syncToLayer)

        QgsProject.instance().addMapLayers(layers)

        cb = QgsRasterBandComboBox()
        cb.setLayer(w.mapLayer())

        def onLayerChanged(layer):
            if isinstance(layer, QgsRasterLayer):
                cb.setLayer(layer)
            else:
                cb.setLayer(None)
            w.setLayer(layer)

        cbChangeLayer = QgsMapLayerComboBox()
        cbChangeLayer.layerChanged.connect(onLayerChanged)

        hl1 = QHBoxLayout()
        for widget in [btnEdit, btnApply, btnReload, btnZoom, cbChangeLayer, cb]:
            hl1.addWidget(widget)
        hl2 = QHBoxLayout()
        hl2.addWidget(w)
        hl2.addWidget(canvas)
        vl = QVBoxLayout()
        vl.addLayout(hl1)
        vl.addLayout(hl2)
        m = QWidget()
        m.setLayout(vl)

        self.showGui(m)

    def test_GDALMetadataModel(self):

        layers = [QgsRasterLayer(self.createImageCopy(enmap)),
                  TestObjects.createRasterLayer(),
                  TestObjects.createVectorLayer(),
                  TestObjects.createSpectralLibrary()
                  ]
        for lyr in layers:
            self.assertIsInstance(lyr, QgsMapLayer)
            model = GDALMetadataModel()
            model.setLayer(lyr)
            model.startEditing()
            model.syncToLayer()
            model.applyToLayer()

    def test_GDALMetadataModelItemWidget(self):

        majorObjects = [gdal.Dataset.__name__,
                        f'{gdal.Band.__name__}_1',
                        ogr.DataSource.__name__,
                        f'{ogr.Layer.__name__}_1',
                        f'{ogr.Layer.__name__}_layername',
                        ]
        domains = ['Domains 1', 'domains2']
        d = GDALMetadataItemDialog(major_objects=majorObjects,
                                   domains=domains)
        d.setKey('MyKey')
        d.setValue('MyValue')
        d.setDomain('MyDomain')
        for mo in majorObjects:
            self.assertTrue(d.setMajorObject(mo))

        self.showGui(d)
