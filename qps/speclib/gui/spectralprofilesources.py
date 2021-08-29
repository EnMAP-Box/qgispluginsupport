import copy
import difflib
import sys
import typing
import enum
import re

from qgis.core import *
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsApplication, QgsTask, \
    QgsTaskManager, QgsRasterDataProvider, QgsRasterRenderer, QgsField, QgsFields

from qgis.gui import *
from qgis.gui import QgsMapCanvas, QgsDockWidget, QgsDoubleSpinBox
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *

from qgis.PyQt.QtWidgets import *

from .spectrallibrarywidget import SpectralLibraryWidget
from .. import speclibUiPath
from ..core import profile_fields, profile_field_names, is_profile_field
from ..core.spectralprofile import SpectralProfileBlock
from ... import SpectralProfile

from ...plotstyling.plotstyling import PlotStyle, MarkerSymbol, PlotStyleButton
import numpy as np
from ...models import TreeModel, TreeNode, TreeView, OptionTreeNode, OptionListModel, Option, setCurrentComboBoxValue
from ...utils import SpatialPoint, loadUi, parseWavelength, HashablePoint, rasterLayerArray

MINIMUM_SOURCENAME_SIMILARITY = 0.5

class SpectralProfileSource(object):

    @staticmethod
    def fromRasterLayer(lyr: QgsRasterLayer):
        return SpectralProfileSource(lyr.source(), lyr.name(), lyr.providerType(), lyr.renderer().clone())

    def __init__(self, uri: str, name: str, provider: str, renderer: QgsRasterRenderer = None):
        assert len(uri) > 0
        self.mUri = uri
        self.mName = name
        self.mProvider = provider
        self.mRenderer: QgsRasterRenderer = None
        if isinstance(renderer, QgsRasterRenderer):
            self.mRenderer = renderer.clone()
            self.mRenderer.setInput(None)

        self.mLyr = None

    def setName(self, name: str):
        self.mName = name

    def name(self) -> str:
        return self.mName

    def toolTip(self) -> str:
        return self.mUri

    def rasterLayer(self) -> QgsRasterLayer:
        if not isinstance(self.mLyr, QgsRasterLayer):
            loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
            self.mLyr = QgsRasterLayer(self.mUri, self.mName, self.mProvider, options=loptions)
            if isinstance(self.mRenderer, QgsRasterRenderer):
                self.mRenderer.setInput(self.mLyr.dataProvider())
                self.mLyr.setRenderer(self.mRenderer)
        return self.mLyr

    def __hash__(self):
        return hash((self.mUri, self.mProvider))

    def __eq__(self, other):
        if not isinstance(other, SpectralProfileSource):
            return False
        return self.mUri == other.mUri and self.mProvider == other.mProvider


class SpectralProfileTopLayerSource(SpectralProfileSource):

    def __init__(self, *args, **kwds):
        super(SpectralProfileTopLayerSource, self).__init__('<toprasterlayer>', '<top raster layer>', None)

        self.mMapLayerSources = []

    def setMapSources(self, sources: typing.List[SpectralProfileSource]):
        self.mMapLayerSources.clear()
        self.mMapLayerSources.extend(sources)

    def mapSources(self) -> typing.List[SpectralProfileSource]:
        return self.mMapLayerSources

    def name(self) -> str:
        return '<top raster layer>'

    def toolTip(self) -> str:
        return 'Reads Spectral Profiles from the top raster layer of a clicked map canvas.'


