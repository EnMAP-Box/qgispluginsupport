import itertools
import os.path
import pathlib
import re
import unittest
from pathlib import Path
from typing import List

import numpy as np
from osgeo import gdal, gdal_array, ogr

from qgis.PyQt.QtCore import QMimeData, QModelIndex, QUrl
from qgis.PyQt.QtWidgets import QAction, QApplication, QDialog, QHBoxLayout, QMenu, QPushButton, QVBoxLayout, QWidget
from qgis.core import edit, QgsFeature, QgsMapLayer, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.gui import QgsDualView, QgsMapCanvas, QgsMapLayerComboBox, QgsRasterBandComboBox
from qps.layerconfigwidgets.gdalmetadata import BandFieldNames, BandPropertyCalculator, GDALBandMetadataModel, \
    GDALMetadataItem, GDALMetadataItemDialog, GDALMetadataModel, GDALMetadataModelConfigWidget
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.testing import start_app, TestCase, TestObjects
from qpstestdata import enmap, enmap_polygon, envi_bsq

start_app()


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

        self.cbBands = QgsRasterBandComboBox()
        self.cbBands.setLayer(self.w.mapLayer())

        self.cbChangeLayer = QgsMapLayerComboBox()
        self.cbChangeLayer.layerChanged.connect(self.onLayerChanged)

        hl1 = QHBoxLayout()
        for widget in [self.btnEdit,
                       self.btnApply,
                       self.btnReload,
                       self.btnZoom,
                       self.cbChangeLayer,
                       self.cbBands]:
            hl1.addWidget(widget)
        hl2 = QHBoxLayout()
        hl2.addWidget(self.w)
        hl2.addWidget(self.canvas)
        vl = QVBoxLayout()
        vl.addLayout(hl1)
        vl.addLayout(hl2)
        self.setLayout(vl)

    def onLayerChanged(self, layer):
        if isinstance(layer, QgsRasterLayer):
            self.cbBands.setLayer(layer)
        else:
            self.cbBands.setLayer(None)
        self.w.setLayer(layer)


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

    def test_GDALBandMetadataModel_PAM(self):
        from qpstestdata import enmap
        img_path = self.createImageCopy(enmap)

        def read_aux_xml(path):
            path = pathlib.Path(path)
            aux_file = [f for f in gdal.Open(path.as_posix()).GetFileList() if f.endswith('.aux.xml')][0]
            with open(aux_file, 'r') as f:
                xml_string = f.read()
            return xml_string

        aux_xml1 = read_aux_xml(img_path)
        assert 'MYNAME_1' not in aux_xml1
        s = ""
        lyr = QgsRasterLayer(img_path)
        model = GDALBandMetadataModel()
        c = QgsMapCanvas()
        view = QgsDualView()
        view.init(model, c)
        model.setLayer(lyr)
        model.syncToLayer()
        model.startEditing()

        bandNames = []
        wavelLength = []
        for i, f in enumerate(list(model.getFeatures())):
            f: QgsFeature
            bandName = f'MYNAME_{i + 1}'
            wl = 500 + i + 1
            f.setAttribute(BandFieldNames.Name, bandName)
            f.setAttribute(BandFieldNames.Wavelength, wl)
            bandNames.append(bandName)
            wavelLength.append(wl)
            model.updateFeature(f)
        model.commitChanges(True)
        assert model.hasEdits
        model.applyToLayer()
        del model, lyr
        aux_xml2 = read_aux_xml(img_path)

        ds: gdal.Dataset = gdal.Open(img_path)
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            name1 = band.GetDescription()
            assert name1 == bandNames[b]
            assert float(band.GetMetadataItem('wavelength')) == float(wavelLength[b])

        self.showGui(view)

    def test_gdal_envi_header_comments(self):

        path = '/vsimem/test.bin'
        gdal_array.SaveArray(np.ones((3, 1, 1)), path, format='ENVI')
        ds: gdal.Dataset = gdal.Open(path, gdal.GA_Update)
        ds.SetMetadataItem('bbl', """{
        0,
        ; a comment to be excluded. See https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html
        1,
        0}""", 'ENVI')
        ds.FlushCache()
        files = ds.GetFileList()
        del ds

        # print ENVI hdr
        path_hdr = '/vsimem/test.hdr'
        fp = gdal.VSIFOpenL(path_hdr, "rb")
        content: str = gdal.VSIFReadL(1, gdal.VSIStatL(path_hdr).size, fp).decode("utf-8")
        gdal.VSIFCloseL(fp)

        # read BBL
        ds: gdal.Dataset = gdal.Open(path)
        bbl = ds.GetMetadataItem('bbl', 'ENVI')
        print(bbl)

        bbl2 = ds.GetMetadata_Dict('ENVI')['bbl']

    def test_QgsRasterLayer_GDAL_interaction(self):

        def readTextFile(path: str) -> str:
            fp = gdal.VSIFOpenL(path, "rb")
            content: str = gdal.VSIFReadL(1, gdal.VSIStatL(path).size, fp).decode("utf-8")
            gdal.VSIFCloseL(fp)
            return content

        def bandNames(dsrc) -> List[str]:
            if isinstance(dsrc, gdal.Dataset):
                return [dsrc.GetRasterBand(b + 1).GetDescription() for b in range(dsrc.RasterCount)]
            elif isinstance(dsrc, QgsRasterLayer):
                return [dsrc.bandName(b + 1) for b in range(dsrc.bandCount())]

        def setBandNames(dsrc: gdal.Dataset, names: List[str]):
            self.assertIsInstance(dsrc, gdal.Dataset)
            for b, n in enumerate(names):
                dsrc.GetRasterBand(b + 1).SetDescription(n)
            dsrc.FlushCache()

        path = '/vsimem/test.bin'
        ds0 = gdal_array.SaveArray(np.ones((3, 1, 1)), path, format='ENVI')
        path_hdr = [f for f in ds0.GetFileList() if f.endswith('.hdr')][0]

        self.assertIsInstance(ds0, gdal.Dataset)
        self.assertEqual(bandNames(ds0), ['', '', ''])

        lyr = QgsRasterLayer(path)
        self.assertTrue(lyr.isValid())
        self.assertEqual(bandNames(lyr), ['Band 1', 'Band 2', 'Band 3'])

        # 1. Write Band Names and the BBL
        # changing metadata will only be written to ENVI hdr if dataset is opened in update mode!
        ds: gdal.Dataset = gdal.Open(path, gdal.GA_Update)
        setBandNames(ds, ['A', 'B', 'C'])
        ds.SetMetadataItem('bbl', '{0,1,0}', 'ENVI')
        ds.SetMetadataItem('bbl false', '0,1,0', 'ENVI')
        ds.FlushCache()

        # print PAM
        path_pam = [f for f in ds0.GetFileList() if f.endswith('aux.xml')][0]
        content_pam = readTextFile(path_pam)
        print(content_pam)

        ds2: gdal.Dataset = gdal.Open(path, gdal.GA_ReadOnly)

        # Check band names in GDAL PAM
        self.assertEqual(bandNames(ds), ['A', 'B', 'C'])
        self.assertEqual(bandNames(ds2), ['A', 'B', 'C'])
        self.assertEqual(ds.GetMetadataItem('bbl', 'ENVI'), '{0,1,0}')
        self.assertEqual(ds2.GetMetadataItem('bbl', 'ENVI'), '{0,1,0}')

        # the original data set still points on old band names / MD values!
        self.assertEqual(bandNames(ds0), ['', '', ''])

        # same for QgsRasterLayer, which generates default names
        self.assertEqual(bandNames(lyr), ['Band 1', 'Band 2', 'Band 3'])
        # ... neither a .reload, nor a new layer help
        lyr.dataProvider().bandStatistics(1)
        lyr.reload()
        self.assertEqual(bandNames(lyr), ['Band 1', 'Band 2', 'Band 3'])
        self.assertEqual(bandNames(QgsRasterLayer(path)), ['Band 1', 'Band 2', 'Band 3'])

        # but overwriting the PAM helps
        gdal.FileFromMemBuffer(path_pam, '')
        lyr = QgsRasterLayer(path)
        self.assertEqual(bandNames(lyr), ['Band 1: A', 'Band 2: B', 'Band 3: C'])
        properties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        self.assertEqual(properties.badBands(), [0, 1, 0])
        # self.assertEqual(bandNames(lyr3), ['Band 1', 'Band 2', 'Band 3'])

        # Check ENVI hdr
        content_hdr = readTextFile(path_hdr)
        content_hdr = re.sub(r',\n', ', ', content_hdr)
        content_hdr = re.sub(r'\{\n', r'{', content_hdr)
        print(content_hdr)
        self.assertTrue('band names = {A, B, C}' in content_hdr)
        self.assertTrue('bbl = {0,1,0}' in content_hdr)

    @unittest.skipIf(gdal.VersionInfo() < '3060000', 'Requires GDAL 3.6+')
    def test_modify_metadata(self):
        nb, nl, ns = 5, 2, 2

        path = self.createTestOutputDirectory() / 'test.bsq'
        path = path.as_posix()

        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        ds: gdal.Dataset = drv.Create(path, ns, nl, nb, eType=gdal.GDT_Byte)

        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            band.Fill(b + 1)
            band.GetStatistics(1, 1)
            band.SetDescription(f'MyBand {b + 1}')
        ds.FlushCache()
        del band
        originalBandNames = [ds.GetRasterBand(b + 1).GetDescription() for b in range(nb)]

        path_hdr: str = [f for f in ds.GetFileList() if f.endswith('.hdr')][0]
        del ds

        def readHeader():
            fp = gdal.VSIFOpenL(path_hdr, "rb")
            hdr: str = gdal.VSIFReadL(1, gdal.VSIStatL(path_hdr).size, fp).decode("utf-8")
            gdal.VSIFCloseL(fp)
            return hdr

        lyr = QgsRasterLayer(path)
        self.assertTrue(lyr.isValid())

        bandModel = GDALBandMetadataModel()
        bandModel.setLayer(lyr)

        map1 = bandModel.asMap()
        # this model is a vector layer with fields for each supported band property
        self.assertIsInstance(bandModel, QgsVectorLayer)

        for feature in bandModel.getFeatures():
            feature: QgsFeature
            fid = feature.id()
            self.assertTrue(0 < fid <= nb)
            self.assertEqual(originalBandNames[fid - 1], feature.attribute(BandFieldNames.Name))

        modifiedBandNames = ['A', 'B', 'C', 'D', 'E']
        # modify band properties
        # set a band names
        self.assertFalse(bandModel.hasEdits)
        bandModel.commitChanges()
        with edit(bandModel):

            for b, name in enumerate(modifiedBandNames):
                f: QgsFeature = bandModel.getFeature(b + 1)
                f.setAttribute(BandFieldNames.Name, name)
                bandModel.updateFeature(f)

            # bandModel.changeAttributeValue(3, iField, 'Another Band Name')
        self.assertTrue(bandModel.hasEdits)
        bandModel.mMapLayer.reload()
        bandModel.applyToLayer()

        ds2: gdal.Dataset = gdal.Open(path)
        bandNames = [ds2.GetRasterBand(b + 1).GetDescription() for b in range(ds2.RasterCount)]

        self.assertListEqual(bandNames, modifiedBandNames)

        # hdr2 = readHeader()
        # bandModel.commitChanges()
        # self.assertTrue('My Band Name' not in hdr1)
        # self.assertTrue('My Band Name' in hdr2)

    def test_GDAL_PAM(self):
        test_dir = self.createTestOutputDirectory(subdir='gdalmetadata_PAM')
        path = test_dir / 'example.tif'
        ds: gdal.Dataset = gdal.Translate(path.as_posix(), enmap.as_posix())
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

    @unittest.skipIf(TestCase.runsInCI(), 'GUI dialog')
    def test_BandPropertyCalculator(self):
        from qps import registerExpressionFunctions
        registerExpressionFunctions()
        from qpstestdata import envi_bsq

        envi_bsq = self.createImageCopy(envi_bsq)
        lyr = QgsRasterLayer(envi_bsq)
        self.assertTrue(lyr.isValid())
        mdm = GDALBandMetadataModel()
        mdm.setLayer(lyr)

        w = QWidget()

        calc = BandPropertyCalculator(mdm)

        if calc.exec_() == QDialog.Accepted:
            pass

    def test_alpha_band(self):
        # relates to issue #159
        path = self.createTestOutputDirectory() / 'test.tif'
        ds = TestObjects.createRasterDataset(10, 10, 3, path=path)
        ds.CreateMaskBand(gdal.GMF_PER_DATASET)
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            band.Fill(b + 1)

        # Get the mask band
        # mask_band = ds.GetRasterBand(1).GetMaskBand()
        ds.FlushCache()
        lyr = QgsRasterLayer(path.as_posix(), 'test')
        assert lyr.bandCount() == ds.RasterCount + 1
        box = QgsRasterBandComboBox()
        box.setLayer(lyr)

        props = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        s = ""

        self.assertTrue(lyr.bandCount() == ds.RasterCount + 1)

        QgsProject.instance().addMapLayers([lyr])

        W = ControlWidget()
        W.onLayerChanged(lyr)
        self.showGui(W)
        QgsProject.instance().removeAllMapLayers()

    def test_GDALMetadataModelConfigWidget(self):

        envi_bsq2 = self.createImageCopy(envi_bsq)

        lyrR = QgsRasterLayer(envi_bsq2, 'ENVI')
        lyrV = QgsVectorLayer(enmap_polygon.as_posix(), 'Vector')

        layers = [QgsRasterLayer(enmap.as_posix(), 'EnMAP'),
                  lyrR,
                  lyrV,
                  TestObjects.createRasterLayer(),
                  TestObjects.createSpectralLibrary(),
                  TestObjects.createRasterLayer(nc=3)]

        QgsProject.instance().addMapLayers(layers)

        W = ControlWidget()
        self.showGui(W)
        QgsProject.instance().removeAllMapLayers()

    def test_rasterFormats(self):
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
            ds = gdal.Translate(path, enmap.as_posix())
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
            lyr = QgsRasterLayer(Path(file).as_posix(), os.path.basename(file))
            self.assertTrue(lyr.isValid())
            layers.append(lyr)
        QgsProject.instance().addMapLayers(layers)

        w = ControlWidget()
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    def test_GDALBandMetadataModelContextMenus(self):
        from qpstestdata import enmap
        from qpstestdata import envi_hdr

        with open(envi_hdr) as f:
            hdr = f.read()

        img_path = self.createImageCopy(enmap)
        lyr = QgsRasterLayer(img_path)
        model = GDALBandMetadataModel()
        c = QgsMapCanvas()
        view = QgsDualView()
        view.init(model, c)
        model.setLayer(lyr)
        model.syncToLayer()
        model.startEditing()

        md1: QMimeData = QMimeData()
        md1.setText(hdr)

        md2: QMimeData = QMimeData()
        md2.setUrls([QUrl.fromLocalFile(envi_hdr.as_posix())])

        md3: QMimeData = QMimeData()
        md3.setUrls([QUrl.fromLocalFile(r'C:/NoneExisting')])

        md4: QMimeData = QMimeData()
        md4.setUrls([QUrl.fromLocalFile(
            r'Q:\EnMAP\Rohdaten\EnmapBoxExternalSensorProducts\planet\Valencia_psscene_analytic_8b_sr_udm2\PSScene\20240403_105501_25_24cd.json')])

        for mimeData in [md1, md2, md3]:
            QApplication.clipboard().setMimeData(mimeData)
            md = model.bandMetadataFromMimeData(QApplication.clipboard().mimeData())
            self.assertIsInstance(md, dict)
            if len(md) > 0:
                self.assertTrue(BandFieldNames.WavelengthUnit in md)
                self.assertTrue(BandFieldNames.Wavelength in md)

        menu1 = QMenu()
        model.onWillShowBandContextMenu(menu1, QModelIndex())
        for a in menu1.findChildren(QAction):
            a: QAction
            if a.isEnabled():
                print(f'Trigger "{a.text()}"')
                a.trigger()

        mimeData: QMimeData = QMimeData()
        mimeData.setText(hdr)
        QApplication.clipboard().setMimeData(mimeData)
        menu2 = QMenu()
        model.onWillShowBandContextMenu(menu2, QModelIndex())

        model.pasteBandMetadata()

    def test_GDALMetadataModel(self):

        layers = [TestObjects.createVectorLayer(),
                  QgsRasterLayer(self.createImageCopy(enmap)),
                  TestObjects.createRasterLayer(),
                  TestObjects.createSpectralLibrary()
                  ]

        for lyr in layers:
            self.assertIsInstance(lyr, QgsMapLayer)
            model = GDALMetadataModel()
            model.setLayer(lyr)
            model.startEditing()
            model.syncToLayer()
            model.applyToLayer()

            items = []
            for o in model.majorObjects():
                item = GDALMetadataItem(o, domain='mydomain', value='myvalue', key='mykey')
                item.initialValue = None
                items.append(item)
                model.appendMetadataItem(item)

            try:
                model.applyToLayer()
                model.syncToLayer()
            except Exception as ex:
                s = ""
            if isinstance(lyr, QgsRasterLayer):
                existing = [str(f) for f in model.mFeatures]
                for f in items:
                    self.assertTrue(str(f) in existing, msg=f'Failed to save: {f} to {lyr.source()}')

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


if __name__ == "__main__":
    unittest.main(buffer=False)
