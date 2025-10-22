import copy
import difflib
import logging
import math
import pathlib
import re
import sys
import warnings
from typing import Any, Dict, Iterable, Iterator, List, Set, Tuple, Union, Optional

import numpy as np
from numpy import nan

from qgis.PyQt.QtCore import NULL, QAbstractListModel, QItemSelection, QModelIndex, QObject, QRect, QRectF, QSize, \
    QSortFilterProxyModel, QVariant, Qt, pyqtSignal
from qgis.PyQt.QtGui import QAbstractTextDocumentLayout, QColor, QFont, QIcon, QPainter, QTextDocument
from qgis.PyQt.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QStyle, QStyleOptionViewItem, \
    QStyledItemDelegate, QTableView, QTreeView, QWidget
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextGenerator, QgsExpressionContextScope, QgsExpressionContextUtils, QgsFeature, QgsField, \
    QgsFieldConstraints, QgsFields, QgsGeometry, QgsLayerItem, QgsMapToPixel, QgsPointXY, QgsProperty, QgsRasterLayer, \
    QgsRectangle, QgsVector, QgsVectorLayer, QgsWkbTypes
from qgis.core import QgsProject, QgsMapLayerModel
from qgis.gui import QgsColorButton, QgsDockWidget, QgsDoubleSpinBox, QgsFieldExpressionWidget, QgsFilterLineEdit, \
    QgsMapCanvas
from .spectrallibrarylistmodel import SpectralLibraryListModel
from .spectrallibrarywidget import SpectralLibraryWidget
from .spectralprofileplotmodel import SpectralProfilePlotModel
from .. import speclibUiPath
from ..core import profile_field_names
from ..core.spectralprofile import encodeProfileValueDict, \
    prepareProfileValueDict
from ...externals.htmlwidgets import HTMLComboBox
from ...models import Option, OptionListModel, OptionTreeNode, TreeModel, TreeNode, TreeView, setCurrentComboBoxValue
from ...plotstyling.plotstyling import PlotStyle, PlotStyleButton
from ...qgisenums import QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QDATETIME, QMETATYPE_QSTRING
from ...qgsfunctions import RasterProfile
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...utils import HashableRect, SpatialPoint, aggregateArray, iconForFieldType, loadUi, rasterLayerMapToPixel

logger = logging.getLogger(__name__)

SCOPE_VAR_SAMPLE_CLICK = 'sample_click'
SCOPE_VAR_SAMPLE_FEATURE = 'sample_feature'
SCOPE_VAR_SAMPLE_ID = 'sample_id'


class SpectralProfileSource(QObject):
    sigRemoveMe = pyqtSignal()

    def __init__(self, name: str = None, toolTip: str = None, parent: QObject = None):
        super().__init__(parent=parent)
        self.mName: str = name
        self.mToolTip: str = toolTip

    def __eq__(self, other):
        # required to distinguish sources by content, e.g. file names
        raise NotImplementedError()

    def setName(self, name: str):
        self.mName = name

    def name(self) -> str:
        return self.mName

    def toolTip(self) -> str:
        return self.mToolTip

    def setToolTip(self, toolTip: str):
        self.mToolTip = toolTip

    def collectProfiles(self,
                        point: SpatialPoint,
                        kernel_size: QSize = QSize(1, 1),
                        snap: bool = False,
                        **kwargs) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        """
        A function to collect profiles.
        Needs to consume point and kernel_size
        Each implementation should be able to ignore additional arguments.
        snap : if True, the source should snap to pixel-center
        Returns
        -------
        A list of (profile Dictionary, QgsExpressionContext) tuples.
        """
        raise NotImplementedError

    def expressionContext(self) -> QgsExpressionContext:
        """
        Returns a QgsExpressionContext prototype similar to that returned by collectProfiles
        It should contain all variables with exemplary values that can be used e.g. to define expression functions.
        -------

        """
        raise NotImplementedError()


class ProfileSamplingMode(object):
    NO_AGGREGATION = 'no_aggregation'
    AGGREGATE_MEAN = 'mean'
    AGGREGATE_MEDIAN = 'median'
    AGGREGATE_MIN = 'min'
    AGGREGATE_MAX = 'max'

    RX_KERNEL_SIZE = re.compile(r'(?P<x>\d+)x(?P<y>\d+)')

    def __init__(self,
                 kernelSize: Union[QSize, str, Tuple[int, int]] = QSize(1, 1),
                 aggregation: str = None):

        if aggregation is None:
            aggregation = self.NO_AGGREGATION

        self.mKernelSize = QSize(1, 1)
        self.mAggregation: str = self.NO_AGGREGATION

        self.setKernelSize(kernelSize)
        self.setAggregation(aggregation)

    def __eq__(self, other):
        if not isinstance(other, ProfileSamplingMode):
            return False
        else:
            return other.mAggregation == self.mAggregation and other.mKernelSize == self.mKernelSize

    def numberOfProfiles(self) -> int:

        if self.mAggregation == ProfileSamplingMode.NO_AGGREGATION:
            return self.kernelSize().width() * self.kernelSize().height()
        else:
            return 1

    def clone(self):

        mode = ProfileSamplingMode()
        mode.setKernelSize(*self.kernelSize())
        mode.setAggregation(self.aggregation())
        return mode

    def setKernelSize(self, x: Union[int, str, QSize, Tuple[int, int]], y: int = None):
        """
        Sets the kernel size
        :param x: str | int
        :param y: int (optional)
        """
        if isinstance(x, Tuple) and len(x) == 2:
            x, y = x

        if isinstance(x, str):
            match = self.RX_KERNEL_SIZE.match(x)
            x = int(match.group('x'))
            y = int(match.group('y'))
            size = QSize(x, y)
        elif isinstance(x, int):
            if isinstance(y, int):
                size = QSize(x, y)
            elif y is None:
                size = QSize(x, x)

        elif isinstance(x, QSize):
            size = x
        assert isinstance(size, QSize)
        assert size.width() > 0 and size.height() > 0

        self.mKernelSize = size

    def kernelSizeXY(self) -> Tuple[int, int]:
        s = self.kernelSize()
        return s.width(), s.height()

    def kernelSize(self) -> QSize:
        """
        Returns the kernel size
        :return: (int x, int y)
        """

        return self.mKernelSize

    def aggregationModes(self) -> List[str]:
        return [self.NO_AGGREGATION,
                self.AGGREGATE_MEDIAN,
                self.AGGREGATE_MEAN,
                self.AGGREGATE_MAX,
                self.AGGREGATE_MIN, ]

    def setAggregation(self, aggregation: str):

        assert aggregation in self.aggregationModes()
        self.mAggregation = aggregation

    def aggregation(self) -> str:
        return self.mAggregation

    def profiles(self, point: SpatialPoint, profiles: List[Tuple[Dict, QgsExpressionContext]]) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        """
        Aggregates the profiles collected from a profile source
        in the way as described
        """

        ksize = self.kernelSize()

        aggregation = self.aggregation()

        if aggregation == self.NO_AGGREGATION or len(profiles) == 1:
            return profiles
        else:
            # aggregate profiles into a single profile and a single expression context

            pdicts: List[Dict] = []
            arrays = []
            pcontexts: List[QgsExpressionContext] = []
            for (d, c) in profiles:
                if 'y' in d:
                    p = d['y']
                    pdicts.append(d)
                    pcontexts.append(c)
                    arrays.append(np.asarray(p))
            if len(arrays) == 0:
                return []

            data = np.stack(arrays)
            if data.dtype == object:
                data = data.astype(float)

            data = aggregateArray(aggregation, data, axis=0, keepdims=False)

            # context: merge
            i_center = int(len(pcontexts) / 2)
            refContext = pcontexts[i_center]

            # use the point coordinate as coordinate for the aggregated profile feature
            g = QgsGeometry.fromPointXY(point)

            if isinstance(refContext.variable('_source_crs'), QgsCoordinateReferenceSystem):
                trans = QgsCoordinateTransform()
                trans.setSourceCrs(point.crs())
                trans.setDestinationCrs(refContext.variable('_source_crs'))
                g.transform(trans)
                refContext.setGeometry(g)

            refProfile = pdicts[i_center]
            profile = prepareProfileValueDict(y=data,
                                              x=refProfile.get('x'),
                                              xUnit=refProfile.get('xUnit'),
                                              yUnit=refProfile.get('yUnit'))
        return [(profile, refContext)]


