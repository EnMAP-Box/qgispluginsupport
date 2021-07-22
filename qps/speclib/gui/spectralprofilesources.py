import copy
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
from ..core import profile_fields, profile_field_names
from ..core.spectralprofile import SpectralProfileBlock
from ... import SpectralProfile

from ...plotstyling.plotstyling import PlotStyle, MarkerSymbol, PlotStyleButton
import numpy as np
from ...models import TreeModel, TreeNode, TreeView, OptionTreeNode, OptionListModel, Option, setCurrentComboBoxValue
from ...utils import SpatialPoint, loadUi



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

    def profilePositions(self, lyr: QgsRasterLayer, spatialPoint: SpatialPoint) -> typing.List[SpatialPoint]:
        """
        Returns a list of spatial points to read the profile from0
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
        return [spatialPoint.toCrs(lyr.crs())]

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
        dx = lyr.rasterUnitsPerPixelX()
        dy = lyr.rasterUnitsPerPixelY()
        cx = spatialPoint.x()
        cy = spatialPoint.y()
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

    def __init__(self, *args, **kwds):
        
        super(FieldGeneratorNode, self).__init__(*args, **kwds)
        self.mField: QgsField = None

    def setField(self, field: QgsField):
        assert isinstance(field, QgsField)
        self.mField = field

    def field(self) -> QgsField:
        return self.mField

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
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.sigUpdated.connect(self.onChildNodeUpdate)
        self.mSourceNode = SpectralProfileSourceNode('Source')
        self.mSamplingNode = SpectralProfileSamplingModeNode('Sampling')
        self.appendChildNodes([self.mSourceNode, self.mSamplingNode])

    def validate(self) -> typing.Tuple[bool, typing.List[str]]:

        errors = []

        if not isinstance(self.source(), SpectralProfileSource):
            errors.append('No source')
        if not isinstance(self.sampling(), SpectralProfileSamplingMode):
            errors.append('No sampling')

        return len(errors) == 0, errors

    def source(self) -> SpectralProfileSource:
        return self.mSourceNode.profileSource()

    def sampling(self) -> SpectralProfileSamplingMode:
        return self.mSamplingNode.profileSamplingMode()

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
    def __int__(self, *args, **kwds):

        self.mExpression: str = ''


class SpectralFeatureGeneratorNode(TreeNode):

    def __init__(self, *args, **kwds):
        # assert isinstance(slw, SpectralLibraryWidget)
        super(SpectralFeatureGeneratorNode, self).__init__(*args, **kwds)
        self.setIcon(QIcon(r':/qps/ui/icons/speclib.svg'))
        self.mSpeclibWidget: SpectralLibraryWidget = None
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)

    def copy(self):
        g = SpectralFeatureGeneratorNode()
        g.setSpeclibWidget(self.speclibWidget())

        self.createFieldNodes(self.fieldNodeNames())

        return g

    def speclibWidget(self) -> SpectralLibraryWidget:
        return self.mSpeclibWidget

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclibWidget.speclib()

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
            self.setName(speclib.name())
            self.setValue(speclib.source())

            new_nodes = []

            # 1. create the geometry generator node
            gnode = GeometryGeneratorNode()
            gnode.setGeometryType(speclib.geometryType())
            new_nodes.append(gnode)

            # 2. create spectral profile field nodes
            for field in profile_fields(speclib):
                self.createFieldNodes(field)

            self.appendChildNodes(new_nodes)

    def fieldNodeNames(self) -> typing.List[str]:
        names = []
        for n in self.childNodes():
            if isinstance(n, FieldGeneratorNode):
                field = n.field()
                if not isinstance(field, QgsField):
                    s = ""
                names.append(n.field().name())

        return names

    def createFieldNodes(self, fieldnames: typing.List[str]):

        if isinstance(fieldnames, QgsField):
            fieldnames = [fieldnames.name()]
        elif isinstance(fieldnames, str):
            fieldnames = [fieldnames]

        for fieldname in fieldnames:
            assert isinstance(fieldname, str)

        fieldnames = [n for n in fieldnames if
                      n not in self.fieldNodeNames() and
                      n in self.speclib().fields().names()]

        new_nodes: typing.List[FieldGeneratorNode] = []

        pf_names = profile_field_names(self.speclib())
        for fname in fieldnames:
            new_node = None

            if fname in pf_names:
                new_node = SpectralProfileGeneratorNode(fname)
            else:
                new_node = StandardFieldGeneratorNode(fname)

            if isinstance(new_node, FieldGeneratorNode):
                i = self.speclib().fields().lookupField(fname)
                new_node.setField(self.speclib().fields().at(i))
                new_nodes.append(new_node)

        if len(new_nodes) > 0:
            self.appendChildNodes(new_nodes)
        return new_nodes

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
            if isinstance(node, (SpectralFeatureGeneratorNode, SpectralProfileSourceNode, SpectralProfileSamplingModeNode)):
                flags = flags | Qt.ItemIsEditable

        return flags

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        # handle missing data appearence
        value = super().data(index, role)
        node = super().data(index, role=Qt.UserRole)
        c = index.column()
        if index.isValid():
            if isinstance(node, SpectralFeatureGeneratorNode):

                if not isinstance(node.speclibWidget(), SpectralLibraryWidget):
                    if c == 0:
                        if role == Qt.DisplayRole:
                            return 'Not set'
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

            if isinstance(node, SpectralProfileGeneratorNode):
                if c == 1:
                    is_valid, errors = node.validate()
                    if not is_valid:
                        if role == Qt.DisplayRole:
                            return '<span style="color:red;">{}</span>'.format(''.join(errors))
                        if role == Qt.ToolTipRole:
                            return '<br>'.join(errors)
                        if role == Qt.ForegroundRole:
                            return QColor('red')
                        if role == Qt.FontRole:
                            f = QFont()
                            f.setItalic(True)
                            return f

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

        if isinstance(node, (SpectralFeatureGeneratorNode, SpectralProfileGeneratorNode)) \
                and role == Qt.CheckStateRole \
                and value in [Qt.Checked, Qt.Unchecked]:
                node.setCheckState(value)

        if isinstance(node, SpectralFeatureGeneratorNode):
            if col in [0, 1] and role == Qt.EditRole:
                if isinstance(value, SpectralLibraryWidget):
                    changed = True
                    node.setSpeclibWidget(value)
                    c0 = 0
                    c1 = 1
                    roles = [Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole]

        if isinstance(node, SpectralProfileGeneratorNode):
            if isinstance(value, SpectralProfileSamplingMode):
                node.setProfileSamplingMode(value)
                changed = False
                # important! node.setProfileSamplingMode has already updated the node

        if isinstance(node, SpectralProfileSourceNode):
            if isinstance(value, SpectralProfileSource):
                node.setSpectralProfileSource(value)

        if isinstance(node, SpectralProfileSamplingModeNode):
            if isinstance(value, SpectralProfileSamplingMode):
                node.setProfileSamplingMode(value)

        if isinstance(node, OptionTreeNode):
            if isinstance(value, Option):
                node.setOption(value)

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
        for slw in slws:
            assert isinstance(slw, SpectralLibraryWidget)
            _slw = self.mDstModel.addSpectralLibraryWidget(slw)
            if isinstance(_slw, SpectralLibraryWidget):
                # add this SLW to generators without any other
                slw_used: bool = False
                for g in self:
                    g: SpectralFeatureGeneratorNode
                    target = g.speclibWidget()
                    if not isinstance(target, SpectralLibraryWidget):
                        g.setSpeclibWidget(_slw)
                    if target == _slw:
                        slw_used = True

                # ensure that there is at least one feature generator for this SLW
                if False and not slw_used:
                    g = SpectralFeatureGeneratorNode()
                    g.setSpeclibWidget(_slw)
                    self.addFeatureGenerator(g)

    def removeDestination(self, slw: SpectralLibraryWidget):
        assert isinstance(slw, SpectralLibraryWidget)
        self.mDstModel.removeSpeclib(slw)

class SpectralProfileBridgeViewDelegateV2(QStyledItemDelegate):
    """

    """
    def __init__(self, parent=None):
        super(SpectralProfileBridgeViewDelegateV2, self).__init__(parent=parent)

        self.mSpectralProfileBridge: SpectralProfileBridge = None

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QtCore.QModelIndex):

        node = index.data(Qt.UserRole)
        if isinstance(node, (SpectralProfileGeneratorNode, OptionTreeNode)) and index.column() == 1:
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

            if isinstance(node, SpectralProfileSourceNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                model = bridge.dataSourceModel()
                w.setModel(model)

            if isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                model = bridge.profileSamplingModeModel()
                w.setModel(model)

            if isinstance(node, OptionTreeNode) and index.column() == 1:
                w = QComboBox(parent=parent)
                w.setModel(node.optionModel())

            # w = QComboBox(parent=parent)
            # model = bridge.dataSourceModel()
            # assert isinstance(model, SpectralProfileSourceModel)
            # w.setModel(model)
            # s = ""

            #elif cname == bridge.cnDst:

            #elif cname == bridge.cnSampling:
            #w = QComboBox(parent=parent)
            #for mode in SpectralProfileSamplingMode:
            #    assert isinstance(mode, SpectralProfileSamplingMode)
            #    w.addItem(mode.name, mode)


            #elif cname == bridge.cnScale:
            #    w = QgsDoubleSpinBox(parent=parent)
            #    w.setClearValue(1)
            #    w.setMinimum(sys.float_info.min)
            #    w.setMaximum(sys.float_info.max)
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

        if isinstance(node, SpectralProfileSourceNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSource())

        if isinstance(node, SpectralProfileSamplingModeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.profileSamplingMode())

        if isinstance(node, OptionTreeNode) and index.column() == 1:
            assert isinstance(editor, QComboBox)
            setCurrentComboBoxValue(editor, node.option())


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

        self.mDelegate = SpectralProfileBridgeViewDelegateV2()
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
        self.bridge().loadProfiles(spatialPoint, mapCanvas=mapCanvas, runAsync=runAsync)


def positionsToPixel(layer: QgsRasterLayer, positions: typing.List[QgsPointXY]) -> typing.List[QPoint]:
    return []

def pixelToPosition(layer: QgsRasterLayer, pixel: typing.List[QPoint]) -> typing.List[SpatialPoint]:
    crs = layer.crs()
    for px in pixel:
        s = ""
    return []

def loadRasterPositions(layer: QgsRasterLayer, positions: typing.List[QgsPointXY]):

    return None
