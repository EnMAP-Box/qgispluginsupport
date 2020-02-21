# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    layerproperties.py
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


import collections
import os
import re
import typing, enum
from osgeo import gdal, ogr, osr
import numpy as np
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtXml import QDomDocument
from . import DIR_UI_FILES
from .utils import *
from .models import OptionListModel, Option
from .classification.classificationscheme import ClassificationScheme, ClassInfo

"""
class RasterLayerProperties(QgsOptionsDialogBase):
    def __init__(self, lyr, canvas, parent, fl=Qt.Widget):
        super(RasterLayerProperties, self).__init__("RasterLayerProperties", parent, fl)
        # self.setupUi(self)
        self.initOptionsBase(False)
        title = "Layer Properties - {}".format(lyr.name())
        self.restoreOptionsBaseUi(title)
"""


"""
    RASTERRENDERER_CREATE_FUNCTIONS['multibandcolor'] = MultiBandColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['multibandcolor (QGIS)'] = QgsMultiBandColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['paletted'] = 
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandgray'] = 
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandgray (QGIS)'] = QgsSingleBandGrayRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandpseudocolor'] = SingleBandPseudoColorRendererWidget.create
    RASTERRENDERER_CREATE_FUNCTIONS['singlebandpseudocolor (QGIS)'] = QgsSingleBandPseudoColorRendererWidget.create
"""

RENDER_CLASSES = {}
RENDER_CLASSES['rasterrenderer'] = {
    'singlebandpseudocolor':QgsSingleBandPseudoColorRenderer,
    'singlebandgray': QgsSingleBandGrayRenderer,
    'paletted':QgsPalettedRasterRenderer,
    'multibandcolor': QgsMultiBandColorRenderer,
    'hillshade': QgsHillshadeRenderer
}
RENDER_CLASSES['renderer-v2'] = {
    'categorizedSymbol':QgsCategorizedSymbolRenderer,
    'singleSymbol':QgsSingleSymbolRenderer
}
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)


MDF_QGIS_LAYER_STYLE = 'application/qgis.style'
MDF_TEXT_PLAIN = 'text/plain'

def openRasterLayerSilent(uri, name, provider)->QgsRasterLayer:
    """
    Opens a QgsRasterLayer without asking for its CRS in case it is undefined.
    :param uri: path
    :param name: name of layer
    :param provider: provider string
    :return: QgsRasterLayer
    """
    key = '/Projections/defaultBehavior'
    v = QgsSettings().value(key)
    isPrompt = v == 'prompt'

    if isPrompt:
        # do not ask!
        QgsSettings().setValue(key, 'useProject')

    loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
    lyr = QgsRasterLayer(uri, name, provider, options=loptions)

    if isPrompt:
        QgsSettings().setValue(key, v)
    return lyr


def rendererFromXml(xml):
    """
    Reads a string `text` and returns the first QgsRasterRenderer or QgsFeatureRenderer (if defined).
    :param xml: QMimeData | QDomDocument
    :return:
    """

    if isinstance(xml, QMimeData):
        for format in [MDF_QGIS_LAYER_STYLE, MDF_TEXT_PLAIN]:
        #for format in ['application/qgis.style', 'text/plain']:
            if format in xml.formats():
                dom  = QDomDocument()
                dom.setContent(xml.data(format))
                return rendererFromXml(dom)
        return None

    elif isinstance(xml, str):
        dom = QDomDocument()
        dom.setContent(xml)
        return rendererFromXml(dom)

    assert isinstance(xml, QDomDocument)
    root = xml.documentElement()
    for baseClass, renderClasses in RENDER_CLASSES.items():
        elements = root.elementsByTagName(baseClass)
        if elements.count() > 0:
            elem = elements.item(0).toElement()
            typeName = elem.attributes().namedItem('type').nodeValue()
            if typeName in renderClasses.keys():
                rClass = renderClasses[typeName]
                if baseClass == 'rasterrenderer':

                    return rClass.create(elem, DUMMY_RASTERINTERFACE)
                elif baseClass == 'renderer-v2':
                    context = QgsReadWriteContext()
                    return rClass.load(elem, context)
            else:
                #print(typeName)
                s =""
    return None

def defaultRasterRenderer(layer:QgsRasterLayer, bandIndices:list=None, sampleSize:int=256)->QgsRasterRenderer:
    """
    Returns a default Raster Renderer.
    See https://bitbucket.org/hu-geomatics/enmap-box/issues/166/default-raster-visualization
    :param layer: QgsRasterLayer
    :return: QgsRasterRenderer
    """
    assert isinstance(sampleSize, int) and sampleSize > 0
    renderer = None

    if not isinstance(layer, QgsRasterLayer):
        return None

    defaultRenderer = layer.renderer()

    nb = layer.bandCount()

    if isinstance(bandIndices, list):
        bandIndices = [b for b in bandIndices if b >=0 and b < nb]
        l = len(bandIndices)
        if l == 0:
            bandIndices = None
        if l >= 3:
            bandIndices = bandIndices[0:3]
        elif l < 3:
            bandIndices = bandIndices[0:1]

    if not isinstance(bandIndices, list):
        if nb >= 3:

            if isinstance(defaultRenderer, QgsMultiBandColorRenderer):
                bandIndices = defaultBands(layer)
            else:
                bandIndices = [2, 1, 0]
        else:
            bandIndices = [0]

    assert isinstance(bandIndices, list)

    # get band stats
    bandStats = [layer.dataProvider().bandStatistics(b + 1, stats=QgsRasterBandStats.Min | QgsRasterBandStats.Max, sampleSize=sampleSize) for b in bandIndices]
    dp = layer.dataProvider()
    assert isinstance(dp, QgsRasterDataProvider)

    # classification ? -> QgsPalettedRasterRenderer
    classes = ClassificationScheme.fromMapLayer(layer)
    if isinstance(classes, ClassificationScheme):
        r = classes.rasterRenderer(band=bandIndices[0] + 1)
        r.setInput(layer.dataProvider())
        return r

    # single-band / two bands -> QgsSingleBandGrayRenderer
    if len(bandStats) < 3:
        b = bandIndices[0]+1
        stats = bandStats[0]
        assert isinstance(stats, QgsRasterBandStats)
        dt = dp.dataType(b)
        ce = QgsContrastEnhancement(dt)

        assert isinstance(ce, QgsContrastEnhancement)
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)

        if dt == Qgis.Byte:
            if stats.minimumValue == 0 and stats.maximumValue == 1:
                # handle mask, stretch over larger range
                ce.setMinimumValue(stats.minimumValue)
                ce.setMaximumValue(stats.maximumValue)
            else:
                ce.setMinimumValue(0)
                ce.setMaximumValue(255)
        else:
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            ce.setMinimumValue(vmin)
            ce.setMaximumValue(vmax)

        r = QgsSingleBandGrayRenderer(layer.dataProvider(), b)
        r.setContrastEnhancement(ce)
        return r

    # 3 or more bands -> RGB
    if len(bandStats) >= 3:
        bands = [b+1 for b in bandIndices[0:3]]
        contrastEnhancements = [QgsContrastEnhancement(dp.dataType(b)) for b in bands]
        ceR, ceG, ceB = contrastEnhancements

        for i, b in enumerate(bands):
            dt = dp.dataType(b)
            ce = contrastEnhancements[i]

            assert isinstance(ce, QgsContrastEnhancement)
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            if dt == Qgis.Byte:
                #standard RGB photo?
                if False and layer.bandCount() == 3:
                    ce.setMinimumValue(0)
                    ce.setMaximumValue(255)
                else:
                    ce.setMinimumValue(vmin)
                    ce.setMaximumValue(vmax)
            else:
                ce.setMinimumValue(vmin)
                ce.setMaximumValue(vmax)
        R, G, B = bands
        r = QgsMultiBandColorRenderer(layer.dataProvider(), R,G,B, None, None, None)
        r.setRedContrastEnhancement(ceR)
        r.setGreenContrastEnhancement(ceG)
        r.setBlueContrastEnhancement(ceB)
        r.setRedBand(R)
        r.setGreenBand(G)
        r.setBlueBand(B)
        return r
    if nb >= 3:
        pass

    return defaultRenderer


