import datetime
import math
import re
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple, Union

import numpy as np

from qgis.PyQt.QtWidgets import QAbstractItemView, QAction, QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, \
    QMenu, QMessageBox, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QTableView, QTreeView, \
    QWidget
from qgis.core import QgsApplication, QgsExpressionContext, QgsExpressionContextScope, QgsFeature, QgsFeatureRenderer, \
    QgsFeatureRequest, QgsField, QgsMapLayerProxyModel, QgsMarkerSymbol, QgsProject, QgsProperty, QgsRasterLayer, \
    QgsReadWriteContext, QgsRenderContext, QgsSettings, QgsSingleSymbolRenderer, QgsSymbol, QgsVectorLayer, \
    QgsVectorLayerCache
from qgis.gui import QgsDualView, QgsFilterLineEdit
from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QItemSelectionModel, QMimeData, QModelIndex, \
    QPoint, QRect, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QContextMenuEvent, QDragEnterEvent, QDropEvent, QFontMetrics, QIcon, \
    QPainter, QPalette, QPen, QPixmap, QStandardItem, QStandardItemModel
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from .spectrallibraryplotitems import FEATURE_ID, FIELD_INDEX, MODEL_NAME, PlotUpdateBlocker, \
    SpectralProfilePlotDataItem, SpectralProfilePlotWidget
from .spectrallibraryplotmodelitems import GeneralSettingsGroup, PlotStyleItem, ProfileCandidateGroup, \
    ProfileCandidateItem, ProfileVisualizationGroup, PropertyItem, PropertyItemBase, PropertyItemGroup, PropertyLabel, \
    RasterRendererGroup
from .spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel, SpectralProfilePlotXAxisUnitWidgetAction
from .spectralprofilefieldmodel import SpectralProfileFieldListModel
from .. import speclibUiPath
from ..core import is_spectral_library, profile_field_indices, profile_field_list, profile_fields
from ..core.spectralprofile import decodeProfileValueDict
from ...models import SettingsModel
from ...plotstyling.plotstyling import PlotStyle, PlotWidgetStyle
from ...qgisenums import QMETATYPE_INT, QMETATYPE_QSTRING
from ...unitmodel import BAND_INDEX, BAND_NUMBER, datetime64, UnitConverterFunctionModel, UnitWrapper
from ...utils import convertDateUnit, loadUi, printCaller, qgsField, SelectMapLayerDialog, SignalObjectWrapper

MAX_PROFILES_DEFAULT: int = 516
FIELD_NAME = str

ATTRIBUTE_ID = Tuple[FEATURE_ID, FIELD_INDEX]
MODEL_DATA_KEY = Tuple[FEATURE_ID, FIELD_INDEX, MODEL_NAME]
PROFILE_DATA_CACHE_KEY = Tuple[FEATURE_ID, FIELD_INDEX]


class SpectralProfilePlotModelProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotModelProxyModel, self).__init__(*args, **kwds)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)


