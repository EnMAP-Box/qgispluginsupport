import copy
import difflib
import math
import pathlib
import re
import sys
import warnings
from typing import List, Any, Iterable, Dict, Union, Tuple, Set, Iterator

import numpy as np
from numpy import NaN

from qgis.PyQt.QtCore import QByteArray, QModelIndex, QRect, QAbstractListModel, QSize, QRectF, QSortFilterProxyModel, \
    QItemSelection, NULL
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import pyqtSignal, QObject
from qgis.PyQt.QtGui import QTextDocument, QAbstractTextDocumentLayout, QIcon, QColor, QFont, QPainter
from qgis.PyQt.QtWidgets import QListWidgetItem, QStyledItemDelegate, QComboBox, QWidget, QDoubleSpinBox, QSpinBox, \
    QTableView, QStyle, QStyleOptionViewItem
from qgis.PyQt.QtWidgets import QTreeView
from qgis.core import QgsRaster
from qgis.core import QgsExpressionContextUtils, QgsFeature, QgsGeometry, QgsWkbTypes, QgsPointXY, QgsExpression, \
    QgsFieldConstraints, QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextGenerator, \
    QgsRasterIdentifyResult, QgsRectangle
from qgis.core import QgsLayerItem
from qgis.core import QgsMapToPixel, QgsRasterBlockFeedback, Qgis
from qgis.core import QgsProperty
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsRasterDataProvider, QgsField, QgsFields
from qgis.gui import QgsFieldExpressionWidget, QgsColorButton, QgsFilterLineEdit, \
    QgsMapCanvas, QgsDockWidget, QgsDoubleSpinBox
from .spectrallibrarywidget import SpectralLibraryWidget
from .. import speclibUiPath
from ..core import profile_field_names
from ..core.spectralprofile import SpectralProfileBlock, SpectralSetting, encodeProfileValueDict, \
    prepareProfileValueDict