def rendererToXml(layerOrRenderer, geomType:QgsWkbTypes=None):
    """
    Returns a renderer XML representation
    :param layerOrRenderer: QgsRasterRender | QgsFeatureRenderer
    :return: QDomDocument
    """
    doc = QDomDocument()
    err = ''
    if isinstance(layerOrRenderer, QgsRasterLayer):
        return rendererToXml(layerOrRenderer.renderer())
    elif isinstance(layerOrRenderer, QgsVectorLayer):
        geomType = layerOrRenderer.geometryType()
        return rendererToXml(layerOrRenderer.renderer(), geomType=geomType)
    elif isinstance(layerOrRenderer, QgsRasterRenderer):
        #create a dummy raster layer
        import uuid
        xml = """<VRTDataset rasterXSize="1" rasterYSize="1">
                  <GeoTransform>  0.0000000000000000e+00,  1.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00,  0.0000000000000000e+00, -1.0000000000000000e+00</GeoTransform>
                  <VRTRasterBand dataType="Float32" band="1">
                    <Metadata>
                      <MDI key="STATISTICS_MAXIMUM">0</MDI>
                      <MDI key="STATISTICS_MEAN">0</MDI>
                      <MDI key="STATISTICS_MINIMUM">0</MDI>
                      <MDI key="STATISTICS_STDDEV">0</MDI>
                    </Metadata>
                    <Description>Band 1</Description>
                    <Histograms>
                      <HistItem>
                        <HistMin>0</HistMin>
                        <HistMax>0</HistMax>
                        <BucketCount>1</BucketCount>
                        <IncludeOutOfRange>0</IncludeOutOfRange>
                        <Approximate>0</Approximate>
                        <HistCounts>0</HistCounts>
                      </HistItem>
                    </Histograms>
                  </VRTRasterBand>
                </VRTDataset>
                """
        path = '/vsimem/{}.vrt'.format(uuid.uuid4())
        drv = gdal.GetDriverByName('VRT')
        assert isinstance(drv, gdal.Driver)
        write_vsimem(path, xml)
        ds = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        ds.FlushCache()
        lyr = QgsRasterLayer(path)
        assert lyr.isValid()
        lyr.setRenderer(layerOrRenderer.clone())
        err = lyr.exportNamedStyle(doc)
        #remove dummy raster layer
        lyr = None
        drv.Delete(path)

    elif isinstance(layerOrRenderer, QgsFeatureRenderer) and geomType is not None:
        #todo: distinguish vector type from requested renderer
        typeName = QgsWkbTypes.geometryDisplayString(geomType)
        lyr = QgsVectorLayer('{}?crs=epsg:4326&field=id:integer'.format(typeName), 'dummy', 'memory')
        lyr.setRenderer(layerOrRenderer.clone())
        err = lyr.exportNamedStyle(doc)
        lyr = None
    else:
        raise NotImplementedError()


    return doc

def pasteStyleToClipboard(layer: QgsMapLayer):

    xml = rendererToXml(layer)
    if isinstance(xml, QDomDocument):
        md = QMimeData()
        # ['application/qgis.style', 'text/plain']

        md.setData('application/qgis.style', xml.toByteArray())
        md.setData('text/plain', xml.toByteArray())
        QApplication.clipboard().setMimeData(md)

