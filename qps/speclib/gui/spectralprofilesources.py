import copy
import difflib
import math
import sys
import typing
import enum
import re
import warnings

from PyQt5.QtCore import QByteArray, QModelIndex, QRect, QAbstractListModel, QSize, QRectF, QPoint, \
    QSortFilterProxyModel, QItemSelection
from PyQt5.QtGui import QTextDocument, QAbstractTextDocumentLayout, QIcon, QColor, QFont, QPainter
from qgis.core import QgsFeature, QgsGeometry, QgsWkbTypes, QgsPointXY, QgsMapLayer, QgsExpression, \
    QgsFieldConstraints, QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextGenerator, \
    QgsRasterIdentifyResult, QgsRaster, QgsRectangle

from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsFieldExpressionWidget
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsApplication, QgsTask, \
    QgsTaskManager, QgsRasterDataProvider, QgsRasterRenderer, QgsField, QgsFields

from qgis.gui import QgsMapCanvas, QgsDockWidget, QgsDoubleSpinBox

from qgis.PyQt.QtWidgets import *

from .spectrallibrarywidget import SpectralLibraryWidget
from .. import speclibUiPath
from ..core import profile_field_list, profile_field_names, is_profile_field
from ..core.spectralprofile import SpectralProfileBlock, SpectralSetting, encodeProfileValueDict, SpectralProfile


from ...plotstyling.plotstyling import PlotStyle, MarkerSymbol, PlotStyleButton
import numpy as np
from ...models import TreeModel, TreeNode, TreeView, OptionTreeNode, OptionListModel, Option, setCurrentComboBoxValue
from ...utils import SpatialPoint, loadUi, parseWavelength, HashablePoint, rasterLayerArray, spatialPoint2px, \
    HashableRect, px2spatialPoint, px2geocoordinatesV2
from ...externals.htmlwidgets import HTMLComboBox

SCOPE_VAR_SAMPLE_CLICK = 'sample_click'
SCOPE_VAR_SAMPLE_FEATURE = 'sample_feature'


class SpectralProfileSource(object):

    def __init__(self):
        self.mName: str = None
        self.mUri: str = None
        self.mProvider: str = None

    def setName(self, name: str):
        self.mName = name

    def name(self) -> str:
        return self.mName

    def toolTip(self) -> str:
        return self.mUri

    def __hash__(self):
        return hash((self.mUri, self.mProvider))

    def __eq__(self, other):
        if not isinstance(other, SpectralProfileSource):
            return False
        return self.mUri == other.mUri and self.mProvider == other.mProvider

    def rasterLayer(self, **kwds) -> QgsRasterLayer:
        raise NotImplementedError


class MapCanvasLayerProfileSource(SpectralProfileSource):
    MODE_FIRST_LAYER = 'first'
    MODE_TOP_LAYER = 'top'
    MODE_BOTTOM_LAYER = 'bottom'

    def __init__(self, mode: str = None):
        super().__init__()
        self.mMapCanvas: QgsMapCanvas = None
        if mode is None:
            mode = self.MODE_FIRST_LAYER

        assert mode in [self.MODE_TOP_LAYER, self.MODE_FIRST_LAYER, self.MODE_BOTTOM_LAYER]
        self.mMode = mode

        if self.mMode == self.MODE_TOP_LAYER:
            self.mName = '<i>Top raster layer</i>'
        elif self.mMode == self.MODE_BOTTOM_LAYER:
            self.mName = '<i>Last raster layer</i>'
        elif self.mMode == self.MODE_FIRST_LAYER:
            self.mName = '<i>First raster layer</i>'

    def __eq__(self, other):
        return isinstance(other, MapCanvasLayerProfileSource) and other.mMode == self.mMode

    def toolTip(self) -> str:
        if self.mMode == self.MODE_TOP_LAYER:
            return 'Returns profiles from the top raster layer  in the map layer stack'
        elif self.mMode == self.MODE_BOTTOM_LAYER:
            return 'Returns profiles from the bottom raster layer in the map layer stack'
        elif self.mMode == self.MODE_FIRST_LAYER:
            return 'Returns profiles of the first visible raster layer in the map layer stack'
        else:
            raise NotImplementedError()

    def rasterLayer(self, mapCanvas: QgsMapCanvas = None, position: SpatialPoint = None) -> QgsRasterLayer:
        """
        Searches for a raster layer in mapCanvas with valid pixel values at "position"
        :param mapCanvas:
        :param position:
        :return: QgsRasterLayer
        """
        if not (isinstance(mapCanvas, QgsMapCanvas) and isinstance(position, QgsPointXY)):
            return None

        raster_layers = [l for l in mapCanvas.layers() if isinstance(l, QgsRasterLayer) and l.isValid()]

        if self.mMode == self.MODE_TOP_LAYER:
            raster_layers = raster_layers[0:1]
        elif self.mMode == self.MODE_BOTTOM_LAYER:
            raster_layers = raster_layers[-1:]
        elif self.mMode == self.MODE_FIRST_LAYER:
            # test which raster layer has a valid pixel
            for lyr in raster_layers:
                pt = position.toCrs(lyr.crs())
                if not lyr.extent().contains(pt):
                    continue
                dp: QgsRasterDataProvider = lyr.dataProvider()
                result: QgsRasterIdentifyResult = dp.identify(pt, QgsRaster.IdentifyFormatValue, QgsRectangle())
                s = ""
                if result.isValid():
                    for v in result.results().values():
                        if v not in [None]:
                            # a valid numeric value
                            return lyr

        return None


class StandardLayerProfileSource(SpectralProfileSource):

    @staticmethod
    def fromRasterLayer(lyr: QgsRasterLayer):
        return StandardLayerProfileSource(lyr.source(), lyr.name(), lyr.providerType(), lyr.renderer().clone())

    def __init__(self, uri: str, name: str, provider: str, renderer: QgsRasterRenderer = None):
        super().__init__()
        assert len(uri) > 0
        self.mUri = uri
        self.mName = name
        self.mProvider = provider
        self.mRenderer: QgsRasterRenderer = None
        if isinstance(renderer, QgsRasterRenderer):
            self.mRenderer = renderer.clone()
            self.mRenderer.setInput(None)

        self.mLyr = None

    def rasterLayer(self, **kwds) -> QgsRasterLayer:
        if not isinstance(self.mLyr, QgsRasterLayer):
            loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
            self.mLyr = QgsRasterLayer(self.mUri, self.mName, self.mProvider, options=loptions)
            if isinstance(self.mRenderer, QgsRasterRenderer):
                self.mRenderer.setInput(self.mLyr.dataProvider())
                self.mLyr.setRenderer(self.mRenderer)
        return self.mLyr


class SpectralProfileTopLayerSource(StandardLayerProfileSource):

    def __init__(self, *args, **kwds):
        super(SpectralProfileTopLayerSource, self).__init__('<toprasterlayer>', '<top raster layer>', None)

        self.mMapLayerSources = []

    def setMapSources(self, sources: typing.List[StandardLayerProfileSource]):
        self.mMapLayerSources.clear()
        self.mMapLayerSources.extend(sources)

    def mapSources(self) -> typing.List[StandardLayerProfileSource]:
        return self.mMapLayerSources

    def name(self) -> str:
        return '<top raster layer>'

    def toolTip(self) -> str:
        return 'Reads Spectral Profiles from the top raster layer of a clicked map canvas.'