from ...externals.htmlwidgets import HTMLComboBox
from ...models import TreeModel, TreeNode, TreeView, OptionTreeNode, OptionListModel, Option, setCurrentComboBoxValue
from ...plotstyling.plotstyling import PlotStyle, PlotStyleButton
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...utils import SpatialPoint, loadUi, rasterArray, spatialPoint2px, \
    HashableRect, px2spatialPoint, px2geocoordinatesV2, iconForFieldType, nextColor, rasterLayerMapToPixel

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

    def collectProfiles(self, point: SpatialPoint, kernel_size: QSize = QSize(1, 1), **kwargs) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        """
        A function to collect profiles.
        Needs to consume point and kernel_size
        Each implementation should be able to ignore additional arguments.

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

    def profiles(self, profiles: List[Tuple[Dict, QgsExpressionContext]]) \
            -> List[Tuple[Dict, QgsExpressionContext]]:
        """
        Aggregates the profiles collected from a profile source
        in the way as described
        """

        ksize = self.kernelSize()

        aggregation = self.aggregation()

        if aggregation == self.NO_AGGREGATION:
            return profiles
        else:
            # aggregate profiles into a single profile
            pdicts: List[Dict] = []
            arrays = []
            pcontexts: List[QgsExpressionContext] = []
            for (d, c) in profiles:
                if 'y' in d:
                    p = d['y']
                    pdicts.append(p)
                    pcontexts.append(c)
                    arrays.append(np.asarray(p))

            data = np.stack(arrays).reshape((ksize.width() * ksize.height(), len(arrays[0])))
            if data.dtype == object:
                data = data.astype(float)

            if aggregation == self.AGGREGATE_MEAN:
                data = np.nanmean(data, axis=0)
            elif aggregation == self.AGGREGATE_MEDIAN:
                data = np.nanmedian(data, axis=0)
            elif aggregation == self.AGGREGATE_MIN:
                data = np.nanmin(data, axis=0)
            elif aggregation == self.AGGREGATE_MAX:
                data = np.nanmax(data, axis=0)

            x = bbl = xUnit = yUnit = None
            # bbl - merge, set 0 if any is 0
            # x, xUnit, yUnit - use 1st

            # context: merge
            context = pcontexts[0]
            profile = prepareProfileValueDict(y=data, x=x, xUnit=xUnit, yUnit=yUnit)
        return [(profile, context)]


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

    def collectProfiles(self, point: SpatialPoint, kernel_size: QSize = QSize(1, 1), **kwargs) \
            -> List[Tuple[Dict, QgsExpressionContext]]:

        point = point.toCrs(self.mLayer.crs())
        if not isinstance(point, SpatialPoint):
            return []

        resX = self.mLayer.rasterUnitsPerPixelX()
        resY = self.mLayer.rasterUnitsPerPixelY()
        c = self.mLayer.extent().center()
        m2p = QgsMapToPixel(resX,
                            c.x(), c.y(),
                            self.mLayer.width(), self.mLayer.height(),
                            0)

        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(self.mLayer))

        sp = QgsRasterLayerSpectralProperties.fromRasterLayer(self.mLayer)

        rect = QRectF(0, 0,
                      resX * kernel_size.width(),
                      resY * kernel_size.height())
        rect.moveCenter(point.toQPointF())
        rect = QgsRectangle(rect)

        dp: QgsRasterDataProvider = self.mLayer.dataProvider()
        feedback = QgsRasterBlockFeedback()
        nb = self.mLayer.bandCount()
        nx = kernel_size.width()
        ny = kernel_size.height()

        geo_x = np.arange(0, nx) * resX
        geo_y = np.arange(0, ny) * resY
        geo_x -= 0.5 * geo_x[-1]
        geo_y -= 0.5 * geo_y[-1]
        geo_x += point.x()
        geo_y += point.y()

        profiles = []
        bbl = sp.badBands()
        wl = sp.wavelengths()
        wlu = sp.wavelengthUnits()
        if True:
            dp: QgsRasterDataProvider = self.mLayer.dataProvider()
            for iX in range(nx):
                for iY in range(ny):

                    pt = QgsPointXY(geo_x[iX], geo_y[iY])
                    if not self.mLayer.extent().contains(pt):
                        continue

                    profileContext = self.expressionContext(pt)

                    if Qgis.versionInt() < 33000:
                        R: QgsRasterIdentifyResult = dp.identify(pt, QgsRaster.IdentifyFormat.IdentifyFormatValue)
                    else:
                        R: QgsRasterIdentifyResult = dp.identify(pt, Qgis.RasterIdentifyFormat)
                    if not R.isValid():
                        continue

                    results = R.results()
                    yValues = [results[b + 1] for b in range(self.mLayer.bandCount())]

                    d = prepareProfileValueDict(y=yValues, x=wl, xUnit=wlu, bbl=bbl)
                    if isinstance(d, dict):
                        profiles.append((d, profileContext))

        return profiles


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
        if self.mLastContext:
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
            r = source.collectProfiles(pt, kernel_size=kernel_size)

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

        self.mErrors: List[str] = []

    def validate(self) -> Tuple[bool, str]:
        """
        A method that validates the node ste.
        This method should add collected error messages to self.mErrors
        Returns a tuple (bool: is valid, str: error message)
        """
        self.mErrors.clear()
        # implement error checks here

        return not self.hasErrors()

    def validateChildNode(self):
        self.childNodes()

    def hasErrors(self, recursive: bool = False) -> bool:
        e = len(self.mErrors) > 0
        if e:
            return True
        elif recursive:
            for c in self.findChildNodes(ValidateNode, recursive=True):
                if isinstance(c, ValidateNode) and c.hasErrors():
                    return True
        return False

    def errors(self, recursive: bool = False) -> List[str]:
        """
        Returns a list of validation errors
        :return:
        """
        errors = self.mErrors[:]
        if recursive:
            for c in self.findChildNodes(ValidateNode, recursive=True):
                if isinstance(c, ValidateNode) and c.hasErrors():
                    err = "\n".join(c.errors())
                    errors.append(f'{c.name()}:{err}')
        return errors


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
        Returns the default SpectralProfileSource
        """
        return self.mDefaultSource

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

        self.mProfileSource: StandardLayerProfileSource = None
        self.setValue('No Source')
        self.setToolTip('Please select a raster source')

    # def icon(self) -> QIcon:
    #    return QIcon(r':/images/themes/default/mIconRaster.svg')
    def validate(self) -> bool:
        super().validate()

        if not isinstance(self.mProfileSource, SpectralProfileSource):
            self.mErrors.append('Profile source is undefined')

        return not self.hasErrors()

    def profileSource(self) -> SpectralProfileSource:
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
            self.setToolTip(None)