class SpectralProfilePlotModel(QStandardItemModel):
    CIX_NAME = 0
    CIX_VALUE = 1

    sigProgressChanged = pyqtSignal(float)
    sigPlotWidgetStyleChanged = pyqtSignal()
    sigMaxProfilesExceeded = pyqtSignal()
    NOT_INITIALIZED = -1

    class UpdateBlocker(object):
        """Blocks plot updates"""

        def __init__(self, plotModel: 'SpectralProfilePlotModel'):
            self.mPlotModel = plotModel
            self.mWasBlocked: bool = False

        def __enter__(self):
            self.mWasBlocked = self.mPlotModel.blockUpdates(True)

        def __exit__(self, exc_type, exc_value, tb):
            self.mPlotModel.blockUpdates(self.mWasBlocked)

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mBlockUpdates: bool = False

        self.mProject: QgsProject = QgsProject.instance()

        self.mModelItems: Set[PropertyItemGroup] = set()

        # # workaround https://github.com/qgis/QGIS/issues/45228
        self.mStartedCommitEditWrapper: bool = False

        self.mCACHE_PROFILE_DATA = dict()
        self.mEnableCaching: bool = False
        self.mProfileFieldModel: SpectralProfileFieldListModel = SpectralProfileFieldListModel()

        self.mPlotWidget: SpectralProfilePlotWidget = None
        symbol = QgsMarkerSymbol.createSimple({'name': 'square', 'color': 'white'})

        try:
            self.mDefaultSymbolRenderer = QgsSingleSymbolRenderer(symbol)
        except TypeError:
            self.mDefaultSymbolRenderer = QgsSingleSymbolRenderer(symbol, None)

        hdr0 = QStandardItem('Name')
        hdr0.setToolTip('Visualization property names')
        hdr1 = QStandardItem('Value')
        hdr1.setToolTip('Visualization property values')
        self.setHorizontalHeaderItem(0, hdr0)
        self.setHorizontalHeaderItem(1, hdr1)

        """
        self.mPropertyTooltips = {
            self.PIX_FIELD: 'Field with profile values.',
            self.PIX_LABEL: 'Field/Expression to generate profile names.',
            self.PIX_COLOR: 'Field/Expression to generate profile colors.',
            self.PIX_STYLE: 'Profile styling.',
            self.PIX_FILTER: 'Filter to exclude/include profiles. If empty, all features are used.'

        }"""

        self.mVectorLayerCache: QgsVectorLayerCache = None

        self.mChangedFIDs: Set[int] = set()
        self.mChangedAttributes: Set[Tuple[int, int]] = set()
        self.mLastEditCommand: str = None
        # self.mPlotDataItems: List[SpectralProfilePlotDataItem] = list()

        # Update plot data and colors

        # .mCache2ModelData: Dict[MODEL_DATA_KEY, dict] = dict()
        # mCache2ModelData[(fid, fidx, modelId, xunit))] -> dict
        # self.mCache3PlotData: Dict[PLOT_DATA_KEY, dict] = dict()

        self.mUnitConverterFunctionModel = UnitConverterFunctionModel.instance()
        self.mDualView: QgsDualView = Optional[None]
        self.mSpeclib: QgsVectorLayer = Optional[None]

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel.instance()
        self.mXUnit: UnitWrapper = self.mXUnitModel.findUnitWrapper(BAND_NUMBER)
        self.mXUnitInitialized: bool = False
        self.mShowSelectedFeaturesOnly: bool = False

        self.mGeneralSettings = GeneralSettingsGroup()

        self.mProfileCandidates = ProfileCandidateGroup()
        self.insertPropertyGroup(0, self.mGeneralSettings)
        self.insertPropertyGroup(1, self.mProfileCandidates)

        self.setMaxProfiles(MAX_PROFILES_DEFAULT)

        self.itemChanged.connect(self.onItemChanged)

    def onItemChanged(self, *args):

        if not self.updatesBlocked():
            # print('#ITEM CHANGED')
            # self.updatePlot()
            pass

    def blockUpdates(self, b: bool) -> bool:
        state = self.mBlockUpdates
        self.mBlockUpdates = b
        return state

    def updatesBlocked(self) -> bool:
        return self.mBlockUpdates

    def createPropertyColor(self, property: QgsProperty, fid: int = None) -> QColor:
        assert isinstance(property, QgsProperty)
        defaultColor = QColor('white')
        renderer: QgsFeatureRenderer = None
        context = QgsExpressionContext()
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            context = speclib.createExpressionContext()
            if speclib.featureCount() > 0:
                feature: QgsFeature = None
                if fid:
                    feature = speclib.getFeature(fid)
                if not isinstance(feature, QgsFeature):
                    for f in speclib.getFeatures():
                        feature = f
                        break
                context.setFeature(feature)

                renderContext = QgsRenderContext()
                if isinstance(speclib.renderer(), QgsFeatureRenderer):
                    renderer = speclib.renderer().clone()

                    renderer.startRender(renderContext, speclib.fields())
                    symbol = renderer.symbolForFeature(feature, renderContext)
                    if isinstance(symbol, QgsSymbol):
                        context.appendScope(QgsExpressionContextScope(
                            symbol.symbolRenderContext().expressionContextScope()))

        color, success = property.valueAsColor(context, defaultColor=defaultColor)
        if isinstance(renderer, QgsFeatureRenderer):
            renderer.stopRender(renderContext)

        return color

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project
        self.mProject.layersWillBeRemoved.connect(self.onLayersWillBeRemoved)

    def project(self) -> QgsProject:
        return self.mProject

    def onLayersWillBeRemoved(self, layerIds: List[str]):

        to_remove = [r for r in self.layerRendererVisualizations() if r.layerId() in layerIds]
        for r in to_remove:
            r.onLayerRemoved()

    def rawData(self, feature: QgsFeature, fieldIndex: int) -> dict:
        """
        Returns the raw data struct of a deserialized spectral profile
        """
        # NA = not initialized
        # None = not available
        if not feature.isValid():
            return None
        NI = SpectralProfilePlotModel.NOT_INITIALIZED

        id_attribute = (feature.id(), fieldIndex)
        rawData = self.mCACHE_PROFILE_DATA.get(id_attribute, NI)

        fieldIndex = id_attribute[1]
        if rawData == NI or not self.mEnableCaching:
            # load profile data
            d: dict = decodeProfileValueDict(feature.attribute(fieldIndex))
            if d is None or len(d) == 0 or 'y' not in d.keys():
                # no profile
                rawData = None
            else:
                rawData = d
                if rawData.get('x', None) is None:
                    rawData['x'] = list(range(len(rawData['y'])))
                    rawData['xUnit'] = BAND_INDEX

                # convert None values to NaN so that numpy arrays will become numeric
                rawData['y'] = [np.nan if v is None or not math.isfinite(v) else v for v in rawData['y']]

            self.mCACHE_PROFILE_DATA[id_attribute] = rawData
        return self.mCACHE_PROFILE_DATA[id_attribute]

    def plotData(self, feature: QgsFeature, fieldIndex: int, xUnit: UnitWrapper) -> Tuple[dict, bool]:
        """
        Returns the data struct of a deserialized spectral profile, converted to xUnit
        """
        if not feature.isValid():
            return None
        NI = SpectralProfilePlotModel.NOT_INITIALIZED
        # NA = not initialized
        # None = not available
        id_plot_data = (feature.id(), fieldIndex, xUnit)
        id_raw_data = (feature.id(), fieldIndex)
        plotData = self.mCACHE_PROFILE_DATA.get(id_plot_data, NI)
        if plotData == NI or not self.mEnableCaching:
            rawData = self.rawData(feature, fieldIndex)

            if rawData is None:
                # cannot load raw data
                self.mCACHE_PROFILE_DATA[id_plot_data] = None
            else:
                # convert profile data to xUnit
                # if not possible, entry will be set to None
                self.mCACHE_PROFILE_DATA[id_plot_data] = self.profileDataToXUnit(rawData, xUnit)

        return self.mCACHE_PROFILE_DATA.get(id_plot_data, None)

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mPlotWidget

    sigShowSelectedFeaturesOnlyChanged = pyqtSignal(bool)

    def setShowSelectedFeaturesOnly(self, b: bool):
        if self.mShowSelectedFeaturesOnly != b:
            self.mShowSelectedFeaturesOnly = b
            self.updatePlot()
            self.sigShowSelectedFeaturesOnlyChanged.emit(self.mShowSelectedFeaturesOnly)

    def showSelectedFeaturesOnly(self) -> bool:
        return self.mShowSelectedFeaturesOnly

    sigXUnitChanged = pyqtSignal(UnitWrapper)

    def setXUnit(self, unit: Union[str, UnitWrapper]):
        unit = self.mXUnitModel.findUnitWrapper(unit)
        if self.mXUnit != unit:

            self.mXUnit = unit

            #  baseUnit = UnitLookup.baseUnit(unit_)
            labelName = self.mXUnitModel.unitData(unit, Qt.DisplayRole)
            self.mPlotWidget.xAxis().setUnit(unit, labelName=labelName)
            self.mPlotWidget.clearInfoScatterPoints()
            # self.mPlotWidget.xAxis().setLabel(text='x values', unit=unit_)
            for bv in self.layerRendererVisualizations():
                bv.setXUnit(self.mXUnit.unit)
            self.updatePlot()
            self.sigXUnitChanged.emit(self.mXUnit)

    def xUnit(self) -> UnitWrapper:
        return self.mXUnit

    def writeXml(self, parent: QDomElement, context: QgsReadWriteContext) -> QDomElement:
        doc: QDomDocument = parent.ownerDocument()

        if not parent.tagName() == 'Visualizations':
            parent = doc.createElement('Visualizations')
            doc.appendChild(parent)

        for v in self.visualizations():
            nV: QDomElement = doc.createElement('Visualization')
            parent.appendChild(nV)
            v.writeXml(nV, context)

        return parent

    def readXml(self, parent: QDomElement, context: QgsReadWriteContext):
        if not parent.tagName() == 'Visualizations':
            parent = parent.firstChildElement('Visualizations')

        if parent.isNull():
            return False

        nV = parent.firstChildElement('Visualization').toElement()

        # clean old visualizations
        self.removePropertyItemGroups(self.visualizations())

        while not nV.isNull():
            vis = ProfileVisualizationGroup()
            vis.initWithPlotModel(self)
            vis.readXml(nV, context)
            self.insertPropertyGroup(-1, vis)
            nV = nV.nextSibling().toElement()
        # clean all

        # append vis
        s = ""

    def setPlotWidget(self, plotWidget: SpectralProfilePlotWidget):
        self.mPlotWidget = plotWidget
        self.mPlotWidget.sigPlotDataItemSelected.connect(self.onPlotSelectionRequest)
        self.mPlotWidget.xAxis().setUnit(self.xUnit())  # required to set x unit in plot widget
        self.mXUnitInitialized = False

        self.mGeneralSettings.initWithPlotModel(self)

        self.mGeneralSettings.mPLegend.applySettings()

    sigMaxProfilesChanged = pyqtSignal(int)

    def setMaxProfiles(self, n: int):
        self.generalSettings().setMaximumProfiles(n)

    def maxProfiles(self) -> int:
        return self.generalSettings().maximumProfiles()

    def __len__(self) -> int:
        return len(self.visualizations())

    def __iter__(self) -> Iterator[ProfileVisualizationGroup]:
        return iter(self.visualizations())

    def profileFieldsModel(self) -> SpectralProfileFieldListModel:
        return self.mProfileFieldModel

    def propertyGroups(self) -> List[PropertyItemGroup]:
        groups = []
        for r in range(self.rowCount()):
            grp = self.invisibleRootItem().child(r, 0)
            if isinstance(grp, PropertyItemGroup):
                groups.append(grp)
        return groups

    def layerRendererVisualizations(self) -> List[RasterRendererGroup]:
        return [v for v in self.propertyGroups() if isinstance(v, RasterRendererGroup)]

    def visualizations(self) -> List[ProfileVisualizationGroup]:

        return [v for v in self.propertyGroups() if isinstance(v, ProfileVisualizationGroup)]

    def insertPropertyGroup(self,
                            index: Union[int, QModelIndex],
                            items: Union[PropertyItemGroup, List[PropertyItemGroup]],
                            ):

        # map to model index within group of same zValues
        if isinstance(items, PropertyItemGroup):
            items = [items]
        _index = None

        if isinstance(index, QModelIndex):
            index = index.row()

        for i, item in enumerate(items):
            assert isinstance(item, PropertyItemGroup)

            # remove items if requestRemoval signal is triggered
            item.signals().requestRemoval.connect(lambda *arg, itm=item: self.removePropertyItemGroups(itm))
            item.signals().requestPlotUpdate.connect(self.updatePlot)

            old_order: List[PropertyItemGroup] = self.propertyGroups()
            idx = index + i
            if idx < 0 or idx > len(old_order):
                idx = len(old_order)
            old_order.insert(idx, item)

            # ensure that items are ordered by zLevel,
            # i.e. zLevel = 0 items first, zLevel = 1 afterwards etc.
            GROUPS: dict = dict()
            for g in old_order:
                GROUPS[g.zValue()] = GROUPS.get(g.zValue(), []) + [g]

            new_group_order = []
            for zLevel in sorted(GROUPS.keys()):
                new_group_order += GROUPS[zLevel]

            self.mModelItems.add(item)
            self.insertRow(new_group_order.index(item), item)
            # if necessary, this should update the plot
            item.initWithPlotModel(self)

    def removePropertyItemGroups(self, groups: Union[PropertyItemGroup, List[PropertyItemGroup]]):

        if isinstance(groups, PropertyItemGroup):
            groups = [groups]

        if len(groups) > 0:
            for v in groups:
                if not (isinstance(v, PropertyItemGroup) and v.isRemovable()):
                    continue
                assert v in self.mModelItems

                v.disconnectGroup()

                for r in range(self.rowCount()):
                    if self.invisibleRootItem().child(r, 0) == v:
                        self.mModelItems.remove(v)
                        self.takeRow(r)
                        break

            self.updatePlot()

    def updatePlot(self, fids_to_update=[]):  #

        if not isinstance(self.speclib(), QgsVectorLayer):
            return
        if self.updatesBlocked() or self.speclib().isEditCommandActive():
            return

        if not (isinstance(self.mPlotWidget, SpectralProfilePlotWidget) and isinstance(self.speclib(), QgsVectorLayer)):
            return

        xunit: str = self.xUnit().unit

        # Recycle plot items
        old_spdis: List[SpectralProfilePlotDataItem] = self.mPlotWidget.spectralProfilePlotDataItems()

        CANDIDATES = self.profileCandidates()

        if self.mShowSelectedFeaturesOnly:
            selected_fids = set()
            # feature_priority already contains selected fids only
        else:
            selected_fids = self.speclib().selectedFeatureIds()

        feature_priority = self.featurePriority()

        visualizations = []
        for v in self.visualizations():
            v.mPlotDataItems.clear()
            if v.isVisible() and v.isComplete() and v.speclib() == self.speclib():
                visualizations.append(v)

        pdi_generator = PDIGenerator([], onProfileClicked=self.mPlotWidget.onProfileClicked)

        feature_renderer: QgsFeatureRenderer = self.speclib().renderer()
        if isinstance(feature_renderer, QgsFeatureRenderer):
            feature_renderer = feature_renderer.clone()
        else:
            feature_renderer = self.mDefaultSymbolRenderer.clone()

        request = QgsFeatureRequest()
        request.setFilterFids(feature_priority)

        # PROFILE_DATA: Dict[tuple, dict] = dict()

        profile_limit_reached: bool = False
        max_profiles = self.generalSettings().maximumProfiles()
        show_bad_bands = self.generalSettings().showBadBands()
        sort_bands = self.generalSettings().sortBands()
        context: QgsExpressionContext = self.speclib().createExpressionContext()

        PLOT_ITEMS = []

        # handle profile candidates - show them first = first positions in PLOT_DATA
        for item in CANDIDATES.candidateItems():
            item: ProfileCandidateItem

            fid = item.featureId()
            fieldIndex = item.featureFieldIndex()
            feature: QgsFeature = self.mVectorLayerCache.getFeature(fid)
            context.setFeature(feature)
            scope = item.expressionContextScope()
            context.appendScope(scope)

            if not isinstance(feature, QgsFeature):
                continue
            plot_item: SpectralProfilePlotDataItem = item.plotItem()
            plot_data = self.plotData(feature, fieldIndex, xunit)
            if plot_data:
                if len(PLOT_ITEMS) >= max_profiles:
                    profile_limit_reached = True
                    break
                plot_style = CANDIDATES.generatePlotStyle(context)
                plot_name = CANDIDATES.generateLabel(context)
                plot_tooltip = CANDIDATES.generateTooltip(context)

                vis_key = (CANDIDATES, fid, fieldIndex, xunit)
                plot_item.setVisualizationKey(vis_key)

                plot_item.setProfileData(plot_data, plot_style,
                                         showBadBands=show_bad_bands,
                                         sortBands=sort_bands,
                                         label=plot_name,
                                         tooltip=plot_tooltip,
                                         zValue=-1 * len(PLOT_ITEMS))

                if context.lastScope() == scope:
                    context.popScope()
                PLOT_ITEMS.append(plot_item)

        temporaryFIDs = CANDIDATES.candidateFeatureIds()
        feature_priority = [fid for fid in feature_priority if fid not in temporaryFIDs]
        # handle other profile visualizations
        for fid in feature_priority:
            if len(PLOT_ITEMS) >= max_profiles:
                profile_limit_reached = True
                break
            # self.mVectorLayerCache.getFeatures(feature_priority):
            feature: QgsFeature = self.mVectorLayerCache.getFeature(fid)
            assert fid == feature.id()
            # fid = feature.id()

            context.setFeature(feature)

            renderContext = QgsRenderContext()
            renderContext.setExpressionContext(context)
            feature_renderer.startRender(renderContext, feature.fields())
            qgssymbol = feature_renderer.symbolForFeature(feature, renderContext)
            symbolScope = None
            if isinstance(qgssymbol, QgsSymbol):
                symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                context.appendScope(symbolScope)

            for vis in visualizations:
                vis: ProfileVisualizationGroup

                if len(PLOT_ITEMS) >= max_profiles:
                    profile_limit_reached = True
                    break
                plotContext = QgsExpressionContext(context)
                plotContext.appendScope(vis.expressionContextScope())

                is_selected = fid in selected_fids
                if is_selected and vis.filterProperty().expressionString() != '':
                    b, success = vis.filterProperty().valueAsBool(plotContext, defaultValue=False)
                    if b is False:
                        continue
                plot_data: dict = self.plotData(feature, vis.fieldIdx(), xunit)

                if not isinstance(plot_data, dict):
                    # profile data can not be transformed to requested x-unit
                    continue

                plot_style: PlotStyle = vis.generatePlotStyle(plotContext)
                if not plot_style.isVisible():
                    continue
                plot_label: str = vis.generateLabel(plotContext)
                plot_tooltip: str = vis.generateTooltip(plotContext, label=plot_label)
                pdi = pdi_generator.__next__()
                pdi: SpectralProfilePlotDataItem
                vis_key = (vis, fid, vis.fieldIdx(), xunit)
                pdi.setVisualizationKey(vis_key)
                pdi.setProfileData(plot_data, plot_style,
                                   showBadBands=show_bad_bands,
                                   sortBands=sort_bands,
                                   label=plot_label,
                                   tooltip=plot_tooltip,
                                   zValue=-1 * len(PLOT_ITEMS))

                vis.mPlotDataItems.append(pdi)
                PLOT_ITEMS.append(pdi)
                del plotContext

            feature_renderer.stopRender(renderContext)

            if context.lastScope() == symbolScope:
                context.popScope()

        selectionColor = self.mGeneralSettings.selectionColor()
        for pdi in PLOT_ITEMS:
            pdi: SpectralProfilePlotDataItem
            fid = pdi.visualizationKey()[1]
            if fid in selected_fids:
                # show all profiles, special highlight of selected
                """
                pen=linePen,
                symbol=symbol,
                symbolPen=symbolPen,
                symbolBrush=symbolBrush,
                symbolSize=symbolSize)
                """
                pen: QPen = pdi.opts['pen']
                symbolPen: QPen = pdi.opts['symbolPen']
                symbolBrush: QBrush = pdi.opts['symbolBrush']

                pen.setColor(selectionColor)
                symbolPen.setColor(selectionColor)
                symbolBrush.setColor(selectionColor)
                pdi.updateItems(styleUpdate=True)
                # pdi.updateItems()
                # pdi.setData(pen=pen, symbolPen=symbolPen, symbolBrush=symbolBrush)
                s = ""

        # check if x unit was different to this one
        if not self.mXUnitInitialized and len(PLOT_ITEMS) > 0:
            vis_key = PLOT_ITEMS[0].visualizationKey()
            id_attribute = (vis_key[1], vis_key[2])
            rawData = self.mCACHE_PROFILE_DATA.get(id_attribute, None)
            if rawData:
                xunit2 = self.mXUnitModel.findUnit(rawData.get('xUnit', None))
                if isinstance(xunit2, str) and xunit2 != xunit:
                    self.mXUnitInitialized = True
                    self.setXUnit(xunit2)
                    # this will call updatePlot again, so we can return afterwards
                    return

        to_remove = [p for p in old_spdis if p not in PLOT_ITEMS]

        # printCaller(suffix=f'Prepare', dt=datetime.datetime.now() - t0)

        with PlotUpdateBlocker(self.mPlotWidget) as blocker:
            t1 = datetime.datetime.now()
            for p in to_remove:
                self.mPlotWidget.removeItem(p)
            existing = self.mPlotWidget.items()
            to_add = [p for p in PLOT_ITEMS if p not in existing]

            for p in to_add:
                self.mPlotWidget.addItem(p)

        # n_total = len([i for i in self.mPlotWidget.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)])

        self.updateProfileLabel(len(PLOT_ITEMS), profile_limit_reached)

        printCaller(suffix='Total', dt=t1)

    def updateProfileLabel(self, n: int, limit_reached: bool):
        propertyItem = self.generalSettings().mP_MaxProfiles

        # with SignalBlocker(propertyItem.signals()) as blocker:
        with SpectralProfilePlotModel.UpdateBlocker(self) as blocker:
            if limit_reached:
                fg = QColor('red')
                tt = 'Profile limit reached. Increase to show more profiles at the same time (decreases speed)'
            else:
                fg = None
                tt = propertyItem.definition().description()
            propertyItem.setData(tt, Qt.ToolTipRole)
            propertyItem.setData(fg, Qt.ForegroundRole)
            propertyItem.emitDataChanged()

        if limit_reached:
            self.sigMaxProfilesExceeded.emit()

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def profileCandidates(self) -> ProfileCandidateGroup:
        return self.mProfileCandidates

    def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int,
                        parent: QModelIndex) -> bool:

        return data.hasFormat(PropertyItemGroup.MIME_TYPE)

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:

        if action == Qt.IgnoreAction:
            return True
        groups = PropertyItemGroup.fromMimeData(data)
        if len(groups) > 0:
            self.insertPropertyGroup(row, groups)
            return True
        else:
            return False

    def mimeTypes(self) -> List[str]:
        return [PropertyItemGroup.MIME_TYPE]

    def mimeData(self, indexes: Iterable[QModelIndex]) -> QMimeData:

        groups: List[PropertyItemGroup] = []

        for idx in indexes:
            r = idx.row()
            grp = self.data(self.index(r, 0), role=Qt.UserRole)
            if isinstance(grp, PropertyItemGroup) and grp not in groups:
                groups.append(grp)

        mimeData = PropertyItemGroup.toMimeData(groups)
        return mimeData

    def profileDataToXUnit(self, profileData: dict, xUnit: str) -> dict:
        """
        Converts the x values from plotData.get('xUnit') to xUnit.
        Returns None if a conversion is not possible (e.g. from meters to time)
        :param profileData: profile dictionary
        :param xUnit: str
        :return: dict | None
        """

        profileData = profileData.copy()
        if profileData.get('xUnit', None) == xUnit:
            return profileData

        func = self.mUnitConverterFunctionModel.convertFunction(profileData.get('xUnit', None), xUnit)
        x = func(profileData['x'])
        y = profileData['y']
        if x is None or len(x) == 0 or len(x) != len(y):
            return None
        else:
            # convert date units to float values with decimal year and second precision to make them plotable
            if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                x = convertDateUnit(datetime64(x), 'DecimalYear')

            if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                y = convertDateUnit(datetime64(y), 'DecimalYear')

            x = np.asarray(x)
            y = np.asarray(y)
            if not (np.issubdtype(x.dtype, np.number) and np.issubdtype(y.dtype, np.number)):
                return None

            profileData['x'] = x
            profileData['y'] = y
            profileData['xUnit'] = xUnit
            return profileData

    def featurePriority(self) -> List[int]:
        """
        Returns the list of potential feature keys to be visualized, ordered by its importance.
        Can contain keys to "empty" profiles, where the value profile_field BLOB is NULL
        1st position = most important, should be plotted on top of all other profiles
        Last position = can be skipped if n_max is reached
        """
        if not is_spectral_library(self.speclib()):
            return []

        selectedOnly = self.mShowSelectedFeaturesOnly

        EXISTING_IDs = self.speclib().allFeatureIds()

        selectedIds = self.speclib().selectedFeatureIds()

        dualView = self.dualView()
        if isinstance(dualView, QgsDualView) and dualView.filteredFeatureCount() > 0:
            allIDs = dualView.filteredFeatures()
        else:
            allIDs = EXISTING_IDs[:]

        # Order:
        # 1. Visible in table
        # 2. Selected
        # 3. Others

        # overlaid features / current spectral

        priority1: List[int] = []  # visible features
        priority2: List[int] = []  # selected features
        priority3: List[int] = []  # any other : not visible / not selected

        if isinstance(dualView, QgsDualView):
            tv = dualView.tableView()
            assert isinstance(tv, QTableView)
            if not selectedOnly:
                rowHeight = tv.rowViewportPosition(1) - tv.rowViewportPosition(0)
                if rowHeight > 0:
                    visible_fids = []
                    for y in range(0, tv.viewport().height(), rowHeight):
                        idx = dualView.tableView().indexAt(QPoint(0, y))
                        if idx.isValid():
                            visible_fids.append(tv.model().data(idx, role=Qt.UserRole))
                    priority1.extend(visible_fids)
            priority2 = self.dualView().masterModel().layer().selectedFeatureIds()
            if not selectedOnly:
                priority3 = dualView.filteredFeatures()
        else:
            priority2 = selectedIds
            if not selectedOnly:
                priority3 = allIDs

        toVisualize = sorted(set(priority1 + priority2 + priority3),
                             key=lambda k: (k not in priority1, k not in priority2, k))

        # remove deleted FIDs -> see QGIS bug
        toVisualize = [fid for fid in toVisualize if fid in EXISTING_IDs]
        return toVisualize

    def generalSettings(self) -> GeneralSettingsGroup:
        return self.mGeneralSettings

    def dualView(self) -> QgsDualView:
        return self.mDualView

    def setDualView(self, dualView: QgsDualView):
        speclib = None
        self.mVectorLayerCache = None

        if self.mDualView != dualView:
            if isinstance(self.mDualView, QgsDualView):
                # disconnect
                self.mDualView.tableView().selectionModel().selectionChanged.disconnect(self.onDualViewSelectionChanged)
                self.mDualView.tableView().verticalScrollBar().sliderMoved.disconnect(self.onDualViewSliderMoved)

            self.mDualView = dualView

            if isinstance(self.mDualView, QgsDualView):
                self.mDualView.tableView().selectionModel().selectionChanged.connect(self.onDualViewSelectionChanged)
                self.mDualView.tableView().verticalScrollBar().sliderMoved.connect(self.onDualViewSliderMoved)
                # self.mDualView.view()
                speclib = dualView.masterModel().layer()

        if self.mSpeclib != speclib:
            if isinstance(self.mSpeclib, QgsVectorLayer):
                # unregister signals
                self.disconnectSpeclibSignals()

            self.mSpeclib = speclib
            self.mProfileFieldModel.setLayer(speclib)

            # connect signals
            if isinstance(self.mSpeclib, QgsVectorLayer):
                self.mVectorLayerCache = QgsVectorLayerCache(speclib, 1000)
                self.connectSpeclibSignals(self.mSpeclib)
                # self.updatePlot()

    def connectSpeclibSignals(self, speclib: QgsVectorLayer):

        speclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
        speclib.editCommandStarted.connect(self.onSpeclibEditCommandStarted)
        speclib.editCommandEnded.connect(self.onSpeclibEditCommandEnded)
        speclib.committedAttributeValuesChanges.connect(self.onSpeclibCommittedAttributeValuesChanges)
        speclib.beforeCommitChanges.connect(self.onSpeclibBeforeCommitChanges)
        speclib.afterCommitChanges.connect(self.onSpeclibAfterCommitChanges)
        speclib.committedFeaturesAdded.connect(self.onSpeclibCommittedFeaturesAdded)
        speclib.featuresDeleted.connect(self.onSpeclibFeaturesDeleted)
        speclib.selectionChanged.connect(self.onSpeclibSelectionChanged)
        speclib.styleChanged.connect(self.onSpeclibStyleChanged)
        # speclib.willBeDeleted.connect(lambda *args, sl=speclib: self.disconnectSpeclibSignals(sl))

    def disconnectSpeclibSignals(self, speclib: QgsVectorLayer):

        speclib.editCommandStarted.disconnect(self.onSpeclibEditCommandStarted)
        speclib.editCommandEnded.disconnect(self.onSpeclibEditCommandEnded)
        speclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
        speclib.beforeCommitChanges.disconnect(self.onSpeclibBeforeCommitChanges)
        # self.mSpeclib.afterCommitChanges.disconnect(self.onSpeclibAfterCommitChanges)
        speclib.committedFeaturesAdded.disconnect(self.onSpeclibCommittedFeaturesAdded)

        speclib.featuresDeleted.disconnect(self.onSpeclibFeaturesDeleted)
        speclib.selectionChanged.disconnect(self.onSpeclibSelectionChanged)
        speclib.styleChanged.disconnect(self.onSpeclibStyleChanged)
        # speclib.willBeDeleted.disconnect(self.onSpeclibWillBeDeleted)

    def onSpeclibBeforeCommitChanges(self):
        """
        Workaround for https://github.com/qgis/QGIS/issues/45228
        """
        self.mStartedCommitEditWrapper = not self.speclib().isEditCommandActive()
        if self.mStartedCommitEditWrapper:
            self.speclib().beginEditCommand('Before commit changes')
            s = ""

    def onSpeclibAfterCommitChanges(self):
        """
        Workaround for https://github.com/qgis/QGIS/issues/45228
        """
        if self.mStartedCommitEditWrapper and self.speclib().isEditCommandActive():
            self.speclib().endEditCommand()
        self.mStartedCommitEditWrapper = False

    def onSpeclibAttributeValueChanged(self, fid, idx, value):
        # warnings.warn('To expansive. Will be called for each single feature!')
        if self.speclib().isEditCommandActive():
            self.mChangedAttributes.add((fid, idx))
        # self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if (k[0], k[1]) != fid_idx}
        # self.updatePlot([fid])

    def onSpeclibCommittedFeaturesAdded(self, id, features):

        if id != self.speclib().id():
            return

        with SpectralProfilePlotModel.UpdateBlocker(self) as blocker:
            newFIDs = [f.id() for f in features]
            # see qgsvectorlayereditbuffer.cpp
            oldFIDs = list(reversed(list(self.speclib().editBuffer().addedFeatures().keys())))

            OLD2NEW = {o: n for o, n in zip(oldFIDs, newFIDs)}
            updates = dict()

            # rename fids in plot data items
            for pdi in self.mPlotWidget.spectralProfilePlotDataItems():
                grp, old_fid, fieldIndex, xunit = pdi.visualizationKey()

                if old_fid in oldFIDs:
                    new_vis_key = (grp, OLD2NEW[old_fid], fieldIndex, xunit)
                    pdi.setVisualizationKey(new_vis_key)

            # rename fids for temporary profiles
            # self.mTemporaryProfileIDs = {t for t in self.mTemporaryProfileIDs if t not in oldFIDs}
            to_remove = {k for k in OLD2NEW.keys() if k < 0}
            self.profileCandidates().syncCandidates()

        self.updatePlot(fids_to_update=OLD2NEW.values())

    def onSpeclibStyleChanged(self, *args):
        # self.loadFeatureColors()
        b = False
        for vis in self.visualizations():
            if vis.isVisible() and 'symbol_color' in vis.colorProperty().expressionString():
                b = True
                break
        if b:
            self.updatePlot()

    def onSpeclibSelectionChanged(self, selected: List[int], deselected: List[int], clearAndSelect: bool):
        s = ""
        self.updatePlot()

    def onSpeclibFeaturesDeleted(self, fids_removed):

        # todo: consider out-of-edit command values
        if len(fids_removed) == 0:
            return

        self.speclib().isEditCommandActive()

        # remove deleted features from internal caches
        # self.mCache1FeatureColors = {k: v for k, v in self.mCache1FeatureColors.items() if k not in fids_removed}
        # self.mCache1FeatureData = {k: v for k, v in self.mCache1FeatureData.items() if k not in fids_removed}
        # self.mCache2ModelData = {k: v for k, v in self.mCache2ModelData.items() if k[0] not in fids_removed}
        # self.mCache3PlotData = {k: v for k, v in self.mCache3PlotData.items() if k[0] not in fids_removed}

        self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if k[0] not in fids_removed}
        self.updatePlot()
        s = ""

    def onSpeclibCommittedAttributeValuesChanges(self, lid: str, changedAttributeValues: Dict[int, dict]):
        changedAttributes = set()
        for fid, attributeMap in changedAttributeValues.items():
            for i in attributeMap.keys():
                changedAttributes.add((fid, i))

        self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if
                                    (k[0], k[1]) != changedAttributes}
        self.updatePlot()
        s = ""

    def onSpeclibEditCommandStarted(self, cmd: str):
        self.mChangedAttributes.clear()
        self.mLastEditCommand = cmd
        s = ""

    def onSpeclibEditCommandEnded(self, *args):
        # changedFIDs1 = list(self.speclib().editBuffer().changedAttributeValues().keys())
        changedFIDs2 = self.mChangedFIDs
        changedAttribute = self.mChangedAttributes
        lastCmd = self.mLastEditCommand
        with SpectralProfilePlotModel.UpdateBlocker(self) as blocker:
            if len(self.mChangedAttributes) > 0:
                n0 = len(self.mCACHE_PROFILE_DATA)
                updated = [k for k in self.mCACHE_PROFILE_DATA.keys() if (k[0], k[1]) in self.mChangedAttributes]
                self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if
                                            (k[0], k[1]) not in self.mChangedAttributes}

                n1 = len(self.mCACHE_PROFILE_DATA)
                # self.mCACHE_PROFILE_DATA.clear()
                if n1 < n0:
                    s = ""
                self.mChangedAttributes.clear()
        self.updatePlot()
        # self.onSpeclibFeaturesDeleted(sorted(changedFIDs2))
        # self.mChangedFIDs.clear()

    def onDualViewSliderMoved(self, *args):
        self.updatePlot()

    def onDualViewSelectionChanged(self, *args):
        s = ""

    def onPlotSelectionRequest(self, pdi, modifiers):
        pdi: SpectralProfilePlotDataItem
        assert isinstance(pdi, SpectralProfilePlotDataItem)
        if isinstance(self.speclib(), QgsVectorLayer):
            vis, fid, field, xUnit = pdi.visualizationKey()

            vis: ProfileVisualizationGroup
            speclib = vis.speclib()

            if isinstance(speclib, QgsVectorLayer):
                fids = self.speclib().selectedFeatureIds()
                if modifiers == Qt.NoModifier:
                    fids = [fid]
                elif modifiers == Qt.ShiftModifier or modifiers == Qt.ControlModifier:
                    if fid in fids:
                        fids.remove(fid)
                    else:
                        fids.append(fid)
                speclib.selectByIds(fids)

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def profileFields(self) -> List[QgsField]:
        return profile_field_list(self.speclib())

    def profileFieldIndices(self) -> List[int]:
        return profile_field_indices(self.speclib())

    def profileFieldNames(self) -> List[str]:
        return profile_field_indices()

    PropertyIndexRole = Qt.UserRole + 1
    PropertyDefinitionRole = Qt.UserRole + 2
    PropertyRole = Qt.UserRole + 3