class SpectralProfileSourceModel(QAbstractListModel):
    """
    A list model that list (raster) sources of SpectralProfiles.
    """

    def __init__(self, *args, **kwds):
        super(SpectralProfileSourceModel, self).__init__(*args, **kwds)

        self.mSources = []

    def __len__(self) -> int:
        return len(self.mSources)

    def __iter__(self):
        return iter(self.mSources)

    def __getitem__(self, slice):
        return self.mSources[slice]

    def sources(self) -> typing.List[SpectralProfileSource]:
        return self[:]

    def addSources(self, sources: typing.List[SpectralProfileSource]) -> typing.List[SpectralProfileSource]:
        if not isinstance(sources, typing.Iterable):
            sources = [sources]

        to_insert = []
        for source in sources:
            if isinstance(source, QgsRasterLayer):
                source = SpectralProfileSource.fromRasterLayer(source)
            assert isinstance(source, SpectralProfileSource)
            if source not in self.mSources:
                to_insert.append(source)
        if len(to_insert) > 0:
            i = len(self)
            self.beginInsertRows(QModelIndex(), i, i + len(to_insert)-1)
            self.mSources.extend(to_insert)
            self.endInsertRows()
        return to_insert

    def sourceModelIndex(self, source) -> QModelIndex:
        if source in self.mSources:
            i = self.mSources.index(source)
            return self.createIndex(i, 0, self.mSources[i])
        else:
            return QModelIndex()

    def removeSource(self, source: SpectralProfileSource) -> SpectralProfileSource:
        if isinstance(source, str):
            to_remove = [s for s in self.sources() if s.mUri == source]
            result = None
            for s in to_remove:
                result = self.removeSource(s)
            return result
        else:
            assert isinstance(source, SpectralProfileSource)
            if source in self.mSources:
                i = self.mSources.index(source)
                self.beginRemoveRows(QModelIndex(), i, i)
                self.mSources.remove(source)
                self.endRemoveRows()
                return source
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

        self.mProfileSource: SpectralProfileSource = None
        self.setValue('No Source')
        self.setToolTip('Please select a raster source')

    def icon(self) -> QIcon:
        return QIcon(r':/images/themes/default/mIconRaster.svg')

    def profileSource(self) -> SpectralProfileSource:
        return self.mProfileSource

    def setSpectralProfileSource(self, source: SpectralProfileSource):
        self.mProfileSource = source
        self.setValue(self.mProfileSource.name())
        self.setToolTip(self.mProfileSource.toolTip())


class SpectralLibraryWidgetListModel(QAbstractListModel):
    """
    A list model that list SpectralLibraries
    """

    def __init__(self, *args, **kwds):
        super(SpectralLibraryWidgetListModel, self).__init__(*args, **kwds)

        self.mSLWs = []

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
        i = self.speclibListIndex(slw)
        if i is None:
            i = len(self)
            self.beginInsertRows(QModelIndex(), i, i)
            self.mSLWs.insert(i, slw)
            self.endInsertRows()
            return slw
        return None

    def speclibListIndex(self, speclib: SpectralLibraryWidget) -> int:
        for i, sl in enumerate(self):
            if sl is speclib:
                return i
        return None

    def speclibModelIndex(self, speclibWidget: SpectralLibraryWidget) -> QModelIndex:

        i = self.speclibListIndex(speclibWidget)
        if isinstance(i, int):
            return self.createIndex(i, 0, speclibWidget)
        return QModelIndex()

    def removeSpeclib(self, slw: SpectralLibraryWidget) -> SpectralLibraryWidget:
        i = self.speclibListIndex(slw)
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

    def profilePositions(self, lyr: QgsRasterLayer, spatialPoint: SpatialPoint) -> \
            typing.Tuple[QgsRasterLayer, typing.List[QPoint]]:
        """
        Returns a list of pixel positions to read a profile from
        :param lyr:
        :param spatialPoint:
        :return:
        """
        raise NotImplementedError()

    def profiles(self, lyr: QgsRasterLayer, pixelProfiles) -> typing.List:
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


class SpectralProfileSamplingModeNode(TreeNode):

    def __init__(self, *args, **kwds):
        super(SpectralProfileSamplingModeNode, self).__init__(*args, **kwds)

        self.mProfileSamplingMode: SpectralProfileSamplingMode = None
        self.mModeInstances: typing.Dict[str, SpectralProfileSamplingMode] = dict()
        self.setProfileSamplingMode(SingleProfileSamplingMode())

    def profileSamplingMode(self) -> SpectralProfileSamplingMode:
        return self.mProfileSamplingMode

    def setProfileSamplingMode(self, mode: SpectralProfileSamplingMode):
        assert isinstance(mode, SpectralProfileSamplingMode)

        mode: SpectralProfileSamplingMode = self.mModeInstances.get(mode.__class__.__name__, mode)

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

    def onChildNodeUpdate(self):

        self.setValue(self.profileSamplingMode().name())