def pasteStyleFromClipboard(layer:QgsMapLayer):
    mimeData = QApplication.clipboard().mimeData()
    renderer = rendererFromXml(mimeData)
    if isinstance(renderer, QgsRasterRenderer) and isinstance(layer, QgsRasterLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    elif isinstance(renderer, QgsFeatureRenderer) and isinstance(layer, QgsVectorLayer):
        layer.setRenderer(renderer)
        layer.triggerRepaint()


def subLayerDefinitions(mapLayer:QgsMapLayer)->typing.List[QgsSublayersDialog.LayerDefinition]:
    """

    :param mapLayer:QgsMapLayer
    :return: list of sublayer definitions
    """
    definitions = []
    dp = mapLayer.dataProvider()

    subLayers = dp.subLayers()
    if len(subLayers) == 0:
        return []

    for i, sub in enumerate(subLayers):
        ldef = QgsSublayersDialog.LayerDefinition()
        assert isinstance(ldef, QgsSublayersDialog.LayerDefinition)
        elements = sub.split(QgsDataProvider.SUBLAYER_SEPARATOR)


        if dp.name() == 'ogr':
            # <layer_index>:<name>:<feature_count>:<geom_type>
            if len(elements) < 4:
                continue

            ldef.layerId = int(elements[0])
            ldef.layerName = elements[1]
            ldef.count = int(elements[2])
            ldef.type = elements[3]

            definitions.append(ldef)

        elif dp.name() == 'gdal':
            ldef.layerId = i

            # remove driver name and file name
            name = elements[0]
            name = name.replace(mapLayer.source(), '')
            name = re.sub('^(netcdf|hdf):', '', name, flags=re.I)
            name = re.sub('^[:"]+', '', name)
            name = re.sub('[:"]+$', '', name)
            ldef.layerName = name

            definitions.append(ldef)

        else:
            s = ""

    return definitions

def subLayers(mapLayer:QgsMapLayer, subLayers:list=None)->typing.List[QgsMapLayer]:
    """
    Returns a list of QgsMapLayer instances extracted from the input QgsMapLayer.
    Returns the "parent" QgsMapLayer in case no sublayers can be extracted
    :param mapLayer: QgsMapLayer
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    dp = mapLayer.dataProvider()


    uriParts = QgsProviderRegistry.instance().decodeUri(mapLayer.providerType(), mapLayer.dataProvider().dataSourceUri())
    uri = uriParts['path']
    if subLayers is None:
        ldefs = subLayerDefinitions(mapLayer)
    else:
        ldefs = subLayers

    if len(ldefs) == 0:
        layers = [mapLayer]
    else:
        uniqueNames = len(set([d.layerName for d in ldefs])) == len(ldefs)
        options = QgsProject.instance().transformContext()
        options.loadDefaultStyle = False

        fileName = os.path.basename(uri)

        if dp.name() == 'ogr':

            for ldef in ldefs:
                assert isinstance(ldef, QgsSublayersDialog.LayerDefinition)
                if uniqueNames:
                    composedURI = '{}|layername={}'.format(uri, ldef.layerName)
                else:
                    composedURI = '{}|layerid={}'.format(uri, ldef.layerId)

                name = '{} {}'.format(fileName, ldef.layerName)

                lyr = QgsVectorLayer(composedURI, name, dp.name())
                layers.append(lyr)

        elif dp.name() == 'gdal':
            subLayers = dp.subLayers()
            for ldef in ldefs:
                name = '{} {}'.format(fileName, ldef.layerName)
                lyr = QgsRasterLayer(subLayers[ldef.layerId], name, dp.name())
                layers.append(lyr)

        else:
            layers.append(mapLayer)

    return layers



class RasterBandConfigWidget(QgsMapLayerConfigWidget):

    @staticmethod
    def icon()->QIcon:
        return QIcon(':/qps/ui/icons/rasterband_select.svg')

    def __init__(self, layer:QgsRasterLayer, canvas:QgsMapCanvas, parent:QWidget=None):

        super(RasterBandConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'rasterbandconfigwidget.ui'
        loadUi(pathUi, self)
        assert isinstance(layer, QgsRasterLayer)
        self.mCanvas = canvas
        self.mLayer = layer
        self.mLayer.rendererChanged.connect(self.syncToLayer)
        assert isinstance(self.cbSingleBand, QgsRasterBandComboBox)

        self.cbSingleBand.setLayer(self.mLayer)
        self.cbMultiBandRed.setLayer(self.mLayer)
        self.cbMultiBandGreen.setLayer(self.mLayer)
        self.cbMultiBandBlue.setLayer(self.mLayer)

        self.cbSingleBand.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandRed.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandGreen.bandChanged.connect(self.widgetChanged)
        self.cbMultiBandBlue.bandChanged.connect(self.widgetChanged)


        assert isinstance(self.sliderSingleBand, QSlider)
        self.sliderSingleBand.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandRed.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandGreen.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandBlue.setRange(1, self.mLayer.bandCount())

        mWL, mWLUnit = parseWavelength(self.mLayer)
        if isinstance(mWL, list):
            mWL = np.asarray(mWL)

        if isinstance(mWLUnit, str) and mWLUnit != 'nm':
            try:
                # convert to nanometers
                mWL = np.asarray([convertMetricUnit(v, mWLUnit, 'nm') for v in mWL])
            except:
                mWL = None
                mWLUnit = None

        self.mWL = mWL
        self.mWLUnit = mWLUnit

        hasWL = self.mWL is not None
        self.gbMultiBandWavelength.setEnabled(hasWL)
        self.gbSingleBandWavelength.setEnabled(hasWL)

        self.btnSetSBBand_B.clicked.connect(lambda : self.setWL(('B',)))
        self.btnSetSBBand_G.clicked.connect(lambda: self.setWL(('G',)))
        self.btnSetSBBand_R.clicked.connect(lambda: self.setWL(('R',)))
        self.btnSetSBBand_NIR.clicked.connect(lambda: self.setWL(('NIR',)))
        self.btnSetSBBand_SWIR.clicked.connect(lambda: self.setWL(('SWIR',)))

        self.btnSetMBBands_RGB.clicked.connect(lambda : self.setWL(('R', 'G', 'B')))
        self.btnSetMBBands_NIRRG.clicked.connect(lambda: self.setWL(('NIR', 'R', 'G')))
        self.btnSetMBBands_SWIRNIRR.clicked.connect(lambda: self.setWL(('SWIR', 'NIR', 'R')))

        self.syncToLayer()

        self.setPanelTitle('Band Selection')

    def syncToLayer(self):

        renderer = self.mLayer.renderer()
        self.setRenderer(renderer)

    def renderer(self)->QgsRasterRenderer:
        oldRenderer = self.mLayer.renderer()
        if isinstance(oldRenderer, QgsSingleBandGrayRenderer):
            newRenderer = self.renderer().clone()
            newRenderer.setGrayBand(self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsSingleBandPseudoColorRenderer):
            # there is a bug when using the QgsSingleBandPseudoColorRenderer.setBand()
            # see https://github.com/qgis/QGIS/issues/31568
            # band = self.cbSingleBand.currentBand()
            vMin, vMax = oldRenderer.shader().minimumValue(), oldRenderer.shader().maximumValue()
            shader = QgsRasterShader(vMin, vMax)

            f = oldRenderer.shader().rasterShaderFunction()
            if isinstance(f, QgsColorRampShader):
                shaderFunction = QgsColorRampShader(f)
            else:
                shaderFunction = QgsRasterShaderFunction(f)

            shader.setRasterShaderFunction(shaderFunction)
            newRenderer = QgsSingleBandPseudoColorRenderer(oldRenderer.input(), self.cbSingleBand.currentBand(), shader)

        elif isinstance(oldRenderer, QgsPalettedRasterRenderer):
            newRenderer = QgsPalettedRasterRenderer(oldRenderer.input(), self.cbSingleBand.currentBand(),
                                                    oldRenderer.classes())

            # r.setBand(band)
        elif isinstance(oldRenderer, QgsSingleBandColorDataRenderer):
            newRenderer = QgsSingleBandColorDataRenderer(oldRenderer.input(), self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsMultiBandColorRenderer):
            newRenderer = oldRenderer.clone()
            newRenderer.setInput(oldRenderer.input())
            newRenderer.setRedBand(self.cbMultiBandRed.currentBand())
            newRenderer.setGreenBand(self.cbMultiBandGreen.currentBand())
            newRenderer.setBlueBand(self.cbMultiBandBlue.currentBand())
        return newRenderer

    def setRenderer(self, renderer:QgsRasterRenderer):
        w = self.renderBandWidget
        assert isinstance(self.labelRenderType, QLabel)
        assert isinstance(w, QStackedWidget)
        self.labelRenderType.setText(str(renderer.type()))
        if isinstance(renderer, (
                QgsSingleBandGrayRenderer,
                QgsSingleBandColorDataRenderer,
                QgsSingleBandPseudoColorRenderer,
                QgsPalettedRasterRenderer)):
            w.setCurrentWidget(self.pageSingleBand)

            if isinstance(renderer, QgsSingleBandGrayRenderer):
                self.cbSingleBand.setBand(renderer.grayBand())

            elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                self.cbSingleBand.setBand(renderer.band())

            elif isinstance(renderer, QgsPalettedRasterRenderer):
                self.cbSingleBand.setBand(renderer.band())

            elif isinstance(renderer, QgsSingleBandColorDataRenderer):
                self.cbSingleBand.setBand(renderer.usesBands()[0])

        elif isinstance(renderer, QgsMultiBandColorRenderer):
            w.setCurrentWidget(self.pageMultiBand)
            self.cbMultiBandRed.setBand(renderer.redBand())
            self.cbMultiBandGreen.setBand(renderer.greenBand())
            self.cbMultiBandBlue.setBand(renderer.blueBand())

        else:
            w.setCurrentWidget(self.pageUnknown)




    def shouldTriggerLayerRepaint(self)->bool:
        return True

    def apply(self):

        newRenderer = self.renderer()

        if isinstance(newRenderer, QgsRasterRenderer) and isinstance(self.mLayer, QgsRasterLayer):
            newRenderer.setInput(self.mLayer.dataProvider())
            self.mLayer.setRenderer(newRenderer)
            self.widgetChanged.emit()

    def wlBand(self, wlKey:str)->int:
        if isinstance(self.mWL, np.ndarray):
            targetWL = float(LUT_WAVELENGTH[wlKey])
            return int(np.argmin(np.abs(self.mWL - targetWL)))+1
        else:
            return None

    def setWL(self, wlRegions:tuple):
        r = self.renderer().clone()
        if isinstance(r, (QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer, QgsSingleBandColorDataRenderer)):
            band = self.wlBand(wlRegions[0])
            self.cbSingleBand.setBand(band)
        elif isinstance(r, QgsMultiBandColorRenderer):
            bR = self.wlBand(wlRegions[0])
            bG = self.wlBand(wlRegions[1])
            bB = self.wlBand(wlRegions[2])

            self.cbMultiBandBlue.setBand(bB)
            self.cbMultiBandGreen.setBand(bG)
            self.cbMultiBandRed.setBand(bR)

        self.widgetChanged.emit()

    def setDockMode(self, dockMode:bool):
        pass

class RasterBandConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(RasterBandConfigWidgetFactory, self).__init__('Raster Band', RasterBandConfigWidget.icon())
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)
        self.setTitle('Band Selection')

        self._PREFERRED_PREDECESSORS = 'Symbology'


    def supportsLayer(self, layer):
        if isinstance(layer, QgsRasterLayer):
            return True

        return False

    def supportLayerPropertiesDialog(self):
        return False

    def supportsStyleDock(self):
        return True

    def createWidget(self, layer, canvas, dockWidget=True, parent=None)->QgsMapLayerConfigWidget:
        w = RasterBandConfigWidget(layer, canvas, parent=parent)
        self._w = w
        return w


class GDALMetadataModel(QAbstractTableModel):

    class MDItem(object):
        def __init__(self, major_object: str, domain: str, key: str, value: str):
            self.major_object: str = major_object
            self.domain: str = domain
            self.key: str = key
            self.value: str = value

    def __init__(self, parent=None):
        super(GDALMetadataModel, self).__init__(parent)

        self.mLayer:QgsMapLayer = None

        self.cnItem = 'Item'
        self.cnDomain = 'Domain'
        self.cnKey = 'Key'
        self.cnValue = 'Value(s)'

        # level0 = gdal.Dataset | ogr.DataSource
        # level1 = gdal.Band | ogr.Layer
        self.MD = []

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.MD)

    def columnNames(self)->typing.List[str]:
        return [self.cnItem, self.cnDomain, self.cnKey, self.cnValue]

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.columnNames())

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames()[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setLayer(self, layer:QgsMapLayer):
        assert isinstance(layer, (QgsRasterLayer, QgsVectorLayer))
        self.mLayer = layer
        self.syncToLayer()

    def syncToLayer(self):
        self.beginResetModel()
        self.MD = self._read_maplayer()
        self.endResetModel()

    def data(self, index:QModelIndex, role=None):
        if not index.isValid():
            return None

        item = self.MD[index.row()]
        assert isinstance(item, GDALMetadataModel.MDItem)

        cname = self.columnNames()[index.column()]

        if role == Qt.DisplayRole:
            if cname == self.cnItem:
                return item.major_object
            elif cname == self.cnDomain:
                return item.domain
            elif cname == self.cnKey:
                return item.key
            elif cname == self.cnValue:
                return item.value

        return None #super(GDALMetadataModel, self).data(index, role)

    def _read_majorobject(self, obj):
        assert isinstance(obj, (gdal.MajorObject, ogr.MajorObject))
        domains = obj.GetMetadataDomainList()
        if isinstance(domains, list):
            for domain in domains:
                for key, value in obj.GetMetadata(domain).items():
                    yield domain, key, value

    def _read_maplayer(self)->list:
        items = []
        if isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.dataProvider().name() == 'gdal':
            ds = gdal.Open(self.mLayer.source())
            if isinstance(ds, gdal.Dataset):
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataModel.MDItem('Dataset', domain, key, value))
                for b in range(ds.RasterCount):
                    band = ds.GetRasterBand(b+1)
                    assert isinstance(band, gdal.Band)
                    bandKey = 'Band{}'.format(b+1)
                    for (domain, key, value) in self._read_majorobject(band):
                        items.append(GDALMetadataModel.MDItem(bandKey, domain, key, value))

        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.dataProvider().name() == 'ogr':
            ds = ogr.Open(self.mLayer.source())
            if isinstance(ds, ogr.DataSource):
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataModel.MDItem('Datasource', domain, key, value))
                for b in range(ds.GetLayerCount()):
                    lyr = ds.GetLayer(b)
                    assert isinstance(lyr, ogr.Layer)
                    lyrKey = 'Layer{}'.format(b+1)
                    for (domain, key, value) in self._read_majorobject(lyr):
                        items.append(GDALMetadataModel.MDItem(lyrKey, domain, key, value))

        return items

class GDALMetadataModelTreeView(QTreeView):
    """
    A QTreeView for the GDALMetadataModel
    """
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Opens a context menue
        """
        index = self.indexAt(event.pos())
        if index.isValid():
            value = str(index.data(Qt.DisplayRole))
            m = QMenu()
            a = m.addAction('Copy Value')
            a.triggered.connect(lambda *args, value=value: QApplication.clipboard().setText(value))
            m.exec_(event.globalPos())


class GDALMetadataModelConfigWidget(QgsMapLayerConfigWidget):

    @staticmethod
    def icon()->QIcon:
        return QIcon(':/qps/ui/icons/edit_gdal_metadata.svg')

    def __init__(self, layer:QgsMapLayer, canvas:QgsMapCanvas, parent:QWidget=None):
        super(GDALMetadataModelConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'gdalmetadatamodelwidget.ui'
        loadUi(pathUi, self)

        self.setWindowIcon(GDALMetadataModelConfigWidget.icon())
        self.tvMetadata: QTableView
        self.tbFilter: QLineEdit
        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)

        self.metadataModel = GDALMetadataModel()
        self.metadataProxyModel = QSortFilterProxyModel()
        self.metadataProxyModel.setSourceModel(self.metadataModel)
        self.metadataProxyModel.setFilterKeyColumn(-1)
        self.tableView.setModel(self.metadataProxyModel)

        self.tbFilter.textChanged.connect(self.updateFilter)
        self.optionMatchCase.changed.connect(self.updateFilter)
        self.optionRegex.changed.connect(self.updateFilter)

        is_gdal = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        is_ogr = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'

        if is_gdal:
            self.gbMetadata.setTitle('GDAL Metadata Model')
            self.metadataModel.setLayer(layer)
        elif is_ogr:
            self.gbMetadata.setTitle('OGR Metadata Model')
            self.metadataModel.setLayer(layer)
        else:
            self.gbMetadata.setTitle('No GDAL/OGR Metadata')

    def apply(self):
        pass

    def updateFilter(self, *args):

        text = self.tbFilter.text()
        if self.optionMatchCase.isChecked():
            matchCase = Qt.CaseSensitive
        else:
            matchCase = Qt.CaseInsensitive

        if self.optionRegex.isChecked():
            syntax = QRegExp.RegExp
        else:
            syntax = QRegExp.Wildcard
        rx = QRegExp(text, cs=matchCase, syntax=syntax)
        if rx.isValid():
            self.metadataProxyModel.setFilterRegExp(rx)
        else:
            self.metadataProxyModel.setFilterRegExp(None)

class GDALMetadataConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):

        super(GDALMetadataConfigWidgetFactory, self).__init__('GDAL Metadata', GDALMetadataModelConfigWidget.icon())
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)
        self.setTitle('Metadata')

        self._PREFERRED_PREDECESSORS = ['Pyramids', 'Rendering']

    def supportsLayer(self, layer):
        is_gdal = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        is_ogr = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'
        return is_gdal or is_ogr

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

    def createWidget(self, layer, canvas, dockWidget=True, parent=None)->GDALMetadataModelConfigWidget:
        w = GDALMetadataModelConfigWidget(layer, canvas, parent=parent)
        self._w = w
        return w

    def title(self)->str:
        return 'GDAL Metadata'

    def icon(self)->QIcon:
        return GDALMetadataModelConfigWidget.icon()