class SpectralProfileSourceModel(QAbstractListModel):
    """
    A list model that lists (raster) sources of SpectralProfiles.
    """

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourceModel, self).__init__(*args, **kwds)

        self.mSources: typing.List[SpectralProfileSource] = [None]
        self.mDefaultSource: SpectralProfileSource = None

    def setDefaultSource(self, source: SpectralProfileSource):
        """
        Sets a default SpectralProfileSource that is used for SpectralProfileGenerator Nodes
        """
        self.addSources(source)

        self.mDefaultSource = source

    def defaultSource(self) -> SpectralProfileSource:
        """
        Returns the default SpectralProfileSource
        """
        return self.mDefaultSource

    def __len__(self) -> int:
        return len(self.mSources)

    def __iter__(self):
        return iter(self.mSources)

    def __getitem__(self, slice):
        return self.mSources[slice]

    def sources(self) -> typing.List[SpectralProfileSource]:
        return [s for s in self[:] if isinstance(s, SpectralProfileSource)]

    def addSources(self, sources: typing.List[SpectralProfileSource]) -> typing.List[SpectralProfileSource]:
        """
        Adds sources to collect spectral profiles from
        :param sources:
        :return:
        """
        if not isinstance(sources, typing.Iterable):
            sources = [sources]

        to_insert = []
        for source in sources:
            if source is None:
                # already in model
                continue

            if isinstance(source, str):
                source = QgsRasterLayer(source)

            if isinstance(source, QgsRasterLayer):
                source = StandardLayerProfileSource.fromRasterLayer(source)

            assert isinstance(source, SpectralProfileSource)
            if source not in self.mSources:
                to_insert.append(source)

        if len(to_insert) > 0:
            i = len(self)
            self.beginInsertRows(QModelIndex(), i, i + len(to_insert) - 1)
            self.mSources.extend(to_insert)
            self.endInsertRows()

        return to_insert

    def sourceModelIndex(self, source) -> QModelIndex:
        if source in self.mSources:
            i = self.mSources.index(source)
            return self.createIndex(i, 0, self.mSources[i])
        else:
            return QModelIndex()

    def findSource(self, source: typing.Any):
        if isinstance(source, SpectralProfileSource):
            if source in self.sources():
                return source
        uri: str = None
        if isinstance(source, QgsMapLayer):
            uri = source.source()
        elif isinstance(source, str):
            uri = source

        if uri:
            for s in self.sources():
                if s.mUri == uri:
                    return s

        return None

    def removeSources(self, sources: StandardLayerProfileSource) -> typing.List[StandardLayerProfileSource]:
        if not isinstance(sources, typing.Iterable):
            sources = [sources]
        removed = []
        for s in sources:
            source = self.findSource(s)
            if isinstance(source, StandardLayerProfileSource):
                i = self.mSources.index(source)
                self.beginRemoveRows(QModelIndex(), i, i)
                self.mSources.remove(source)
                self.endRemoveRows()
                removed.append(source)
        return removed

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):

        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return 'Raster Source'
        return super(SpectralProfileSourceModel, self).headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):

        if not index.isValid():
            return None

        source = self.mSources[index.row()]
        if isinstance(source, SpectralProfileSource):
            if role == Qt.DisplayRole:
                return source.name()
            elif role == Qt.DecorationRole:
                pass
                # return QIcon(r':/images/themes/default/mIconRaster.svg')
            elif role == Qt.ToolTipRole:
                return source.toolTip()
            elif role == Qt.UserRole:
                return source
        elif source is None:
            if role == Qt.DisplayRole:
                return 'None'
            elif role == Qt.ToolTipRole:
                return 'No raster source selected.'

        return None


class SpectralProfileSourceProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourceProxyModel, self).__init__(*args, **kwds)


class SpectralProfileSourceNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mProfileSource: StandardLayerProfileSource = None
        self.setValue('No Source')
        self.setToolTip('Please select a raster source')

    def icon(self) -> QIcon:
        return QIcon(r':/images/themes/default/mIconRaster.svg')

    def profileSource(self) -> SpectralProfileSource:
        return self.mProfileSource

    def setSpectralProfileSource(self, source: SpectralProfileSource):
        if isinstance(source, QgsRasterLayer):
            source = StandardLayerProfileSource.fromRasterLayer(source)
        elif isinstance(source, QgsMapCanvas):
            source = MapCanvasLayerProfileSource('top')

        assert source is None or isinstance(source, SpectralProfileSource)
        self.mProfileSource = source

        if isinstance(source, SpectralProfileSource):
            self.setValue(self.mProfileSource.name())
            self.setToolTip(self.mProfileSource.toolTip())
        else:
            self.setValue(None)
            self.setToolTip(None)


class SpectralLibraryWidgetListModel(QAbstractListModel):
    """
    A list model that list SpectralLibraries
    """

    def __init__(self, *args, **kwds):
        super(SpectralLibraryWidgetListModel, self).__init__(*args, **kwds)

        self.mSLWs: typing.List[SpectralLibraryWidget] = []

    def __len__(self) -> int:
        return len(self.mSLWs)

    def __iter__(self):
        return iter(self.mSLWs)

    def __getitem__(self, slice):
        return self.mSLWs[slice]

    def spectralLibraryWidgets(self) -> typing.List[SpectralLibraryWidget]:
        return self[:]

    def addSpectralLibraryWidget(self, slw: SpectralLibraryWidget) -> SpectralLibraryWidget:
        assert isinstance(slw, SpectralLibraryWidget)
        i = self.spectralLibraryWidgetListIndex(slw)
        if i is None:
            i = len(self)
            self.beginInsertRows(QModelIndex(), i, i)
            self.mSLWs.insert(i, slw)
            # slw.destroyed.connect(lambda s=slw: self.removeSpectralLibraryWidget(s))
            slw.sigWindowIsClosing.connect(lambda s=slw: self.removeSpectralLibraryWidget(s))
            self.endInsertRows()
            return slw
        return None

    def spectralLibraryWidgetListIndex(self, speclib: SpectralLibraryWidget) -> int:
        for i, sl in enumerate(self):
            if sl is speclib:
                return i
        return None

    def spectralLibraryWidgetModelIndex(self, speclibWidget: SpectralLibraryWidget) -> QModelIndex:

        i = self.spectralLibraryWidgetListIndex(speclibWidget)
        if isinstance(i, int):
            return self.createIndex(i, 0, speclibWidget)
        return QModelIndex()

    def removeSpectralLibraryWidget(self, slw: SpectralLibraryWidget) -> SpectralLibraryWidget:
        i = self.spectralLibraryWidgetListIndex(slw)
        if isinstance(i, int):
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mSLWs.remove(slw)
            self.endRemoveRows()
            return slw
        else:
            return None

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):

        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return 'Spectral Library'
        return super(SpectralLibraryWidgetListModel, self).headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):

        if not index.isValid():
            return None

        slw = self.mSLWs[index.row()]
        if isinstance(slw, SpectralLibraryWidget):

            if role == Qt.DisplayRole:
                return slw.speclib().name()

            elif role == Qt.ToolTipRole:
                return slw.windowTitle()

            elif role == Qt.DecorationRole:
                return QIcon(r':/enmapbox/gui/ui/icons/viewlist_spectrumdock.svg')

            elif role == Qt.UserRole:
                return slw

        return None


class SamplingBlockDescription(object):
    """
    Describes the pixel block to be read from a raster layer in pixel coordinates.
    Upper left pixel == (0,0)
    """

    def __init__(self,
                 point: SpatialPoint,
                 layer: QgsRasterLayer,
                 rect: QRect,
                 meta: dict = None):
        """
        :param point: The point for which to read pixel values from layer
        :param layer: The QgsRasterLayer to read pixel values from
        :param rect: QRect in pixel coordinates. Upper-Left image coordinate = (0,0)
        :param meta: dict with other information to be used in the SpectralProfileSamplingMode's .
        """
        assert isinstance(layer, QgsRasterLayer) and layer.isValid()
        if not isinstance(point, SpatialPoint):
            assert isinstance(point, QgsPointXY)
            point = SpatialPoint(layer.crs(), point.x(), point.y())

        assert isinstance(point, SpatialPoint)

        self.mPoint: SpatialPoint = point.toCrs(layer.crs())
        self.mLayer: QgsRasterLayer = layer
        assert rect.width() > 0
        assert rect.height() > 0
        self.mRect: HashableRect = HashableRect(rect)
        if not isinstance(meta, dict):
            meta = dict()
        self.mMeta = meta

    def samplingPoint(self) -> SpatialPoint:
        """
        The sampling point the rect referes to.
        :return: SpatialPoint
        """
        return self.mPoint

    def uri(self) -> str:
        """
        Source URI string
        :return: str
        """
        return self.layer().source()

    def layer(self) -> QgsRasterLayer:
        """
        The raster layer source from which to sample pixel profiles
        :return: QgsRasterLayer
        """
        return self.mLayer

    def rect(self) -> HashableRect:
        """
        The QRect rectangle to load the pixel profiles from (HashableRect just makes it hashable)
        :return:
        """
        return self.mRect

    def meta(self) -> dict:
        """
        Additional metadata that can be used by other functions of the sampling method
        :return:
        """
        return self.mMeta


class SpectralProfileSamplingMode(object):

    def __init__(self):
        super(SpectralProfileSamplingMode, self).__init__()

    def name(self) -> str:
        raise NotImplementedError()

    def settings(self) -> dict:
        return {'name': self.name()}

    def htmlSummary(self) -> str:
        return self.name()

    def icon(self) -> QIcon:
        return QIcon()

    def nodes(self) -> typing.List[TreeNode]:
        """
        Returns nodes, e.g. to set additional options
        """
        return []

    def mapOverlay(self, lyr: QgsRasterLayer, spatialPoint: SpatialPoint) -> typing.Optional[QgsGeometry]:
        return None

    def samplingBlockDescription(self,
                                 lyr: QgsRasterLayer,
                                 point: QgsPointXY) -> SamplingBlockDescription:
        """
        Returns rectangle in pixel coordinates for the pixel block to sample and additional metadata
        :param lyr: QgsRasterLayer, the raster layer to read data from
        :param point: QgsPointXY, the point within the raster layers's extent to sample values for
        :return: a tuple with the pixel block boundaries (QRect) and dict of additional metadata
        """
        raise NotImplementedError()

    def profiles(self,
                 profileBlock: SpectralProfileBlock,
                 blockDescription: SamplingBlockDescription) -> SpectralProfileBlock:
        """
        Returns the sampled profile(s) as SpectralProfileBlock
        :param profileBlock: SpectralProfileBlock with input profiles, as read for the SamplingBlockDescription
        :param blockDescription: SamplingBlockDescription
        :return: SpectralProfileBlock with sampled profile, e.g. by aggregation of profiles in SpectralProfileBlock
        """
        raise NotImplementedError()

    def tooltip(self) -> str:
        lines = [self.name()]
        for k, v in self.settings().items():
            lines.append(f'{k}: {v}')
        return '<br>'.join(lines)

    def writeXml(self):
        pass

    @staticmethod
    def fromXml(self):
        pass

    def clone(self):
        raise NotImplementedError()