class SingleProfileSamplingMode(SpectralProfileSamplingMode):

    def __init__(self):
        super(SingleProfileSamplingMode, self).__init__()

    def name(self) -> str:
        return 'Single Profile'

    def tooltip(self) -> str:
        return 'Returns a single profile from the clicked position'

    def profilePositions(self, lyr: QgsRasterLayer, spatialPoint: SpatialPoint) -> typing.List[QPoint]:
        assert isinstance(lyr, QgsRasterLayer)

        # convert point to pixel position of interest
        px = spatialPoint.toPixel(lyr)
        if px:
            return [px]
        else:
            return []


    def profiles(self, pixelPositions, pixelProfiles: SpectralProfileBlock):

        return None


class KernelProfileSamplingMode(SpectralProfileSamplingMode):

    def __init__(self):
        super().__init__()

        self.mKernelModel = OptionListModel()
        self.mKernelModel.addOptions([
            Option('3x3', toolTip='Reads the 3x3 pixel around the cursor location'),
            Option('5x5', toolTip='Reads the 5x5 pixel around the cursor location'),
            Option('7x7', toolTip='Reads the 7x7 pixel around the cursor location'),
            ]
        )

        self.mAggregationModel = OptionListModel()
        self.mAggregationModel.addOptions([
            Option(None, name='All profiles', toolTip='Keep all profiles'),
            Option('mean', name='Mean', toolTip='Mean profile'),
            Option('median', name='Median', toolTip='Median profile'),
        ])

        self.mKernel = OptionTreeNode(self.mKernelModel)
        self.mKernel.setName('Kernel')

        self.mAggregation = OptionTreeNode(self.mAggregationModel)
        self.mAggregation.setName('Aggregation')

        self.mKernel.sigUpdated.connect(self.updateProfilesPerClickNode)
        self.mAggregation.sigUpdated.connect(self.updateProfilesPerClickNode)

        self.mProfilesPerClick = TreeNode()
        self.mProfilesPerClick.setName('Profiles')
        self.mProfilesPerClick.setToolTip('Profiles per click')
        self.updateProfilesPerClickNode()

    def nodes(self) -> typing.List[TreeNode]:
        return [self.mKernel, self.mAggregation, self.mProfilesPerClick]

    def name(self) -> str:
        return 'Kernel'

    def settings(self) -> dict:

        settings = super(KernelProfileSamplingMode, self).settings()
        settings['kernel'] = self.mKernel.option().value()
        settings['aggregation'] = self.mAggregation.option().value()
        return settings

    def updateProfilesPerClickNode(self):
        S = self.settings()
        rx = re.compile(r'(?P<x>\d+)x(?P<y>\d+)')

        if S['aggregation'] is None:
            match = rx.match(S['kernel'])
            nProfiles = int(match.group('x')) * int(match.group('y'))
        else:
            nProfiles = 1
        self.mProfilesPerClick.setValue(nProfiles)

    def htmlSummary(self) -> str:
        S = self.settings()
        info = f'Kernel <i>{S["kernel"]}'
        if S['aggregation']:
            info += f' {S["aggregation"]}'
        info += '</i>'
        return info

    def profilePositions(self, lyr: QgsRasterLayer, spatialPoint: SpatialPoint) -> typing.List[QPoint]:
        assert isinstance(lyr, QgsRasterLayer)
        spatialPoint = spatialPoint.toCrs(lyr.crs())
        positions = []
        centerPx = spatialPoint.toPixel(lyr)
        positions.append(centerPx)

        positions = []

        return positions

    def profiles(self, pixelPositions, pixelProfiles: SpectralProfileBlock):

        return None