class LabelFieldModel(QgsFieldModel):
    """
    A model to show the QgsFields of an QgsVectorLayer.
    Inherits QgsFieldModel and allows to change the name of the 1st column.
    """
    def __init__(self, parent):
        """
        Constructor
        :param parent:
        """
        super(LabelFieldModel, self).__init__(parent)
        self.mColumnNames = ['Fields']

    def headerData(self, col, orientation, role=Qt.DisplayRole):
        """
        Returns header data
        :param col: int
        :param orientation: Qt.Horizontal | Qt.Vertical
        :param role:
        :return: value
        """
        if Qt is None:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setHeaderData(self, col, orientation, value, role=Qt.EditRole):
        """
        Sets the header data.
        :param col: int
        :param orientation:
        :param value: any
        :param role:
        """
        result = False

        if role == Qt.EditRole:
            if orientation == Qt.Horizontal and col < len(self.mColumnNames) and isinstance(value, str):
                self.mColumnNames[col] = value
                result = True

        if result == True:
            self.headerDataChanged.emit(orientation, col, col)
        return result

class FieldConfigEditorWidget(QWidget):

    class ConfigInfo(QStandardItem):
        """
        Describes a QgsEditorWidgetFactory configuration.
        """
        def __init__(self, key:str, factory:QgsEditorWidgetFactory, configWidget:QgsEditorConfigWidget):
            super(FieldConfigEditorWidget.ConfigInfo, self).__init__()

            assert isinstance(key, str)
            assert isinstance(factory, QgsEditorWidgetFactory)
            assert isinstance(configWidget, QgsEditorConfigWidget)
            self.mKey = key
            self.mFactory = factory
            self.mConfigWidget = configWidget
            self.setText(factory.name())
            self.setToolTip(factory.name())
            self.mInitialConfig = dict(configWidget.config())


        def resetConfig(self):
            """
            Resets the widget to its initial values
            """
            self.mConfigWidget.setConfig(dict(self.mInitialConfig))

        def factoryKey(self)->str:
            """
            Returns the QgsEditorWidgetFactory key, e.g. "CheckBox"
            :return: str
            """
            return self.mKey

        def factoryName(self)->str:
            """
            Returns the QgsEditorWidgetFactory name, e.g. "Checkbox"
            :return: str
            """
            return self.factory().name()

        def config(self)->dict:
            """
            Returns the config dictionary
            :return: dict
            """
            return self.mConfigWidget.config()

        def configWidget(self)->QgsEditorConfigWidget:
            """
            Returns the QgsEditorConfigWidget
            :return: QgsEditorConfigWidget
            """
            return self.mConfigWidget

        def factory(self)->QgsEditorWidgetFactory:
            """
            Returns the QgsEditorWidgetFactory
            :return: QgsEditorWidgetFactory
            """
            return self.mFactory

        def editorWidgetSetup(self)->QgsEditorWidgetSetup:
            """
            Creates a QgsEditorWidgetSetup
            :return: QgsEditorWidgetSetup
            """
            return QgsEditorWidgetSetup(self.factoryKey(), self.config())


    sigChanged = pyqtSignal(object)

    def __init__(self, parent, layer:QgsVectorLayer, index:int):
        super(FieldConfigEditorWidget, self).__init__(parent)

        self.setLayout(QVBoxLayout())

        assert isinstance(layer, QgsVectorLayer)
        assert isinstance(index, int)

        self.mLayer = layer
        self.mField = layer.fields().at(index)
        assert isinstance(self.mField, QgsField)
        self.mFieldIndex = index

        self.mFieldNameLabel = QLabel(parent)
        self.mFieldNameLabel.setText(self.mField.name())

        self.layout().addWidget(self.mFieldNameLabel)

        self.gbWidgetType = QgsCollapsibleGroupBox(self)
        self.gbWidgetType.setTitle('Widget Type')
        self.gbWidgetType.setLayout(QVBoxLayout())
        self.cbWidgetType = QComboBox(self.gbWidgetType)

        self.stackedWidget = QStackedWidget(self.gbWidgetType)
        self.gbWidgetType.layout().addWidget(self.cbWidgetType)
        self.gbWidgetType.layout().addWidget(self.stackedWidget)




        currentSetup = self.mLayer.editorWidgetSetup(self.mFieldIndex)
        #self.mInitialConf = currentSetup.config()
        refkey = currentSetup.type()
        if refkey == '':
            refkey = QgsGui.editorWidgetRegistry().findBest(self.mLayer, self.mField.name()).type()

        self.mItemModel = QStandardItemModel(parent=self.cbWidgetType)

        iCurrent = -1
        i = 0
        factories = QgsGui.editorWidgetRegistry().factories()
        for key, fac in factories.items():
            assert isinstance(key, str)
            assert isinstance(fac, QgsEditorWidgetFactory)
            score = fac.fieldScore(self.mLayer, self.mFieldIndex)
            configWidget = fac.configWidget(self.mLayer, self.mFieldIndex, self.stackedWidget)

            if isinstance(configWidget, QgsEditorConfigWidget):
                configWidget.changed.connect(lambda: self.sigChanged.emit(self))
                self.stackedWidget.addWidget(configWidget)
                confItem = FieldConfigEditorWidget.ConfigInfo(key, fac, configWidget)
                if key == refkey:
                    iCurrent = i
                confItem.setEnabled(score > 0)
                confItem.setData(self, role=Qt.UserRole)
                self.mItemModel.appendRow(confItem)

                i += 1

        self.cbWidgetType.setModel(self.mItemModel)
        self.cbWidgetType.currentIndexChanged.connect(self.updateConfigWidget)

        self.layout().addWidget(self.gbWidgetType)
        self.layout().addStretch()
        self.cbWidgetType.setCurrentIndex(iCurrent)


        conf = self.currentFieldConfig()
        if isinstance(conf, FieldConfigEditorWidget.ConfigInfo):
            self.mInitialFactoryKey = conf.factoryKey()
            self.mInitialConf = conf.config()
        else:
            s = ""


    def setFactory(self, factoryKey:str):
        """
        Shows the QgsEditorConfigWidget of QgsEditorWidgetFactory `factoryKey`
        :param factoryKey: str
        """
        for i in range(self.mItemModel.rowCount()):
            confItem = self.mItemModel.item(i)
            assert isinstance(confItem, FieldConfigEditorWidget.ConfigInfo)
            if confItem.factoryKey() == factoryKey:
                self.cbWidgetType.setCurrentIndex(i)
                break


    def changed(self)->bool:
        """
        Returns True if the QgsEditorWidgetFactory or its configuration has been changed
        :return: bool
        """

        recentConfigInfo = self.currentFieldConfig()
        if isinstance(recentConfigInfo, FieldConfigEditorWidget.ConfigInfo):
            if self.mInitialFactoryKey != recentConfigInfo.factoryKey():
                return True
            elif self.mInitialConf != recentConfigInfo.config():
                return True

        return False

    def apply(self):
        """
        Applies the
        :return:
        """
        if self.changed():
            configInfo = self.currentFieldConfig()
            self.mInitialConf = configInfo.config()
            self.mInitialFactoryKey = configInfo.factoryKey()
            setup = QgsEditorWidgetSetup(self.mInitialFactoryKey, self.mInitialConf)
            self.mLayer.setEditorWidgetSetup(self.mFieldIndex, setup)

    def reset(self):
        """
        Resets the widget to its initial status
        """
        if self.changed():

            self.setFactory(self.mInitialFactoryKey)
            self.currentEditorConfigWidget().setConfig(self.mInitialConf)

    def currentFieldConfig(self)->ConfigInfo:
        i = self.cbWidgetType.currentIndex()
        return self.mItemModel.item(i)

    def currentEditorConfigWidget(self)->QgsEditorConfigWidget:
        return self.currentFieldConfig().configWidget()


    def updateConfigWidget(self, index):
        self.stackedWidget.setCurrentIndex(index)
        fieldConfig = self.currentFieldConfig()
        if isinstance(fieldConfig, FieldConfigEditorWidget.ConfigInfo):

            self.sigChanged.emit(self)