class StandardLayerProfileSource(SpectralProfileSource):

    @staticmethod
    def fromRasterLayer(layer: QgsRasterLayer):
        warnings.warn(DeprecationWarning('Use StandardLayerProfileSource(raster_layer)'))
        return StandardLayerProfileSource(layer)

    def __init__(self, layer: [QgsRasterLayer, str, pathlib.Path]):
        if not isinstance(layer, QgsRasterLayer):
            layer = QgsRasterLayer(str(layer))
        else:
            assert isinstance(layer, QgsRasterLayer)
        assert layer.isValid()

        super().__init__(name=layer.name())
        self.mLayer: QgsRasterLayer = layer
        self.m2p: QgsMapToPixel = rasterLayerMapToPixel(layer)
        self.mLayer.willBeDeleted.connect(self.sigRemoveMe)
        self.mToolTip = '{}<br>{}'.format(layer.name(), layer.source())

    def __eq__(self, other):
        return isinstance(other, StandardLayerProfileSource) \
            and other.mLayer == self.mLayer

    def layer(self) -> QgsRasterLayer:
        return self.mLayer

    def expressionContext(self, point: Union[QgsPointXY, SpatialPoint] = None) -> QgsExpressionContext:
        if point is None:
            # dummy point
            point = SpatialPoint.fromMapLayerCenter(self.mLayer)
        else:
            if isinstance(point, SpatialPoint):
                point = point.toCrs(self.mLayer.crs())
        assert isinstance(point, QgsPointXY)

        context = QgsExpressionContext()
        source_scope = QgsExpressionContextUtils.layerScope(self.mLayer)
        renameScopeVariables(source_scope, 'layer_', 'source_')
        renameScopeVariables(source_scope, '_layer_', '_source_')
        context.appendScope(source_scope)
        context.setGeometry(QgsGeometry.fromPointXY(point))
        px = self.m2p.transform(point)
        scope = QgsExpressionContextScope('pixel')

        def addVar(name, value, description):
            scope.addVariable(QgsExpressionContextScope.StaticVariable(
                name=name, value=value, description=description
            ))

        addVar('px_x', int(px.x()), 'Pixel x position.<br>Most-left = 0')
        addVar('px_y', int(px.y()), 'Pixel y position.<br>Most-top = 0')
        addVar('geo_x', point.x(), 'Pixel x coordinate in source CRS')
        addVar('geo_y', point.y(), 'Pixel y coordinate in source CRS')

        context.setHighlightedVariables(['px_x', 'px_y', 'geo_x', 'geo_y'])
        context.appendScope(scope)
        return context

    def collectProfiles(self,
                        point: SpatialPoint,
                        kernel_size: QSize = QSize(1, 1),
                        snap: bool = False,
                        **kwargs) \
            -> List[Tuple[Dict, QgsExpressionContext]]:

        point = point.toCrs(self.mLayer.crs())
        if not isinstance(point, SpatialPoint):
            return []

        resX = self.mLayer.rasterUnitsPerPixelX()
        resY = self.mLayer.rasterUnitsPerPixelY()

        c = self.mLayer.extent().center()

        if snap:
            M2PX = QgsMapToPixel(self.mLayer.rasterUnitsPerPixelX(),
                                 c.x(), c.y(),
                                 self.mLayer.width(),
                                 self.mLayer.height(),
                                 0
                                 )
            px = M2PX.transform(point)
            px_snapped = QgsPointXY(int(px.x()) + 0.5, int(px.y()) + 0.5)
            point = M2PX.toMapCoordinatesF(px_snapped.x(), px_snapped.y())

        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mLayer))

        sp = QgsRasterLayerSpectralProperties.fromRasterLayer(self.mLayer)

        rect = QRectF(0, 0,
                      resX * kernel_size.width(),
                      resY * kernel_size.height())
        rect.moveCenter(point.toQPointF())

        profilesWithContext: List[Dict, QgsExpressionContext] = []

        if kernel_size == QSize(1, 1):
            g = QgsGeometry.fromPointXY(point)
        else:
            v = QgsVector(-0.5 * kernel_size.width() * resX,
                          0.5 * kernel_size.height() * resY)

            k = QgsRectangle(point + v, point - v)

            g = QgsGeometry.fromRect(k)

        f = RasterProfile()
        all_touched = False
        values = [self.mLayer, point, 'none', all_touched, 'dict']
        exp = QgsExpression()
        fcontext = QgsExpressionContext(context)
        fcontext.setGeometry(g)
        profiles_at = f.func(values, fcontext, exp, None)

        if exp.hasParserError() or exp.hasEvalError() or profiles_at is None:
            return []

        if isinstance(profiles_at, dict):
            profiles_at = [profiles_at]

        loc_geo = fcontext.variable('raster_array_geo')

        for pDict, px_geo in zip(profiles_at, loc_geo):
            context = self.expressionContext(px_geo)
            profilesWithContext.append((pDict, context))

        return profilesWithContext


class MapCanvasLayerProfileSource(SpectralProfileSource):
    MODE_FIRST_LAYER = 'first'
    MODE_LAST_LAYER = 'last'
    MODE_ALL_LAYERS = 'all'

    MODE_TOOLTIP = {MODE_FIRST_LAYER:
                        'Returns profiles of the first / top visible raster layer in the map layer stack',
                    MODE_LAST_LAYER:
                        'Returns profiles of the last / bottom visible raster layer in the map layer stack',
                    MODE_ALL_LAYERS:
                        'Returns profiles of all raster layers',
                    }

    def __init__(self, canvas: QgsMapCanvas = None, mode: str = MODE_FIRST_LAYER):
        super().__init__()
        self.mMapCanvas: QgsMapCanvas = canvas
        if mode is None:
            mode = self.MODE_FIRST_LAYER
        else:
            assert mode in self.MODE_TOOLTIP.keys(), f'Unknown mode: {mode}'
        self.mMode = mode

        if self.mMode == self.MODE_LAST_LAYER:
            self.mName = '<i>Last raster layer</i>'
        elif self.mMode == self.MODE_FIRST_LAYER:
            self.mName = '<i>First raster layer</i>'

        self.mLastContext: QgsExpressionContext = None

    def __eq__(self, other):
        return isinstance(other, MapCanvasLayerProfileSource) \
            and other.mMode == self.mMode \
            and other.mMapCanvas == self.mMapCanvas

    def toolTip(self) -> str:
        return self.MODE_TOOLTIP[self.mMode]

    def expressionContext(self) -> QgsExpressionContext:
        if isinstance(self.mLastContext, QgsExpressionContext):
            return self.mLastContext
        elif isinstance(self.mMapCanvas, QgsMapCanvas):
            for lyr in self.mMapCanvas.layers():
                if isinstance(lyr, QgsRasterLayer):
                    src = StandardLayerProfileSource(lyr)
                    return src.expressionContext()
        return QgsExpressionContext()

    def collectProfiles(self, point: SpatialPoint,
                        kernel_size: QSize = QSize(1, 1),
                        canvas: QgsMapCanvas = None,
                        snap: bool = False,
                        **kwargs) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        if isinstance(canvas, QgsMapCanvas):
            self.mMapCanvas = canvas

        if not isinstance(self.mMapCanvas, QgsMapCanvas) and isinstance(point, SpatialPoint):
            self.mLastContext = None
            return []

        raster_layers = [layer for layer in self.mMapCanvas.layers()
                         if isinstance(layer, QgsRasterLayer) and layer.isValid()]

        if self.mMode == self.MODE_LAST_LAYER:
            raster_layers = reversed(raster_layers)

        results: List[Tuple[dict, QgsExpressionContext]] = []
        # test which raster layer has a valid pixel
        for lyr in raster_layers:
            pt = point.toCrs(lyr.crs())
            if not lyr.extent().contains(pt):
                continue

            source = StandardLayerProfileSource(lyr)
            r = source.collectProfiles(pt, kernel_size=kernel_size, snap=snap)

            if isinstance(r, list) and len(r) > 0:
                results.extend(r)
                if self.mMode != self.MODE_ALL_LAYERS:
                    break

        if len(results) > 0:
            self.mLastContext = QgsExpressionContext(results[0][1])
        return results


class SpectralProfileTopLayerSource(StandardLayerProfileSource):

    def __init__(self, *args, **kwds):
        super(SpectralProfileTopLayerSource, self).__init__('<toprasterlayer>', '<top raster layer>', None)

        self.mMapLayerSources = []

    def setMapSources(self, sources: List[StandardLayerProfileSource]):
        self.mMapLayerSources.clear()
        self.mMapLayerSources.extend(sources)

    def mapSources(self) -> List[StandardLayerProfileSource]:
        return self.mMapLayerSources

    def name(self) -> str:
        return '<top raster layer>'

    def toolTip(self) -> str:
        return 'Reads Spectral Profiles from the top raster layer of a clicked map canvas.'


class ValidateNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def validate(self) -> Iterator[str]:
        """
        Implements validation tests and, in case of errors, returns them
        Returns the tests for this node only.
        User .errors(recursive=True) to collect errors from childs as well

        """
        return []

    def hasErrors(self, recursive: bool = False) -> bool:
        """
        Returns True if this node or any child-node has an error

        """
        for e in self.errors(recursive=recursive):
            return True
        return False

    def errors(self, recursive: bool = False) -> Iterator[str]:
        """
        Yields validation errors
        :return: iterates over all errors
        """
        # print(self)
        if self.isCheckable() and self.checked() or not self.isCheckable():
            for e in self.validate():
                yield e
        if recursive:
            for c in self.findChildNodes(ValidateNode, recursive=False):
                if c.isCheckable() and not c.checked():
                    continue
                for e in c.errors(recursive=recursive):
                    yield f'{self.name()}:{e}'
        s = ""