class SpectralProfileSamplingModeModel(QAbstractListModel):

    MODES = dict()

    @staticmethod
    def registerMode(mode: SpectralProfileSamplingMode):
        assert isinstance(mode, SpectralProfileSamplingMode)

        assert mode.__class__.__name__ not in SpectralProfileSamplingModeModel.MODES.keys()
        SpectralProfileSamplingModeModel.MODES[mode.__class__.__name__] = mode

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
        for mode in SpectralProfileSamplingModeModel.MODES.values():
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

    def setGeometryType(self, wkbType:QgsWkbTypes.GeometryType):
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
            if not isinstance(self.source(), SpectralProfileSource):
                errors.append('No source')
            if not isinstance(self.sampling(), SpectralProfileSamplingMode):
                errors.append('No sampling')

        return len(errors) == 0, errors

    def source(self) -> SpectralProfileSource:
        return self.mSourceNode.profileSource()

    def setSource(self, source:SpectralProfileSource):
        self.mSourceNode.setSpectralProfileSource(source)

    def sampling(self) -> SpectralProfileSamplingMode:
        return self.mSamplingNode.profileSamplingMode()

    def profilePositions(self, spatialPoint: SpatialPoint) -> typing.Tuple[QgsRasterLayer, typing.List[QPoint]]:
        source = self.source()
        if not isinstance(source, SpectralProfileSource):
            return None, []

        # resolve the source layer
        layer = source.rasterLayer()

        # return profile positions
        return layer, self.sampling().profilePositions(layer, spatialPoint)

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
        scope.addVariable(QgsExpressionContextScope.StaticVariable("profile_click", 9999))
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
        OLD_NODES = dict()
        for n in self.childNodes():
            OLD_NODES[n.name()] = n

        self.removeAllChildNodes()
        self.mSpeclibWidget = None

        if isinstance(speclibWidget, SpectralLibraryWidget):
            self.mSpeclibWidget = speclibWidget
            speclib = self.mSpeclibWidget.speclib()
            if isinstance(speclib, QgsVectorLayer):
                self.setName(speclib.name())
                dp_name = speclib.dataProvider().name()
                source = speclib.source()
                if dp_name == 'memory':
                    match = RX_MEMORY_UID.match(source)
                    if match:
                        source = f'memory uid={match.group("uid")}'
                self.setValue(source)

                new_nodes = []

                # 1. create the geometry generator node
                gnode = GeometryGeneratorNode()
                gnode.setGeometryType(speclib.geometryType())
                new_nodes.append(gnode)

                # 2. create spectral profile field nodes
                #new_nodes.append(self.createFieldNodes(profile_fields(speclib)))

                #other_fields = [f for f in speclib.fields() if not f]
                new_nodes.extend(self.createFieldNodes(speclib.fields()))
                # 3. add other fields

                self.appendChildNodes(new_nodes)

    def fieldNodes(self) -> typing.List[FieldGeneratorNode]:
        return [n for n in self.childNodes() if isinstance(n, FieldGeneratorNode)]

    def fieldNodeNames(self) -> typing.List[str]:
        return [n.field().name() for n in self.fieldNodes()]

    def createFieldNodes(self, fieldnames: typing.List[str]):

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
        return [n for n in self.childNodes() if isinstance(n, SpectralProfileGeneratorNode)]

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
        self.mProfileSamplingModeModel = SpectralProfileSamplingModeModel()
        self.mSrcModel.rowsRemoved.connect(lambda: self.updateListColumn(self.cnSrc))
        # self.mSrcModel.rowsInserted.connect(lambda : self.updateListColumn(self.cnSrc))

        self.mDstModel.rowsRemoved.connect(lambda: self.updateListColumn(self.cnDst))
        # self.mDstModel.rowsInserted.connect(lambda : self.updateListColumn(self.cnDst))

        self.mSamplingModel = SpectralProfileSamplingModeModel()
        self.mTasks = dict()

    def __iter__(self) -> typing.Iterator[SpectralFeatureGeneratorNode]:
        return iter(self.rootNode().childNodes())

    def __len__(self):
        return len(self.rootNode().childNodes())

    def __getitem__(self, slice):
        return self.rootNode().childNodes()[slice]

    def loadProfiles(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas=None, runAsync: bool = False):

        """
        Loads the spectral profiles as defined in the bridge model
        :param spatialPoint:
        :param mapCanvas:
        :param runAsync:
        :return:
        """

        # 1. collect required sources and source positions
        SOURCE_PIXEL = dict()
        SOURCE_PIXEL_SET = dict()
        SOURCE2LYR = dict()
        SOURCE_VALUES: typing.Dict[str, typing.Tuple[HashablePoint, HashablePoint, np.ndarray]]

        for g in self:
            g: SpectralFeatureGeneratorNode

            for n in g.spectralProfileGeneratorNodes():
                n: SpectralProfileGeneratorNode

                lyr, positions = n.profilePositions(spatialPoint)
                if not (isinstance(lyr, QgsRasterLayer) and len(positions) > 0):
                    # no positions found. continue
                    continue

                positions = [HashablePoint(p) for p in positions if not isinstance(p, HashablePoint)]

                if len(positions) > 0:
                    source = lyr.source()
                    PIXEL: dict = SOURCE_PIXEL.get(lyr.source(), {})
                    PIXEL_SET: set = SOURCE_PIXEL_SET.get(lyr.source(), set())

                    PIXEL[n] = positions
                    PIXEL_SET = PIXEL_SET.union(positions)
                    SOURCE_PIXEL[source] = PIXEL
                    SOURCE_PIXEL_SET[source] = PIXEL_SET

                    if source not in SOURCE2LYR.keys():
                        SOURCE2LYR[source] = lyr

        # 2. loads required source profiles
        for source, pixel_positions in SOURCE_PIXEL_SET.items():
            lyr: QgsRasterLayer = SOURCE2LYR[source]
            # todo: optimize single-pixel / pixel-block reading

            # read block of data

            wl, wlu = parseWavelength(lyr)

            # create profile block
            xvec = [p.x() for p in pixel_positions]
            yvec = [p.y() for p in pixel_positions]
            xmin, xmax = min(xvec), max(xvec)
            ymin, ymax = min(yvec), max(yvec)

            array = rasterLayerArray(lyr, QPoint(xmin, ymax), QPoint(xmax, ymin))

            s  = ""
            if False:
                pixel_profiles = dict()
                for p in pixel_positions:
                    i = p.x() - xmin
                    j = ymax - p.y()
                    pixel_profiles[p] = array[:, j, i]

            # create source context


            # transform pixel data into final profiles


            # create new speclib feature

        # 3. distribute source profiles to spectral library widgets


        pass


    def profileSamplingModeModel(self) -> SpectralProfileSamplingModeModel:
        return self.mProfileSamplingModeModel

    def spectralLibraryModel(self) -> SpectralLibraryWidgetListModel:
        return self.mDstModel

    def destinations(self) -> typing.List[SpectralLibraryWidget]:
        return self.spectralLibraryModel().spectralLibraryWidgets()

    def dataSourceModel(self) -> SpectralProfileSourceModel:
        return self.mSrcModel

    def createFeatureGenerator(self):

        if len(self) == 0:
            g = SpectralFeatureGeneratorNode()

            if len(self.mDstModel) > 0:
                g.setSpeclibWidget(self.mDstModel[0])
        else:
            g = self[-1].copy()

        self.addFeatureGenerator(g)
        self.setDefaultSources(g)

    def addFeatureGenerator(self, generator: SpectralFeatureGeneratorNode):

        if generator not in self.rootNode().childNodes():
            self.rootNode().appendChildNodes(generator)

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
        if col == 0 and isinstance(node, TreeNode) and node.isCheckable():
            flags = flags | Qt.ItemIsUserCheckable

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
        changed = False # set only True if not handled by underlying TreeNode

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

        elif isinstance(node, SpectralProfileSourceNode):
            if isinstance(value, SpectralProfileSource):
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
            source = SpectralProfileSource(layer.source(), layer.name(), layer.providerType())
            layer.nameChanged.connect(lambda *args, lyr=layer, src=source: src.setName(lyr.name()))
            self.addSources(source)

    def addSources(self, source: SpectralProfileSource):
        n = len(self.mSrcModel)
        src = self.mSrcModel.addSources(source)

        # if this is the first source, set it to all existing relations
        if n == 0 and isinstance(src, SpectralProfileSource):
            for r in self.bridgeItems():
                r.setSource(src)

    def removeSource(self, source: SpectralProfileSource):

        self.mSrcModel.removeSource(source)

    def sources(self) -> typing.List[SpectralProfileSource]:
        return self.mSrcModel[:]

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

    def setDefaultSources(self, generator: SpectralFeatureGeneratorNode):
        assert isinstance(generator, SpectralFeatureGeneratorNode)

        existing_sources = self.sources()
        if len(existing_sources) == 0:
            return

        missing_source_nodes = [n for n in generator.spectralProfileGeneratorNodes()
                                    if n.source() is None]

        source_names = [source.name() for source in existing_sources]

        for n in missing_source_nodes:
            n: SpectralProfileGeneratorNode
            field_name = n.field().name().lower()

            similarity = [difflib.SequenceMatcher(None, field_name, sn).ratio()
                          for sn in source_names]
            s_max = max(similarity)
            if s_max > MINIMUM_SOURCENAME_SIMILARITY:
                similar_source = existing_sources[similarity.index(max(similarity))]
                n.setSource(similar_source)

                # match to source with most-similar name



    def removeDestination(self, slw: SpectralLibraryWidget):
        assert isinstance(slw, SpectralLibraryWidget)
        self.mDstModel.removeSpeclib(slw)