class SpectralProfileSamplingModeNode(TreeNode):

    def __init__(self, *args, **kwds):
        super(SpectralProfileSamplingModeNode, self).__init__(*args, **kwds)

        self.mProfileSamplingMode: SpectralProfileSamplingMode = None
        self.mModeInstances: typing.Dict[str, SpectralProfileSamplingMode] = dict()
        self.setProfileSamplingMode(SingleProfileSamplingMode())

    def profileSamplingMode(self) -> SpectralProfileSamplingMode:
        return self.mProfileSamplingMode

    def setProfileSamplingMode(self, mode: SpectralProfileSamplingMode) -> SpectralProfileSamplingMode:
        assert isinstance(mode, SpectralProfileSamplingMode)

        mode: SpectralProfileSamplingMode = self.mModeInstances.get(mode.__class__.__name__, mode.clone())

        oldNodes = self.childNodes()
        for oldNode in oldNodes:
            oldNode.sigUpdated.disconnect(self.onChildNodeUpdate)

        self.removeChildNodes(oldNodes)
        self.mProfileSamplingMode = mode
        self.mModeInstances[mode.__class__.__name__] = mode
        # self.setValue(mode.name())
        # set option nodes as child nodes

        newNodes = mode.nodes()
        for newNode in newNodes:
            newNode.sigUpdated.connect(self.onChildNodeUpdate)
        self.appendChildNodes(newNodes)
        self.onChildNodeUpdate()
        return mode

    def onChildNodeUpdate(self):

        self.setValue(self.profileSamplingMode().name())


class SingleProfileSamplingMode(SpectralProfileSamplingMode):

    def __init__(self):
        super(SingleProfileSamplingMode, self).__init__()

    def clone(self):
        return SingleProfileSamplingMode()

    def name(self) -> str:
        return 'Single Profile'

    def tooltip(self) -> str:
        return 'Returns a single profile from the clicked position'

    def samplingBlockDescription(self, lyr: QgsRasterLayer, point: typing.Union[QgsPointXY, SpatialPoint]) \
            -> SamplingBlockDescription:
        assert isinstance(lyr, QgsRasterLayer)

        # convert point to pixel position of interest

        px = spatialPoint2px(lyr, point)

        if 0 <= px.x() < lyr.width() and 0 <= px.y() < lyr.height():
            return SamplingBlockDescription(point, lyr, QRect(px, px))
        else:
            return None

    def profiles(self,
                 profileBlock: SpectralProfileBlock,
                 blockDescription: SamplingBlockDescription) -> SpectralProfileBlock:
        # nothing else to do here
        assert profileBlock.n_profiles() == 1
        return profileBlock


class KernelProfileSamplingMode(SpectralProfileSamplingMode):
    NO_AGGREGATION = 'no_aggregation'
    AGGREGATE_MEAN = 'mean'
    AGGREGATE_MEDIAN = 'median'
    AGGREGATE_MIN = 'min'
    AGGREGATE_MAX = 'max'

    RX_KERNEL_SIZE = re.compile(r'(?P<x>\d+)x(?P<y>\d+)')

    KERNEL_MODEL = OptionListModel()
    KERNEL_MODEL.addOptions([
        Option('3x3', toolTip='Reads the 3x3 pixel around the cursor location'),
        Option('5x5', toolTip='Reads the 5x5 pixel around the cursor location'),
        Option('7x7', toolTip='Reads the 7x7 pixel around the cursor location'),
    ]
    )

    AGGREGATION_MODEL = OptionListModel()
    AGGREGATION_MODEL.addOptions([
        Option(NO_AGGREGATION, name='All profiles', toolTip='Keep all profiles'),
        Option(AGGREGATE_MEAN, name='Mean', toolTip='Mean profile'),
        Option(AGGREGATE_MEDIAN, name='Median', toolTip='Median profile'),
        Option(AGGREGATE_MIN, name='Min', toolTip='Min value profile'),
        Option(AGGREGATE_MAX, name='Max', toolTip='Max value profile'),
    ])

    def __init__(self):
        super().__init__()

        self.mKernel = OptionTreeNode(KernelProfileSamplingMode.KERNEL_MODEL)
        self.mKernel.setName('Kernel')

        self.mAggregation = OptionTreeNode(KernelProfileSamplingMode.AGGREGATION_MODEL)
        self.mAggregation.setName('Aggregation')

        self.mKernel.sigUpdated.connect(self.updateProfilesPerClickNode)
        self.mAggregation.sigUpdated.connect(self.updateProfilesPerClickNode)

        self.mProfilesPerClick = TreeNode()
        self.mProfilesPerClick.setName('Profiles')
        self.mProfilesPerClick.setToolTip('Profiles per click')
        self.updateProfilesPerClickNode()

    def clone(self):

        mode = KernelProfileSamplingMode()
        mode.setKernelSize(*self.kernelSize())
        mode.setAggregation(self.aggregation())
        return mode

    def nodes(self) -> typing.List[TreeNode]:
        return [self.mKernel, self.mAggregation, self.mProfilesPerClick]

    def name(self) -> str:
        return 'Kernel'

    def settings(self) -> dict:
        settings = super(KernelProfileSamplingMode, self).settings()
        settings['kernel'] = '{}x{}'.format(*self.kernelSize())
        settings['aggregation'] = self.aggregation()
        return settings

    def updateProfilesPerClickNode(self):
        """
        Updates the description on how many profiles will be created
        """
        if self.aggregation() == KernelProfileSamplingMode.NO_AGGREGATION:
            x, y = self.kernelSize()
            nProfiles = x * y
        else:
            nProfiles = 1
        self.mProfilesPerClick.setValue(nProfiles)

    def setKernelSize(self, x: int, y: int = None):
        """
        Sets the kernel size
        :param x: str | int
        :param y: int (optional)
        """
        if isinstance(x, str):
            match = self.RX_KERNEL_SIZE.match(x)
            x = int(match.group('x'))
            y = int(match.group('y'))
        assert isinstance(x, int) and x > 0
        if y is None:
            y = x

        assert isinstance(y, int) and y > 0
        kernel_string = f'{x}x{y}'
        option = KernelProfileSamplingMode.KERNEL_MODEL.findOption(kernel_string)
        if not isinstance(option, Option):
            # make new kernel available to other kernel nodes
            option = Option(f'{x}x{y}', toolTip=f'Reads the {x}x{y} pixel around the cursor location.')
            KernelProfileSamplingMode.KERNEL_MODEL.addOption(option)

        self.mKernel.setOption(option)

    def kernelSize(self) -> typing.Tuple[int, int]:
        """
        Returns the kernel size
        :return: (int x, int y)
        """

        kernel_string = self.mKernel.option().value()
        match = self.RX_KERNEL_SIZE.match(kernel_string)
        return int(match.group('x')), int(match.group('y'))

    def setAggregation(self, aggregation: str):
        option = KernelProfileSamplingMode.AGGREGATION_MODEL.findOption(aggregation)
        assert isinstance(option, Option), f'"{aggregation}" is not supported'
        self.mAggregation.setOption(option)

    def aggregation(self) -> str:
        return self.mAggregation.option().value()

    def htmlSummary(self) -> str:
        S = self.settings()
        info = f'Kernel <i>{S["kernel"]}'
        if S['aggregation']:
            info += f' {S["aggregation"]}'
        info += '</i>'
        return info

    def samplingBlockDescription(self, lyr: QgsRasterLayer, point: typing.Union[QgsPointXY, SpatialPoint]) \
            -> SamplingBlockDescription:

        assert isinstance(lyr, QgsRasterLayer)
        if not isinstance(point, SpatialPoint):
            assert isinstance(point, QgsPointXY)
            point = SpatialPoint(lyr.crs(), point.x(), point.y())

        centerPx: QPoint = spatialPoint2px(lyr, point)
        x, y = self.kernelSize()
        meta = {'x': x, 'y': y,
                'aggregation': self.aggregation()}

        xmin = math.floor(centerPx.x() - (x - 1) * 0.5)
        ymin = math.floor(centerPx.y() - (y - 1) * 0.5)

        xmax = xmin + x - 1
        ymax = ymin + y - 1

        # fit reading bounds to existing pixels
        xmin, ymin = max(0, xmin), max(0, ymin)
        xmax, ymax = min(lyr.width() - 1, xmax), min(lyr.height() - 1, ymax)

        if xmax < xmin or ymax < ymin:
            # no overlap with existing pixel
            return None
        else:
            rect = QRect(QPoint(xmin, ymin), QPoint(xmax, ymax))
            return SamplingBlockDescription(point, lyr, rect, meta=meta)

    def profiles(self,
                 profileBlock: SpectralProfileBlock,
                 blockDescription: SamplingBlockDescription) -> SpectralProfileBlock:
        meta = blockDescription.meta()
        x, y = meta['x'], meta['y']
        aggregation = meta['aggregation']
        data: np.ndarray = profileBlock.data()
        spectra_settings = profileBlock.spectralSetting()
        result: SpectralProfileBlock = None
        if aggregation == KernelProfileSamplingMode.NO_AGGREGATION:
            return profileBlock
        elif aggregation == KernelProfileSamplingMode.AGGREGATE_MEAN:
            result = SpectralProfileBlock(np.nanmean(data, axis=(1, 2)), spectra_settings)
        elif aggregation == KernelProfileSamplingMode.AGGREGATE_MEDIAN:
            result = SpectralProfileBlock(np.nanmedian(data, axis=(1, 2)), spectra_settings)
        elif aggregation == KernelProfileSamplingMode.AGGREGATE_MIN:
            result = SpectralProfileBlock(np.nanmin(data, axis=(1, 2)), spectra_settings)
        elif aggregation == KernelProfileSamplingMode.AGGREGATE_MAX:
            result = SpectralProfileBlock(np.nanmax(data, axis=(1, 2)), spectra_settings)

        posX = profileBlock.mPositionsX
        posY = profileBlock.mPositionsY
        if isinstance(posX, np.ndarray):
            if aggregation != KernelProfileSamplingMode.NO_AGGREGATION:
                posX = np.nanmean(posX)
                posY = np.nanmean(posY)

            result.setPositions(posX, posY, profileBlock.crs())

        return result


