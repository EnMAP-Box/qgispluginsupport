import datetime
import json
import math
import re
from typing import Iterable, Iterator, List, Optional, Set, Tuple, Union, Dict

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QItemSelectionModel, QMimeData, QModelIndex, \
    QPoint, QRect, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QDragEnterEvent, QDropEvent, QFontMetrics, QIcon, \
    QPainter, QPalette, QPixmap, QStandardItem, QStandardItemModel
from qgis.PyQt.QtGui import QPen
from qgis.PyQt.QtWidgets import QAbstractItemView, QAction, QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, \
    QMenu, QMessageBox, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QTableView, QTreeView, \
    QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsApplication, QgsExpressionContext, QgsExpressionContextScope, QgsFeature, QgsFeatureRenderer, \
    QgsFeatureRequest, QgsField, QgsMapLayerProxyModel, QgsMarkerSymbol, QgsProject, QgsProperty, QgsRasterLayer, \
    QgsReadWriteContext, QgsRenderContext, QgsSettings, QgsSingleSymbolRenderer, QgsSymbol, QgsVectorLayer, \
    QgsVectorLayerCache, QgsExpressionContextUtils, QgsExpression
from qgis.gui import QgsDualView, QgsFilterLineEdit
from .spectrallibraryplotitems import PlotUpdateBlocker, \
    SpectralProfilePlotDataItem, SpectralProfilePlotWidget, SpectralProfilePlotLegend
from .spectrallibraryplotmodelitems import GeneralSettingsGroup, PlotStyleItem, ProfileCandidateGroup, \
    ProfileVisualizationGroup, PropertyItem, PropertyItemBase, PropertyItemGroup, PropertyLabel, \
    RasterRendererGroup
from .spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel, SpectralProfilePlotXAxisUnitWidgetAction
from .spectralprofilefieldmodel import SpectralProfileFieldListModel
from .. import speclibUiPath
from ..core import is_spectral_library, profile_field_indices, profile_field_list, profile_fields
from ..core.spectralprofile import decodeProfileValueDict
from ...models import SettingsModel
from ...plotstyling.plotstyling import PlotStyle, PlotWidgetStyle
from ...pyqtgraph.pyqtgraph import SignalProxy, PlotCurveItem, PlotDataItem, SpotItem, ScatterPlotItem
from ...pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent, HoverEvent
from ...qgisenums import QMETATYPE_INT, QMETATYPE_QSTRING
from ...unitmodel import BAND_INDEX, BAND_NUMBER, datetime64, UnitConverterFunctionModel, UnitWrapper
from ...utils import convertDateUnit, loadUi, SelectMapLayerDialog

MAX_PROFILES_DEFAULT: int = 516
FIELD_NAME = str


class SpectralProfilePlotModelProxyModel(QSortFilterProxyModel):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotModelProxyModel, self).__init__(*args, **kwds)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)