class LayerFieldConfigEditorWidget(QWidget):
    """
    A widget to set QgsVetorLayer field settings
    """
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        loadUi(DIR_UI_FILES / 'layerfieldconfigeditorwidget.ui', self)

        self.scrollArea.resizeEvent = self.onScrollAreaResize
        self.mFieldModel = LabelFieldModel(self)
        self.treeView.setModel(self.mFieldModel)
        self.treeView.selectionModel().currentRowChanged.connect(self.onSelectedFieldChanged)

        self.btnApply = self.buttonBox.button(QDialogButtonBox.Apply)
        self.btnReset = self.buttonBox.button(QDialogButtonBox.Reset)
        self.btnApply.clicked.connect(self.onApply)
        self.btnReset.clicked.connect(self.onReset)

    def onSelectedFieldChanged(self, index1:QModelIndex, index2:QModelIndex):
        """
        Shows the widget for the selected QgsField
        :param index1:
        :param index2:
        """
        if isinstance(index1, QModelIndex) and index1.isValid():
            r = index1.row()
            if r < 0 or r >= self.stackedWidget.count():
                s = ""
            self.stackedWidget.setCurrentIndex(r)

    def onScrollAreaResize(self, resizeEvent:QResizeEvent):
        """
        Forces the stackedWidget's width to fit into the scrollAreas viewport
        :param resizeEvent: QResizeEvent
        """
        assert isinstance(resizeEvent, QResizeEvent)
        self.stackedWidget.setMaximumWidth(resizeEvent.size().width())
        s  =""

    def onReset(self):

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.reset()
        self.onSettingsChanged()

    def onApply(self):
        """
        Applies all changes to the QgsVectorLayer
        :return:
        """

        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)

        for i in range(sw.count()):
            w = sw.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            w.apply()
        self.onSettingsChanged()


    def setLayer(self, layer:QgsVectorLayer):
        """
        Sets the QgsVectorLayer
        :param layer:
        """
        self.mFieldModel.setLayer(layer)
        self.updateFieldWidgets()

    def layer(self)->QgsVectorLayer:
        """
        Returns the current QgsVectorLayer
        :return:
        """
        return self.mFieldModel.layer()

    def updateFieldWidgets(self):
        """
        Empties the stackedWidget and populates it with a FieldConfigEditor
        for each QgsVectorLayer field.
        """
        sw = self.stackedWidget
        assert isinstance(sw, QStackedWidget)
        i = sw.count() - 1
        while i >= 0:
            w = sw.widget(i)
            w.setParent(None)
            i -= 1

        lyr = self.layer()
        if isinstance(lyr, QgsVectorLayer):
            for i in range(lyr.fields().count()):
                w = FieldConfigEditorWidget(sw, lyr, i)
                w.sigChanged.connect(self.onSettingsChanged)
                sw.addWidget(w)

        self.onSettingsChanged()

    def onSettingsChanged(self):
        """
        Enables/disables buttons
        :return:
        """
        b = False
        for i in range(self.stackedWidget.count()):
            w = self.stackedWidget.widget(i)
            assert isinstance(w, FieldConfigEditorWidget)
            if w.changed():
                b = True
                break

        self.btnReset.setEnabled(b)
        self.btnApply.setEnabled(b)