class SpectralProfileSamplingModeModel(QAbstractListModel):
    SAMPLING_MODES: typing.Dict[str, SpectralProfileSamplingMode] = dict()

    @staticmethod
    def registerMode(mode: SpectralProfileSamplingMode):
        assert isinstance(mode, SpectralProfileSamplingMode)
        if mode.__class__.__name__ not in SpectralProfileSamplingModeModel.SAMPLING_MODES.keys():
            SpectralProfileSamplingModeModel.SAMPLING_MODES[mode.__class__.__name__] = mode

    @staticmethod
    def registeredModes() -> typing.List[SpectralProfileSamplingMode]:
        return list(SpectralProfileSamplingModeModel.SAMPLING_MODES.values())

    def __init__(self, *args, **kwds):

        super(SpectralProfileSamplingModeModel, self).__init__(*args, **kwds)

        self.mSamplingMethods = []
        self.initModes()

    def __getitem__(self, slice):
        return self.mSamplingMethods[slice]

    def __iter__(self):
        return iter(self.mSamplingMethods)

    def __len__(self):
        return len(self.mSamplingMethods)

    def initModes(self):

        self.beginResetModel()
        self.mSamplingMethods.clear()
        for mode in SpectralProfileSamplingModeModel.SAMPLING_MODES.values():
            self.mSamplingMethods.append(mode.__class__())
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mSamplingMethods)

    def data(self, index: QModelIndex, role: int) -> typing.Any:

        if not index.isValid():
            return None

        samplingMode = self.mSamplingMethods[index.row()]
        if not isinstance(samplingMode, SpectralProfileSamplingMode):
            return None

        if role == Qt.DisplayRole:
            return samplingMode.name()
        if role == Qt.ToolTipRole:
            return samplingMode.tooltip()
        if role == Qt.DecorationRole:
            return samplingMode.icon()
        if role == Qt.UserRole:
            return samplingMode
        return None


class FieldGeneratorNode(TreeNode):
    """
    Base-class for nodes that generate values for a QgsFeature field
    """

    def __init__(self, *args, **kwds):
        super(FieldGeneratorNode, self).__init__(*args, **kwds)
        self.mField: QgsField = None
        self.setCheckable(True)
        self.setCheckState(Qt.Unchecked)

    def setField(self, field: QgsField):
        """
        Defines the QgsField the node is linked to
        :param field:
        :type field:
        :return:
        :rtype:
        """
        assert isinstance(field, QgsField)
        # todo: evaluate constraints. if field has to be present -> make uncheckable
        self.mField = field

    def field(self) -> QgsField:
        """
        Returns the QgsField the node is linked to
        :return:
        :rtype:
        """
        return self.mField

    def validate(self) -> typing.Tuple[bool, typing.List[str]]:
        """
        Returns (True, []) if all settings are fine (default) or (False, ['list of error messages']) if not.
        :return:
        :rtype:
        """
        if not isinstance(self.field(), QgsField):
            return False, 'Field is not set'
        return True, []


class GeometryGeneratorNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def geometry(self, point_clicked: SpatialPoint) -> QgsGeometry:

        return None

    def setGeometryType(self, wkbType: QgsWkbTypes.GeometryType):
        assert isinstance(wkbType, QgsWkbTypes.GeometryType)

        if wkbType == QgsWkbTypes.PointGeometry:
            self.setIcon(QIcon(r':/images/themes/default/mActionCapturePoint.svg'))
            self.setName('Point')
        else:
            raise NotImplementedError()


class SpectralProfileGeneratorNode(FieldGeneratorNode):

    def __init__(self, *args, **kwds):
        super(SpectralProfileGeneratorNode, self).__init__(*args, **kwds)
        self.setIcon(QIcon(r':/qps/ui/icons/profile.svg'))
        self.setCheckState(Qt.Checked)
        self.sigUpdated.connect(self.onChildNodeUpdate)
        self.mSourceNode = SpectralProfileSourceNode('Source')
        self.mSamplingNode = SpectralProfileSamplingModeNode('Sampling')
        self.appendChildNodes([self.mSourceNode, self.mSamplingNode])

    def validate(self) -> typing.Tuple[bool, typing.List[str]]:

        is_valid, errors = super().validate()

        if is_valid:
            if not isinstance(self.profileSource(), SpectralProfileSource):
                errors.append('No source')
            if not isinstance(self.sampling(), SpectralProfileSamplingMode):
                errors.append('No sampling')

        return len(errors) == 0, errors

    def profileSource(self) -> SpectralProfileSource:
        return self.mSourceNode.profileSource()

    def setProfileSource(self, source: SpectralProfileSource):
        self.mSourceNode.setSpectralProfileSource(source)

    def sampling(self) -> SpectralProfileSamplingMode:
        return self.mSamplingNode.profileSamplingMode()

    def setSampling(self, mode: SpectralProfileSamplingMode) -> SpectralProfileSamplingMode:
        return self.mSamplingNode.setProfileSamplingMode(mode)

    def samplingBlockDescription(self, point: typing.Union[QgsPointXY, SpatialPoint], mapCanvas: QgsMapCanvas) \
            -> SamplingBlockDescription:
        """
        Returns a description of the pixel block to be sampled from a raster layer
        :param point:
        :return: QgsRasterLayer, QRect
        """
        source = self.profileSource()
        if not isinstance(source, SpectralProfileSource):
            return None

        # resolve the source layer
        layer = source.rasterLayer(mapCanvas=mapCanvas, position=point)
        if not isinstance(layer, QgsRasterLayer):
            return None

        # get the requested pixel positions for the sampling
        return self.sampling().samplingBlockDescription(layer, point)

    def profiles(self,
                 profileBlock: SpectralProfileBlock,
                 blockDescription: SamplingBlockDescription,
                 ) -> SpectralProfileBlock:
        return self.sampling().profiles(profileBlock, blockDescription)

    def onChildNodeUpdate(self):
        """
        Updates the node description, which is a summary of all its setting
        """
        info = []
        tt = []

        source = self.mSourceNode.profileSource()
        if not isinstance(source, SpectralProfileSource):
            info.append('<no source>')
            tt.append('<no source>')
        else:
            info.append(source.name())
            tt.append(f'Source {source.name()} ({source.mUri})')

        sampling = self.mSamplingNode.profileSamplingMode()
        info.append(sampling.htmlSummary())
        tt.append(sampling.tooltip())

        info = ' '.join(info)
        tt = '<br>'.join(tt)
        self.setValue(info)
        self.setToolTip(tt)


class StandardFieldGeneratorNode(FieldGeneratorNode):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mExpressionString: str = ''

    def expression(self) -> QgsExpression:
        return QgsExpression(self.mExpressionString)

    def setExpression(self, expression: typing.Union[str, QgsExpression]):
        if isinstance(expression, QgsExpression):
            expression = expression.expression()
        self.mExpressionString = expression
        self.setValue(self.mExpressionString)

    def validate(self) -> typing.Tuple[bool, typing.List[str]]:

        is_valid, errors = super().validate()

        if is_valid:
            expr = self.expression()

            # todo: set context

            if expr.expression().strip() == '':
                errors.append('undefined')
            else:
                if not expr.isValid():
                    if expr.hasParserError():
                        errors.append(expr.parserErrorString().strip())
                    if expr.hasEvalError():
                        errors.append(expr.evalErrorString().strip())

        return len(errors) == 0, errors