class SpectralProfileBridgeViewDelegate(QStyledItemDelegate):
    """

    """
    def __init__(self, parent=None):
        super(SpectralProfileBridgeViewDelegate, self).__init__(parent=parent)

        self.mSpectralProfileBridge: SpectralProfileBridge = None

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QtCore.QModelIndex):

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
            if isinstance(node, SpectralFeatureGeneratorNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                model = bridge.spectralLibraryModel()
                assert isinstance(model, SpectralLibraryWidgetListModel)
                w.setModel(model)
                s = ""

            elif isinstance(node, SpectralProfileSourceNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                model = bridge.dataSourceModel()
                w.setModel(model)

            elif isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                model = bridge.profileSamplingModeModel()
                w.setModel(model)

            elif isinstance(node, OptionTreeNode) and index.column() == 1:
                w = QComboBox(parent=parent)
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
                idx = model.speclibModelIndex(slw)
                if idx.isValid():
                    editor.setCurrentIndex(idx.row())

        if isinstance(node, SpectralProfileGeneratorNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSamplingMode())

        elif isinstance(node, SpectralProfileSourceNode) and index.column() == 1:
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
        self.progressBar.setVisible(False)
        self.treeView: SpectralProfileBridgeTreeView
        self.mBridge = SpectralProfileBridge()
       # self.mBridge.sigProgress.connect(self.progressBar.setValue)
        self.mProxyModel = SpectralProfileSourceProxyModel()
        self.mProxyModel.setSourceModel(self.mBridge)
        self.treeView.setModel(self.mProxyModel)

        self.mDelegate = SpectralProfileBridgeViewDelegate()
        self.mDelegate.setBridge(self.mBridge)
        self.mDelegate.setItemDelegates(self.treeView)


        self.treeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

        # self.mProxyModel.rowsInserted.connect(self.tableView.resizeColumnsToContents)

        # self.mViewDelegate = SpectralProfileBridgeViewDelegate(self.tableView)
        # self.mViewDelegate.setItemDelegates(self.tableView)

        self.btnAddRelation.setDefaultAction(self.actionAddRelation)
        self.btnRemoveRelation.setDefaultAction(self.actionRemoveRelation)

        self.actionAddRelation.triggered.connect(self.createRelation)
        self.actionRemoveRelation.triggered.connect(self.onRemoveRelations)

        self.onSelectionChanged([], [])

    def createRelation(self):
        self.mBridge.createFeatureGenerator()

    def setRunAsync(self, b: bool):
        self.bridge().setRunAsync(b)

    def onSelectionChanged(self, selected: QItemSelection, deselected: QItemSelection):

        tv: SpectralProfileBridgeTreeView = self.treeView
        gnodes = tv.selectedFeatureGenerators()
        self.actionRemoveRelation.setEnabled(len(gnodes) > 0)

    def onRemoveRelations(self):
        tv: SpectralProfileBridgeTreeView = self.treeView
        self.mBridge.removeFeatureGenerators(tv.selectedFeatureGenerators())

    def loadCurrentMapSpectra(self, spatialPoint: SpatialPoint, mapCanvas: QgsMapCanvas = None, runAsync: bool = None):
        self.mBridge.loadProfiles(spatialPoint, mapCanvas=mapCanvas, runAsync=runAsync)


def positionsToPixel(layer: QgsRasterLayer, positions: typing.List[QgsPointXY]) -> typing.List[QPoint]:
    return []

def pixelToPosition(layer: QgsRasterLayer, pixel: typing.List[QPoint]) -> typing.List[SpatialPoint]:
    crs = layer.crs()
    for px in pixel:
        s = ""
    return []

def loadRasterPositions(layer: QgsRasterLayer, positions: typing.List[QgsPointXY]):

    return None