class LayerPropertiesDialog(QgsOptionsDialogBase):

    def __init__(self,
                 lyr:typing.Union[QgsRasterLayer, QgsVectorLayer],
                 canvas:QgsMapCanvas=None,
                 parent=None,
                 mapLayerConfigFactories:typing.List[QgsMapLayerConfigWidgetFactory] = None):

        super(QgsOptionsDialogBase, self).__init__('QPS_LAYER_PROPERTIES', parent, Qt.Dialog, settings=None)
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'layerpropertiesdialog.ui'
        loadUi(pathUi.as_posix(), self)
        self.initOptionsBase(False, 'Layer Properties - {}'.format(lyr.name()))
        self.mOptionsListWidget: QListWidget
        assert isinstance(self.mOptionsListWidget, QListWidget)
        self.mOptionsListWidget.currentRowChanged.connect(self.onPageChanged)
        assert isinstance(lyr, QgsMapLayer)
        self.mLayer: QgsMapLayer = lyr

        self.buttonBox: QDialogButtonBox

        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas()
            canvas.setDestinationCrs(lyr.crs())
            canvas.setExtent(lyr.extent())
            canvas.setLayers([lyr])

        self.mCanvas: QgsMapCanvas
        self.mCanvas = canvas
        self.btnApply: QPushButton = self.buttonBox.button(QDialogButtonBox.Apply)
        self.btnCancel: QPushButton = self.buttonBox.button(QDialogButtonBox.Cancel)
        self.btnOk: QPushButton = self.buttonBox.button(QDialogButtonBox.Ok)

        assert isinstance(self.mOptionsListWidget, QListWidget)


        # pageInformation

        self.mMetadataViewer: QTextBrowser
        self.pageInformation: QWidget

        # pageSource
        self.pageSource: QWidget
        self.tbLayerName: QLineEdit
        self.tbLayerDisplayName: QLineEdit
        self.mCRS: QgsProjectionSelectionWidget
        self.tbLayerName.textChanged.connect(lambda name: self.tbLayerDisplayName.setText(lyr.formatLayerName(name)))

        # pageSymbology
        self.pageSymbology: QWidget
        self.symbologyScrollArea: QScrollArea
        assert isinstance(self.symbologyScrollArea, QScrollArea)
        self.symbologyWidget: QWidget = None

        # pageLabels
        self.pageLabels: QWidget

        # pageTransparency
        self.pageTransparency: QWidget
        self.mRasterTransparencyWidget:QgsRasterTransparencyWidget = None

        # pageHistogram
        self.pageHistogram: QWidget

        # pageRendering
        self.pageRendering: QWidget
        self.mScaleRangeWidget: QgsScaleRangeWidget
        self.mScaleRangeWidget.setMapCanvas(canvas)

        # pagePyramids
        self.pagePyramids: QWidget

        # pageForms
        self.pageForms: QWidget
        self.mLayerFieldConfigEditorWidget: LayerFieldConfigEditorWidget

        self.pageLegend: QWidget
        self.legendWidget: QgsLayerTreeEmbeddedConfigWidget

        self.sync()

        self.btnApply.clicked.connect(self.apply)
        self.btnOk.clicked.connect(self.onOk)
        self.btnCancel.clicked.connect(self.onCancel)

        if mapLayerConfigFactories is None:
            from . import mapLayerConfigWidgetFactories as getFactories
            mapLayerConfigFactories = getFactories()

        self.initConfigFactories(mapLayerConfigFactories)

        # select the first item
        self.mOptionsListWidget.setCurrentRow(0)

    def onPageChanged(self, row):
        if self.currentPage() == self.pageSymbology:
            pass
            #self.symbologyScrollArea.ensureWidgetVisible(self.symbologyWidget)



    def initConfigFactories(self, mapLayerConfigFactories: list = []):
        """
        Initialized additional items created from QgsMapLayerConfigFactories
        :param mapLayerConfigFactories:
        :type mapLayerConfigFactories:
        :return:
        :rtype:
        """
        for f in mapLayerConfigFactories:
            assert isinstance(f, QgsMapLayerConfigWidgetFactory)
            if f.supportsLayer(self.mapLayer()):


                listItem = QListWidgetItem(f.icon(), f.title())
                listWidget = f.createWidget(self.mapLayer(), self.canvas(), dockWidget=False)
                assert isinstance(listWidget, QgsMapLayerConfigWidget)

                i = self.mOptionsListWidget.count()
                if hasattr(f, '_PREFERRED_PREDECESSORS'):
                    predecessorNames = f._PREFERRED_PREDECESSORS
                    if not isinstance(predecessorNames, list):
                        predecessorNames = [predecessorNames]

                    itemNames = [self.mOptionsListWidget.item(i).text() for i in range(self.mOptionsListWidget.count())]
                    for p in predecessorNames:
                        if p in itemNames:
                            i = itemNames.index(p) + 1
                            break

                #listWidget.widgetChanged.connect(self.onApply)
                self.mOptionsListWidget.insertItem(i, listItem)
                self.mOptionsStackedWidget.insertWidget(i, listWidget)


    def onOk(self):
        self.apply()
        self.accept()

    def onCancel(self):
        # do restore previous settings?

        #self.setResult(QDialog.Rejected)
        self.reject()


    def currentPage(self)->QWidget:
        return self.mOptionsStackedWidget.currentWidget()

    def apply(self):

        page = self.currentPage()
        child = None
        for t in [QgsMapLayerConfigWidget, QgsRendererPropertiesDialog]:
            child = page.findChild(t)
            if child:
                break
        if isinstance(page, QgsMapLayerConfigWidget):
            page.apply()
        elif isinstance(child, (QgsMapLayerConfigWidget, QgsRendererPropertiesDialog)):
            child.apply()
            if isinstance(child, QgsRendererPropertiesDialog):
                s = ""
        elif page == self.pageInformation:
            self.apply_information()
        elif page == self.pageSource:
            self.apply_source()
        elif page == self.pageLabels:
            self.apply_labels()
        elif page == self.pageTransparency:
            self.apply_transparency()
        elif page == self.pageHistogram:
            self.apply_histogram()
        elif page == self.pageRendering:
            self.apply_rendering()
        elif page == self.pagePyramids:
            self.apply_pyramids()
        elif page == self.pageFields:
            self.apply_fields()
        elif page == self.pageForms:
            self.apply_forms()
        elif page == self.pageLegend:
            self.apply_legend()

        self.mapLayer().triggerRepaint()
        self.sync()



    def canvas(self)->QgsMapCanvas:
        return self.mCanvas

    def mapLayer(self)->QgsMapLayer:
        """
        Returns the QgsMapLayer
        :return:
        :rtype:
        """
        return self.mLayer


    def styleMenu(self)->QMenu:
        """
        Returns the Style menue with buttons to load, save, copy or paste a layer style
        """
        m = QMenu()
        m.addAction(self.actionLoadStyle)
        m.addAction(self.actionSaveStyle)
        m.addAction(self.actionCopyStyle)
        m.addAction(self.actionPasteStyle)

        return m

    def sync(self):
        """
        Call to reload properties
        """
        lyr = self.mapLayer()
        self.sync_information(lyr)
        self.sync_source(lyr)
        self.sync_symbology(lyr)
        self.sync_labels(lyr)
        self.sync_transparency(lyr)
        self.sync_histogram(lyr)
        self.sync_rendering(lyr)
        self.sync_pyramids(lyr)
        self.sync_fields(lyr)
        self.sync_forms(lyr)
        self.sync_legend(lyr)

    def listWidgetItem(self, page:QWidget)->QListWidgetItem:
        """
        Returns the QListWidgetItem that corresponds to a page
        :param name:
        :type name:
        :return:
        :rtype:
        """
        assert self.mOptionsStackedWidget.count() == self.mOptionsListWidget.count()
        i = self.mOptionsStackedWidget.indexOf(page)
        assert i >= 0
        item = self.mOptionsListWidget.item(i)
        assert isinstance(item, QListWidgetItem)
        #print((page.objectName(), item.text()))
        return item


    def activateListItem(self, page:QWidget, is_active:bool)->bool:
        page.setEnabled(is_active)
        item = self.listWidgetItem(page)
        assert isinstance(item, QListWidgetItem)
        item.setHidden(not is_active)
        return is_active

    def sync_information(self, lyr):
        if self.activateListItem(self.pageInformation, isinstance(lyr, QgsMapLayer)):
            style = QgsApplication.reportStyleSheet(QgsApplication.WebBrowser)
            md = lyr.htmlMetadata()
            md = md.replace('<head>', '<head><style type="text/css">{}</style>'.format(style))
            self.mMetadataViewer.setHtml(md)
        else:
            self.mMetadataViewer.setHtml('')

    def apply_information(self):
        pass

    def sync_source(self, lyr:QgsMapLayer):
        if self.activateListItem(self.pageSource, isinstance(lyr, QgsMapLayer)):
            self.tbLayerName.setText(lyr.name())
            self.mCRS.setCrs(lyr.crs())
        else:
            self.tbLayerName.setText('')
            self.tbLayerDisplayName.setText('')
            self.mCRS.setCrs(None)

    def apply_source(self):
        lyr = self.mapLayer()

        if isinstance(lyr, QgsMapLayer):
            name = self.tbLayerName.text()
            if name != lyr.name():
                lyr.setName(name)
            if self.mCRS.crs() != lyr.crs():
                lyr.setCrs(self.mCRS.crs())

    def sync_symbology(self, lyr:QgsMapLayer):
        is_raster = isinstance(lyr, QgsRasterLayer)
        is_vector = isinstance(lyr, QgsVectorLayer)
        is_maplayer = is_raster or is_vector

        if self.activateListItem(self.pageSymbology, is_maplayer):
            w = self.symbologyWidget

            if is_raster:

                if isinstance(self.symbologyWidget, QgsRendererRasterPropertiesWidget):
                    r1 = self.symbologyWidget.currentRenderWidget().renderer()
                    r2 = lyr.renderer()
                    if r1.usesBands() != r2.usesBands():
                        if True: # see https://github.com/qgis/QGIS/issues/34602
                            self.symbologyWidget = None
                            w.setParent(None)
                        else:
                            self.symbologyWidget.syncToLayer(lyr)

                if not isinstance(self.symbologyWidget, QgsRendererRasterPropertiesWidget):
                    self.symbologyWidget = QgsRendererRasterPropertiesWidget(lyr, self.canvas(), None)
                    self.symbologyScrollArea.setWidget(self.symbologyWidget)

            elif is_vector:
                if not isinstance(self.symbologyWidget, QgsRendererPropertiesDialog):
                    self.symbologyWidget = QgsRendererPropertiesDialog(lyr, QgsStyle(), embedded=True)


            if self.symbologyScrollArea.widget() != self.symbologyWidget:
                self.symbologyScrollArea.setWidget(self.symbologyWidget)

    def sync_labels(self, lyr:QgsMapLayer):
        is_vector = isinstance(lyr, QgsVectorLayer)
        if self.activateListItem(self.pageLabels, False):
            # to be implemented
            pass

    def apply_labels(self):

        self.sync_labels()

    def sync_transparency(self, lyr:QgsMapLayer):
        l = self.pageTransparency.layout()
        assert isinstance(l, QVBoxLayout)
        is_raster = isinstance(lyr, QgsRasterLayer)
        if self.activateListItem(self.pageTransparency, is_raster):
            w = self.pageTransparency.findChild(QgsRasterTransparencyWidget)
            if not isinstance(w, QgsRasterTransparencyWidget):
                self.mRasterTransparencyWidget = QgsRasterTransparencyWidget(lyr, self.canvas(), None)
                l.addWidget(self.mRasterTransparencyWidget)
            else:
                w.syncToLayer()


    def apply_transparency(self):

        for w in self.pageTransparency.findChildren(QgsRasterTransparencyWidget):
            assert isinstance(w, QgsRasterTransparencyWidget)

            s = ""
            w.apply()
            s = ""
            break

        self.sync_transparency(self.mapLayer())
        pass

    def sync_histogram(self, lyr:QgsMapLayer):
        is_raster = isinstance(lyr, QgsRasterLayer)
        if self.activateListItem(self.pageHistogram, is_raster):
                w = self.histogramScrollArea.widget()
                if not isinstance(w, QgsRasterHistogramWidget):
                    w = QgsRasterHistogramWidget(lyr, None)
                    self.histogramScrollArea.setWidget(w)

    def apply_histogram(self):
        pass

    def sync_rendering(self, lyr:QgsMapLayer):
        is_maplayer = isinstance(lyr, QgsMapLayer)
        if self.activateListItem(self.pageRendering, is_maplayer):
            self.gbRenderingScale.setChecked(lyr.hasScaleBasedVisibility())
            self.mScaleRangeWidget.setScaleRange(lyr.minimumScale(), lyr.maximumScale())

    def apply_rendering(self):
        assert isinstance(self.mScaleRangeWidget, QgsScaleRangeWidget)
        lyr = self.mapLayer()
        if not isinstance(lyr, QgsMapLayer):
            return
        lyr.setScaleBasedVisibility(self.gbRenderingScale.isChecked())
        if self.gbRenderingScale.isChecked():
            lyr.setMaximumScale(self.mScaleRangeWidget.maximumScale())
            lyr.setMinimumScale(self.mScaleRangeWidget.minimumScale())

    def sync_pyramids(self, lyr:QgsMapLayer):
        is_raster = isinstance(lyr, QgsRasterLayer)
        if self.activateListItem(self.pagePyramids, False):
            # to be implemented
            pass

    def apply_pyramids(self):
        pass

    def sync_fields(self, lyr:QgsMapLayer):
        is_vector = isinstance(lyr, QgsVectorLayer)
        if self.activateListItem(self.pageFields, False):
            # tbi
            pass
    def apply_fields(self):

        pass


    def apply_fields(self):

        pass

    def sync_forms(self, lyr:QgsMapLayer):
        if self.activateListItem(self.pageForms, isinstance(lyr, QgsVectorLayer)):
            self.mLayerFieldConfigEditorWidget.setLayer(lyr)

    def apply_forms(self):

        pass


    def sync_legend(self, lyr:QgsMapLayer):
        if self.activateListItem(self.pageLegend, isinstance(lyr, QgsMapLayer)):
            self.legendWidget.setLayer(lyr)

    def apply_legend(self):
        self.legendWidget.applyToLayer()