class SpectralFeatureGeneratorExpressionContextGenerator(QgsExpressionContextGenerator):
    """
    A generator to create the context for a new SpectralProfile feature
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mNode: SpectralFeatureGeneratorNode = None

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()
        scope = QgsExpressionContextScope()
        scope.addVariable(QgsExpressionContextScope.StaticVariable(SCOPE_VAR_SAMPLE_CLICK, 1))
        scope.addVariable(QgsExpressionContextScope.StaticVariable(SCOPE_VAR_SAMPLE_FEATURE, 1))
        context.appendScope(scope)
        return context


RX_MEMORY_UID = re.compile(r'.*uid=[{](?P<uid>[^}]+)}.*')


class SpectralFeatureGeneratorNode(TreeNode):

    def __init__(self, *args, **kwds):
        # assert isinstance(slw, SpectralLibraryWidget)
        super(SpectralFeatureGeneratorNode, self).__init__(*args, **kwds)

        self.setIcon(QIcon(r':/qps/ui/icons/speclib.svg'))
        self.mSpeclibWidget: SpectralLibraryWidget = None
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.mExpressionContextGenerator = SpectralFeatureGeneratorExpressionContextGenerator()
        self.mExpressionContextGenerator.mNode = self

    def expressionContextGenerator(self) -> SpectralFeatureGeneratorExpressionContextGenerator:
        return self.mExpressionContextGenerator

    def copy(self):
        g = SpectralFeatureGeneratorNode()
        g.setSpeclibWidget(self.speclibWidget())

        nodes = self.createFieldNodes(self.fieldNodeNames())
        g.appendChildNodes(nodes)

        return g

    def speclibWidget(self) -> SpectralLibraryWidget:
        return self.mSpeclibWidget

    def speclib(self) -> QgsVectorLayer:
        if self.mSpeclibWidget:
            return self.mSpeclibWidget.speclib()
        else:
            return None

    def setSpeclibWidget(self, speclibWidget: SpectralLibraryWidget):

        assert speclibWidget is None or isinstance(speclibWidget, SpectralLibraryWidget)

        oldSpeclib = self.speclib()
        if isinstance(oldSpeclib, QgsVectorLayer):
            oldSpeclib.nameChanged.disconnect(self.updateSpeclibName)

        OLD_NODES = dict()
        for n in self.childNodes():
            OLD_NODES[n.name()] = n

        self.removeAllChildNodes()
        self.mSpeclibWidget = None

        if isinstance(speclibWidget, SpectralLibraryWidget):
            self.mSpeclibWidget = speclibWidget
            speclib = self.mSpeclibWidget.speclib()
            if isinstance(speclib, QgsVectorLayer):
                speclib.nameChanged.connect(self.updateSpeclibName)
                self.updateSpeclibName()

                new_nodes = []

                # 1. create the geometry generator node
                gnode = GeometryGeneratorNode()
                gnode.setGeometryType(speclib.geometryType())
                new_nodes.append(gnode)

                # 2. create spectral profile field nodes
                # new_nodes.append(self.createFieldNodes(profile_fields(speclib)))

                # other_fields = [f for f in speclib.fields() if not f]
                new_nodes.extend(self.createFieldNodes(speclib.fields()))
                # 3. add other fields

                self.appendChildNodes(new_nodes)

    def fieldNodes(self) -> typing.List[FieldGeneratorNode]:
        return [n for n in self.childNodes() if isinstance(n, FieldGeneratorNode)]

    def fieldNodeNames(self) -> typing.List[str]:
        return [n.field().name() for n in self.fieldNodes()]

    def createFieldNodes(self, fieldnames: typing.Union[typing.List[str], QgsField, QgsFields, str]):
        """
        Create a list of TreeNodes for the given list of field names
        :param fieldnames:
        :return:
        """

        if isinstance(fieldnames, QgsField):
            fieldnames = [fieldnames.name()]
        elif isinstance(fieldnames, QgsFields):
            fieldnames = fieldnames.names()
        elif isinstance(fieldnames, str):
            fieldnames = [fieldnames]

        for fieldname in fieldnames:
            assert isinstance(fieldname, str)

        fieldnames = [n for n in fieldnames if
                      n not in self.fieldNodeNames() and
                      n in self.speclib().fields().names()]

        new_nodes: typing.List[FieldGeneratorNode] = []

        if not self.speclib():
            # no speclibs connected, no nodes to create
            return new_nodes

        pfield_names = profile_field_names(self.speclib())
        for fname in fieldnames:
            new_node = None
            idx = self.speclib().fields().lookupField(fname)
            if idx < 0:
                continue

            field: QgsField = self.speclib().fields().at(idx)
            if field.isReadOnly():
                continue

            constraints: QgsFieldConstraints = field.constraints()

            if fname in pfield_names:
                new_node = SpectralProfileGeneratorNode(fname)

            else:
                new_node = StandardFieldGeneratorNode(fname)

            if isinstance(new_node, FieldGeneratorNode):
                new_node.setField(field)
                new_nodes.append(new_node)

        return new_nodes

    def spectralProfileGeneratorNodes(self) -> typing.List[SpectralProfileGeneratorNode]:
        """
        Returns a list of SpectralProfileGeneratorNodes
        :return:
        """
        return [n for n in self.childNodes() if isinstance(n, SpectralProfileGeneratorNode)]

    def spectralProfileSources(self) -> typing.Set[SpectralProfileSource]:
        """
        Returns the set of used SpectralProfileSources
        :return: set of SpectralProfileSources
        """
        return {n.profileSource() for n in self.spectralProfileGeneratorNodes() if
                isinstance(n.profileSource(), SpectralProfileSource)}

    def updateSpeclibName(self):
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            self.setName(speclib.name())
            dp_name = speclib.dataProvider().name()
            source = speclib.source()
            if dp_name == 'memory':
                matches = RX_MEMORY_UID.match(source)
                if matches:
                    source = f'memory uid={matches.group("uid")}'
        # self.setValue(source)

    def updateNodeOrder(self):
        """
        Updates the node order
        :return:
        """
        pass


class SpectralProfileBridge(TreeModel):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mSrcModel = SpectralProfileSourceModel()
        self.mDstModel = SpectralLibraryWidgetListModel()
        self.mDefaultSource: SpectralProfileSource = None

        self.mLastDestinations: typing.Set[str] = set()

        self.mProfileSamplingModeModel = SpectralProfileSamplingModeModel()
        self.mSrcModel.rowsRemoved.connect(self.updateSourceReferences)
        # self.mSrcModel.rowsInserted.connect(lambda : self.updateListColumn(self.cnSrc))

        self.mDstModel.rowsRemoved.connect(self.updateDestinationReferences)
        # self.mDstModel.rowsInserted.connect(lambda : self.updateListColumn(self.cnDst))

        self.mClickCount: typing.Dict[str, int] = dict()

        self.mTasks = dict()

        self.mSnapToPixelCenter: bool = False
        self.mMinimumSourceNameSimilarity = 0.5

    def addCurrentProfilesToSpeclib(self):
        """
        Makes current profiles in connected spectral library destinations permanent
        """
        for slw in self.destinations():
            sl = slw.speclib()
            if isinstance(sl, QgsVectorLayer) and sl.id() in self.mLastDestinations:
                slw.addCurrentProfilesToSpeclib()

    def setMinimumSourceNameSimilarity(self, threshold: float):
        assert 0 <= threshold <= 1.0
        self.mMinimumSourceNameSimilarity = threshold

    def minimumSourceNameSimilarity(self) -> float:
        return self.mMinimumSourceNameSimilarity

    def updateSourceReferences(self):
        sources = self.sources()
        for g in self[:]:
            for node in g.spectralProfileGeneratorNodes():
                node: SpectralProfileGeneratorNode
                if node.profileSource() not in sources:
                    # remove reference on removed source
                    node.setProfileSource(None)
                    s = ""

    def updateDestinationReferences(self):
        to_remove = []
        for g in self[:]:
            g: SpectralFeatureGeneratorNode
            if g.speclibWidget() not in self.destinations():
                # remove node widget reference
                to_remove.append(g)
        self.removeFeatureGenerators(to_remove)

    def __iter__(self) -> typing.Iterator[SpectralFeatureGeneratorNode]:
        return iter(self.featureGenerators(speclib=False, checked=False))

    def __len__(self):
        return len(self.rootNode().childNodes())

    def __getitem__(self, slice):
        return self.rootNode().childNodes()[slice]

    def loadProfiles(self,
                     spatialPoint: SpatialPoint,
                     mapCanvas: QgsMapCanvas = None,
                     add_permanent: bool = None,
                     runAsync: bool = False) -> typing.Dict[str, typing.List[QgsFeature]]:
        """
        Loads the spectral profiles as defined in the bridge model
        :param spatialPoint:
        :param mapCanvas:
        :param runAsync:
        :return:
        """
        self.mLastDestinations.clear()
        RESULTS: typing.Dict[str, typing.List[QgsFeature]] = dict()

        # 1. collect infos on sources, pixel positions and additional metadata

        URI2LAYER: typing.Dict[str, QgsRasterLayer] = dict()
        SAMPLING_BLOCK_DESCRIPTIONS: typing.Dict[SpectralProfileGeneratorNode, SamplingBlockDescription] = dict()
        SAMPLING_FEATURES: typing.List[SpectralFeatureGeneratorNode] = []
        # 1. collect source infos
        for fgnode in self:
            fgnode: SpectralFeatureGeneratorNode

            if not (isinstance(fgnode.speclib(), QgsVectorLayer) and fgnode.checked()):
                continue

            use_feature_generator: bool = False
            for pgnode in fgnode.spectralProfileGeneratorNodes():
                pgnode: SpectralProfileGeneratorNode

                if not pgnode.checked():
                    continue

                sbd: SamplingBlockDescription = pgnode.samplingBlockDescription(spatialPoint, mapCanvas)
                if isinstance(sbd, SamplingBlockDescription):
                    use_feature_generator = True
                    SAMPLING_BLOCK_DESCRIPTIONS[pgnode] = sbd

            if use_feature_generator:
                SAMPLING_FEATURES.append(fgnode)

        # order by source the blocks we need to read
        SOURCE_BLOCKS: typing.Dict[str, typing.Dict[HashableRect, SpectralProfileBlock]] = dict()
        for pgnode, sbd in SAMPLING_BLOCK_DESCRIPTIONS.items():
            sbd: SamplingBlockDescription
            uri = sbd.uri()
            URI2LAYER[uri] = sbd.layer()
            source_blocks: typing.Dict[HashableRect, np.ndarray] = SOURCE_BLOCKS.get(uri, dict())
            source_blocks[sbd.rect()] = None
            SOURCE_BLOCKS[uri] = source_blocks

        # todo: optimize block reading

        # read blocks
        for uri, BLOCKS in SOURCE_BLOCKS.items():
            layer: QgsRasterLayer = URI2LAYER[uri]
            wl, wlu = parseWavelength(layer)
            if wl is None:
                wl = list(range(layer.bandCount()))

            for rect in list(BLOCKS.keys()):
                array = rasterLayerArray(layer, rect)


                if not isinstance(array, np.ndarray):
                    continue
                is_nodata = np.zeros(array.shape, dtype=bool)
                dp: QgsRasterDataProvider = layer.dataProvider()
                for b in range(dp.bandCount()):
                    band = b + 1
                    band_mask = is_nodata[b, :, :]
                    if dp.sourceHasNoDataValue(band):
                        no_data = dp.sourceNoDataValue(band)
                        band_mask = band_mask | (array[b, :, :] == no_data)
                    for no_data in dp.userNoDataValues(band):
                        band_mask = band_mask | (array[b, :, :] == no_data)
                    is_nodata[b, :, :] = band_mask
                if is_nodata.all():
                    continue
                array = np.ma.array(array, mask=is_nodata)
                settings = SpectralSetting(wl, xUnit=wlu)
                profileBlock = SpectralProfileBlock(array, settings)

                px_x, px_y = np.meshgrid(np.arange(rect.width()), np.arange(rect.height()))
                px_x = px_x + rect.x()
                px_y = px_y + rect.y()
                geo_x, geo_y = px2geocoordinatesV2(layer, px_x, px_y)

                # get shift between pixel center and true click positions
                if not self.mSnapToPixelCenter:
                    pointClicked = spatialPoint.toCrs(layer.crs())
                    pointPxCenter = px2spatialPoint(layer, spatialPoint2px(layer, pointClicked))
                    dx = pointPxCenter.x() - pointClicked.x()
                    dy = pointPxCenter.y() - pointClicked.y()
                    geo_x -= dx
                    geo_y -= dy

                profileBlock.setPositions(geo_x, geo_y, layer.crs())
                BLOCKS[rect] = profileBlock

        # 3. calculate required source profiles
        for fgnode in SAMPLING_FEATURES:
            assert isinstance(fgnode, SpectralFeatureGeneratorNode)
            speclib = fgnode.speclib()
            if not speclib:
                continue

            new_speclib_features: typing.List[QgsFeature] = []

            # calculate final profile value dictionaries
            FINAL_PROFILE_VALUES: typing.Dict[SpectralProfileGeneratorNode,
                                              typing.List[typing.Tuple[QByteArray, QgsGeometry]]] = dict()

            for pgnode in fgnode.spectralProfileGeneratorNodes():
                pgnode: SpectralProfileGeneratorNode

                sbd: SamplingBlockDescription = SAMPLING_BLOCK_DESCRIPTIONS.get(pgnode, None)
                if not isinstance(sbd, SamplingBlockDescription):
                    continue

                inputProfileBlock: SpectralProfileBlock = SOURCE_BLOCKS[sbd.uri()].get(sbd.rect(), None)
                if isinstance(inputProfileBlock, SpectralProfileBlock):
                    # convert profileBlock to final profiles
                    outputProfileBlock: SpectralProfileBlock = pgnode.profiles(inputProfileBlock, sbd)
                    outputProfileBlock.toCrs(speclib.crs())

                    FINAL_PROFILE_VALUES[pgnode] = []
                    for _, ba, g in outputProfileBlock.profileValueByteArrays():
                        FINAL_PROFILE_VALUES[pgnode].append((ba, g))

            n_new_features = 0
            for node, profiles in FINAL_PROFILE_VALUES.items():
                n_new_features = max(n_new_features, len(profiles))

            for i in range(n_new_features):
                new_feature: QgsFeature = QgsFeature(fgnode.speclib().fields())

                # set profile fields
                # let's say the sampling methods for profile fields A, B and C return 1, 3 and 4 profiles, then
                # we create 4 new features with
                # feature 1: A, B, C
                # feature 2: None, B, C
                # feature 4: None, None, C

                for pgnode, profileInputs in FINAL_PROFILE_VALUES.items():

                    if len(profileInputs) > 0:
                        # pop 1st profile
                        byteArray, geometry = profileInputs.pop(0)
                        assert isinstance(byteArray, QByteArray)
                        assert isinstance(geometry, QgsGeometry)
                        if new_feature.geometry().type() in [QgsWkbTypes.UnknownGeometry, QgsWkbTypes.NullGeometry]:
                            new_feature.setGeometry(geometry)
                        new_feature[pgnode.field().name()] = byteArray

                new_speclib_features.append(new_feature)

            if isinstance(speclib, QgsVectorLayer) and len(new_speclib_features) > 0:
                # increase click count
                self.mClickCount[speclib.id()] = self.mClickCount.get(speclib.id(), 0) + 1

            for i, new_feature in enumerate(new_speclib_features):
                # create context for other values
                scope = fgnode.speclib().createExpressionContextScope()
                scope.setVariable(SCOPE_VAR_SAMPLE_CLICK, self.mClickCount[speclib.id()])
                scope.setVariable(SCOPE_VAR_SAMPLE_FEATURE, i + 1)
                context = fgnode.expressionContextGenerator().createExpressionContext()
                context.setFeature(new_feature)
                context.appendScope(scope)
                for node in fgnode.childNodes():
                    if isinstance(node, StandardFieldGeneratorNode) and node.checked():
                        expr = node.expression()
                        if expr.isValid():
                            new_feature[node.field().name()] = expr.evaluate(context)
            RESULTS[fgnode.speclib().id()] = new_speclib_features[:]
            fgnode.speclibWidget().setCurrentProfiles(new_speclib_features, make_permanent=add_permanent)
            self.mLastDestinations.add(fgnode.speclib().id())

        return RESULTS

    def profileSamplingModeModel(self) -> SpectralProfileSamplingModeModel:
        return self.mProfileSamplingModeModel

    def spectralLibraryModel(self) -> SpectralLibraryWidgetListModel:
        return self.mDstModel

    def destinations(self) -> typing.List[SpectralLibraryWidget]:
        return self.spectralLibraryModel().spectralLibraryWidgets()

    def dataSourceModel(self) -> SpectralProfileSourceModel:
        return self.mSrcModel

    def createFeatureGenerator(self) -> SpectralFeatureGeneratorNode:

        if len(self) == 0:
            g = SpectralFeatureGeneratorNode()

            if len(self.mDstModel) > 0:
                g.setSpeclibWidget(self.mDstModel[0])
        else:
            g = self[-1].copy()

        self.addFeatureGenerator(g)
        self.setDefaultDestination(g)
        self.setDefaultSources(g)
        return g

    def addFeatureGenerator(self, generator: SpectralFeatureGeneratorNode):

        if generator not in self.rootNode().childNodes():
            self.rootNode().appendChildNodes(generator)

    def featureGenerators(self, speclib:bool = True, checked:bool = True) -> typing.List[SpectralFeatureGeneratorNode]:
        for n in self.rootNode().childNodes():
            if isinstance(n, SpectralFeatureGeneratorNode):
                if speclib == True and not isinstance(n.speclib(), QgsVectorLayer):
                    continue
                if checked == True and not n.checked():
                    continue
                yield n

    def removeFeatureGenerators(self, generators: typing.List[SpectralFeatureGeneratorNode]):
        if isinstance(generators, SpectralFeatureGeneratorNode):
            generators = [generators]
        for g in generators:
            assert isinstance(g, SpectralFeatureGeneratorNode)
            assert g in self.rootNode().childNodes()
        self.rootNode().removeChildNodes(generators)

    def flags(self, index: QModelIndex):

        if not index.isValid():
            return Qt.NoItemFlags
        col = index.column()

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        node = index.data(Qt.UserRole)
        if col == 0:
            if isinstance(node, TreeNode) and node.isCheckable():
                flags = flags | Qt.ItemIsUserCheckable
            if isinstance(node, SpectralFeatureGeneratorNode):
                flag = flags | Qt.ItemIsEditable

        if col == 1:
            if isinstance(node, (SpectralFeatureGeneratorNode, SpectralProfileSourceNode,
                                 SpectralProfileSamplingModeNode, StandardFieldGeneratorNode)):
                if isinstance(node, StandardFieldGeneratorNode):
                    s = ""
                flags = flags | Qt.ItemIsEditable

        return flags

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        # handle missing data appearence
        value = super().data(index, role)
        node = super().data(index, role=Qt.UserRole)
        c = index.column()
        if index.isValid():
            if isinstance(node, SpectralFeatureGeneratorNode):
                if not isinstance(node.speclib(), QgsVectorLayer):
                    if c == 0:
                        if role == Qt.DisplayRole:
                            return 'Missing Spectral Library'

                        if role == Qt.ForegroundRole:
                            return QColor('grey')

                        if role == Qt.FontRole:
                            f = QFont()
                            f.setItalic(True)
                            return f

                    if role == Qt.ToolTipRole:
                        return 'Select a Spectral Library Window'
                else:
                    speclib = node.speclib()

                    if role == Qt.ToolTipRole:
                        tt = f'Spectral Library: {speclib.name()}<br>' \
                             f'Source: {speclib.source()}<br>' \
                             f'Features: {speclib.featureCount()}'
                        return tt

            if isinstance(node, FieldGeneratorNode):
                field: QgsField = node.field()
                editor = field.editorWidgetSetup().type()

                if c == 0:
                    if role == Qt.ToolTipRole:
                        if isinstance(field, QgsField):
                            return f'"{field.displayName()}" ' \
                                   f'{field.displayType(True)} {editor}'

                if c == 1:
                    is_checked = node.checked()
                    is_required = not node.isCheckable()
                    is_valid, errors = node.validate()
                    if not is_valid:
                        if role == Qt.DisplayRole:
                            if is_checked or is_required:
                                return '<span style="color:red;font-style:italic">{}</span>'.format(''.join(errors))
                            else:
                                return '<span style="color:grey;font-style:italic">{}</span>'.format(''.join(errors))
                        if role == Qt.ToolTipRole:
                            return '<br>'.join(errors)
                        if role == Qt.FontRole:
                            f = QFont()
                            f.setItalic(True)
                            return f
                    else:
                        if isinstance(node, StandardFieldGeneratorNode):

                            expr = str(node.mExpressionString).strip()
                            if expr == '':
                                if role == Qt.DisplayRole:
                                    return '<span style="color:grey;font-style:italic">undefined</span>'

        return value

    def setData(self, index: QModelIndex, value: typing.Any, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        col = index.column()

        node = index.data(Qt.UserRole)
        c0 = c1 = col
        r0 = r1 = index.row()
        roles = [role]
        changed = False  # set only True if not handled by underlying TreeNode

        if role == Qt.CheckStateRole \
                and isinstance(node, TreeNode) \
                and node.isCheckable() and \
                value in [Qt.Checked, Qt.Unchecked]:
            changed = True
            node.setCheckState(value)
            # return True
            c0 = 1
            c1 = 1
            roles.append(Qt.DisplayRole)

        elif isinstance(node, SpectralFeatureGeneratorNode):
            if col in [0, 1] and role == Qt.EditRole:
                if isinstance(value, SpectralLibraryWidget):
                    changed = True
                    node.setSpeclibWidget(value)
                    c0 = 0
                    c1 = 1
                    roles = [Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole]

        elif isinstance(node, SpectralProfileGeneratorNode):
            if isinstance(value, SpectralProfileSamplingMode):
                node.setProfileSamplingMode(value)
                changed = False
                # important! node.setProfileSamplingMode has already updated the node
            elif value is None or isinstance(value, SpectralProfileSource):
                node.setProfileSource(value)
                changed = False

        elif isinstance(node, SpectralProfileSourceNode):
            assert value is None or isinstance(value, SpectralProfileSource)
            node.setSpectralProfileSource(value)

        elif isinstance(node, SpectralProfileSamplingModeNode):
            if isinstance(value, SpectralProfileSamplingMode):
                node.setProfileSamplingMode(value)

        elif isinstance(node, OptionTreeNode):
            if isinstance(value, Option):
                node.setOption(value)

        elif isinstance(node, StandardFieldGeneratorNode):
            if isinstance(value, (str, QgsExpression)):
                node.setExpression(value)

        if changed:
            self.dataChanged.emit(self.index(r0, c0, parent=index.parent()),
                                  self.index(r1, c1, parent=index.parent()),
                                  roles)
        return changed

    def addRasterLayer(self, layer: QgsRasterLayer):
        if layer.isValid():
            source = StandardLayerProfileSource(layer.source(), layer.name(), layer.providerType())
            layer.nameChanged.connect(lambda *args, lyr=layer, src=source: src.setName(lyr.name()))
            self.addSources(source)

    def addSources(self, source: SpectralProfileSource):
        n = len(self.mSrcModel)
        src = self.mSrcModel.addSources(source)

        # if this is the first source, set it to all existing relations
        if n == 0 and isinstance(src, SpectralProfileSource):
            for r in self.bridgeItems():
                r.setSource(src)

    def removeSources(self, sources: typing.List[typing.Any]):

        self.mSrcModel.removeSources(sources)

    def sources(self) -> typing.List[SpectralProfileSource]:
        return self.mSrcModel.sources()

    def addSpectralLibraryWidgets(self, slws: typing.Union[
        SpectralLibraryWidget, typing.Iterable[SpectralLibraryWidget]]):

        if not isinstance(slws, typing.Iterable):
            slws = [slws]

        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)

        added_targets = []
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            target = self.mDstModel.addSpectralLibraryWidget(slw)
            if target:
                added_targets.append(target)

        if len(added_targets) == 0:
            return
        generators = self[:]
        missing_target_generators = [g for g in generators
                                     if not isinstance(g.speclibWidget(), SpectralLibraryWidget)]
        if len(generators) == 0:
            # create a new generator for the 1st speclib target
            g = SpectralFeatureGeneratorNode()
            g.setSpeclibWidget(added_targets[0])
            self.setDefaultSources(g)
        else:
            # add the speclib targets to existing generators
            for g in missing_target_generators:
                if len(added_targets) > 0:
                    target = added_targets.pop(0)
                g.setSpeclibWidget(target)
                self.setDefaultSources(g)

    def setDefaultDestination(self, generator: SpectralFeatureGeneratorNode):
        assert isinstance(generator, SpectralFeatureGeneratorNode)

        destinations = self.destinations()
        if len(destinations) == 0 or isinstance(generator.speclibWidget(), SpectralLibraryWidget):
            # not possible / no need to set a spectral library widget
            return

        generator.setSpeclibWidget(destinations[-1])

    def setSnapToPixelCenter(self, b: bool):
        assert isinstance(b, bool)
        self.mSnapToPixelCenter = b

    def setDefaultSources(self, generator: SpectralFeatureGeneratorNode):
        assert isinstance(generator, SpectralFeatureGeneratorNode)

        existing_sources = self.sources()
        if len(existing_sources) == 0:
            return

        def missingSourceNodes(g: SpectralFeatureGeneratorNode) -> typing.List[SpectralProfileGeneratorNode]:
            return [n for n in g.spectralProfileGeneratorNodes() if n.profileSource() is None]

        source_names = [source.name() for source in existing_sources]

        for n in missingSourceNodes(generator):
            n: SpectralProfileGeneratorNode
            field_name = n.field().name().lower()

            similarity = [difflib.SequenceMatcher(None, field_name, sn).ratio()
                          for sn in source_names]
            s_max = max(similarity)

            # match to source with most-similar name
            if s_max > self.mMinimumSourceNameSimilarity:
                similar_source = existing_sources[similarity.index(max(similarity))]
                n.setProfileSource(similar_source)

        # match
        default_source = self.defaultSource()
        if isinstance(default_source, SpectralProfileSource):
            for n in missingSourceNodes(generator):
                n.setProfileSource(default_source)

    def defaultSource(self) -> SpectralProfileSource:
        return self.mSrcModel.defaultSource()

    def setDefaultSource(self, source: SpectralProfileSource):
        self.mSrcModel.setDefaultSource(source)

    def removeSpectralLibraryWidgets(self, slws: typing.Iterable[SpectralLibraryWidget]):
        if not isinstance(slws, typing.Iterable):
            slws = [slws]
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            self.mDstModel.removeSpectralLibraryWidget(slw)


class SpectralProfileBridgeViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, parent=None):
        super(SpectralProfileBridgeViewDelegate, self).__init__(parent=parent)

        self.mSpectralProfileBridge: SpectralProfileBridge = None

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QModelIndex):

        node = index.data(Qt.UserRole)
        if index.column() == 1:
            # isinstance(node, (SpectralProfileGeneratorNode, FieldGeneratorNode, OptionTreeNode)) and index.column() == 1:
            # taken from https://stackoverflow.com/questions/1956542/how-to-make-item-view-render-rich-html-text-in-qt
            self.initStyleOption(option, index)
            painter.save()

            doc = QTextDocument()
            doc.setHtml(option.text)
            option.text = ""
            option.widget.style().drawControl(QStyle.CE_ItemViewItem, option, painter)

            # shift text right to make icon visible
            iconSize: QSize = option.icon.actualSize(option.rect.size())
            if iconSize.isValid():
                dx = iconSize.width()
            else:
                dx = 0
            painter.translate(option.rect.left() + dx, option.rect.top())
            clip = QRectF(0, 0, option.rect.width() + dx, option.rect.height())
            # doc.drawContents(painter, clip);
            painter.setClipRect(clip)

            ctx = QAbstractTextDocumentLayout.PaintContext()
            # set text color to red for selected item
            # if (option.state & QStyle.State_Selected):
            #     ctx.palette.setColor(QPalette.Text, QColor("red"))
            ctx.clip = clip
            doc.documentLayout().draw(painter, ctx)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def setBridge(self, bridge: SpectralProfileBridge):
        assert isinstance(bridge, SpectralProfileBridge)
        self.mSpectralProfileBridge = bridge

    def bridge(self) -> SpectralProfileBridge:
        return self.mSpectralProfileBridge

    def setItemDelegates(self, tableView: QTableView):
        for c in range(tableView.model().columnCount()):
            tableView.setItemDelegateForColumn(c, self)

    def createEditor(self, parent, option, index):
        bridge = self.bridge()

        w = None
        if index.isValid():
            node = index.data(Qt.UserRole)
            if isinstance(node, SpectralFeatureGeneratorNode) and index.column() in [0, 1]:
                w = HTMLComboBox(parent=parent)
                model = bridge.spectralLibraryModel()
                assert isinstance(model, SpectralLibraryWidgetListModel)
                w.setModel(model)
                s = ""
            elif isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode)) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                model = bridge.dataSourceModel()
                w.setModel(model)

            elif isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                model = bridge.profileSamplingModeModel()
                w.setModel(model)

            elif isinstance(node, OptionTreeNode) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                w.setModel(node.optionModel())

            elif isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
                w = QgsFieldExpressionWidget(parent=parent)
                field: QgsField = node.field()

                genNode: SpectralFeatureGeneratorNode = node.parentNode()
                w.registerExpressionContextGenerator(genNode.expressionContextGenerator())
                # w.setField(field)
                w.setExpressionDialogTitle(f'{field.name()}')
                w.setToolTip(f'Set an expression to specify the field "{field.name()}"')
                # w.setExpression(node.expression().expression())
                # w.setLayer(vis.speclib())
                # w.setFilters(QgsFieldProxyModel.String | QgsFieldProxyModel.Numeric)
                s = ""

        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        if not index.isValid():
            return
        bridge = self.bridge()
        node = index.data(Qt.UserRole)
        if isinstance(node, SpectralFeatureGeneratorNode) and index.column() in [0, 1]:
            assert isinstance(editor, QComboBox)
            model: SpectralLibraryWidgetListModel = editor.model()
            slw = node.speclibWidget()
            if slw:
                idx = model.spectralLibraryWidgetModelIndex(slw)
                if idx.isValid():
                    editor.setCurrentIndex(idx.row())

        if isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode)) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSource())

        elif isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSamplingMode())

        elif isinstance(node, OptionTreeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.option())

        elif isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
            assert isinstance(editor, QgsFieldExpressionWidget)
            editor.setExpression(node.expression().expression())

    def setModelData(self, w, bridge, index):
        if not index.isValid():
            return

        bridge = self.bridge()
        node = index.data(Qt.UserRole)
        if isinstance(node, SpectralFeatureGeneratorNode):
            if index.column() in [0, 1]:
                assert isinstance(w, QComboBox)
                bridge.setData(index, w.currentData(Qt.UserRole), Qt.EditRole)

        if isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode,
                             SpectralProfileSamplingModeNode, OptionTreeNode)):
            if index.column() in [1]:
                assert isinstance(w, QComboBox)
                bridge.setData(index, w.currentData(Qt.UserRole), Qt.EditRole)

        if isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
            assert isinstance(w, QgsFieldExpressionWidget)
            expr = w.expression()
            bridge.setData(index, expr, Qt.EditRole)


class SpectralProfileBridgeTreeView(TreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def selectedFeatureGenerators(self) -> typing.List[SpectralFeatureGeneratorNode]:
        return [n for n in self.selectedNodes() if isinstance(n, SpectralFeatureGeneratorNode)]


class SpectralProfileSourcePanel(QgsDockWidget):

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourcePanel, self).__init__(*args, **kwds)

        loadUi(speclibUiPath('spectralprofilesourcepanel.ui'), self)

        self.treeView: SpectralProfileBridgeTreeView
        self.mBridge = SpectralProfileBridge()
        self.mBridge.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_FIRST_LAYER))

        self.mProxyModel = SpectralProfileSourceProxyModel()
        self.mProxyModel.setSourceModel(self.mBridge)
        self.treeView.setModel(self.mProxyModel)

        self.mDelegate = SpectralProfileBridgeViewDelegate()
        self.mDelegate.setBridge(self.mBridge)
        self.mDelegate.setItemDelegates(self.treeView)

        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

        self.btnAddRelation.setDefaultAction(self.actionAddRelation)
        self.btnRemoveRelation.setDefaultAction(self.actionRemoveRelation)
        self.btnSnapToPixelCenter.setDefaultAction(self.actionSnapToPixelCenter)
        self.actionAddRelation.triggered.connect(self.createRelation)
        self.actionRemoveRelation.triggered.connect(self.onRemoveRelations)
        self.actionSnapToPixelCenter.setChecked(self.mBridge.mSnapToPixelCenter)
        self.actionSnapToPixelCenter.toggled.connect(self.mBridge.setSnapToPixelCenter)

        self.onSelectionChanged([], [])

    def relations(self) -> typing.List[SpectralFeatureGeneratorNode]:
        return list(self.mBridge[:])

    def createRelation(self) -> SpectralFeatureGeneratorNode:
        return self.mBridge.createFeatureGenerator()

    def setDefaultSource(self, source: SpectralProfileSource):
        self.mBridge.setDefaultSource(source)

    def defaultSource(self) -> SpectralProfileSource:
        return self.mBridge.defaultSource()

    def addSources(self, sources):
        self.mBridge.addSources(sources)

    def removeSources(self, sources):
        self.mBridge.removeSources(sources)

    def addSpectralLibraryWidgets(self, slws):
        self.mBridge.addSpectralLibraryWidgets(slws)

    def removeSpectralLibraryWidgets(self, slws):
        self.mBridge.removeSpectralLibraryWidgets(slws)

    def setRunAsync(self, b: bool):
        self.bridge().setRunAsync(b)

    def onSelectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        tv: SpectralProfileBridgeTreeView = self.treeView
        gnodes = tv.selectedFeatureGenerators()
        self.actionRemoveRelation.setEnabled(len(gnodes) > 0)

    def onRemoveRelations(self):
        tv: SpectralProfileBridgeTreeView = self.treeView
        self.mBridge.removeFeatureGenerators(tv.selectedFeatureGenerators())

    def loadCurrentMapSpectra(self,
                              spatialPoint: SpatialPoint,
                              mapCanvas: QgsMapCanvas = None,
                              runAsync: bool = None) -> typing.Dict[str, typing.List[QgsFeature]]:
        return self.mBridge.loadProfiles(spatialPoint, mapCanvas=mapCanvas, runAsync=runAsync)

    def addCurrentProfilesToSpeclib(self):
        self.mBridge.addCurrentProfilesToSpeclib()

def initSamplingModes():
    """
    Inititalizes known SpectralProfileSamplingModes to the SpectralProfileSamplingModeModel
    :rtype:
    """
    for mode in [SingleProfileSamplingMode(),
                 KernelProfileSamplingMode()]:

        SpectralProfileSamplingModeModel.registerMode(mode)