class PDIGenerator(object):
    """
    A generator over SpectralProfilePlotData items.
    Uses existing ones and, if nececessary, creates new ones.
    """

    def __init__(self, existingPDIs: List[SpectralProfilePlotDataItem] = [],
                 onProfileClicked: Callable = None):
        self.pdiList: List[SpectralProfilePlotDataItem] = existingPDIs
        self.onProfileClicked = onProfileClicked
        self.mZValue = -1

    def zValue(self) -> int:
        return self.mZValue

    def __iter__(self):
        return self

    def __next__(self):
        self.mZValue += 1
        if len(self.pdiList) > 0:
            return self.pdiList.pop(0)
        else:
            # create new
            pdi = SpectralProfilePlotDataItem()
            if self.onProfileClicked:
                pdi.setClickable(True)
                pdi.sigProfileClicked.connect(self.onProfileClicked)

            return pdi

    def remaining(self) -> List[SpectralProfilePlotDataItem]:
        return self.pdiList[:]


class SpectralProfilePlotView(QTreeView):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotView, self).__init__(*args, **kwds)
        # self.horizontalHeader().setStretchLastSection(True)
        # self.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def controlTable(self) -> SpectralProfilePlotModel:
        return self.model()

    def selectedPropertyGroups(self) -> List[PropertyItemGroup]:
        return [idx.data(Qt.UserRole)
                for idx in self.selectionModel().selectedIndexes()
                if isinstance(idx.data(Qt.UserRole), PropertyItemGroup)]

    def selectPropertyGroups(self, visualizations):
        if isinstance(visualizations, ProfileVisualizationGroup):
            visualizations = [visualizations]

        model = self.model()
        rows = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            vis = model.data(idx, Qt.UserRole)
            if isinstance(vis, ProfileVisualizationGroup) and vis in visualizations:
                self.selectionModel().select(idx, QItemSelectionModel.Rows)

    def setModel(self, model: Optional[QAbstractItemModel]) -> None:
        super().setModel(model)
        if isinstance(model, QAbstractItemModel):
            model.rowsInserted.connect(self.onRowsInserted)

            for r in range(0, model.rowCount()):
                idx = model.index(r, 0)
                item = idx.data(Qt.UserRole)
                if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                    self.setFirstColumnSpanned(r, idx.parent(), True)

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        for r in range(first, last + 1):
            idx = self.model().index(r, 0, parent=parent)
            item = idx.data(Qt.UserRole)
            if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                self.setFirstColumnSpanned(r, idx.parent(), True)
        s = ""

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        selected_indices = self.selectionModel().selectedRows()
        if len(selected_indices) == 1:
            item = selected_indices[0].data(Qt.UserRole)
            if isinstance(item, PropertyLabel):
                item = item.propertyItem()
            if isinstance(item, PropertyItemBase):
                item.populateContextMenu(menu)
            if isinstance(item, PropertyItem):
                # add menu of parent group
                group = item.parent()
                if isinstance(group, PropertyItemBase):
                    if len(menu.actions()) > 0 and menu.actions()[-1].text() != '':
                        menu.addSeparator()
                    group.populateContextMenu(menu)
                s = ""

            s = ""

        elif len(selected_indices) > 0:
            selected_items = []
            for idx in selected_indices:
                item = idx.data(Qt.UserRole)
                if isinstance(item, PropertyItemGroup) and item not in selected_items:
                    selected_items.append(item)

            removable = [item for item in selected_items if item.isRemovable()]
            copyAble = [item for item in selected_items if item.isDragEnabled()]

            profileVis = [item for item in selected_items if isinstance(item, ProfileVisualizationGroup)]

            a = menu.addAction('Remove')
            a.setIcon(QIcon(r':/images/themes/default/mActionDeleteSelected.svg'))
            a.triggered.connect(lambda *args, v=removable: self.removeItems(v))
            a.setEnabled(len(removable) > 0)

            a = menu.addAction('Copy')
            a.setIcon(QIcon(r':/images/themes/default/mActionEditCopy.svg'))
            a.triggered.connect(lambda *args, v=copyAble: self.copyItems(v))
            a.setEnabled(len(copyAble) > 0)

            a = menu.addAction('Paste')
            a.setIcon(QIcon(r':/images/themes/default/mActionEditPaste.svg'))
            a.setEnabled(QApplication.clipboard().mimeData().hasFormat(ProfileVisualizationGroup.MIME_TYPE))
            a.triggered.connect(lambda *args: self.pasteItems())
            a.setEnabled(
                QApplication.clipboard().mimeData().hasFormat(ProfileVisualizationGroup.MIME_TYPE)
            )

            if len(profileVis) > 0:
                a = menu.addAction('Use vector symbol colors')
                a.setToolTip('Use map vector symbol colors as profile color.')
                a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
                a.triggered.connect(lambda *args, v=profileVis: self.userColorsFromSymbolRenderer(v))

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def removeItems(self, vis: List[PropertyItemGroup]):

        model = self.model()

        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        if isinstance(model, SpectralProfilePlotModel):
            model.removePropertyItemGroups(vis)

    def copyItems(self, visualizations: List[ProfileVisualizationGroup]):

        indices = []
        for vis in visualizations:
            idx = self.vis2index(vis)
            if idx.isValid():
                indices.append(idx)
        if len(indices) > 0:
            mimeData = self.model().mimeData(indices)
            QApplication.clipboard().setMimeData(mimeData)

    def pasteItems(self):

        md: QMimeData = QApplication.clipboard().mimeData()

        idx = self.currentIndex()
        self.model().dropMimeData(md, Qt.CopyAction, idx.row(), idx.column(), idx.parent())

    def vis2index(self, vis: ProfileVisualizationGroup) -> QModelIndex:
        for r in range(self.model().rowCount()):
            idx = self.model().index(r, 0)
            if self.model().data(idx, Qt.UserRole) == vis:
                return idx
        return QModelIndex()

    def idx2vis(self, index: QModelIndex) -> PropertyItemGroup:

        if index.isValid():
            obj = self.model().data(index, role=Qt.UserRole)
            if isinstance(obj, PropertyItemGroup):
                return obj
            elif isinstance(obj, PropertyItem):
                return obj.parent()

        return None

    def userColorsFromSymbolRenderer(self, vis: List[ProfileVisualizationGroup]):
        for v in vis:
            if isinstance(v, ProfileVisualizationGroup):
                v.mPColor.setToSymbolColor()


class SpectralProfilePlotViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: SpectralProfilePlotView, parent=None):
        assert isinstance(treeView, SpectralProfilePlotView)
        super(SpectralProfilePlotViewDelegate, self).__init__(parent=parent)
        self.mTreeView: SpectralProfilePlotView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: PropertyItem = index.data(Qt.UserRole)
        bc = QColor(self.plotControl().generalSettings().backgroundColor())
        total_h = self.mTreeView.rowHeight(index)
        total_w = self.mTreeView.columnWidth(index.column())
        style: QStyle = option.styleObject.style()
        # print(style)
        margin = 2  # px
        if isinstance(item, PropertyItemBase):
            if item.hasPixmap():
                super().paint(painter, option, index)
                rect = option.rect
                size = QSize(rect.width(), rect.height())
                pixmap = item.previewPixmap(size)
                if isinstance(pixmap, QPixmap):
                    painter.drawPixmap(rect, pixmap)

            elif isinstance(item, ProfileVisualizationGroup):
                # super().paint(painter, option, index)
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                h = option.rect.height()
                plot_style: PlotStyle = item.mPStyle.plotStyle()

                # add pixmap
                pm = plot_style.createPixmap(size=QSize(h, h), hline=True, bc=bc)
                to_paint.append(pm)
                if not item.isComplete():
                    to_paint.append(QIcon(r':/images/themes/default/mIconWarning.svg'))
                to_paint.append(item.data(Qt.DisplayRole))

                x0 = option.rect.x()  # + 1
                y0 = option.rect.y()
                # print(to_paint)

                for p in to_paint:
                    o: QStyleOptionViewItem = QStyleOptionViewItem(option)
                    self.initStyleOption(o, index)
                    o.styleObject = option.styleObject
                    o.palette = QPalette(option.palette)

                    if isinstance(p, Qt.CheckState):
                        # size = style.sizeFromContents(QStyle.CE_CheckBox, o, QSize(), None)
                        o = QStyleOptionButton()

                        o.rect = QRect(x0, y0, h, h)
                        # print(o.rect)
                        o.state = {Qt.Unchecked: QStyle.State_Off,
                                   Qt.Checked: QStyle.State_On,
                                   Qt.PartiallyChecked: QStyle.State_NoChange}[p]
                        o.state = o.state | QStyle.State_Enabled | QStyleOptionButton.Flat | QStyleOptionButton.AutoDefaultButton

                        check_option = QStyleOptionButton()
                        check_option.state = o.state  # Checkbox is enabled

                        # Set the geometry of the checkbox within the item
                        check_option.rect = option.rect
                        QApplication.style().drawControl(QStyle.CE_CheckBox, check_option, painter)

                    elif isinstance(p, QPixmap):
                        o.rect = QRect(x0, y0, h * 2, h)
                        painter.drawPixmap(o.rect, p)

                    elif isinstance(p, QIcon):
                        o.rect = QRect(x0, y0, h, h)
                        p.paint(painter, o.rect)
                    elif isinstance(p, str):
                        font_metrics = QFontMetrics(self.mTreeView.font())
                        w = font_metrics.horizontalAdvance(p)
                        o.rect = QRect(x0 + margin, y0, x0 + margin + w, h)
                        # palette =
                        # palette = style.standardPalette()

                        enabled = item.checkState() == Qt.Checked
                        if not enabled:
                            o.palette.setCurrentColorGroup(QPalette.Disabled)
                        style.drawItemText(painter, o.rect, Qt.AlignLeft | Qt.AlignVCenter, o.palette, enabled, p,
                                           textRole=QPalette.Foreground)

                    else:
                        raise NotImplementedError(f'Does not support painting of "{p}"')
                    x0 = o.rect.x() + margin + o.rect.width()

            elif isinstance(item, PlotStyleItem):
                # self.initStyleOption(option, index)
                plot_style: PlotStyle = item.plotStyle()

                if total_h > 0 and total_w > 0:
                    px = plot_style.createPixmap(size=QSize(total_w, total_h), bc=bc)
                    painter.drawPixmap(option.rect, px)
                else:
                    super().paint(painter, option, index)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def setItemDelegates(self, treeView: QTreeView):
        for c in range(treeView.model().columnCount()):
            treeView.setItemDelegateForColumn(c, self)

    def onRowsInserted(self, parent, idx0, idx1):
        nameStyleColumn = self.bridge().cnPlotStyle

        for c in range(self.mTreeView.model().columnCount()):
            cname = self.mTreeView.model().headerData(c, Qt.Horizontal, Qt.DisplayRole)
            if cname == nameStyleColumn:
                for r in range(idx0, idx1 + 1):
                    idx = self.mTreeView.model().index(r, c, parent=parent)
                    self.mTreeView.openPersistentEditor(idx)

    def plotControl(self) -> SpectralProfilePlotModel:
        return self.mTreeView.model().sourceModel()

    def createEditor(self, parent, option, index):
        w = None
        editor = None
        if index.isValid():
            item = index.data(Qt.UserRole)
            if isinstance(item, PropertyItem):
                editor = item.createEditor(parent)
            if isinstance(item, ProfileCandidateGroup):
                s = ""
        if isinstance(editor, QWidget):
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        if not index.isValid():
            return

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setEditorData(editor, index)
        else:
            super().setEditorData(editor, index)

        return

    def setModelData(self, w, model, index):

        item = index.data(Qt.UserRole)
        if isinstance(item, PropertyItem):
            item.setModelData(w, model, index)
        else:
            super().setModelData(w, model, index)