def _dict_differs(d_old: Optional[dict], d_new: Optional[dict], key: str) -> bool:
    if d_old is None:
        d_old = dict()
    if d_new is None:
        d_new = dict()

    if key in d_old.keys() != key in d_new.keys():
        return True
    elif key in d_old.keys() and key in d_new.keys():
        return d_old[key] != d_new[key]
    else:
        return False


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

        self.mLastSettings: dict = dict()
        self.mLastReferencedColumns: dict = dict()
        self.mLayerCaches: Dict[str, QgsVectorLayerCache] = dict()
        self.nUpdates: int = 0
        self.mProject: QgsProject = QgsProject.instance()

        self.mSignalProxies: Dict[str, List[SignalProxy]] = dict()
        self.mModelItems: Set[PropertyItemGroup] = set()

        self.mSELECTED_SPOTS: Dict[str, Tuple[int, int]] = dict()

        # # workaround https://github.com/qgis/QGIS/issues/45228
        self.mStartedCommitEditWrapper: bool = False

        # data cache organized by: level1: layer id (str),
        #                          level2: attribute field (int),
        #                          level3: feature id (int)             = raw data
        #                                  (feature id (int), xUnit (str))  = unit data
        #                          items
        self.mCACHE_PROFILE_DATA: Dict[
            str, Dict[int, Dict[Union[int, Tuple[int, str]], Union[None, dict, int]]]] = dict()
        self.mEnableCaching: bool = True
        self.mProfileFieldModel: SpectralProfileFieldListModel = SpectralProfileFieldListModel()

        self.mPlotWidget: Optional[SpectralProfilePlotWidget] = None

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
        self._update_rate_limit = 60
        self._sp1 = SignalProxy(self.itemChanged, rateLimit=self._update_rate_limit, slot=self.updatePlotIfChanged)
        self._sp2 = SignalProxy(self.rowsInserted, rateLimit=self._update_rate_limit, slot=self.updatePlotIfChanged)

        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        fg = self.generalSettings().foregroundColor()
        style.setLineColor(fg)
        style.setMarkerColor(fg)
        style.setMarkerSymbol(None)
        style.setBackgroundColor(self.generalSettings().backgroundColor())
        self.mDefaultProfileStyle = style

    def settingsMap(self) -> dict:
        """
        Returns the plot settings as JSON-serializable dictionary.
        """
        settings = dict()
        settings['general'] = self.mGeneralSettings.asMap()
        settings['general']['x_unit'] = str(self.xUnit().unit)
        settings['candidates'] = self.profileCandidates().asMap()
        settings['visualizations'] = [v.asMap() for v in self.visualizations()
                                      if v.isVisible() and v.isComplete()]

        return settings

    def updatePlotIfChanged(self, *args):
        old_settings = self.mLastSettings
        new_settings = self.settingsMap()
        if new_settings != old_settings:
            self.mLastSettings = new_settings

            g_new = new_settings.get('general', {})
            g_old = old_settings.get('general', {})

            # do the light work
            if g_new != g_old:
                w: SpectralProfilePlotWidget = self.plotWidget()
                w.setSelectionColor(g_new['color_sc'])
                w.setCrosshairColor(g_new['color_ch'])
                w.setShowCrosshair(g_new['show_crosshair'])
                w.setForegroundColor(g_new['color_fg'])
                w.setBackground(g_new['color_bg'])
                legend = w.getPlotItem().legend
                if isinstance(legend, SpectralProfilePlotLegend):
                    pen = legend.pen()
                    pen.setColor(QColor(g_new['color_fg']))
                    legend.setPen(pen)
                    legend.setLabelTextColor(QColor(g_new['color_fg']))
                    legend.update()

            update_heavy = False
            for k in ['x_unit', 'sort_bands', 'show_bad_bands', 'max_profiles']:
                if g_old.get(k, None) != g_new.get(k, None):
                    update_heavy = True

            # doing the heavy work
            if update_heavy \
                    or old_settings.get('visualizations', {}) != new_settings.get('visualizations', {}) \
                    or old_settings.get('candidates', {}) != new_settings.get('candidates', {}):
                self.updatePlot(settings=new_settings)

        # if not self.updatesBlocked():
        # print('#ITEM CHANGED')
        # self.updatePlot()
        #    pass

    def dict_differences(self, dict1, dict2):
        # Find keys that are in both dictionaries but have different values
        common_keys = set(dict1.keys()) & set(dict2.keys())
        diff = {k: (dict1[k], dict2[k]) for k in common_keys if dict1[k] != dict2[k]}

        # Find keys that are only in dict1
        only_in_dict1 = {k: dict1[k] for k in dict1.keys() - dict2.keys()}

        # Find keys that are only in dict2
        only_in_dict2 = {k: dict2[k] for k in dict2.keys() - dict1.keys()}

        # Combine all differences into a single dictionary
        differences = {
            'changed_values': diff,
            'only_in_dict1': only_in_dict1,
            'only_in_dict2': only_in_dict2
        }

        return differences

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

    def rawData(self,
                layer_id: str,
                fieldIndex: int,
                feature: Union[int, QgsFeature]) -> Union[None, int, dict]:
        """
        Returns the raw data struct of a spectral profile field, after it has been
        extracted from a QgsFeature.
        """
        # NA = not initialized
        # None = not available
        NI = SpectralProfilePlotModel.NOT_INITIALIZED

        if isinstance(feature, int):
            return self.mCACHE_PROFILE_DATA[layer_id][fieldIndex].get(feature, NI)

        else:
            if not feature.isValid():
                return None

            raw_data = self.mCACHE_PROFILE_DATA[layer_id][fieldIndex].get(feature.id, NI)

            if raw_data == NI or not self.mEnableCaching:
                # load profile data
                d: dict = decodeProfileValueDict(feature.attribute(fieldIndex))
                if d is None or len(d) == 0 or 'y' not in d.keys():
                    # no profile
                    raw_data = None
                else:
                    raw_data = d
                    if raw_data.get('x', None) is None:
                        raw_data['x'] = list(range(len(raw_data['y'])))
                        raw_data['xUnit'] = BAND_INDEX

                    # convert None values to NaN so that numpy arrays will become numeric
                    raw_data['y'] = [np.nan if v is None or not math.isfinite(v) else v for v in raw_data['y']]

                self.mCACHE_PROFILE_DATA[layer_id][fieldIndex][feature.id()] = raw_data
            return raw_data

    def plotData2(self, layer_id: str, fieldIndex: int, feature: QgsFeature, xUnit: str) -> Optional[dict]:

        # raw_data = feature.attributes()[fieldIndex]
        # if raw_data is None:
        #    return None

        try:
            raw_data = self.rawData(layer_id, fieldIndex, feature)
            # d: dict = decodeProfileValueDict(feature.attribute(fieldIndex))
            if raw_data in [SpectralProfilePlotModel.NOT_INITIALIZED, None]:
                return None
            return self.profileDataToXUnit(raw_data, xUnit)
        except Exception as e:
            return None

    def plotData1(self, layer_id: str, fieldIndex: int, feature: QgsFeature, xUnit: str) -> Optional[dict]:
        """
        Returns the data struct of a deserialized spectral profile, converted to xUnit
        """
        if not feature.isValid():
            return None
        NI = SpectralProfilePlotModel.NOT_INITIALIZED
        # NA = not initialized
        # None = not available
        id_raw_data = feature.id()
        id_unit_data = (feature.id(), xUnit)

        FIELD_DATA = self.mCACHE_PROFILE_DATA[layer_id][fieldIndex]
        plotData = FIELD_DATA.get(id_unit_data, NI)
        if plotData == NI or not self.mEnableCaching:
            rawData = self.rawData(layer_id, fieldIndex, feature)

            if rawData is None:
                # cannot load raw data
                plotData = None

            else:
                # convert profile data to xUnit
                # if not possible, entry will be set to None
                plotData = self.profileDataToXUnit(rawData, xUnit)
            FIELD_DATA[id_unit_data] = plotData

        return plotData

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

    def setPlotWidget(self, plotWidget: SpectralProfilePlotWidget):
        self.mPlotWidget = plotWidget
        self.mPlotWidget.sigPlotDataItemSelected.connect(self.onPlotSelectionRequest)
        self.mPlotWidget.xAxis().setUnit(self.xUnit())  # required to set x unit in plot widget
        self.mXUnitInitialized = False

        bg = plotWidget.backgroundBrush().color()
        fg = plotWidget.xAxis().pen().color()
        general = self.generalSettings()

        general.mP_BG.setProperty(QgsProperty.fromValue(bg))
        general.mP_FG.setProperty(QgsProperty.fromValue(fg))

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

        # map to model index within a group of same zValues
        if isinstance(items, PropertyItemGroup):
            items = [items]
        _index = None

        if isinstance(index, QModelIndex):
            index = index.row()

        for i, item in enumerate(items):
            assert isinstance(item, PropertyItemGroup)

            # remove items if requestRemoval signal is triggered
            item.signals().requestRemoval.connect(lambda *arg, itm=item: self.removePropertyItemGroups(itm))
            # item.signals().requestPlotUpdate.connect(self.updatePlot)

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
            # item.initWithPlotModel(self)

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

    def selectedCurveFeatures(self) -> Dict[str, set]:
        """
        Returns the layer and features ids related to selected profile curves in the plot
        :return:
        """
        result = dict()
        for item in self.mPlotWidget.spectralProfilePlotDataItems(is_selected=True):
            layer_id = item.layerID()
            layer_features = result.get(layer_id, set())
            layer_features.add(item.featureID())
            result[layer_id] = layer_features

        return result

    def onPointsHovered(self, item: ScatterPlotItem, points: List, event: HoverEvent, **kwarg):
        s = ""
        print(points)
        print(event)
        info = []
        for spot in points:
            spot: SpotItem
            info.append(f'{spot.pos().x()},{spot.pos().y()}')

        if event.exit:
            s = ""
        else:
            s = ""

    def onPointsClicked(self, item: PlotDataItem, spots: List[SpotItem], event: MouseClickEvent, **kwarg):
        """
        Handles the selection / unselection of spectral profile points
        """
        if isinstance(item, SpectralProfilePlotDataItem):
            lid = item.layerID()
            fid = item.featureID()

            OLD_SELECTION = self.mSELECTED_SPOTS.copy()
            new_spots = self.mSELECTED_SPOTS.get(lid, set())

            # Check for modifier keys
            modifiers = event.modifiers()
            has_ctrl = modifiers & Qt.KeyboardModifier.ControlModifier
            has_shift = modifiers & Qt.KeyboardModifier.ShiftModifier

            for spot in spots:
                k = (fid, spot.index())

                # Select-item logic
                if has_ctrl:
                    # toggle this spot only
                    if k in new_spots:
                        new_spots.remove(k)
                    else:
                        new_spots.add(k)

                elif has_shift:
                    # Handle SHIFT+click
                    # allways add to the existing selection
                    new_spots.add(k)
                else:
                    # this item is the new selection
                    self.mSELECTED_SPOTS.clear()
                    new_spots.clear()
                    new_spots.add(k)

            self.mSELECTED_SPOTS[lid] = new_spots

            if OLD_SELECTION != self.mSELECTED_SPOTS:
                self._updateSpotSelection(OLD_SELECTION)
        pass

    def onCurveClicked(self, item: PlotCurveItem, event: MouseClickEvent):
        """
        Handles the selection / unselection of spectral profiles
        :param item:
        :param event:
        :return:
        """
        parent = item.parentItem()
        if isinstance(parent, SpectralProfilePlotDataItem):
            is_selected = parent.curveIsSelected()

            old_selection = self.selectedCurveFeatures()

            # Check for modifier keys
            modifiers = event.modifiers()
            has_ctrl = modifiers & Qt.KeyboardModifier.ControlModifier
            has_shift = modifiers & Qt.KeyboardModifier.ShiftModifier

            # Select-item logic
            if has_ctrl:
                # toggle this item only
                parent.setCurveIsSelected(not is_selected)
            elif has_shift:
                # Handle SHIFT+click
                # allways add to existing selection
                parent.setCurveIsSelected(True)
            else:
                # this item is the new selection
                # 1. clear previous
                for item in self.mPlotWidget.spectralProfilePlotDataItems(is_selected=True):
                    item.setCurveIsSelected(False)
                # 2. this item is the new selection
                parent.setCurveIsSelected(True)

            new_selection = self.selectedCurveFeatures()

            if old_selection != new_selection and not self.showSelectedFeaturesOnly():
                layers = set(old_selection.keys()) | set(new_selection.keys())

                # 1. select layer features that have a selected curve
                for layerID in layers:
                    layer = self.project().mapLayer(layerID)
                    if isinstance(layer, QgsVectorLayer):
                        new_ids = new_selection.get(layerID, set())
                        old_ids = old_selection.get(layerID, set())

                        layer.selectByIds(list(new_ids))

                # 2. select curves that have a selected layer feature
                self._updateCurveSelection()

    def _updateSpotSelection(self, old_selection: dict):

        for item in self.plotWidget().spectralProfilePlotDataItems():
            lid = item.layerID()
            fid = item.featureID()
            if lid in self.mSELECTED_SPOTS or lid in old_selection:

                new_pts = self.mSELECTED_SPOTS.get(lid, set())
                old_pts = old_selection.get(lid, set())
                # item.scatter.setPointsVisible()

                to_unset = old_pts.difference(new_pts)
                to_set = new_pts.difference(old_pts)
                for pt in to_unset:
                    pass
                for pt in to_set:
                    pass
            s = ""

    def _updateCurveSelection(self):
        SELECTED_FEATURES = dict()

        for item in self.mPlotWidget.spectralProfilePlotDataItems():
            lid = item.layerID()
            fid = item.featureID()
            if lid not in SELECTED_FEATURES:
                layer = self.project().mapLayer(lid)
                if isinstance(layer, QgsVectorLayer):
                    SELECTED_FEATURES[lid] = layer.selectedFeatureIds()
                else:
                    SELECTED_FEATURES[lid] = []
            item.setCurveIsSelected(fid in SELECTED_FEATURES[lid])

            s = ""

    def updatePlot(self,
                   settings: Optional[dict] = None):  #

        self.mCACHE_PROFILE_DATA.clear()

        if settings is None:
            settings = self.settingsMap()

        settings = settings.copy()
        if self.updatesBlocked():
            return

        if not isinstance(self.mPlotWidget, SpectralProfilePlotWidget):
            return

        print(f'# UPDATE PLOT {self.nUpdates}')

        self.nUpdates += 1
        # xunit: str = self.xUnit().unit
        xunit: str = settings.get('x_unit', BAND_NUMBER)

        sc = QColor(settings['general']['color_sc'])

        def func_selected_style(plotStyle: PlotStyle):
            style2 = plotStyle.clone()
            style2.setLineWidth(plotStyle.lineWidth() + 2)
            style2.setLineColor(sc)
            return style2

        visualizations: List[dict] = settings['visualizations']
        layer_ids = []
        for vis in visualizations:
            lid = vis.get('layer_id')
            layer_ids.append(lid)
            if lid in self.mLayerCaches:
                continue
            else:
                # lsrc = vis.get('layer_source', speclib.source())
                lyr = self.project().mapLayer(lid)
                if lyr is None:
                    s = ""

                if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
                    self.mLayerCaches[lid] = QgsVectorLayerCache(lyr, 1024)

        # prepare a profile data cache dict for each layer and spectral profile field
        for vis in visualizations:
            layer_cache: QgsVectorLayerCache = self.mLayerCaches[vis['layer_id']]
            layer = layer_cache.layer()
            field_name = vis['field_name']
            field_index = layer.fields().lookupField(field_name)
            layer_data_cache = self.mCACHE_PROFILE_DATA.get(layer.id(), dict())
            field_data_cache = layer_data_cache.get(field_index, dict())
            layer_data_cache[field_index] = field_data_cache
            self.mCACHE_PROFILE_DATA[layer.id()] = layer_data_cache

        # for v in self.visualizations():
        #    v.mPlotDataItems.clear()
        #    if v.isVisible() and v.isComplete() and v.speclib() == self.speclib():
        #        visualizations.append(v)

        # pdi_generator = PDIGenerator([], onProfileClicked=self.mPlotWidget.onProfileClicked)

        # request.setFilterFids(feature_priority)

        # PROFILE_DATA: Dict[tuple, dict] = dict()

        profile_limit_reached: bool = False
        max_profiles = self.generalSettings().maximumProfiles()
        show_bad_bands = self.generalSettings().showBadBands()
        sort_bands = self.generalSettings().sortBands()
        show_selected_only = self.showSelectedFeaturesOnly()

        PLOT_ITEMS: List[SpectralProfilePlotDataItem] = []

        DT = dict()

        def add_dt(key: str, t0: datetime.datetime):
            dt = (datetime.datetime.now() - t0).total_seconds()

            dtl = DT.get(key, [])
            dtl.append(dt)
            DT[key] = dtl

        t0 = datetime.datetime.now()

        for i_vis, vis in enumerate(visualizations):

            layer_cache: QgsVectorLayerCache = self.mLayerCaches[vis['layer_id']]
            layer = layer_cache.layer()
            layer_id = layer.id()
            selected_fids = layer.selectedFeatureIds()

            referenced_aids = []
            color_expression = QgsExpression(vis['color_expression'])
            if color_expression.hasParserError():
                continue
            else:
                referenced_aids.extend(color_expression.referencedAttributeIndexes(layer.fields()))

            label_expression = QgsExpression(vis['label_expression'])
            if label_expression.expression() == '':
                label_expression.setExpression('$id')
            elif label_expression.hasParserError():
                continue
            else:
                referenced_aids.extend(label_expression.referencedAttributeIndexes(layer.fields()))

            filter_expression = QgsExpression(vis['filter_expression'])
            if filter_expression.expression() == '':
                filter_expression.setExpression('$id')
            elif filter_expression.hasParserError():
                continue
            else:
                referenced_aids.extend(filter_expression.referencedAttributeIndexes(layer.fields()))

            tooltip_expression = QgsExpression(vis['tooltip_expression'])
            if tooltip_expression.expression() == '':
                tooltip_expression.setExpression("'Feature ' + to_string(@id)")
            elif tooltip_expression.hasParserError():
                continue
            else:
                referenced_aids.extend(label_expression.referencedAttributeIndexes(layer.fields()))

            self.mLastReferencedColumns[layer_id] = set(referenced_aids)

            request = QgsFeatureRequest()
            request.setLimit(max_profiles)
            request.setFlags(QgsFeatureRequest.NoGeometry)

            if filter_expression:
                request.setFilterExpression(filter_expression.expression())

            if show_selected_only:
                request.setFilterFids(selected_fids)

            field_name = vis['field_name']
            field_index = layer.fields().lookupField(field_name)

            vis_context = QgsExpressionContext()
            vis_context.appendScope(QgsExpressionContextUtils.globalScope())
            vis_context.appendScope(QgsExpressionContextUtils.layerScope(layer))

            scope = QgsExpressionContextScope('profile_visualization')
            scope.setVariable('field_name', vis['field_name'])
            scope.setVariable('field_index', field_index)
            scope.setVariable('visualization_name', vis['name'])

            vis_plot_style: PlotStyle = PlotStyle.fromMap(vis['plot_style'])

            feature_renderer: QgsFeatureRenderer = layer.renderer()
            if isinstance(feature_renderer, QgsFeatureRenderer):
                feature_renderer = feature_renderer.clone()
                add_symbol_scope = 'symbol_color' in color_expression.expression()
            else:
                # layers without geometry do not have a symbol renderer
                add_symbol_scope = False
                feature_renderer = self.mDefaultSymbolRenderer.clone()

            for iFeature, feature in enumerate(layer_cache.getFeatures(request)):
                feature: QgsFeature
                fid = feature.id()
                if len(PLOT_ITEMS) >= max_profiles:
                    profile_limit_reached = True
                    break
                # self.mVectorLayerCache.getFeatures(feature_priority):
                # feature: QgsFeature = self.mVectorLayerCache.getFeature(fid)
                # assert fid == feature.id()
                # fid = feature.id()
                feature_context = QgsExpressionContext(vis_context)
                feature_context.setFeature(feature)

                if True and add_symbol_scope:
                    renderContext = QgsRenderContext()
                    renderContext.setExpressionContext(feature_context)
                    feature_renderer.startRender(renderContext, feature.fields())
                    qgssymbol = feature_renderer.symbolForFeature(feature, renderContext)
                    symbolScope = None
                    if isinstance(qgssymbol, QgsSymbol):
                        symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                        feature_context.appendScope(QgsExpressionContextScope(symbolScope))
                    feature_renderer.stopRender(renderContext)

                t0 = datetime.datetime.now()
                plot_data: Optional[dict] = self.plotData1(layer_id, field_index, feature, xunit)
                add_dt('plotData1', t0)

                t0 = datetime.datetime.now()
                plot_data: Optional[dict] = self.plotData2(layer_id, field_index, feature, xunit)
                add_dt('plotData2', t0)

                if not isinstance(plot_data, dict):
                    # profile data can not be transformed to requested x-unit
                    continue

                t0 = datetime.datetime.now()
                plot_style = vis_plot_style.clone()

                line_color = color_expression.evaluate(feature_context)
                if isinstance(line_color, str):
                    try:
                        line_color = QColor(line_color)
                    except Exception:
                        pass

                if isinstance(line_color, QColor):
                    plot_style.setLineColor(line_color)
                    plot_style.setMarkerColor(line_color)
                    plot_style.setMarkerLinecolor(line_color)
                s = ""
                # plot_style: PlotStyle = vis.generatePlotStyle(plotContext)

                add_dt('plotStyle', t0)

                t0 = datetime.datetime.now()
                plot_label: str = label_expression.evaluate(feature_context)
                plot_tooltip: str = tooltip_expression.evaluate(feature_context)
                add_dt('label_tooltip', t0)

                is_selected = fid in selected_fids

                pdi = SpectralProfilePlotDataItem()
                pdi.setClickable(True, 4)
                pdi.mLayerID = layer_id
                pdi.mFeatureID = fid
                pdi.mFieldIndex = field_index
                pdi.mSelectedStyle = func_selected_style

                pdi.setProfileData(plot_data, plot_style,
                                   showBadBands=show_bad_bands,
                                   sortBands=sort_bands,
                                   label=plot_label,
                                   tooltip=plot_tooltip)
                pdi.setCurveIsSelected(is_selected)
                PLOT_ITEMS.append(pdi)

        # check if x unit was different to this one
        if not self.mXUnitInitialized and len(PLOT_ITEMS) > 0:
            pdi: SpectralProfilePlotDataItem = PLOT_ITEMS[0]
            rawData = self.rawData(pdi.mLayerID, pdi.mFieldIndex, pdi.mFeatureID)

            if rawData:
                xunit2 = self.mXUnitModel.findUnit(rawData.get('xUnit', None))
                if isinstance(xunit2, str) and xunit2 != xunit:
                    self.mXUnitInitialized = True
                    self.setXUnit(xunit2)
                    # this will call updatePlot again, so we can return afterward
                    return

        t0 = datetime.datetime.now()
        self.mPlotWidget.viewBox()._updatingRange = True
        self.mPlotWidget.plotItem.clearPlots()
        add_dt('clearPlots', t0)
        t0 = datetime.datetime.now()
        with PlotUpdateBlocker(self.mPlotWidget) as blocker:
            for p in PLOT_ITEMS:
                p.sigClicked.connect(self.onCurveClicked)
                p.sigPointsClicked.connect(self.onPointsClicked)
                p.sigPointsHovered.connect(self.onPointsHovered)
                p.scatter.setAcceptHoverEvents(True)
                p.scatter.setData(hoverPen=QPen(QColor('yellow')), hoverable=True, hoverSize=10)

                self.mPlotWidget.plotItem.addItem(p)
        add_dt('add plot items', t0)

        for k, dtl in DT.items():
            dtl = np.asarray(dtl)
            print(f'{k}: {dtl.sum():.2f} s  {dtl.mean():.3f}s n = {len(dtl)}')

        self.updateProfileLabel(len(PLOT_ITEMS), profile_limit_reached)

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

    def profileDataToXUnit(self, profileData: dict, xUnit: str) -> Optional[dict]:
        """
        Converts the x values from plotData.get('xUnit') to xUnit.
        Returns None if a conversion is not possible (e.g., from meters to time)
        :param profileData: profile dictionary
        :param xUnit: str
        :return: dict | None
        """
        if not isinstance(profileData, dict):
            return None
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

                if speclib.id() not in self.project().mapLayers().keys():
                    self.project().addMapLayer(speclib)
                self.connectSpeclibSignals(speclib)

    def defaultProfileStyle(self) -> PlotStyle:
        return self.mDefaultProfileStyle

    def setDefaultProfileStyle(self, style: PlotStyle):
        self.mDefaultProfileStyle = style

    def connectSpeclibSignals(self, speclib: QgsVectorLayer):
        """"
        Connects signals to the given spectral library vector layer.
        """
        rl = self._update_rate_limit

        def _plotted_value_changed(lid, *args, **kwargs):
            fid, aid, value = args[0][0]
            if aid in self.mLastReferencedColumns.get(lid, set()):
                self.updatePlot()

        if speclib.id() not in self.mSignalProxies:
            proxies = [
                SignalProxy(speclib.attributeValueChanged, delay=1, rateLimit=rl * 10,
                            slot=lambda *args, lid=speclib.id(): _plotted_value_changed(lid, args)),
                SignalProxy(speclib.featuresDeleted, rateLimit=rl, slot=lambda: self.updatePlot()),
                SignalProxy(speclib.featureAdded, rateLimit=rl, slot=lambda: self.updatePlot()),
                SignalProxy(speclib.styleChanged, rateLimit=rl, slot=self.onSpeclibStyleChanged),
                SignalProxy(speclib.selectionChanged, rateLimit=rl, slot=self.onSpeclibSelectionChanged),
                SignalProxy(speclib.updatedFields, rateLimit=rl, slot=lambda: self.onSpeclibFieldsUpdated),
            ]

            self.mSignalProxies[speclib.id()] = proxies
            speclib.willBeDeleted.connect(lambda *args, fid=speclib.id(): self.disconnectSpeclibSignals(fid))

        # speclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
        # speclib.editCommandStarted.connect(self.onSpeclibEditCommandStarted)
        # speclib.editCommandEnded.connect(self.onSpeclibEditCommandEnded)
        # speclib.committedAttributeValuesChanges.connect(self.onSpeclibCommittedAttributeValuesChanges)
        # speclib.beforeCommitChanges.connect(self.onSpeclibBeforeCommitChanges)
        # speclib.afterCommitChanges.connect(self.onSpeclibAfterCommitChanges)
        # speclib.committedFeaturesAdded.connect(self.onSpeclibCommittedFeaturesAdded)
        # speclib.featuresDeleted.connect(self.onSpeclibFeaturesDeleted)
        # speclib.selectionChanged.connect(self.onSpeclibSelectionChanged)
        # speclib.styleChanged.connect(self.onSpeclibStyleChanged)

        # speclib.willBeDeleted.connect(lambda *args, sl=speclib: self.disconnectSpeclibSignals(sl))

    def disconnectSpeclibSignals(self, speclib: Union[str, QgsVectorLayer]):

        if isinstance(speclib, QgsVectorLayer):
            lid = speclib.id()
        else:
            lid = speclib

        if lid in self.mSignalProxies:
            for proxy in self.mSignalProxies[lid]:
                proxy.disconnect()
            del self.mSignalProxies[lid]

        # speclib.editCommandStarted.disconnect(self.onSpeclibEditCommandStarted)
        # speclib.editCommandEnded.disconnect(self.onSpeclibEditCommandEnded)
        # speclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
        # speclib.beforeCommitChanges.disconnect(self.onSpeclibBeforeCommitChanges)
        # self.mSpeclib.afterCommitChanges.disconnect(self.onSpeclibAfterCommitChanges)
        # speclib.committedFeaturesAdded.disconnect(self.onSpeclibCommittedFeaturesAdded)

        # speclib.featuresDeleted.disconnect(self.onSpeclibFeaturesDeleted)
        # speclib.selectionChanged.disconnect(self.onSpeclibSelectionChanged)
        # speclib.styleChanged.disconnect(self.onSpeclibStyleChanged)

        # speclib.willBeDeleted.disconnect(self.onSpeclibWillBeDeleted)

    def onSpeclibFieldsUpdated(self, *args, **kwargs):

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

    def onSpeclibStyleChanged(self, *args):
        # self.loadFeatureColors()
        b = False
        # we need to update the plot only if any visualization uses the vector layer symbol style
        for vis in self.visualizations():
            if vis.isVisible() and 'symbol_color' in vis.colorProperty().expressionString():
                b = True
                break
        if b:
            self.updatePlot()

    def onSpeclibSelectionChanged(self, *args, **kwds):

        if self.showSelectedFeaturesOnly():
            self.updatePlot()
        else:
            self._updateCurveSelection()
        # self.updatePlot()

    def onDualViewSliderMoved(self, *args):
        pass
        # self.updatePlot()

    def onDualViewSelectionChanged(self, *args):
        s = ""
        pass

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