class SpectralProfileSourceModel(QAbstractListModel):
    """
    A model that lists sources from which SpectralProfiles can be loaded using a point coordinate,
    e.g. raster files.
    """

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourceModel, self).__init__(*args, **kwds)

        self.mSources: List[SpectralProfileSource] = []
        self.mDefaultSource: SpectralProfileSource = None

    def setDefaultSource(self, source: SpectralProfileSource):
        """
        Sets a default SpectralProfileSource that is used for SpectralProfileGenerator Nodes
        """
        assert isinstance(source, SpectralProfileSource)
        self.addSources(source)
        self.mDefaultSource = source

    def defaultSource(self) -> SpectralProfileSource:
        """
        Returns the default SpectralProfileSource.
        If not set with setDefaultSource(), the 1st input source is used.
        """
        if isinstance(self.mDefaultSource, SpectralProfileSource):
            return self.mDefaultSource
        elif len(self.mSources) > 0:
            return self.mSources[0]
        else:
            return None

    def __len__(self) -> int:
        return len(self.mSources)

    def __iter__(self):
        return iter(self.mSources)

    def __getitem__(self, slice):
        return self.mSources[slice]

    def sources(self) -> List[SpectralProfileSource]:
        return [s for s in self[:] if isinstance(s, SpectralProfileSource)]

    def addSources(self, sources: List[SpectralProfileSource]) -> List[SpectralProfileSource]:
        """
        Adds sources to collect spectral profiles from
        :param sources:
        :return:
        """
        if not isinstance(sources, Iterable):
            sources = [sources]

        to_insert = []
        for source in sources:

            if isinstance(source, str):
                source = QgsRasterLayer(source)

            if isinstance(source, QgsRasterLayer):
                source = StandardLayerProfileSource(source)

            if source is None:
                # already in model
                continue

            assert isinstance(source, SpectralProfileSource), f'Got {source} instead SpectralProfileSource'
            if source not in self.mSources \
                    and source not in to_insert:
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

    def findSource(self, source: Union[SpectralProfileSource, QgsRasterLayer, str]) -> SpectralProfileSource:
        """
        Tries to find a stored SpectralProfileSource related that matches the source arguments
        Parameters
        ----------
        source

        Returns
        -------

        """
        if isinstance(source, SpectralProfileSource):
            for s in self.sources():
                if isinstance(s, SpectralProfileSource):
                    if s == source:
                        return s
                    if isinstance(s, StandardLayerProfileSource):
                        if s.layer() == source or s.layer().source == source:
                            return s

        return None

    def removeSources(self, sources: Union[SpectralProfileSource, List[SpectralProfileSource]]) \
            -> List[SpectralProfileSource]:
        if not isinstance(sources, Iterable):
            sources = [sources]
        removed = []
        for s in sources:
            source = self.findSource(s)
            if isinstance(source, SpectralProfileSource):
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
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)


