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


class QPSMapLayerConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self, title:str, icon:QIcon=QIcon()):
        super(QPSMapLayerConfigWidgetFactory, self).__init__(title, icon)
        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)
        self.mPreferredPredecessors = []

    def preferredPredecessors(self)->typing.List[str]:
        """
        Overwrite to return a list of ConfigWidgetNames this config widget should follow
        """
        return self.mPreferredPredecessors[:]


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