def copy_items(items: List[SpectralProfilePlotDataItem],
               mode: str = 'json',
               xUnit: Optional[str] = None):
    mode = mode.lower()
    assert mode in ['json', 'csv', 'json_raw']

    txt = None
    if mode == 'json':
        s = ""
        data = []
        for item in items:
            item: SpectralProfilePlotDataItem

            d = {'x': item.xData.tolist(),
                 'y': item.yData.tolist(),

                 }
            data.append(d)
            s = ""
        if xUnit is not None:
            for item in data:
                item['xUnit'] = xUnit
        txt = json.dumps(data, ensure_ascii=False)
    elif mode == 'csv':
        # make one big CSV table
        # sort by x vector
        x_values = np.asarray([])
        for item in items:
            item: SpectralProfilePlotDataItem
            x_values = np.unique(np.concatenate((x_values, item.xData)))

        ncol = len(items) + 2
        nrow = len(x_values) + 1
        arr = np.empty((nrow, ncol), dtype=object)
        arr[0, 0] = 'x'
        arr[1:, 0] = x_values
        arr[0, 1] = 'x unit'
        arr[1:, 1] = xUnit

        for c, item in enumerate(items):
            name = item.name()
            if name in ['', None]:
                name = f'profile_{c + 1}'
            c += 2
            arr[0, c] = name
            for x, y in zip(item.xData, item.yData):
                r = x_values.index(x)
                arr[r + 1, c] = y
        txt = ""

    if txt:
        md = QMimeData()
        md.setText(txt)
        QApplication.clipboard().setMimeData(md)