class SpectralProfileSourceNode(ValidateNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mProfileSource: Optional[StandardLayerProfileSource] = None
        self.setValue('No Source')
        self.setToolTip('Please select a raster source')

    # def icon(self) -> QIcon:
    #    return QIcon(r':/images/themes/default/mIconRaster.svg')
    def validate(self) -> Iterator[str]:
        for err in super().validate():
            yield err
        if not isinstance(self.mProfileSource, SpectralProfileSource):
            yield 'Profile source is undefined'

    def profileSource(self) -> Optional[SpectralProfileSource]:
        return self.mProfileSource

    def setSpectralProfileSource(self, source: SpectralProfileSource):
        if isinstance(source, QgsRasterLayer):
            source = StandardLayerProfileSource(source)
        elif isinstance(source, QgsMapCanvas):
            source = MapCanvasLayerProfileSource('top')

        assert source is None or isinstance(source, SpectralProfileSource)
        self.mProfileSource = source

        if isinstance(source, SpectralProfileSource):
            self.setValue(self.mProfileSource.name())
            self.setToolTip(self.mProfileSource.toolTip())
        else:
            self.setValue(None)
            self.setToolTip('')


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


class SpectralProfileSamplingModeNode(TreeNode):
    KERNEL_MODEL = OptionListModel()
    KERNEL_MODEL.addOptions([
        Option(QSize(1, 1), name='Single pixel', toolTip='Reads 1 single pixel at cursor location'),
        Option(QSize(3, 3), name='3x3', toolTip='Reads the 3x3 pixel around the cursor location'),
        Option(QSize(5, 5), name='5x5', toolTip='Reads the 5x5 pixel around the cursor location'),
        Option(QSize(7, 7), name='7x7', toolTip='Reads the 7x7 pixel around the cursor location'),
    ]
    )

    AGGREGATION_MODEL = OptionListModel()
    AGGREGATION_MODEL.addOptions([
        Option(ProfileSamplingMode.NO_AGGREGATION, name='All profiles', toolTip='Keep all profiles'),
        Option(ProfileSamplingMode.AGGREGATE_MEAN, name='Mean', toolTip='Mean profile'),
        Option(ProfileSamplingMode.AGGREGATE_MEDIAN, name='Median', toolTip='Median profile'),
        Option(ProfileSamplingMode.AGGREGATE_MIN, name='Min', toolTip='Min value profile'),
        Option(ProfileSamplingMode.AGGREGATE_MAX, name='Max', toolTip='Max value profile'),
    ])

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        sampling: ProfileSamplingMode = ProfileSamplingMode()
        self.mProfileSamplingMode: ProfileSamplingMode = sampling

        self.nodeAggregation = OptionTreeNode(self.AGGREGATION_MODEL)
        self.nodeAggregation.setName('Aggregation')
        self.nodeAggregation.sigUpdated.connect(self.onAggregationChanged)

        self.nodeProfilesPerClick = TreeNode()
        self.nodeProfilesPerClick.setName('Profiles')
        self.nodeProfilesPerClick.setToolTip('Profiles per click')
        self.appendChildNodes([self.nodeAggregation, self.nodeProfilesPerClick])

        self.setProfileSamplingMode(sampling)

    def onAggregationChanged(self):

        aggr = self.nodeAggregation.option().value()
        if aggr != self.mProfileSamplingMode.aggregation():
            self.mProfileSamplingMode.setAggregation(aggr)
            self.updateProfilesPerClickNode()
            self.sigUpdated.emit(self)  # this resets tooltips ets.

    def updateChildVisibility(self):

        # do not show the aggregation and number of profiles node in
        # case we sample a single pixel only
        mode = self.profileSamplingMode()
        show_nodes = mode.kernelSize() != QSize(1, 1)
        nodes = [self.nodeAggregation, self.nodeProfilesPerClick]
        if show_nodes:
            to_add = [n for n in nodes if n not in self.childNodes()]
            self.insertChildNodes(0, to_add)
        else:
            to_remove = [n for n in nodes if n in self.childNodes()]
            self.removeChildNodes(to_remove)

    def toolTip(self) -> str:
        mode = self.profileSamplingMode()
        kernel = mode.kernelSize()
        x, y = kernel.width(), kernel.height()

        if (x, y) == (1, 1):
            info = ['Sample 1 pixel']
        else:
            info = [f'Sample {x}x{y} pixel']

        if mode.aggregation() != ProfileSamplingMode.NO_AGGREGATION:
            info.append(f'Aggregation: {mode.aggregation()}')

        return '<br>'.join(info)

    def settings(self) -> dict:
        settings = dict()
        settings['kernel'] = '{}x{}'.format(*self.kernelSize())
        settings['aggregation'] = self.aggregation()
        return settings

    def updateProfilesPerClickNode(self):
        """
        Updates the description on how many profiles will be created
        """
        mode = self.profileSamplingMode()
        self.nodeProfilesPerClick.setValue(mode.numberOfProfiles())

    def profileSamplingMode(self) -> ProfileSamplingMode:
        return self.mProfileSamplingMode

    def setProfileSamplingMode(self, mode: ProfileSamplingMode) -> ProfileSamplingMode:
        assert isinstance(mode, ProfileSamplingMode)

        if mode != self.profileSamplingMode():
            self.mProfileSamplingMode = mode
            self.nodeAggregation.setValue(mode.aggregation())
            self.nodeProfilesPerClick.setValue(mode.numberOfProfiles())

        self.updateProfilesPerClickNode()
        self.updateChildVisibility()

        return self.mProfileSamplingMode


class FloatValueNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def setValue(self, value: float):
        super().setValue(float(value))

    def value(self) -> float:
        return float(super().value())


class PlotStyleNode(TreeNode):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setValue(PlotStyle())

    def setValue(self, plotStyle: PlotStyle):
        assert isinstance(plotStyle, PlotStyle)
        super().setValue(plotStyle)

    def value(self) -> PlotStyle:
        return super().value()

    def plotStyle(self) -> PlotStyle:
        return self.value()


class ColorNode(TreeNode):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def setValue(self, value: QColor):
        super().setValue(QColor(value))

    def color(self) -> QColor:
        return self.value()

    def setColor(self, color: QColor):
        self.setValue(color)

    def value(self) -> QColor:
        return QColor(super().value())


class FieldGeneratorNode(ValidateNode):
    """
    Base-class for nodes that generate values for a QgsField
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
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
        self.setIcon(iconForFieldType(field))

    def field(self) -> QgsField:
        """
        Returns the QgsField the node is linked to
        :return:
        :rtype:
        """
        return self.mField

    def validate(self) -> Iterator[str]:
        """
        Returns (True, []) if all settings are fine (default) or (False, ['list of error messages']) if not.
        :return:
        :rtype:
        """
        name = self.name()
        if not isinstance(self.field(), QgsField):
            yield f'{name}: Field is undefined.'
        if self.isCheckable() and self.checkState() == Qt.Checked or not self.isCheckable():
            if self.value() in [None, NULL, '']:
                yield f'{name}: Value is undefined. Needs a value/expression or uncheck the field.'


class GeometryGeneratorNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def geometry(self, point_clicked: SpatialPoint) -> QgsGeometry:
        return None

    def setWkbType(self, wkbType: QgsWkbTypes.Type):
        assert isinstance(wkbType, QgsWkbTypes.Type)

        icon = QgsLayerItem.iconForWkbType(wkbType)
        name = QgsWkbTypes.displayString(wkbType)
        self.setIcon(icon)
        self.setName(name)


class SpectralProfileGeneratorNode(FieldGeneratorNode):

    def __init__(self, *args, **kwds):
        super(SpectralProfileGeneratorNode, self).__init__(*args, **kwds)

        self.setCheckState(Qt.Checked)
        self.sigUpdated.connect(self.onChildNodeUpdate)

        self.mSourceNode = SpectralProfileSourceNode('Source')
        self.mSourceNode.sigUpdated.connect(self.validate)
        self.mSamplingNode = SpectralProfileSamplingModeNode('Sampling')
        self.mScalingNode = SpectralProfileScalingNode('Scaling')

        # self.mProfileStyleNode = PlotStyleNode('Style', toolTip='Style of temporary profile candidates')

        self.appendChildNodes([
            # self.mColorNode,
            # self.mProfileStyleNode,
            self.mSourceNode, self.mSamplingNode, self.mScalingNode])

    # def setColor(self, *args, **kwds):
    #    self.mProfileStyleNode.value().setLineColor(QColor(*args))

    def setScaling(self, *args, **kwds):
        self.mScalingNode.setScaling(*args, **kwds)

    def scale(self) -> float:
        return self.mScalingNode.scale()

    # def plotStyle(self) -> PlotStyle:
    #    return self.mProfileStyleNode.plotStyle()

    def offset(self) -> float:
        return self.mScalingNode.offset()

    def validate(self) -> Iterator[str]:

        for err in super().validate():
            yield err

        for n in self.findChildNodes(ValidateNode, recursive=True):
            n: ValidateNode
            for err in n.validate():
                yield err

    def profileSource(self) -> SpectralProfileSource:
        return self.mSourceNode.profileSource()

    def setProfileSource(self, source: SpectralProfileSource):
        self.mSourceNode.setSpectralProfileSource(source)

    def sampling(self) -> ProfileSamplingMode:
        return self.mSamplingNode.profileSamplingMode()

    def setSampling(self, mode: ProfileSamplingMode) -> ProfileSamplingMode:
        assert isinstance(mode, ProfileSamplingMode)
        return self.mSamplingNode.setProfileSamplingMode(mode)

    # def profileStyle(self) -> PlotStyle:
    #    return self.mProfileStyleNode

    def profiles(self, point, *args, **kwargs) -> List[Tuple[Dict, QgsExpressionContext]]:

        kwargs = copy.copy(kwargs)
        sampling: ProfileSamplingMode = self.sampling()
        kwargs['kernel_size'] = QSize(sampling.kernelSize())
        source = self.mSourceNode.profileSource()
        if isinstance(source, SpectralProfileSource):
            profiles = source.collectProfiles(point, *args, **kwargs)
            profiles = sampling.profiles(point, profiles)
            return self.mScalingNode.profiles(profiles)

        return []

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
            tt.append(source.toolTip())

        info.append(self.mSamplingNode.name())
        tt.append(self.mSamplingNode.name())
        info = ' '.join([i for i in info if isinstance(i, str)])
        tt = '<br>'.join([t for t in tt if isinstance(t, str)])
        self.setValue(info)
        self.setToolTip(tt)


class StandardFieldGeneratorNode(FieldGeneratorNode):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mExpressionString: str = ''

    def expressionString(self) -> str:
        return self.mExpressionString.strip()

    def expression(self) -> QgsExpression:
        return QgsExpression(self.mExpressionString)

    def setExpression(self, expression: Union[str, QgsExpression]):
        if isinstance(expression, QgsExpression):
            expression = expression.expression()
        elif isinstance(expression, str):
            expression = expression.strip()
            # if the expression does not start with @, ' or ", wrap it as string 'example string'
            if not re.search(r'^[@"\']', expression.strip()):
                expression = f"'{expression}'"
        self.mExpressionString = expression
        super().setValue(self.mExpressionString)
        self.validate()

    def setValue(self, value):
        self.setExpression(value)

    def validate(self) -> Iterator[str]:

        b = False
        for err in super().validate():
            yield err
            b = True

        if b:
            return

        expr = self.expression()
        if expr.expression() == '':
            yield f'{self.name()} Expression is undefined'
        else:
            genNode: SpectralFeatureGeneratorNode = self.parentNode()
            if isinstance(genNode, SpectralFeatureGeneratorNode):
                context = genNode.expressionContextGenerator().createExpressionContext()
                expr.prepare(context)
                if expr.hasParserError():
                    yield f'{self.name()}: {expr.parserErrorString().strip()}'
                else:
                    _ = expr.evaluate(context)
                    if expr.hasEvalError():
                        yield f'{self.name()}: {expr.evalErrorString().strip()}'


class SpectralFeatureGeneratorExpressionContextGenerator(QgsExpressionContextGenerator):
    """
    A generator to create the context for a new SpectralProfile feature
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mNode: SpectralFeatureGeneratorNode = None
        self.mFeature: QgsFeature = None
        self.mLastContext: QgsExpressionContext = QgsExpressionContext()

    def createExpressionContext(self) -> QgsExpressionContext:
        """
        Returns the Expression Context that is used within the Expression Widget
        """
        context = QgsExpressionContext()
        highlighted = set(context.highlightedVariables())
        if isinstance(self.mNode, SpectralFeatureGeneratorNode):
            speclib = self.mNode.speclib()
            if isinstance(speclib, QgsVectorLayer) and speclib.isValid():
                context.appendScope(QgsExpressionContextUtils.globalScope())
                context.appendScope(QgsExpressionContextUtils.layerScope(speclib))
                context.setFields(speclib.fields())
                self.mFeature = QgsFeature(speclib.fields())
                context.setFeature(self.mFeature)

            scope = QgsExpressionContextScope('profiles')
            for source in self.mNode.spectralProfileSources(checked=True):
                c = source.expressionContext()
                highlighted.update(c.highlightedVariables())
                addVariablesToScope(scope, c)
            context.appendScope(scope)

        context.setHighlightedVariables(list(highlighted))
        self.mLastContext = context

        return context


RX_MEMORY_UID = re.compile(r'.*uid=[{](?P<uid>[^}]+)}.*')


class SpectralFeatureGeneratorNode(ValidateNode):

    def __init__(self, *args, **kwds):
        # assert isinstance(slw, SpectralLibraryWidget)
        super(SpectralFeatureGeneratorNode, self).__init__(*args, **kwds)

        self.setIcon(QIcon(r':/qps/ui/icons/speclib.svg'))
        self.mSpeclib: Optional[QgsVectorLayer] = None
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.mExpressionContextGenerator = SpectralFeatureGeneratorExpressionContextGenerator()
        self.mExpressionContextGenerator.mNode = self

    def expressionContextGenerator(self) -> SpectralFeatureGeneratorExpressionContextGenerator:
        return self.mExpressionContextGenerator

    def copy(self):
        g = SpectralFeatureGeneratorNode()
        g.setSpeclib(self.speclib())

        nodes = self.createFieldNodes(self.fieldNodeNames())
        g.appendChildNodes(nodes)

        return g

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def setSpeclib(self, speclib: QgsVectorLayer):

        assert speclib is None or isinstance(speclib, QgsVectorLayer)

        oldSpeclib = self.speclib()
        if isinstance(oldSpeclib, QgsVectorLayer):
            oldSpeclib.nameChanged.disconnect(self.updateSpeclibName)
            oldSpeclib.attributeAdded.disconnect(self.updateFieldNodes)
            oldSpeclib.attributeDeleted.disconnect(self.updateFieldNodes)
            oldSpeclib.configChanged.disconnect(self.updateFieldNodes)

        OLD_NODES = dict()
        for n in self.childNodes():
            OLD_NODES[n.name()] = n

        self.removeAllChildNodes()
        self.mSpeclib = None

        if isinstance(speclib, QgsVectorLayer):
            self.mSpeclib = speclib

            if isinstance(speclib, QgsVectorLayer):
                speclib.nameChanged.connect(self.updateSpeclibName)
                speclib.attributeAdded.connect(self.updateFieldNodes)
                speclib.attributeDeleted.connect(self.updateFieldNodes)
                speclib.configChanged.connect(self.updateFieldNodes)
                self.updateSpeclibName()

                new_nodes = []

                # 1. create the geometry generator node
                if False:
                    gnode = GeometryGeneratorNode()
                    gnode.setWkbType(speclib.wkbType())
                    new_nodes.append(gnode)

                # 2. create spectral profile field nodes
                # new_nodes.append(self.createFieldNodes(profile_fields(speclib)))

                # other_fields = [f for f in speclib.fields() if not f]
                new_nodes.extend(self.createFieldNodes(speclib.fields()))
                # 3. add other fields

                self.appendChildNodes(new_nodes)
                self.validate()

    def fieldNode(self, field: Union[str, QgsField, int]) -> FieldGeneratorNode:
        if isinstance(field, int):
            field = self.speclib().fields().at(field).name()
        elif isinstance(field, QgsField):
            field = field.name()

        if isinstance(field, str):
            for n in self.fieldNodes():
                if n.name() == field:
                    return n
        return None

    def fieldNodes(self, checked: bool = None) -> List[FieldGeneratorNode]:
        nodes = [n for n in self.childNodes() if isinstance(n, FieldGeneratorNode)]

        if isinstance(checked, bool) and checked:
            nodes = [n for n in nodes if n.checked()]

        return nodes

    def fieldNodeNames(self) -> List[str]:
        return [n.field().name() for n in self.fieldNodes()]

    def createFieldNodes(self, fieldnames: Union[List[str], QgsField, QgsFields, str]):
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

        fieldnames = [n for n in fieldnames
                      if n not in self.fieldNodeNames()
                      and n in self.speclib().fields().names()]

        new_nodes: List[FieldGeneratorNode] = []

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

    def spectralProfileGeneratorNodes(self, checked: bool = None) -> List[SpectralProfileGeneratorNode]:
        """
        Returns a list of SpectralProfileGeneratorNodes
        :return:
        """
        return [n for n in self.fieldNodes(checked=checked)
                if isinstance(n, SpectralProfileGeneratorNode)]

    def spectralProfileSources(self, checked: bool = None) -> List[SpectralProfileSource]:
        """
        Returns the set of used SpectralProfileSources
        :return: set of SpectralProfileSources
        """
        sources = []
        for node in self.spectralProfileGeneratorNodes(checked=checked):
            s = node.profileSource()
            if isinstance(s, SpectralProfileSource) and s not in sources:
                sources.append(s)
        return sources

    def updateFieldNodes(self, *args):

        if not isinstance(self.speclib(), QgsVectorLayer):
            return

        OLD: Dict[str, FieldGeneratorNode] = {n.name(): n for n in self.fieldNodes()}

        to_remove = []
        to_add = []

        field_names = self.speclib().fields().names()

        for name in field_names:
            if name not in OLD.keys():
                to_add.append(name)
        to_add = self.createFieldNodes(to_add)
        for name, node in OLD.items():
            if name not in self.speclib().fields().names():
                to_remove.append(node)

        if len(to_remove) > 0:
            self.removeChildNodes(to_remove)

        if len(to_add) > 0:
            for node in to_add:
                i = field_names.index(node.name())

                self.insertChildNodes(i, [node])

    def onAttributeDeleted(self, idx: int):

        pass

    def validate(self) -> Iterator[str]:
        """
        Checks all checked field nodes for errors
        Returns True if all checked field nodes are valid
        -------

        """
        if not isinstance(self.mSpeclib, QgsVectorLayer):
            yield 'Missing Spectral Library'

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


class SpectralProfileScalingNode(TreeNode):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.nOffset = FloatValueNode('Offset', value=0)
        self.nScale = FloatValueNode('Scale', value=1)

        self.appendChildNodes([self.nOffset, self.nScale])

        self.nOffset.sigUpdated.connect(self.updateInfo)
        self.nScale.sigUpdated.connect(self.updateInfo)

        self.updateInfo()

    def updateInfo(self):
        info = f"{self.offset()} + {self.scale()} * y"
        self.setValue(info)

    def setScaling(self, offset, scale):
        self.nOffset.setValue(offset)
        self.nScale.setValue(scale)

    def scale(self) -> float:
        return float(self.nScale.value())

    def offset(self) -> float:
        return float(self.nOffset.value())

    def profiles(self, profiles: List[Tuple[Dict, QgsExpressionContext]]) -> List[Tuple[Dict, QgsExpressionContext]]:
        scale = self.scale()
        offset = self.offset()
        if offset != 0 or scale != 1:
            for i in range(len(profiles)):
                d, _ = profiles[i]
                y = d['y']
                d['y'] = [v * scale + offset if v not in [None, nan] and math.isfinite(v)
                          else v for v in y
                          ]

        return profiles


def addVariablesToScope(scope: QgsExpressionContextScope,
                        context: QgsExpressionContext) -> QgsExpressionContextScope:
    """
    Copies variables of a QgsExpressionContext to an QgsExpressionContextScope
    Parameters
    ----------
    scope: the QgsExpressionContextScope to copy the variables
    context: the QgsExpressionContext to thake the variables from

    """
    for v1 in context.variableNames():
        v2 = v1
        i = 0
        while v2 in scope.variableNames():
            i += 1
            v2 = f'{v1}{i}'
        scope.addVariable(QgsExpressionContextScope.StaticVariable(
            name=v2, value=context.variable(v1), description=context.description(v1)))

    return scope


def renameScopeVariables(scope: QgsExpressionContextScope, old_prefix: str, new_prefix: str):
    names = [n for n in scope.variableNames() if n.startswith(old_prefix)]
    for n1 in names:
        n2 = new_prefix + n1[len(old_prefix):]
        scope.addVariable(QgsExpressionContextScope.StaticVariable(
            name=n2, value=scope.variable(n1), description=scope.description(n1)))
        scope.removeVariable(n1)


class SpectralProfileBridge(TreeModel):
    """
    A TreeModel to be used in a view, and to be used in a view,
    """

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mSrcModel = SpectralProfileSourceModel()
        self.mDstModel = SpectralLibraryListModel()
        self.mDefaultSource: SpectralProfileSource = None

        self.mSLWs: List[SpectralLibraryWidget] = []
        self.mLastDestinations: Set[str] = set()
        self.mSrcModel.rowsRemoved.connect(self.updateSourceReferences)
        self.mDstModel.rowsRemoved.connect(self.updateDestinationReferences)
        self.mClickCount: Dict[str, int] = dict()

        self.mTasks = dict()
        self.mSnapToPixelCenter: bool = False
        self.mMinimumSourceNameSimilarity = 0.5

    def setProject(self, project: QgsProject):
        self.mDstModel.setProject(project)

    def project(self) -> QgsProject:
        return self.mDstModel.project()

    def addCurrentProfilesToSpeclib(self):
        """
        Makes current profiles in connected spectral library destinations permanent
        """
        for fgnode in self.featureGenerators(speclib=True, checked=True):
            fgnode: SpectralFeatureGeneratorNode
            sl = fgnode.speclib()
            if isinstance(sl, QgsVectorLayer) and sl.id() in self.mLastDestinations:
                fgnode.speclibWidget().addCurrentProfilesToSpeclib()

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
            if g.speclib() not in self.destinations():
                to_remove.append(g)
        self.removeFeatureGenerators(to_remove)

    def __iter__(self) -> Iterator[SpectralFeatureGeneratorNode]:
        return iter(self.featureGenerators(speclib=False, checked=False))

    def __len__(self):
        return len(self.rootNode().childNodes())

    def __getitem__(self, slice):
        return self.rootNode().childNodes()[slice]

    def showErrors(self, fgnode: SpectralFeatureGeneratorNode, errors: Dict[str, str]):
        pass

    def loadProfiles(self,
                     spatialPoint: SpatialPoint,
                     mapCanvas: QgsMapCanvas = None,
                     runAsync: bool = False) -> Dict[str, List[QgsFeature]]:
        """
        Loads the spectral profiles as defined in the bridge model
        :param spatialPoint:
        :param mapCanvas:
        :param runAsync:
        :return:
        """
        self.mLastDestinations.clear()

        errorNodes: List[FieldGeneratorNode] = []
        # 1. collect feature generators with at least one checked profileGenerator
        featureGenerators: List[SpectralFeatureGeneratorNode] = []
        for fgnode in self.featureGenerators(speclib=True, checked=True):
            is_valid = fgnode.validate()
            if is_valid:
                featureGenerators.append(fgnode)
            else:
                errorNodes.append(fgnode)

            # update all subnodes to show errors
            idx_parent = self.node2idx(fgnode)
            idx0 = self.index(0, 0, idx_parent)
            idx1 = self.index(self.rowCount(idx_parent) - 1, 0, idx_parent)
            self.dataChanged.emit(idx0, idx1, [Qt.BackgroundColorRole])

        # 3. generate features from a feature generators
        #    multiple feature generators can create features for the same speclib
        # store as RESULTS[layer id, ([features], {field_name:PlotStyle})
        RESULTS: Dict[str, List[QgsFeature]] = dict()

        for fgnode in featureGenerators:
            fgnode: SpectralFeatureGeneratorNode

            sid = fgnode.speclib().id()

            features: List[QgsFeature] = RESULTS.get(sid, [])

            fid0 = len(features)

            features1 = self.createFeatures(fgnode, spatialPoint, canvas=mapCanvas)
            for i, f in enumerate(features1):
                fid = fid0 + i  # the unique feature ID
                f.setId(fid)
                features.append(f)
                RESULTS[sid] = features

        # Add profiles to spectral libraries

        to_add = {}

        for sid, features in RESULTS.items():
            to_add[sid] = to_add.get(sid, []) + features

        results = to_add.copy()

        refresh_plot: List[SpectralProfilePlotModel] = []
        for slw in self.mSLWs:
            candidates = {}
            model = slw.plotModel()
            for lyr in model.spectralLibraries():
                sid = lyr.id()
                if sid in to_add:
                    candidates[sid] = to_add.pop(sid)

            if len(candidates) > 0:
                # add new profiles as profile candidates
                # into 1st SpectralLibraryWidget that has a visualization for the layer
                model.addProfileCandidates(candidates)
            else:
                model.addProfileCandidates({})
                # refresh the SpectralLibraryWidget in case it has any layer
                # that might have got updated by another SLW
                # for lyr in model.spectralLibraries():
                #     if lyr.id() in results:
                #         refresh_plot.append(model)
                #         break

        if len(to_add) > 0:
            # add to speclibs which are not visualized in any profile widget
            pass

        for model in refresh_plot:
            model.updatePlot()

        return results

    def createFeatures(self,
                       fgnode: SpectralFeatureGeneratorNode,
                       point: SpatialPoint,
                       canvas: QgsMapCanvas = None) -> List[QgsFeature]:
        """
        Create the QgsFeatures related to position 'point'
        Parameters
        ----------
        fgnode: SpectralFeatureGeneratorNode
        point: SpatialPoint
        canvas: QgsMapCanvas (optional)

        Returns: a list of QgsFeatures and plotstyles for each profile field
        -------

        """
        fgnode: SpectralFeatureGeneratorNode

        speclib: QgsVectorLayer = fgnode.speclib()

        if not isinstance(speclib, QgsVectorLayer) and speclib.isValid():
            return []

        new_features: List[QgsFeature] = []
        PROFILE_DATA: Dict[str, List[dict, QgsExpressionContext]] = dict()
        # PLOT_STYLES: Dict[str, PlotStyle] = dict()
        for pgnode in fgnode.spectralProfileGeneratorNodes(checked=True):
            pgnode: SpectralProfileGeneratorNode
            results = pgnode.profiles(point, canvas=canvas, snap=self.mSnapToPixelCenter)
            if len(results) > 0:
                PROFILE_DATA[pgnode.field().name()] = results
                # PLOT_STYLES[pgnode.field().name()] = pgnode.plotStyle().clone()

        while len(PROFILE_DATA) > 0:
            pfields = list(PROFILE_DATA.keys())
            new_feature = QgsFeature(speclib.fields())

            context = fgnode.expressionContextGenerator().createExpressionContext()
            # context = QgsExpressionContext()
            # context.setFeature(new_feature)

            scope = QgsExpressionContextScope('profile')
            g: QgsGeometry = None

            # add profile field data
            for f in pfields:
                pdata, pcontext = PROFILE_DATA[f].pop(0)
                dump = encodeProfileValueDict(pdata, encoding=speclib.fields()[f])
                new_feature.setAttribute(f, dump)

                pcontext: QgsExpressionContext

                if g is None and pcontext.hasGeometry():
                    # use the geometry related to the origin of the 1. profile field as
                    # feature geometry
                    _g = QgsGeometry(pcontext.geometry())
                    crs = pcontext.variable('_source_crs')
                    if speclib.crs().isValid() and isinstance(crs, QgsCoordinateReferenceSystem) and crs.isValid():
                        trans = QgsCoordinateTransform()
                        trans.setSourceCrs(crs)
                        trans.setDestinationCrs(speclib.crs())
                        if _g.transform(trans) == Qgis.GeometryOperationResult.Success:
                            g = _g

                    del crs

                addVariablesToScope(scope, pcontext)
                # provide context variables from potentially multiple profile sources

            # remove empty list
            for f in list(PROFILE_DATA.keys()):
                if len(PROFILE_DATA[f]) == 0:
                    del PROFILE_DATA[f]

            if isinstance(g, QgsGeometry) and speclib.geometryType() == g.type():
                new_feature.setGeometry(g)
                context.setGeometry(g)

            context.setFeature(new_feature)
            context.appendScope(scope)

            # set other field values by evaluating expression
            for node in fgnode.fieldNodes(checked=True):
                if isinstance(node, SpectralProfileGeneratorNode):
                    continue
                node: FieldGeneratorNode
                field: QgsField = node.field()
                prop = QgsProperty.fromExpression(node.expressionString())
                t = field.type()
                b = False
                if t == QMETATYPE_INT:
                    v, b = prop.valueAsInt(context)
                elif t == QMETATYPE_BOOL:
                    v, b = prop.valueAsBool(context)
                elif t == QMETATYPE_DOUBLE:
                    v, b = prop.valueAsDouble(context)
                elif t == QMETATYPE_QDATETIME:
                    v, b = prop.valueAsDateTime(context)
                elif t == QMETATYPE_QSTRING:
                    v, b = prop.valueAsString(context)
                elif t == QVariant.Color:
                    v, b = prop.valueAsColor(context)
                else:
                    continue
                if b:
                    new_feature.setAttribute(field.name(), v)

            new_features.append(new_feature)
        return new_features  # , PLOT_STYLES

    def spectralLibraryModel(self) -> SpectralLibraryListModel:
        return self.mDstModel

    def destinations(self) -> List[QgsVectorLayer]:
        return self.spectralLibraryModel().spectralLibraries()

    def dataSourceModel(self) -> SpectralProfileSourceModel:
        return self.mSrcModel

    def createFeatureGenerator(self) -> SpectralFeatureGeneratorNode:

        if len(self) == 0:
            g = SpectralFeatureGeneratorNode()

            if len(self.mDstModel) > 0:
                g.setSpeclib(self.mDstModel[0])
        else:
            g = self[-1].copy()

        self.setDefaultDestination(g)
        self.setDefaultSources(g)
        self.addFeatureGenerator(g)
        g.validate()
        return g

    def addFeatureGenerator(self, generator: SpectralFeatureGeneratorNode):

        if generator not in self.rootNode().childNodes():
            self.rootNode().appendChildNodes(generator)
        generator.validate()

    def featureGenerators(self, speclib: bool = True, checked: bool = True) -> \
            List[SpectralFeatureGeneratorNode]:

        for n in self.rootNode().childNodes():
            if isinstance(n, SpectralFeatureGeneratorNode):
                if speclib is True and not isinstance(n.speclib(), QgsVectorLayer):
                    continue
                if checked is True and not n.checked():
                    continue
                yield n

    def removeFeatureGenerators(self, generators: List[SpectralFeatureGeneratorNode]):
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

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        node = index.data(Qt.UserRole)
        if not isinstance(node, TreeNode):
            s = ""
        if col == 0:
            if isinstance(node, TreeNode) and node.isCheckable():
                flags = flags | Qt.ItemIsUserCheckable
            if isinstance(node, (SpectralFeatureGeneratorNode,)):
                flags = flags | Qt.ItemIsEditable

        if col == 1:

            if isinstance(node, (SpectralFeatureGeneratorNode, SpectralProfileSourceNode,
                                 SpectralProfileGeneratorNode,
                                 SpectralProfileSamplingModeNode, StandardFieldGeneratorNode,
                                 FloatValueNode, ColorNode, OptionTreeNode, PlotStyleNode)):
                flags = flags | Qt.ItemIsEditable

        return flags

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        cError = 'red'
        cValid = 'black'
        cNotUsed = 'grey'

        # handle missing data appearances
        value = super().data(index, role)
        node = super().data(index, role=Qt.UserRole)
        c = index.column()

        if index.isValid():
            if isinstance(node, ValidateNode) and role == Qt.ForegroundRole:
                if isinstance(node, SpectralFeatureGeneratorNode):
                    s = ""
                if node.isCheckable() and not node.checked():
                    return QColor(cNotUsed)
                if node.hasErrors(recursive=True):
                    node.hasErrors(recursive=True)
                    return QColor(cError)
                else:
                    return QColor(cValid)

            if isinstance(node, SpectralFeatureGeneratorNode):
                speclib = node.speclib()

                if c == 0:
                    if role == Qt.DisplayRole:
                        if not isinstance(speclib, QgsVectorLayer):
                            return 'Missing Spectral Library'
                        else:
                            return speclib.name()

                    if role == Qt.ForegroundRole:
                        if not node.checked():
                            return QColor(cNotUsed)

                        if node.hasErrors(True):
                            return QColor(cError)

                    if role == Qt.FontRole:
                        if not isinstance(speclib, QgsVectorLayer):
                            f = QFont()
                            f.setItalic(True)
                            return f

                    if role == Qt.ToolTipRole:
                        if not isinstance(speclib, QgsVectorLayer):
                            return 'Select a Spectral Library View'
                        else:
                            tt = f'Spectral Library: {speclib.name()}<br>' \
                                 f'Source: {speclib.source()}<br>' \
                                 f'Features: {speclib.featureCount()}'
                            return tt

            if isinstance(node, ColorNode):
                if c == 0:
                    if role == Qt.ToolTipRole:
                        return node.toolTip()

                if c == 1:
                    if role == Qt.DisplayRole:
                        return node.color().name(QColor.HexArgb)

                    if role == Qt.DecorationRole:
                        return node.color()

                    if role == Qt.ToolTipRole:
                        return str(node.value())

            if isinstance(node, PlotStyleNode):
                if c == 0:
                    if role == Qt.ToolTipRole:
                        return node.toolTip()

            if isinstance(node, SpectralProfileSourceNode):
                has_source = isinstance(node.profileSource(), SpectralProfileSource)
                p = node.parentNode()

                if role == Qt.ForegroundRole:
                    if isinstance(p, SpectralProfileGeneratorNode):
                        if not has_source and p.checked():
                            return QColor(cError)

                if c == 1 and role == Qt.DisplayRole:
                    for err in node.errors():
                        return f'<span style="color:{cError};">{err}</span>'

                    return node.value()

            if isinstance(node, SpectralProfileSamplingModeNode):
                mode = node.profileSamplingMode()

                if c == 1:
                    if role == Qt.DisplayRole:
                        if mode.kernelSize() == QSize(1, 1):
                            return 'Single Pixel'
                        else:
                            ksize = mode.kernelSize()
                            aopt = SpectralProfileSamplingModeNode.AGGREGATION_MODEL.findOption(mode.aggregation())
                            return f'{ksize.width()}x{ksize.height()} {aopt.name()}'

            if isinstance(node, FieldGeneratorNode):
                field: QgsField = node.field()
                editor = field.editorWidgetSetup().type()
                has_errors = node.hasErrors(recursive=True)
                is_checked = node.checked()
                is_required = not node.isCheckable()

                if is_checked or is_required:
                    if has_errors:
                        cstring = cError
                    else:
                        cstring = cValid
                else:
                    cstring = cNotUsed

                if c == 0:
                    if role == Qt.DisplayRole:
                        return value
                    if role == Qt.ToolTipRole:
                        tt = ''
                        if isinstance(field, QgsField):
                            tt += f'"{field.displayName()}" {field.displayType(False)} {editor}'
                        if has_errors:
                            errors = node.errors(recursive=True)
                            tt += '<br><span style="color:' + cstring + '">' + '<br>'.join(errors) + '</span>'
                        return tt
                    if role == Qt.ForegroundRole:
                        return QColor(cstring)

                if c == 1:
                    if role == Qt.DisplayRole:
                        if isinstance(node, StandardFieldGeneratorNode):
                            expr = node.expressionString()
                            if isinstance(expr, str):
                                if expr == '':
                                    return f'<span style="color:{cstring};font-style:italic">Undefined</span>'
                                else:
                                    return f'<span style="color:{cstring};font-style:italic">{expr}</span>'

                    if role == Qt.ToolTipRole:
                        tt = ''
                        if isinstance(node, StandardFieldGeneratorNode):
                            tt += node.expressionString().strip() + '<br>'
                        if has_errors:
                            tt += '<span style="color:red">' + '<br>'.join(node.errors(recursive=True)) + '</span>'
                        return tt

                    if role == Qt.FontRole:
                        f = QFont()
                        f.setItalic(True)

                    if role == Qt.EditRole:
                        if isinstance(node, StandardFieldGeneratorNode):
                            return node.expressionString()

        return value

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        col = index.column()

        node = index.data(Qt.UserRole)
        c0 = c1 = col
        r0 = r1 = index.row()
        roles = [role]
        changed = False  # set only True if not handled by underlying TreeNode

        update_parent = None

        if role == Qt.CheckStateRole \
                and isinstance(node, TreeNode) \
                and node.isCheckable() and \
                value in [Qt.Checked, Qt.Unchecked]:
            changed = node.checkState() != value
            if changed:
                node.setCheckState(value)
                update_parent = isinstance(node, ValidateNode)
                # return True
                c0 = 1
                c1 = 1
                roles.append(Qt.DisplayRole)

        elif isinstance(node, SpectralFeatureGeneratorNode):
            if col in [0, 1] and role == Qt.EditRole:
                if isinstance(value, QgsVectorLayer) and node.speclib() != value:
                    changed = True
                    node.setSpeclib(value)
                    c0 = 0
                    c1 = 1
                    roles = [Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole]

        elif isinstance(node, SpectralProfileGeneratorNode):
            if isinstance(value, ProfileSamplingMode):
                node.setProfileSamplingMode(value)
                changed = False
                # important! node.setProfileSamplingMode has already updated the node
            elif value is None or isinstance(value, SpectralProfileSource):
                node.setProfileSource(value)
                changed = False

        elif isinstance(node, SpectralProfileSourceNode):
            assert value is None or isinstance(value, SpectralProfileSource)
            node.setSpectralProfileSource(value)
            update_parent = True

        elif isinstance(node, SpectralProfileSamplingModeNode):
            if isinstance(value, Option):
                value = value.value()

            mode = None
            if isinstance(value, ProfileSamplingMode):
                mode = value
            elif isinstance(value, QSize):
                mode = node.profileSamplingMode()
                mode.setKernelSize(value)
            if isinstance(mode, ProfileSamplingMode):
                node.setProfileSamplingMode(mode)

        elif isinstance(node, OptionTreeNode):
            if isinstance(value, Option):
                node.setOption(value)

        # elif isinstance(node, ColorNode):
        #     if isinstance(value, (QColor, str)):
        #         node.setColor(value)

        elif isinstance(node, PlotStyleNode):
            if isinstance(value, PlotStyle):
                node.setValue(value)

        elif isinstance(node, StandardFieldGeneratorNode):
            if isinstance(value, (str, QgsExpression)):
                node.setExpression(value)

        elif isinstance(node, TreeNode):
            node.setValue(value)

        if isinstance(node, FieldGeneratorNode):
            node.validate()

        if changed:
            self.dataChanged.emit(self.index(r0, c0, parent=index.parent()),
                                  self.index(r1, c1, parent=index.parent()),
                                  roles)
        if update_parent:
            r = index.parent().row()
            c = index.parent().column()

            fnode = node.findParentNode(SpectralFeatureGeneratorNode)
            if isinstance(fnode, SpectralFeatureGeneratorNode):
                fnode.validate()
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

    def removeAllSources(self):
        self.removeSources(self.sources()[:])

    def removeSources(self, sources: List[Any]):

        self.mSrcModel.removeSources(sources)

    def sources(self) -> List[SpectralProfileSource]:
        return self.mSrcModel.sources()

    def addSpectralLibraryWidgets(self, slws: Union[SpectralLibraryWidget, Iterable[SpectralLibraryWidget]]):
        """
        Registers a spectral library widget.
        """
        if not isinstance(slws, Iterable):
            slws = [slws]

        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)

        added_targets = []
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            if slw not in self.mSLWs:
                added_targets.append(slw)
                slw.sigWindowIsClosing.connect(lambda *args, s=slw: self.removeSpectralLibraryWidgets(slw))
                self.mSLWs.append(slw)

        if len(added_targets) == 0:
            return

        # create a new generator node for each speclib that
        # is shown in the added SLWs and not covered by existing generator nodes
        self.destinations()

        existing_targets = [g.speclib() for g in self[:]]
        missing_targets = []
        for slw in slws:
            for sl in slw.spectralLibraries():
                if sl not in existing_targets:
                    missing_targets.append(sl)

        if len(missing_targets) > 0:
            for speclib in missing_targets:
                self.project().addMapLayer(speclib)
                # create a new generator for the 1st speclib target
                g = SpectralFeatureGeneratorNode()
                g.setSpeclib(speclib)
                self.setDefaultSources(g)
                self.addFeatureGenerator(g)
                break

    def setDefaultDestination(self, generator: SpectralFeatureGeneratorNode):
        assert isinstance(generator, SpectralFeatureGeneratorNode)

        destinations = self.destinations()
        if len(destinations) == 0:
            return

        generator.setSpeclib(destinations[-1])

    def setSnapToPixelCenter(self, b: bool):
        assert isinstance(b, bool)
        self.mSnapToPixelCenter = b

    def setDefaultSources(self, generator: SpectralFeatureGeneratorNode):
        assert isinstance(generator, SpectralFeatureGeneratorNode)

        existing_sources = self.sources()
        if len(existing_sources) == 0:
            return

        def missingSourceNodes(g: SpectralFeatureGeneratorNode) -> List[SpectralProfileGeneratorNode]:
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

    def removeSpectralLibraryWidgets(self, slws: Union[SpectralLibraryWidget, Iterable[SpectralLibraryWidget]]):
        if not isinstance(slws, Iterable):
            slws = [slws]
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            if slw in self.mSLWs:
                self.mSLWs.remove(slw)
            # self.mDstModel.removeSpectralLibraryWidget(slw)


class SpectralProfileBridgeViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, treeView: QTreeView, parent=None):
        super(SpectralProfileBridgeViewDelegate, self).__init__(parent=parent)
        assert isinstance(treeView, QTreeView)
        self.mTreeView: QTreeView = treeView
        self.mSpectralProfileBridge: SpectralProfileBridge = None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):

        node = index.data(Qt.UserRole)
        if index.column() == 1 and isinstance(node, PlotStyleNode):
            plotStyle: PlotStyle = node.value()
            total_h = self.mTreeView.rowHeight(index)
            w = self.mTreeView.columnWidth(index.column())
            if total_h > 0 and w > 0:
                px = plotStyle.createPixmap(size=QSize(w, total_h))
                painter.drawPixmap(option.rect, px)
        elif index.column() == 1:
            # isinstance(node, (SpectralProfileGeneratorNode, FieldGeneratorNode,
            # OptionTreeNode)) and index.column() == 1:
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
                assert isinstance(model, SpectralLibraryListModel)
                w.setModel(model)
                s = ""
            elif isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode)) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                model = bridge.dataSourceModel()
                w.setModel(model)

            elif isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                model = SpectralProfileSamplingModeNode.KERNEL_MODEL
                w.setModel(model)

            elif isinstance(node, OptionTreeNode) and index.column() == 1:
                w = HTMLComboBox(parent=parent)
                w.setModel(node.optionModel())

            elif isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
                w = QgsFieldExpressionWidget(parent=parent)
                w.setAllowEmptyFieldName(True)
                field: QgsField = node.field()

                genNode: SpectralFeatureGeneratorNode = node.parentNode()
                w.registerExpressionContextGenerator(genNode.expressionContextGenerator())
                w.setExpressionDialogTitle(f'{field.name()}')
                w.setToolTip(f'Set an expression to specify the field "{field.name()}"')

            elif isinstance(node, FloatValueNode):
                w = QgsDoubleSpinBox(parent=parent)
                w.setSingleStep(1)
                w.setMinimum(-1 * sys.float_info.max)
                w.setMaximum(sys.float_info.max)
                # w = super().createEditor(parent, option, index)
            elif isinstance(node, ColorNode):
                w = QgsColorButton(parent=parent)
            elif isinstance(node, PlotStyleNode):
                w = PlotStyleButton(parent=parent)
                w.setMinimumSize(5, 5)
                w.setPlotStyle(node.value())
                w.setPreviewVisible(False)
                w.setColorWidgetVisibility(True)
                w.setVisibilityCheckboxVisible(False)
                w.setToolTip('Set curve style')

        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        if not index.isValid():
            return
        bridge = self.bridge()
        node = index.data(Qt.UserRole)
        if isinstance(node, SpectralFeatureGeneratorNode) and index.column() in [0, 1]:
            assert isinstance(editor, QComboBox)
            model: SpectralLibraryListModel = editor.model()
            sl = node.speclib()
            if isinstance(sl, QgsVectorLayer):
                for i in range(model.rowCount()):
                    idx = model.index(i, 0)
                    if sl == model.data(idx, QgsMapLayerModel.CustomRole.Layer):
                        editor.setCurrentIndex(idx)
                        break

        if isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode)) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSource())

        elif isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSamplingMode().kernelSize())

        elif isinstance(node, OptionTreeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.option())

        elif isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
            assert isinstance(editor, QgsFieldExpressionWidget)
            # editor.setField(node.field())
            genNode: SpectralFeatureGeneratorNode = node.parentNode()
            if isinstance(genNode, SpectralFeatureGeneratorNode) and isinstance(genNode.speclib(), QgsVectorLayer):
                contextGen: SpectralFeatureGeneratorExpressionContextGenerator = genNode.expressionContextGenerator()
                editor.setLayer(genNode.speclib())
                editor.registerExpressionContextGenerator(contextGen)

            editor.setExpression(node.expression().expression())

        elif isinstance(node, FloatValueNode) and index.column() == 1:
            if isinstance(editor, QDoubleSpinBox):
                editor.setValue(node.value())
        elif isinstance(node, ColorNode) and index.column() == 1:
            if isinstance(editor, QgsColorButton):
                editor.setColor(node.value())
        elif isinstance(node, PlotStyleNode) and index.column() == 1:
            if isinstance(editor, PlotStyleButton):
                editor.setPlotStyle(node.value())

    def setModelData(self, w, bridge, index):
        if not index.isValid():
            return

        bridge = self.bridge()
        node = index.data(Qt.UserRole)
        if isinstance(node, SpectralFeatureGeneratorNode):
            if index.column() in [0, 1]:
                assert isinstance(w, QComboBox)
                bridge.setData(index, w.currentData(QgsMapLayerModel.CustomRole.Layer), Qt.EditRole)
        elif isinstance(node, (SpectralProfileGeneratorNode, SpectralProfileSourceNode,
                               SpectralProfileSamplingModeNode, OptionTreeNode)):
            if index.column() in [1]:
                assert isinstance(w, QComboBox)
                bridge.setData(index, w.currentData(Qt.UserRole), Qt.EditRole)

        elif isinstance(node, StandardFieldGeneratorNode) and index.column() == 1:
            assert isinstance(w, QgsFieldExpressionWidget)
            expr = w.expression()
            bridge.setData(index, expr, Qt.EditRole)
        elif isinstance(node, FloatValueNode) and index.column() == 1:
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                bridge.setData(index, w.value(), Qt.EditRole)

        elif isinstance(node, ColorNode) and index.column() == 1:
            if isinstance(w, QgsColorButton):
                bridge.setData(index, w.color(), Qt.EditRole)

        elif isinstance(node, PlotStyleNode) and index.column() == 1:
            if isinstance(w, PlotStyleButton):
                bridge.setData(index, w.plotStyle(), Qt.EditRole)