def showLayerPropertiesDialog(layer:QgsMapLayer,
                              canvas:QgsMapCanvas=None,
                              parent:QObject=None,
                              modal:bool=True,
                              useQGISDialog:bool=False)->typing.Union[QDialog.DialogCode, QDialog]:
    """
    Opens a dialog to adjust map layer settings.
    :param layer: QgsMapLayer of type QgsVectorLayer or QgsRasterLayer
    :param canvas: QgsMapCanvas
    :param parent:
    :param modal: bool
    :return: QDialog.DialogCode
    """
    dialog = None
    result = QDialog.Rejected
    from .utils import qgisAppQgisInterface
    iface = qgisAppQgisInterface()
    qgisUsed = False
    if useQGISDialog and isinstance(iface, QgisInterface):
        # try to use the QGIS vector layer properties dialog
        try:
            root = iface.layerTreeView().model().rootGroup()
            assert isinstance(root, QgsLayerTreeGroup)
            temporaryGroup = None
            lastActiveLayer = iface.activeLayer()

            if root.findLayer(layer) is None:
                temporaryGroup = root.addGroup('.')
                assert isinstance(temporaryGroup, QgsLayerTreeGroup)
                temporaryGroup.setItemVisibilityChecked(False)
                lyrNode = temporaryGroup.addLayer(layer)
                assert isinstance(lyrNode, QgsLayerTreeLayer)
            iface.setActiveLayer(layer)
            iface.showLayerProperties(layer)

            if isinstance(temporaryGroup, QgsLayerTreeGroup):
                root.removeChildNode(temporaryGroup)
            iface.setActiveLayer(lastActiveLayer)

            return QDialog.Accepted

        except Exception as ex:
            print(ex, file=sys.stderr)

    else:

        dialog = LayerPropertiesDialog(layer, canvas=canvas)

        if modal == True:
            dialog.setModal(True)
            return dialog.exec_()
        else:
            dialog.setModal(False)
            dialog.show()
            return dialog

    return None