class SpectralLibraryPlotWidget(QWidget):
    sigDragEnterEvent = pyqtSignal(QDragEnterEvent)
    sigDropEvent = pyqtSignal(QDropEvent)
    sigPlotWidgetStyleChanged = pyqtSignal()

    SHOW_MAX_PROFILES_HINT = True

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryplotwidget.ui'), self)

        assert isinstance(self.panelVisualization, QFrame)

        assert isinstance(self.plotWidget, SpectralProfilePlotWidget)
        assert isinstance(self.treeView, SpectralProfilePlotView)

        self.plotWidget: SpectralProfilePlotWidget
        assert isinstance(self.plotWidget, SpectralProfilePlotWidget)
        # self.plotWidget.sigPopulateContextMenuItems.connect(self.onPopulatePlotContextMenu)
        self.mPlotControlModel = SpectralProfilePlotModel()
        self.mPlotControlModel.setPlotWidget(self.plotWidget)
        self.mPlotControlModel.sigPlotWidgetStyleChanged.connect(self.sigPlotWidgetStyleChanged.emit)
        self.mPlotControlModel.sigMaxProfilesExceeded.connect(self.onMaxProfilesReached)
        self.mINITIALIZED_VISUALIZATIONS = set()

        # self.mPlotControlModel.sigProgressChanged.connect(self.onProgressChanged)
        self.setAcceptDrops(True)

        self.mProxyModel = SpectralProfilePlotModelProxyModel()
        self.mProxyModel.setSourceModel(self.mPlotControlModel)

        self.mFilterLineEdit: QgsFilterLineEdit
        self.mFilterLineEdit.textChanged.connect(self.setFilter)

        self.treeView.setModel(self.mProxyModel)
        self.treeView.selectionModel().selectionChanged.connect(self.onVisSelectionChanged)

        self.mViewDelegate = SpectralProfilePlotViewDelegate(self.treeView)
        self.mViewDelegate.setItemDelegates(self.treeView)

        self.mDualView: QgsDualView = None
        self.mSettingsModel = SettingsModel(QgsSettings('qps'), key_filter='qps/spectrallibrary')

        self.optionShowVisualizationSettings: QAction
        self.optionShowVisualizationSettings.setCheckable(True)
        self.optionShowVisualizationSettings.setChecked(True)
        self.optionShowVisualizationSettings.setIcon(QgsApplication.getThemeIcon(r'/legend.svg'))
        self.optionShowVisualizationSettings.toggled.connect(self.panelVisualization.setVisible)

        self.actionAddProfileVis: QAction
        self.actionAddProfileVis.triggered.connect(self.createProfileVisualization)
        self.actionAddProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionAdd.svg'))

        self.actionAddRasterLayerRenderer: QAction
        self.actionAddRasterLayerRenderer.triggered.connect(self.createLayerBandVisualization)
        self.actionAddRasterLayerRenderer.setIcon(QgsApplication.getThemeIcon('/rendererCategorizedSymbol.svg'))

        self.actionRemoveProfileVis: QAction
        self.actionRemoveProfileVis.triggered.connect(self.removeSelectedPropertyGroups)
        self.actionRemoveProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionRemove.svg'))

        self.optionSelectedFeaturesOnly: QAction
        self.optionSelectedFeaturesOnly.toggled.connect(self.mPlotControlModel.setShowSelectedFeaturesOnly)
        self.optionSelectedFeaturesOnly.setIcon(QgsApplication.getThemeIcon("/mActionShowSelectedLayers.svg"))
        self.mPlotControlModel.sigShowSelectedFeaturesOnlyChanged.connect(self.optionSelectedFeaturesOnly.setChecked)

        # self.sbMaxProfiles: QSpinBox
        # self.sbMaxProfiles.valueChanged.connect(self.mPlotControlModel.setMaxProfiles)
        # self.labelMaxProfiles: QLabel
        # self.mPlotControlModel.setMaxProfilesWidget(self.sbMaxProfiles)

        self.optionCursorCrosshair: QAction
        self.optionCursorCrosshair.toggled.connect(self.plotWidget.setShowCrosshair)

        self.optionCursorPosition: QAction
        self.optionCursorPosition.toggled.connect(self.plotWidget.setShowCursorInfo)

        self.optionXUnit = SpectralProfilePlotXAxisUnitWidgetAction(self, self.mPlotControlModel.mXUnitModel)
        self.optionXUnit.setUnit(self.mPlotControlModel.xUnit())
        self.optionXUnit.setDefaultWidget(self.optionXUnit.createUnitComboBox())
        self.optionXUnit.sigUnitChanged.connect(self.mPlotControlModel.setXUnit)
        self.mPlotControlModel.sigXUnitChanged.connect(self.optionXUnit.setUnit)

        self.visButtonLayout: QHBoxLayout
        self.visLayoutTop: QHBoxLayout
        # self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1,
        #                                  self.optionMaxNumberOfProfiles.createWidget(self))

        # self.visLayoutTop = QHBoxLayout()
        cb: QComboBox = self.optionXUnit.createUnitComboBox()
        # cb.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.visLayoutTop.addWidget(cb)
        self.visLayoutTop.setStretchFactor(cb, 3)
        # self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1,
        #                                  self.optionMaxNumberOfProfiles.createWidget(self))

        widgetXAxis: QWidget = self.plotWidget.viewBox().menu.widgetGroups[0]
        widgetYAxis: QWidget = self.plotWidget.viewBox().menu.widgetGroups[1]
        # grid: QGridLayout = widgetXAxis.layout()
        # grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        # grid.addWidget(self.optionXUnit.createUnitComboBox(), 0, 2, 1, 2)

        self.plotWidget.plotItem.sigPopulateContextMenuItems.connect(self.populateProfilePlotContextMenu)

        # connect actions with buttons
        self.btnAddProfileVis.setDefaultAction(self.actionAddProfileVis)
        self.btnAddRasterLayerRenderer.setDefaultAction(self.actionAddRasterLayerRenderer)
        self.btnRemoveProfileVis.setDefaultAction(self.actionRemoveProfileVis)
        self.btnSelectedFeaturesOnly.setDefaultAction(self.optionSelectedFeaturesOnly)

    def setProject(self, project: QgsProject):
        self.plotWidget.setProject(project)
        self.plotControlModel().setProject(project)

    def plotWidgetStyle(self) -> PlotWidgetStyle:
        return self.mPlotControlModel.plotWidgetStyle()

    def populateProfilePlotContextMenu(self, listWrapper: SignalObjectWrapper):
        itemList: list = listWrapper.wrapped_object
        # update current renderer

    def plotControlModel(self) -> SpectralProfilePlotModel:
        return self.mPlotControlModel

    def updatePlot(self):
        self.mPlotControlModel.updatePlot()

    def readSettings(self):
        pass

    def writeSettings(self):
        pass

    def onVisSelectionChanged(self):

        # rows = self.treeView.selectionModel().selectedRows()
        groups = [g for g in self.treeView.selectedPropertyGroups() if g.isRemovable()]
        self.actionRemoveProfileVis.setEnabled(len(groups) > 0)

    def onMaxProfilesReached(self):

        if self.SHOW_MAX_PROFILES_HINT:
            n = self.mPlotControlModel.maxProfiles()

            self.panelVisualization.setVisible(True)

            item = self.plotControlModel().mGeneralSettings.mP_MaxProfiles
            idx = self.plotControlModel().indexFromItem(item)
            idx2 = self.treeView.model().mapFromSource(idx)
            self.treeView.setExpanded(idx2, True)
            self.treeView.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

            result = QMessageBox.information(self,
                                             'Maximum number of profiles',
                                             f'Reached maximum number of profiles to display ({n}).\n'
                                             'Increase this value to display more profiles at same time.\n'
                                             'Showing large numbers of profiles at same time can reduce '
                                             'the visualization speed')

            self.SHOW_MAX_PROFILES_HINT = False

    def onSpeclibFieldsUpdated(self, *args):

        profilefields = profile_fields(self.speclib())
        to_remove = []
        to_add = []

        # remove visualizations for removed fields
        for vis in self.profileVisualizations():
            if not isinstance(vis.field(), QgsField) or vis.field().name() not in profilefields.names():
                to_remove.append(vis)

        self.mPlotControlModel.removePropertyItemGroups(to_remove)

        for name in list(self.mINITIALIZED_VISUALIZATIONS):
            if name not in profilefields.names():
                self.mINITIALIZED_VISUALIZATIONS.remove(name)

        for field in profilefields:
            name = field.name()
            if name not in self.mINITIALIZED_VISUALIZATIONS:

                has_checked_vis = any([v.checkState() == Qt.Checked for v in self.profileVisualizations()])

                self.createProfileVisualization(field=field, checked=not has_checked_vis)
                # keep in mind if a visualization was created at least once for a profile field
                self.mINITIALIZED_VISUALIZATIONS.add(name)

    def createLayerBandVisualization(self, *args):

        layer = None
        d = SelectMapLayerDialog()
        d.setWindowTitle('Select Raster Layer')
        d.setProject(self.plotControlModel().project())
        d.mapLayerComboBox().setFilters(QgsMapLayerProxyModel.RasterLayer)
        if d.exec_() == QDialog.Accepted:
            layer = d.layer()

        existing_layers = [v.layer() for v in self.mPlotControlModel.layerRendererVisualizations()]
        if isinstance(layer, QgsRasterLayer) and layer not in existing_layers:
            lvis = RasterRendererGroup(layer=layer)
            self.mPlotControlModel.insertPropertyGroup(0, lvis)

    def createProfileVisualization(self, *args,
                                   name: str = None,
                                   field: Union[QgsField, int, str] = None,
                                   color: Union[str, QColor] = None,
                                   style: PlotStyle = None,
                                   checked: bool = True):
        item = ProfileVisualizationGroup()
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        # set defaults
        # set speclib
        item.setSpeclib(self.speclib())

        # set profile source in speclib
        if field:
            item.setField(qgsField(item.speclib(), field))
        else:
            existing_fields = [v.field()
                               for v in self.plotControlModel().visualizations()
                               if isinstance(v.field(), QgsField)]

            for fld in profile_field_list(item.speclib()):
                if fld not in existing_fields:
                    item.setField(fld)
                    break

            if not isinstance(item.field(), QgsField) and len(existing_fields) > 0:
                item.setField(existing_fields[-1])

        if name is None:
            if isinstance(item.field(), QgsField):
                _name = f'Group "{item.field().name()}"'
            else:
                _name = 'Group'

            existing_names = [v.name() for v in self.mPlotControlModel]
            n = 1
            name = _name
            while name in existing_names:
                n += 1
                name = f'{_name} {n}'

        item.setName(name)

        if isinstance(item.speclib(), QgsVectorLayer):
            # get a good guess for the name expression
            # 1. "<source_field_name>_name"
            # 2. "name"
            # 3. $id (fallback)

            name_field = None
            source_field_name = item.fieldName()
            rx1 = re.compile(source_field_name + '_?name', re.I)
            rx2 = re.compile('name', re.I)
            rx3 = re.compile('fid', re.I)
            for rx in [rx1, rx2, rx3]:
                for field in item.speclib().fields():
                    if field.type() in [QMETATYPE_QSTRING, QMETATYPE_INT] and rx.search(field.name()):
                        name_field = field
                        break
                if name_field:
                    break
            if isinstance(name_field, QgsField):
                item.setLabelExpression(f'"{name_field.name()}"')
            else:
                item.setLabelExpression('$id')

        if not isinstance(style, PlotStyle):
            style = self.plotControlModel().generalSettings().defaultProfileStyle()
        item.setPlotStyle(style)

        if color is not None:
            item.setColor(color)

        self.mPlotControlModel.insertPropertyGroup(-1, item)

    def profileVisualizations(self) -> List[ProfileVisualizationGroup]:
        return self.mPlotControlModel.visualizations()

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.sigDragEnterEvent.emit(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.sigDropEvent.emit(event)

    def removeSelectedPropertyGroups(self, *args):
        rows = self.treeView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows if isinstance(r.data(Qt.UserRole), PropertyItemGroup)]
        self.mPlotControlModel.removePropertyItemGroups(to_remove)

    def setDualView(self, dualView):
        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            sl.updatedFields.disconnect(self.onSpeclibFieldsUpdated)

        self.mDualView = dualView
        self.mPlotControlModel.setDualView(dualView)

        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            sl.updatedFields.connect(self.onSpeclibFieldsUpdated)
        self.onSpeclibFieldsUpdated()

    def speclib(self) -> QgsVectorLayer:
        return self.mPlotControlModel.speclib()

    # def addSpectralModel(self, model):
    #    self.mPlotControlModel.addModel(model)

    def setFilter(self, pattern: str):
        self.mProxyModel.setFilterWildcard(pattern)