class SpectralLibraryPlotWidget(QWidget):
    sigDragEnterEvent = pyqtSignal(QDragEnterEvent)
    sigDropEvent = pyqtSignal(QDropEvent)
    sigPlotWidgetStyleChanged = pyqtSignal()

    SHOW_MAX_PROFILES_HINT = True

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryplotwidget.ui'), self)

        assert isinstance(self.panelVisualization, QFrame)

        assert isinstance(self.mPlotWidget, SpectralProfilePlotWidget)
        assert isinstance(self.treeView, SpectralProfilePlotView)

        self.mPlotWidget: SpectralProfilePlotWidget
        assert isinstance(self.mPlotWidget, SpectralProfilePlotWidget)
        # self.plotWidget.sigPopulateContextMenuItems.connect(self.onPopulatePlotContextMenu)
        self.mPlotModel = SpectralProfilePlotModel()
        self.mPlotModel.setPlotWidget(self.mPlotWidget)
        self.mPlotModel.sigPlotWidgetStyleChanged.connect(self.sigPlotWidgetStyleChanged.emit)
        self.mPlotModel.sigMaxProfilesExceeded.connect(self.onMaxProfilesReached)
        self.mINITIALIZED_VISUALIZATIONS = set()

        # self.mPlotControlModel.sigProgressChanged.connect(self.onProgressChanged)
        self.setAcceptDrops(True)

        self.mProxyModel = SpectralProfilePlotModelProxyModel()
        self.mProxyModel.setSourceModel(self.mPlotModel)

        self.mFilterLineEdit: QgsFilterLineEdit
        self.mFilterLineEdit.textChanged.connect(self.setFilter)

        self.treeView.setModel(self.mProxyModel)
        self.treeView.selectionModel().selectionChanged.connect(self.onVisSelectionChanged)

        self.mViewDelegate = SpectralProfilePlotViewDelegate(self.treeView)
        self.mViewDelegate.setItemDelegates(self.treeView)

        self.mDualView: Union[QgsDualView] = None
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
        self.optionSelectedFeaturesOnly.toggled.connect(self.mPlotModel.setShowSelectedFeaturesOnly)
        self.optionSelectedFeaturesOnly.setIcon(QgsApplication.getThemeIcon("/mActionShowSelectedLayers.svg"))
        self.mPlotModel.sigShowSelectedFeaturesOnlyChanged.connect(self.optionSelectedFeaturesOnly.setChecked)

        # self.sbMaxProfiles: QSpinBox
        # self.sbMaxProfiles.valueChanged.connect(self.mPlotControlModel.setMaxProfiles)
        # self.labelMaxProfiles: QLabel
        # self.mPlotControlModel.setMaxProfilesWidget(self.sbMaxProfiles)

        self.optionCursorCrosshair: QAction
        self.optionCursorCrosshair.toggled.connect(self.mPlotWidget.setShowCrosshair)

        self.optionCursorPosition: QAction
        self.optionCursorPosition.toggled.connect(self.mPlotWidget.setShowCursorInfo)

        self.optionXUnit = SpectralProfilePlotXAxisUnitWidgetAction(self, self.mPlotModel.mXUnitModel)
        self.optionXUnit.setUnit(self.mPlotModel.xUnit())
        self.optionXUnit.setDefaultWidget(self.optionXUnit.createUnitComboBox())
        self.optionXUnit.sigUnitChanged.connect(self.mPlotModel.setXUnit)
        self.mPlotModel.sigXUnitChanged.connect(self.optionXUnit.setUnit)

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

        widgetXAxis: QWidget = self.mPlotWidget.viewBox().menu.widgetGroups[0]
        widgetYAxis: QWidget = self.mPlotWidget.viewBox().menu.widgetGroups[1]
        # grid: QGridLayout = widgetXAxis.layout()
        # grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        # grid.addWidget(self.optionXUnit.createUnitComboBox(), 0, 2, 1, 2)

        self.mPlotWidget.plotItem.sigPopulateContextMenuItems.connect(self.populateProfilePlotContextMenu)

        # connect actions with buttons
        self.btnAddProfileVis.setDefaultAction(self.actionAddProfileVis)
        self.btnAddRasterLayerRenderer.setDefaultAction(self.actionAddRasterLayerRenderer)
        self.btnRemoveProfileVis.setDefaultAction(self.actionRemoveProfileVis)
        self.btnSelectedFeaturesOnly.setDefaultAction(self.optionSelectedFeaturesOnly)

    def setProject(self, project: QgsProject):
        self.plotModel().setProject(project)

        # ensure that the dual-view layer is added to the recent QgsProject
        lyr = self.mDualView.masterModel().layer()
        if isinstance(lyr, QgsVectorLayer) and lyr.id() not in project.mapLayers():
            project.addLayer(lyr)

    def project(self) -> QgsProject:
        return self.plotModel().project()

    def plotWidgetStyle(self) -> PlotWidgetStyle:
        return self.mPlotModel.plotWidgetStyle()

    def populateProfilePlotContextMenu(self, menu_list: list):
        s = ""

        items = list(self.plotWidget().spectralProfilePlotDataItems(is_selected=True))
        n = len(items)

        m = QMenu('Copy ...')
        m.setToolTipsVisible(True)
        m.setEnabled(n > 0)
        if n > 0:
            a = m.addAction('JSON')
            a.setToolTip(f'Copy {n} selected profile(s) as JSON')
            a.setIcon(QIcon(r':/images/themes/default/mIconFieldJson.svg'))

            a.triggered.connect(lambda *args, itm=items: self.copyItems(itm, 'json'))

            a = m.addAction('CSV')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_copy.svg'))
            a.setToolTip(f'Copy {n} selected profile(s) in CSV format')
            a.triggered.connect(lambda *args, itm=items: self.copyItems(itm, 'csv'))

        menu_list.append(m)
        # update current renderer

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mPlotWidget

    def plotModel(self) -> SpectralProfilePlotModel:
        return self.mPlotModel

    def updatePlot(self):
        self.mPlotModel.updatePlot()

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
            self.SHOW_MAX_PROFILES_HINT = False
            n = self.mPlotModel.maxProfiles()

            self.panelVisualization.setVisible(True)

            item = self.plotModel().mGeneralSettings.mP_MaxProfiles
            idx = self.plotModel().indexFromItem(item)
            idx2 = self.treeView.model().mapFromSource(idx)
            self.treeView.setExpanded(idx2, True)
            self.treeView.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

            result = QMessageBox.information(self,
                                             'Maximum number of profiles',
                                             f'Reached maximum number of profiles to display ({n}).\n'
                                             'Increase this value to display more profiles at same time.\n'
                                             'Showing a large numbers of profiles (and bands) can reduce '
                                             'visualization speed')

    def createLayerBandVisualization(self, *args):

        layer = None
        d = SelectMapLayerDialog()
        d.setWindowTitle('Select Raster Layer')
        d.setProject(self.plotModel().project())
        d.mapLayerComboBox().setFilters(QgsMapLayerProxyModel.RasterLayer)
        if d.exec_() == QDialog.Accepted:
            layer = d.layer()

        existing_layers = [v.layer() for v in self.mPlotModel.layerRendererVisualizations()]
        if isinstance(layer, QgsRasterLayer) and layer not in existing_layers:
            lvis = RasterRendererGroup(layer=layer)
            self.mPlotModel.insertPropertyGroup(0, lvis)

    def createProfileVisualization(self, *args,
                                   name: str = None,
                                   layer_id: Union[QgsVectorLayer, str, None] = None,
                                   field_name: Union[QgsField, int, str] = None,
                                   color: Union[str, QColor] = None,
                                   style: PlotStyle = None,
                                   checked: bool = True):
        """
        Creates a new profile visualization
        :param args:
        :param name:
        :param field_name:
        :param color:
        :param style:
        :param checked:
        :return:
        """
        item = ProfileVisualizationGroup()
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        # set defaults

        if isinstance(layer_id, QgsVectorLayer):
            layer_id = layer_id.id()
        if isinstance(field_name, QgsField):
            field_name = field_name.name()

        existing_fields = [(v.layerId(), v.field())
                           for v in self.plotModel().visualizations()
                           if isinstance(v.fieldName(), str) and isinstance(v.layerId(), str)]

        if layer_id is None and field_name is None:
            last_speclib = self.speclib()
            if isinstance(last_speclib, QgsVectorLayer):

                layer_id = last_speclib.id()

                for field in profile_field_list(last_speclib):
                    k = (layer_id, field.name())
                    if k not in existing_fields:
                        layer_id, field_name = k
                        break
        if layer_id is None and field_name is None and len(existing_fields) > 0:
            layer_id, field_name = existing_fields[-1]

        # set profile source in speclib
        if isinstance(layer_id, str) and isinstance(field_name, str):
            item.setLayerField(layer_id, field_name)

        if name is None:
            if isinstance(item.fieldName(), str):
                _name = f'Group "{item.fieldName()}"'
            else:
                _name = 'Group'

            existing_names = [v.name() for v in self.mPlotModel]
            n = 1
            name = _name
            while name in existing_names:
                n += 1
                name = f'{_name} {n}'

        item.setName(name)

        if item.layerId() and item.fieldName():
            # get a good guess for the name expression
            # 1. "<source_field_name>_name"
            # 2. "name"
            # 3. $id (fallback)

            layer = self.project().mapLayer(item.layerId())
            if isinstance(layer, QgsVectorLayer):
                name_field = None
                source_field_name = item.fieldName()
                rx1 = re.compile(source_field_name + '_?name', re.I)
                rx2 = re.compile('name', re.I)
                rx3 = re.compile('fid', re.I)
                for rx in [rx1, rx2, rx3]:
                    for field_name in layer.fields():
                        if field_name.type() in [QMETATYPE_QSTRING, QMETATYPE_INT] and rx.search(field_name.name()):
                            name_field = field_name
                            break
                    if name_field:
                        break
                if isinstance(name_field, QgsField):
                    item.setLabelExpression(f'"{name_field.name()}"')
                else:
                    item.setLabelExpression('$id')

        if not isinstance(style, PlotStyle):
            style = self.plotModel().defaultProfileStyle()
        item.setPlotStyle(style)

        if color is not None:
            item.setColor(color)

        self.mPlotModel.insertPropertyGroup(-1, item)
        # self.mPlotControlModel.updatePlot()

    def profileVisualizations(self) -> List[ProfileVisualizationGroup]:
        return self.mPlotModel.visualizations()

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.sigDragEnterEvent.emit(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.sigDropEvent.emit(event)

    def removeSelectedPropertyGroups(self, *args):
        rows = self.treeView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows if isinstance(r.data(Qt.UserRole), PropertyItemGroup)]
        self.mPlotModel.removePropertyItemGroups(to_remove)

    def setDualView(self, dualView):
        self.mDualView = dualView
        self.mPlotModel.setDualView(dualView)

    def speclib(self) -> QgsVectorLayer:
        # will be removed
        return self.mDualView.masterModel().layer()

    # def addSpectralModel(self, model):
    #    self.mPlotControlModel.addModel(model)

    def setFilter(self, pattern: str):
        self.mProxyModel.setFilterWildcard(pattern)
