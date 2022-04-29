import datetime
import itertools
import os.path
import unittest

from osgeo import gdal, ogr

from qgis.PyQt.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsMapLayer
from qgis.gui import QgsMessageBar, QgsMapCanvas, QgsDualView, QgsRasterBandComboBox, QgsMapLayerComboBox
from qps import registerMapLayerConfigWidgetFactories
from qps.layerconfigwidgets.gdalmetadata import GDALBandMetadataModel, GDALMetadataItemDialog, GDALMetadataModel, \
    GDALMetadataModelConfigWidget
from qps.layerproperties import showLayerPropertiesDialog
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.testing import TestCase, TestObjects
from qpstestdata import enmap


class ControlWidget(QWidget):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.canvas = QgsMapCanvas()
        self.w = GDALMetadataModelConfigWidget(None, self.canvas)
        self.w.setEditable(False)
        self.w.widgetChanged.connect(lambda: print('Changed'))

        self.canvas.setLayers([self.w.mapLayer()])
        self.canvas.mapSettings().setDestinationCrs(self.w.mapLayer().crs())
        self.canvas.zoomToFullExtent()
        self.btnEdit = QPushButton('Edit')
        self.btnEdit.setCheckable(True)
        self.btnEdit.toggled.connect(self.w.setEditable)
        self.btnApply = QPushButton('Apply')
        self.btnApply.clicked.connect(self.w.apply)
        self.btnZoom = QPushButton('Center')
        self.btnZoom.clicked.connect(self.canvas.zoomToFullExtent)
        self.btnReload = QPushButton('Reload')
        self.btnReload.clicked.connect(self.w.syncToLayer)

        cb = QgsRasterBandComboBox()
        cb.setLayer(self.w.mapLayer())

        def onLayerChanged(layer):
            if isinstance(layer, QgsRasterLayer):
                cb.setLayer(layer)
            else:
                cb.setLayer(None)
            self.w.setLayer(layer)

        self.cbChangeLayer = QgsMapLayerComboBox()
        self.cbChangeLayer.layerChanged.connect(onLayerChanged)

        hl1 = QHBoxLayout()
        for widget in [self.btnEdit,
                       self.btnApply,
                       self.btnReload,
                       self.btnZoom,
                       self.cbChangeLayer, cb]:
            hl1.addWidget(widget)
        hl2 = QHBoxLayout()
        hl2.addWidget(self.w)
        hl2.addWidget(self.canvas)
        vl = QVBoxLayout()
        vl.addLayout(hl1)
        vl.addLayout(hl2)
        self.setLayout(vl)


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

    def test_GDAL_PAM(self):
        test_dir = self.createTestOutputDirectory(subdir='gdalmetadata_PAM')
        path = test_dir / 'example.tif'
        ds: gdal.Dataset = gdal.Translate(path.as_posix(), enmap)
        del ds

        lyr = QgsRasterLayer(path.as_posix())
        lyr2 = lyr.clone()
        self.assertTrue(lyr.isValid())
        ds: gdal.Dataset = gdal.Open(path.as_posix(), gdal.GA_Update)
        self.assertIsInstance(ds, gdal.Dataset)
        ds.SetMetadataItem('Example', 'foobar', 'MyDomain')
        band = ds.GetRasterBand(1)
        band.SetDescription('BAND_EXAMPLE')
        ds.FlushCache()
        del ds

    def test_GDALMetadataModelConfigWidget(self):
        from qpstestdata import envi_bsq, enmap_polygon

        envi_bsq = self.createImageCopy(envi_bsq)

        lyrR = QgsRasterLayer(envi_bsq, 'ENVI')
        lyrV = QgsVectorLayer(enmap_polygon, 'Vector')

        layers = [QgsRasterLayer(enmap, 'EnMAP'),
                  lyrR,
                  lyrV,
                  TestObjects.createRasterLayer(),
                  TestObjects.createSpectralLibrary(),
                  TestObjects.createSpectralLibrary(),
                  TestObjects.createRasterLayer(nc=3)]

        QgsProject.instance().addMapLayers(layers)

        W = ControlWidget()
        self.showGui(W)

    def test_rasterFormats(self):
        from qpstestdata import enmap
        properties = QgsRasterLayerSpectralProperties.fromRasterLayer(enmap)
        wl = properties.wavelengths()
        wlu = properties.wavelengthUnits()
        bbl = properties.badBands()
        fwhm = properties.fwhm()
        fwhm = [0.042 if n % 2 == 0 else 0.024 for n in range(len(fwhm))]
        files = []

        test_dir = self.createTestOutputDirectory(subdir='gdalmetadata')

        def create_vrt(name: str) -> gdal.Dataset:
            path = (test_dir / f'{name}.vrt').as_posix()
            assert path not in files, 'already created'
            files.append(path)
            ds = gdal.Translate(path, enmap)
            # clear existing metadata
            ds.SetMetadataItem('wavelength', None)
            ds.SetMetadataItem('wavelength_units', None)
            assert isinstance(ds, gdal.Dataset)
            return ds

        def set_metadata(ds: gdal.Dataset,
                         key: str,
                         values: list,
                         domain: str = None,
                         band_wise: bool = True):
            assert ds.RasterCount == len(values)
            if band_wise:
                for b in range(ds.RasterCount):
                    band: gdal.Band = ds.GetRasterBand(b + 1)
                    band.SetMetadataItem(key, str(values[b]), domain)
            else:
                value_string = '{' + ','.join([str(v) for v in values]) + '}'
                ds.SetMetadataItem(key, value_string, domain)

            ds.FlushCache()

        domains = [None, 'ENVI']
        band_wise = [False, True]

        for domain, bw in itertools.product(domains, band_wise):
            suffix = ''
            if domain:
                suffix += f'_{domain}'
            if bw:
                suffix += '_bandwise'
            else:
                suffix += '_dataset'
            kwds = dict(domain=domain, band_wise=bw)
            ds = create_vrt('all' + suffix)
            set_metadata(ds, 'wavelength', wl, **kwds)
            set_metadata(ds, 'wavelength_units', wlu, **kwds)
            set_metadata(ds, 'bbl', bbl, **kwds)
            set_metadata(ds, 'fwhm', fwhm, **kwds)

            ds = create_vrt('wl_only' + suffix)
            set_metadata(ds, 'wavelength', wl, **kwds)

            ds = create_vrt('wl_and_wlu' + suffix)
            set_metadata(ds, 'wavelength', wl, **kwds)
            set_metadata(ds, 'wavelength_units', wlu, **kwds)

            ds = create_vrt('wlu_only' + suffix)
            set_metadata(ds, 'wavelength_units', wlu, **kwds)

        ds = create_vrt('plain')
        files.append(enmap)

        layers = []
        for file in files:
            lyr = QgsRasterLayer(file, os.path.basename(file))
            self.assertTrue(lyr.isValid())
            layers.append(lyr)
        QgsProject.instance().addMapLayers(layers)

        w = ControlWidget()
        self.showGui(w)

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

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
    def test_speed(self):

        registerMapLayerConfigWidgetFactories()
        from enmapbox.exampledata import enmap as em
        layer = QgsRasterLayer(em, 'EnMAP')
        p = QgsProject()
        p.addMapLayer(layer)
        canvas = QgsMapCanvas()
        canvas.setLayers([layer])
        canvas.zoomToFullExtent()
        messageBar = QgsMessageBar()

        t0 = datetime.datetime.now()
        showLayerPropertiesDialog(layer, canvas=canvas, messageBar=messageBar, modal=True, useQGISDialog=False)
        dt = datetime.datetime.now() - t0
        print(dt)

    @unittest.skipIf(TestCase.runsInCI(), 'blocking dialog')
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