class SpectralProfileBridgeTreeView(TreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def selectedFeatureGenerators(self) -> List[SpectralFeatureGeneratorNode]:
        return [n for n in self.selectedNodes() if isinstance(n, SpectralFeatureGeneratorNode)]


class SpectralProfileSourcePanel(QgsDockWidget):

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourcePanel, self).__init__(*args, **kwds)

        loadUi(speclibUiPath('spectralprofilesourcepanel.ui'), self)

        self.treeView: SpectralProfileBridgeTreeView
        self.mFilterLineEdit: QgsFilterLineEdit
        self.mFilterLineEdit.textChanged.connect(self.setFilter)

        self.mBridge = SpectralProfileBridge()
        self.mBridge.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_FIRST_LAYER))

        self.mProxyModel = SpectralProfileSourceProxyModel()
        self.mProxyModel.setSourceModel(self.mBridge)
        self.treeView.setModel(self.mProxyModel)

        self.mDelegate = SpectralProfileBridgeViewDelegate(self.treeView)
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

    def spectralProfileBridge(self) -> SpectralProfileBridge:
        return self.mBridge

    def setFilter(self, pattern: str):
        self.mProxyModel.setFilterWildcard(pattern)

    def relations(self) -> List[SpectralFeatureGeneratorNode]:
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
                              runAsync: bool = None) -> Dict[str, List[QgsFeature]]:
        return self.mBridge.loadProfiles(spatialPoint, mapCanvas=mapCanvas, runAsync=runAsync)

    def addCurrentProfilesToSpeclib(self):
        self.mBridge.addCurrentProfilesToSpeclib()