class SpectralLibraryWidgetListModel(QAbstractListModel):
    """
    A list model that list SpectralLibraries
    """

    def __init__(self, *args, **kwds):
        super(SpectralLibraryWidgetListModel, self).__init__(*args, **kwds)

        self.mSLWs: List[SpectralLibraryWidget] = []

    def __len__(self) -> int:
        return len(self.mSLWs)

    def __iter__(self):
        return iter(self.mSLWs)

    def __getitem__(self, slice):
        return self.mSLWs[slice]

    def spectralLibraryWidgets(self) -> List[SpectralLibraryWidget]:
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

    def item(self, i) -> QListWidgetItem:
        idx = self.index(i, 0)
        item = QListWidgetItem()
        item.setIcon(self.data(idx, Qt.DecorationRole))
        item.setToolTip(self.data(idx, Qt.ToolTipRole))
        # item.setCheckState(self.data(idx, Qt.CheckStateRole))
        # item.setData(self.data(idx, Qt.UserRole))
        # item.setFont(self.data(idx, Qt.FontRole))
        item.setText(self.data(idx, Qt.DisplayRole))
        return item

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

    def validate(self) -> bool:
        """
        Returns (True, []) if all settings are fine (default) or (False, ['list of error messages']) if not.
        :return:
        :rtype:
        """
        super().validate()

        if not isinstance(self.field(), QgsField):
            self.mErrors.append('Field is not set')
        if self.checked() and self.value() in [None, NULL, '']:
            self.mErrors.append('Undefined. Define a value/expression or uncheck the field.')
        return not self.hasErrors()


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

        self.mProfileStyleNode = PlotStyleNode('Style', toolTip='Style of temporary profile candidates')

        self.appendChildNodes([
            # self.mColorNode,
            self.mProfileStyleNode, self.mSourceNode, self.mSamplingNode, self.mScalingNode])

    def setColor(self, *args, **kwds):
        self.mProfileStyleNode.value().setLineColor(QColor(*args))

    def setScaling(self, *args, **kwds):
        self.mScalingNode.setScaling(*args, **kwds)

    def scale(self) -> float:
        return self.mScalingNode.scale()

    def plotStyle(self) -> PlotStyle:
        return self.mProfileStyleNode.plotStyle()

    def offset(self) -> float:
        return self.mScalingNode.offset()

    def validate(self) -> bool:

        b = super().validate()

        for n in self.findChildNodes(ValidateNode, recursive=True):
            n: ValidateNode
            b &= n.validate()

        return b

    def profileSource(self) -> SpectralProfileSource:
        return self.mSourceNode.profileSource()

    def setProfileSource(self, source: SpectralProfileSource):
        self.mSourceNode.setSpectralProfileSource(source)

    def sampling(self) -> ProfileSamplingMode:
        return self.mSamplingNode.profileSamplingMode()

    def setSampling(self, mode: ProfileSamplingMode) -> ProfileSamplingMode:
        assert isinstance(mode, ProfileSamplingMode)
        return self.mSamplingNode.setProfileSamplingMode(mode)

    def profileStyle(self) -> PlotStyle:
        return self.mProfileStyleNode

    def profiles(self, *args, **kwargs) -> List[Tuple[Dict, QgsExpressionContext]]:

        kwargs = copy.copy(kwargs)
        sampling: ProfileSamplingMode = self.sampling()
        kwargs['kernel_size'] = QSize(sampling.kernelSize())
        profiles = self.mSourceNode.profileSource().collectProfiles(*args, **kwargs)
        profiles = sampling.profiles(profiles)
        profiles = self.mScalingNode.profiles(profiles)

        return profiles

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
        self.mExpressionString = expression
        self.setValue(self.mExpressionString)

    def validate(self) -> bool:

        super().validate()

        expr = self.expression()
        if expr.expression() != '':
            genNode: SpectralFeatureGeneratorNode = self.parentNode()
            if isinstance(genNode, SpectralFeatureGeneratorNode):
                context = genNode.expressionContextGenerator().createExpressionContext()
                expr.prepare(context)
                if expr.hasParserError():
                    self.mErrors.append(expr.parserErrorString().strip())
                else:
                    _ = expr.evaluate(context)
                    if expr.hasEvalError():
                        self.mErrors.append(expr.evalErrorString().strip())

        return not self.hasErrors()


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
            oldSpeclib.attributeAdded.disconnect(self.updateFieldNodes)
            oldSpeclib.attributeDeleted.disconnect(self.updateFieldNodes)
            oldSpeclib.configChanged.disconnect(self.updateFieldNodes)

        OLD_NODES = dict()
        for n in self.childNodes():
            OLD_NODES[n.name()] = n

        self.removeAllChildNodes()
        self.mSpeclibWidget = None

        if isinstance(speclibWidget, SpectralLibraryWidget):
            self.mSpeclibWidget = speclibWidget
            self.mSpeclibWidget.spectralLibraryPlotWidget().sigPlotWidgetStyleChanged.connect(
                self.onPlotWidgetStyleChanged)
            speclib = self.mSpeclibWidget.speclib()
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

    def onPlotWidgetStyleChanged(self):
        if isinstance(self.speclibWidget(), SpectralLibraryWidget):
            backgroundColor = self.speclibWidget().plotControl().generalSettings().backgroundColor()
            for n in self.spectralProfileGeneratorNodes():
                n.mProfileStyleNode.value().setBackgroundColor(QColor(backgroundColor))
                n.mProfileStyleNode.sigUpdated.emit(n.mProfileStyleNode)

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

    def errors(self, checked: bool = True) -> List[str]:
        """

        """
        errors = []
        for n in self.fieldNodes(checked=checked):
            errors.extend(n.errors())
        return errors

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
                slw = self.speclibWidget()
                if isinstance(slw, SpectralLibraryWidget):
                    color = QColor('green')
                    for vis in slw.plotControl().visualizations():
                        if vis.field().name() == fname:
                            color = nextColor(vis.color(), 'brighter')
                            break
                    new_node.setColor(color)

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

    def validate(self) -> bool:
        super().validate()

        for n in self.fieldNodes(checked=True):
            n.validate()
            errors = n.errors(recursive=True)
            if len(errors) > 0:
                errStr = '\n'.join(errors)
                self.mErrors.append(f'{n.name()}:{errStr}')

        return not self.hasErrors()

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
                d['y'] = [v * scale + offset if v not in [None, NaN] and math.isfinite(v)
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

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mSrcModel = SpectralProfileSourceModel()
        self.mDstModel = SpectralLibraryWidgetListModel()
        self.mDefaultSource: SpectralProfileSource = None

        self.mLastDestinations: Set[str] = set()
        self.mSrcModel.rowsRemoved.connect(self.updateSourceReferences)
        self.mDstModel.rowsRemoved.connect(self.updateDestinationReferences)
        self.mClickCount: Dict[str, int] = dict()

        self.mTasks = dict()
        self.mSnapToPixelCenter: bool = False
        self.mMinimumSourceNameSimilarity = 0.5

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
            if g.speclibWidget() not in self.destinations():
                # remove node widget reference
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

    def loadProfilesV2(self,
                       spatialPoint: SpatialPoint,
                       mapCanvas: QgsMapCanvas = None,
                       add_permanent: bool = None,
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
        #    multiple feature generators could create features for the same speclib
        RESULTS: Dict[str, Tuple[List[QgsFeature],
                                 Dict[Tuple[int, str], PlotStyle]]] = dict()

        for fgnode in featureGenerators:
            fgnode: SpectralFeatureGeneratorNode

            sid = fgnode.speclib().id()

            features, feature_styles = RESULTS.get(sid, ([], dict()))
            features: List[QgsFeature]
            feature_styles: Dict[Tuple[int, str], PlotStyle]

            fid0 = len(features)

            features1, styles = self.createFeatures(fgnode, spatialPoint, canvas=mapCanvas)
            for i, f in enumerate(features1):
                fid = fid0 + i  # the unique feature ID
                f.setId(fid)
                for fname, style in styles.items():
                    feature_styles[(fid, fname)] = style
                features.append(f)
                RESULTS[sid] = (features, feature_styles)

        # Add profiles to speclibs
        SLWidgets = {fgnode.speclib().id(): fgnode.speclibWidget() for fgnode in featureGenerators}
        results2 = dict()
        for sid, (features, styles) in RESULTS.items():
            slw: SpectralLibraryWidget = SLWidgets[sid]
            slw.setCurrentProfiles(features, currentProfileStyles=styles)
            results2[sid] = features
        return results2

    def createFeatures(self,
                       fgnode: SpectralFeatureGeneratorNode,
                       point: SpatialPoint,
                       canvas: QgsMapCanvas = None) -> Tuple[List[QgsFeature], Dict[str, PlotStyle]]:
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
        PLOT_STYLES: Dict[str, PlotStyle] = dict()
        for pgnode in fgnode.spectralProfileGeneratorNodes(checked=True):
            pgnode: SpectralProfileGeneratorNode
            results = pgnode.profiles(point, canvas=canvas)
            if len(results) > 0:
                PROFILE_DATA[pgnode.field().name()] = results
                PLOT_STYLES[pgnode.field().name()] = pgnode.plotStyle().clone()

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
                    g = QgsGeometry(pcontext.geometry())

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
                if t == QVariant.Int:
                    v, b = prop.valueAsInt(context)
                elif t == QVariant.Bool:
                    v, b = prop.valueAsBool(context)
                elif t == QVariant.Double:
                    v, b = prop.valueAsDouble(context)
                elif t == QVariant.DateTime:
                    v, b = prop.valueAsDateTime(context)
                elif t == QVariant.String:
                    v, b = prop.valueAsString(context)
                elif t == QVariant.Color:
                    v, b = prop.valueAsColor(context)
                else:
                    continue
                if b:
                    new_feature.setAttribute(field.name(), v)

            new_features.append(new_feature)
        return new_features, PLOT_STYLES

    def loadProfiles(self,
                     spatialPoint: SpatialPoint,
                     mapCanvas: QgsMapCanvas = None,
                     add_permanent: bool = None,
                     runAsync: bool = False) -> Dict[str, List[QgsFeature]]:
        """
        Loads the spectral profiles as defined in the bridge model
        :param spatialPoint:
        :param mapCanvas:
        :param runAsync:
        :return:
        """
        self.mLastDestinations.clear()
        RESULTS: Dict[str, List[QgsFeature]] = dict()
        TEMPORAL_COLORS: Dict[str, List[Tuple[int, QColor]]] = dict()
        TEMPORAL_STYLES: Dict[str, List[Tuple[int, PlotStyle]]] = dict()
        # 1. collect infos on sources, pixel positions and additional metadata

        URI2LAYER: Dict[str, QgsRasterLayer] = dict()
        SAMPLING_BLOCK_DESCRIPTIONS: Dict[SpectralProfileGeneratorNode, SamplingBlockDescription] = dict()
        SAMPLING_FEATURES: List[SpectralFeatureGeneratorNode] = []

        # 1. collect source infos
        for fgnode in self.featureGenerators(speclib=True, checked=True):

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
        SOURCE_BLOCKS: Dict[str, Dict[HashableRect, SpectralProfileBlock]] = dict()
        for pgnode, sbd in SAMPLING_BLOCK_DESCRIPTIONS.items():
            sbd: SamplingBlockDescription
            uri = sbd.uri()
            URI2LAYER[uri] = sbd.layer()
            source_blocks: Dict[HashableRect, np.ndarray] = SOURCE_BLOCKS.get(uri, dict())
            source_blocks[sbd.rect()] = None
            SOURCE_BLOCKS[uri] = source_blocks

        # todo: optimize block reading

        # read blocks
        for uri, BLOCKS in SOURCE_BLOCKS.items():
            layer: QgsRasterLayer = URI2LAYER[uri]
            spectralProperties = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)

            for rect in list(BLOCKS.keys()):
                array = rasterArray(layer, rect)

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
                wl = spectralProperties.wavelengths()
                bbl = spectralProperties.badBands()
                wlu = spectralProperties.wavelengthUnits()
                nb = spectralProperties.bandCount()
                if len(wl) > 0:
                    settings = SpectralSetting(wl, xUnit=wlu[0], bbl=bbl)
                else:
                    settings = SpectralSetting(nb, bbl=bbl)

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

            new_speclib_features: List[QgsFeature] = []
            # new_temporal_colors: List[Tuple[int, QColor]] = []
            new_temporal_styles: List[Tuple[int, PlotStyle]] = []
            # calculate final profile value dictionaries
            FINAL_PROFILE_VALUES: Dict[SpectralProfileGeneratorNode, List[Tuple[QByteArray, QgsGeometry]]] = dict()

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
                    outputProfileBlock.mData = pgnode.offset() + outputProfileBlock.mData * pgnode.scale()

                    FINAL_PROFILE_VALUES[pgnode] = []
                    for _, ba, g in outputProfileBlock.profileValueDictionaries():
                        FINAL_PROFILE_VALUES[pgnode].append((ba, g))

            n_new_features = 0
            for node, profiles in FINAL_PROFILE_VALUES.items():
                n_new_features = max(n_new_features, len(profiles))

            for i in range(n_new_features):
                new_feature: QgsFeature = QgsFeature(fgnode.speclib().fields())
                # new_feature_colors: List[Tuple[str, QColor]] = []
                new_feature_styles: List[Tuple[str, PlotStyle]] = []
                # set profile fields
                # let's say the sampling methods for profile fields A, B and C return 1, 3 and 4 profiles, then
                # we create 4 new features with
                # feature 1: A, B, C
                # feature 2: None, B, C
                # feature 4: None, None, C

                for pgnode, profileInputs in FINAL_PROFILE_VALUES.items():

                    if len(profileInputs) > 0:
                        # pop 1st profile
                        profileDict, geometry = profileInputs.pop(0)
                        assert isinstance(profileDict, dict)
                        assert isinstance(geometry, QgsGeometry)
                        if new_feature.geometry().type() in [QgsWkbTypes.UnknownGeometry, QgsWkbTypes.NullGeometry]:
                            new_feature.setGeometry(geometry)
                        field_name = pgnode.field().name()
                        new_feature[field_name] = encodeProfileValueDict(profileDict, encoding=pgnode.field())

                        new_feature_styles.append((field_name, pgnode.mProfileStyleNode.value()))

                new_speclib_features.append(new_feature)
                # new_temporal_colors.append(new_feature_colors)
                new_temporal_styles.append(new_feature_styles)

            sample_id = 1
            if isinstance(speclib, QgsVectorLayer) and len(new_speclib_features) > 0:
                # increase click count
                self.mClickCount[speclib.id()] = self.mClickCount.get(speclib.id(), 0) + 1
                if speclib.featureCount() > 0:
                    fids = sorted(speclib.allFeatureIds())
                    sample_id = fids[-1]
                    if sample_id < 0:
                        sample_id = 0

                    # account for already existing temporary features with fid < 0
                    sample_id += len([f for f in fids if f < 0])

                    # ensure a none-existing sample id
                    while sample_id in fids:
                        sample_id += 1

            for i, new_feature in enumerate(new_speclib_features):
                # create context for other values
                scope = fgnode.speclib().createExpressionContextScope()
                scope.setVariable(SCOPE_VAR_SAMPLE_CLICK, self.mClickCount[speclib.id()])
                scope.setVariable(SCOPE_VAR_SAMPLE_FEATURE, i + 1)
                scope.setVariable(SCOPE_VAR_SAMPLE_ID, sample_id + i)

                context = fgnode.expressionContextGenerator().createExpressionContext()
                context.setFeature(new_feature)
                context.appendScope(scope)
                for node in fgnode.childNodes():
                    if isinstance(node, StandardFieldGeneratorNode) and node.checked():
                        expr = node.expression()
                        if expr.isValid() and expr.prepare(context):
                            new_feature[node.field().name()] = expr.evaluate(context)

            sid = fgnode.speclib().id()

            RESULTS[sid] = RESULTS.get(sid, []) + new_speclib_features
            # TEMPORAL_COLORS[sid] = TEMPORAL_COLORS.get(sid, []) + new_temporal_colors
            TEMPORAL_STYLES[sid] = TEMPORAL_STYLES.get(sid, []) + new_temporal_styles
            self.mLastDestinations.add(fgnode.speclib().id())

        for slw in self.destinations():
            speclib = slw.speclib()
            if isinstance(speclib, QgsVectorLayer) and speclib.id() in RESULTS.keys():
                features = RESULTS[speclib.id()]

                candidate_styles = dict()
                # ensure unique FIDs
                for i, f in enumerate(features):
                    fid = f.id() + i
                    f.setId(f.id() + i)
                    for (field, style) in TEMPORAL_STYLES[speclib.id()][i]:
                        candidate_styles[(fid, field)] = style

                slw.setCurrentProfiles(features,
                                       make_permanent=add_permanent,
                                       currentProfileStyles=candidate_styles,
                                       )
            else:
                slw.setCurrentProfiles([])
        return RESULTS

    def spectralLibraryModel(self) -> SpectralLibraryWidgetListModel:
        return self.mDstModel

    def destinations(self) -> List[SpectralLibraryWidget]:
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

        # handle missing data appearance
        value = super().data(index, role)
        node = super().data(index, role=Qt.UserRole)
        c = index.column()
        if index.isValid():

            if isinstance(node, ValidateNode):
                if role == Qt.ForegroundRole:
                    if node.hasErrors(recursive=True):
                        return QColor('red')

            if isinstance(node, SpectralFeatureGeneratorNode):
                speclib = node.speclib()

                if c == 0:
                    if role == Qt.DisplayRole:
                        if not isinstance(speclib, QgsVectorLayer):
                            return 'Missing Spectral Library'
                        else:
                            return speclib.name()

                    if role == Qt.ForegroundRole:
                        if len(node.errors()) > 0:
                            return QColor('red')

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
                            return QColor('red')
                if c == 1 and role == Qt.DisplayRole:
                    if node.hasErrors() and p.checked():
                        errorStr = '<br>'.join(node.errors())
                        return f'<span style="color:{cError};">{node.value()}</span>'

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
                errors = node.errors()
                has_errors = node.hasErrors()
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
                            tt += '<span style="color:red">' + '<br>'.join(errors) + '</span>'
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
                if isinstance(value, SpectralLibraryWidget):
                    changed = True
                    node.setSpeclibWidget(value)
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

        elif isinstance(node, ColorNode):
            if isinstance(value, (QColor, str)):
                node.setColor(value)

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
            # self.dataChanged.emit(self.index(r, c, index.parent().parent()),
            #                      self.index(r, c, index.parent().parent()))
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

        if not isinstance(slws, Iterable):
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

    def removeSpectralLibraryWidgets(self, slws: Iterable[SpectralLibraryWidget]):
        if not isinstance(slws, Iterable):
            slws = [slws]
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            self.mDstModel.removeSpectralLibraryWidget(slw)


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
                assert isinstance(model, SpectralLibraryWidgetListModel)
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
                bridge.setData(index, w.currentData(Qt.UserRole), Qt.EditRole)
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
        return self.mBridge.loadProfilesV2(spatialPoint, mapCanvas=mapCanvas, runAsync=runAsync)

    def addCurrentProfilesToSpeclib(self):
        self.mBridge.addCurrentProfilesToSpeclib()
