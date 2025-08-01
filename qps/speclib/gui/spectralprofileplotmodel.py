import datetime
import io
import json
import logging
import math
from typing import Dict, Iterator, List, Optional, Set, Tuple, Union

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QMimeData, QModelIndex, QPoint, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QPen, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QApplication, QTableView
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextUtils, \
    QgsFeature, QgsFeatureRenderer, QgsFeatureRequest, QgsField, QgsMarkerSymbol, QgsProject, QgsProperty, \
    QgsReadWriteContext, QgsRenderContext, QgsSingleSymbolRenderer, QgsSymbol, QgsVectorLayer, QgsVectorLayerCache
from qgis.gui import QgsDualView
from ..core import is_spectral_library, profile_field_indices, profile_field_list, profile_fields
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectralprofile import decodeProfileValueDict
from ..gui.spectrallibraryplotitems import PlotUpdateBlocker, SpectralProfilePlotDataItem, SpectralProfilePlotWidget
from ..gui.spectrallibraryplotmodelitems import GeneralSettingsGroup, ProfileColorPropertyItem, \
    ProfileVisualizationGroup, PropertyItem, PropertyItemGroup, RasterRendererGroup, SpectralProfileLayerFieldItem
from ..gui.spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel
from ..gui.spectralprofilefieldmodel import SpectralProfileFieldListModel
from ...plotstyling.plotstyling import PlotStyle
from ...pyqtgraph.pyqtgraph import (LegendItem, PlotCurveItem, PlotDataItem, ScatterPlotItem, SignalProxy, SpotItem)
from ...pyqtgraph.pyqtgraph.GraphicsScene.mouseEvents import HoverEvent, MouseClickEvent
from ...unitmodel import BAND_INDEX, BAND_NUMBER, datetime64, UnitConverterFunctionModel, UnitWrapper
from ...utils import convertDateUnit, xy_pair_matrix

logger = logging.getLogger(__name__)


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
    sigOpenAttributeTableRequest = pyqtSignal(str)
    NOT_INITIALIZED = -1
    MAX_PROFILES_DEFAULT: int = 516

    class UpdateBlocker(object):
        """Blocks plot updates and proxy signals"""

        def __init__(self, plotModel: 'SpectralProfilePlotModel'):
            self.mPlotModel = plotModel
            self.mWasBlocked: bool = False

        def __enter__(self):
            self.mWasBlocked = self.mPlotModel.blockUpdates(True)

            for lid, signals in self.mPlotModel.mSignalProxies.items():
                for signal in signals:
                    signal.blockSignal = True

        def __exit__(self, exc_type, exc_value, tb):
            self.mPlotModel.blockUpdates(self.mWasBlocked)

            for lid, signals in self.mPlotModel.mSignalProxies.items():
                for signal in signals:
                    signal.blockSignal = False

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mBlockUpdates: bool = False

        self.mAddProfileCandidates: bool = False
        self.mPROFILE_CANDIDATES: Dict[str, List] = {}

        # allows to overwrite automatic generated plot styles
        self.mPROFILE_CANDIDATE_STYLES: Dict[Tuple[str, str], Dict[int, PlotStyle]] = {}

        self.mSELECTED_SPOTS: Dict[str, Tuple[int, int]] = dict()

        self.mLastSettings: dict = dict()
        self.mLastReferencedColumns: dict = dict()
        self.mLayerCaches: Dict[str, QgsVectorLayerCache] = dict()
        self.nUpdates: int = 0
        self.mProject: QgsProject = QgsProject.instance()

        self.mSignalProxies: Dict[str, List[SignalProxy]] = dict()
        self.mModelItems: Set[PropertyItemGroup] = set()

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

        # self.mProfileCandidates = ProfileCandidateGroup()
        self.insertPropertyGroup(0, self.mGeneralSettings)
        # self.insertPropertyGroup(1, self.mProfileCandidates)

        self.setMaxProfiles(self.MAX_PROFILES_DEFAULT)
        self._update_rate_limit = 60
        self.itemChanged.connect(self.onItemChanged)
        self.itemChanged.connect(self.updatePlotIfChanged)
        self.rowsInserted.connect(self.updatePlotIfChanged)
        self._standardProxySignals = [
            # SignalProxy(self.itemChanged, rateLimit=self._update_rate_limit, slot=self.onItemChanged),
            # SignalProxy(self.itemChanged, rateLimit=self._update_rate_limit, slot=self.updatePlotIfChanged),
            # SignalProxy(self.rowsInserted, rateLimit=self._update_rate_limit, slot=self.updatePlotIfChanged)
        ]

        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        fg = self.generalSettings().foregroundColor()
        style.setLineColor(fg)
        style.setMarkerColor(fg)
        style.setMarkerSymbol(None)
        style.setAntialias(self.mGeneralSettings.antialias())
        style.setBackgroundColor(self.generalSettings().backgroundColor())

        self.mDefaultProfileStyle = style

        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        style.linePen.setWidth(2)
        style.setLineColor('green')
        style.setAntialias(self.mGeneralSettings.antialias())
        self.mDefaultProfileCandidateStyle = style

        self.mCurrentSelectionColor: QColor = QColor('white')

    @classmethod
    def fromSettingsMap(cls, settings: dict, project: Optional[QgsProject] = None):

        if project is None:
            project = QgsProject.instance()

        model = SpectralProfilePlotModel()
        model.blockUpdates(True)
        model.setProject(project)
        model.mGeneralSettings.fromMap(settings.get('general', {}))
        model.blockUpdates(False)
        visGrps = []
        for visSettings in settings.get('visualizations', []):

            field_name = visSettings.get('field_name')
            layer_id = visSettings.get('layer_id')
            layer_name = visSettings.get('layer_name')
            layer_src = visSettings.get('layer_source')
            layer_provider = visSettings.get('layer_provider')
            layer = project.mapLayer(layer_id)
            if not isinstance(layer, QgsVectorLayer):
                for lid, lyr in project.mapLayers().items():
                    if lyr.source() == layer_src:
                        layer = lyr
                        break
            if not isinstance(layer, QgsVectorLayer):
                lyr = QgsVectorLayer(layer_src, layer_name, layer_provider)
                if lyr.isValid():
                    layer = lyr

            if isinstance(layer, QgsVectorLayer) and field_name in layer.fields().names():
                vis = ProfileVisualizationGroup()
                vis.setProject(project)
                vis.setLayerField(layer, field_name)

                vis.setFilterExpression(visSettings.get('filter_expression', ''))
                vis.setColorExpression(visSettings.get('color_expression', ''))
                vis.setLabelExpression(visSettings.get('label_expression', ''))
                visGrps.append(vis)

        if len(visGrps) > 0:
            model.insertPropertyGroup(-1, visGrps)

        return model

    def settingsMap(self) -> dict:
        """
        Returns the plot settings as JSON-serializable dictionary.
        """
        settings = dict()
        settings['general'] = self.mGeneralSettings.asMap()
        settings['general']['x_unit'] = str(self.xUnit().unit)
        # settings['candidates'] = self.profileCandidates().asMap()
        settings['visualizations'] = [v.asMap() for v in self.visualizations()
                                      if v.isVisible() and v.isComplete()]

        if True:
            dumps = json.dumps(settings, indent=4, ensure_ascii=False)
        return settings

    def updatePlotIfChanged(self, *args):
        old_settings = self.mLastSettings
        new_settings = self.settingsMap()
        if new_settings != old_settings:
            self.mLastSettings = new_settings

            g_new = new_settings.get('general', {})
            g_old = old_settings.get('general', {})

            # do the light work
            w: Optional[SpectralProfilePlotWidget] = self.plotWidget()
            if g_new != g_old and isinstance(w, SpectralProfilePlotWidget):

                # selection color
                w.setSelectionColor(g_new['color_sc'])

                self.mCurrentSelectionColor = QColor(g_new['color_sc'])

                w.setCrosshairColor(g_new['color_ch'])

                w.setShowCrosshair(g_new['show_crosshair'])
                w.setForegroundColor(g_new['color_fg'])
                w.setBackground(g_new['color_bg'])
                legend = w.mLegendItem
                if isinstance(legend, LegendItem):
                    g_legend = g_new.get('legend', {'show': False})
                    legend.setLabelTextColor(QColor(g_new['color_fg']))
                    legend.setLabelTextSize(g_legend.get('text_size', '9px'))
                    legend.setColumnCount(g_legend.get('columns', 1))
                    pi = w.getPlotItem()
                    show_legend = g_legend.get('show', False)
                    update_legend_items = legend.isVisible() != show_legend
                    if show_legend:
                        legend.setVisible(True)
                        pi.legend = legend
                        if update_legend_items:
                            legend.clear()
                            for item in pi.items:
                                if isinstance(item, SpectralProfilePlotDataItem):
                                    legend.addItem(item, item.name())
                    else:
                        legend.setVisible(False)
                        legend.clear()
                        pi.legend = None

                    # pen = legend.pen()
                    # pen.setColor(QColor(g_new['color_fg']))
                    # legend.setPen(pen)

                    # legend.update()

            update_heavy = False
            # check for general settings that require a re-plot
            for k in ['x_unit',
                      'sort_bands', 'show_bad_bands',
                      'max_profiles', 'antialiasing',
                      'show_candidates', 'candidate_style']:
                if g_old.get(k, None) != g_new.get(k, None):
                    update_heavy = True
                    break

            # doing the heavy work that requires to reload and draw profiles
            if update_heavy \
                    or old_settings.get('visualizations', {}) != new_settings.get('visualizations', {}) \
                    or old_settings.get('candidates', {}) != new_settings.get('candidates', {}):
                self.updatePlot(settings=new_settings)

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
        for item in self.mModelItems:
            if isinstance(item, PropertyItemGroup):
                item.setProject(project)
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

    def plotWidget(self) -> Optional[SpectralProfilePlotWidget]:
        return self.mPlotWidget

    sigShowSelectedFeaturesOnlyChanged = pyqtSignal(bool)

    def setShowLegend(self, b: bool):
        """
        Show or hides the legend
        :param b: bool
        """
        self.generalSettings().setShowLegend(b)

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
            self.updatePlotIfChanged()
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

            item.setProject(self.mProject)
            # remove items if requestRemoval signal is triggered
            # item.signals().requestRemoval.connect(lambda *arg, itm=item: self.removePropertyItemGroups(itm))
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
        # print(item)
        # print(event)
        html = ''
        if event.isEnter() or len(points) > 0:
            info = []
            for spot in points:
                info.append(f'{spot.pos().x()},{spot.pos().y()}')
            html = '<br>'.join(info)
        elif event.isExit():
            html = ''

        self.plotWidget().mInfoHover.setHtml(html)

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
        self.plotWidget().mLegendItem.update()

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

        logger.debug(f'update #{self.nUpdates}')

        self.nUpdates += 1
        xunit: str = self.xUnit().unit
        if xunit is None:
            xunit = BAND_NUMBER
        xunit: str = settings.get('x_unit', xunit)

        antialiasing = settings['general'].get('antialiasing', False)
        self.mCurrentSelectionColor = QColor(settings['general']['color_sc'])

        show_candidates = settings['general'].get('show_candidates', False)
        default_candidate_style = settings['general'].get('candidate_style')
        if isinstance(default_candidate_style, dict):
            default_candidate_style = PlotStyle.fromMap(default_candidate_style)
        else:
            default_candidate_style = self.mDefaultProfileCandidateStyle

        def func_selected_style(plotStyle: PlotStyle):
            style2 = plotStyle.clone()
            style2.setLineWidth(plotStyle.lineWidth() + 2)
            style2.setLineColor(self.mCurrentSelectionColor)
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
            candidate_fids = self.mPROFILE_CANDIDATES.get(layer_id, [])

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

            s = ""

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

            candidate_plot_styles = self.mPROFILE_CANDIDATE_STYLES.get((layer_id, field_name), {})

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

                is_candidate = fid in candidate_fids

                # self.mVectorLayerCache.getFeatures(feature_priority):
                # feature: QgsFeature = self.mVectorLayerCache.getFeature(fid)
                # assert fid == feature.id()
                # fid = feature.id()

                t0 = datetime.datetime.now()
                plot_data: Optional[dict] = self.plotData1(layer_id, field_index, feature, xunit)
                add_dt('plotData1', t0)

                # t0 = datetime.datetime.now()
                # plot_data: Optional[dict] = self.plotData2(layer_id, field_index, feature, xunit)
                # add_dt('plotData2', t0)

                if not isinstance(plot_data, dict):
                    # profile data can not be transformed to requested x-unit
                    continue

                feature_context = QgsExpressionContext(vis_context)
                feature_context.setFeature(feature)

                # get the curve plot style
                if show_candidates and is_candidate:
                    # apply a candidate style
                    plot_style: PlotStyle = candidate_plot_styles.get(fid, default_candidate_style).clone()
                    s = ""
                    # line_color = candidate_style.lineColor()

                else:
                    # get standard visualization style
                    plot_style = vis_plot_style.clone()
                    if add_symbol_scope:
                        renderContext = QgsRenderContext()
                        renderContext.setExpressionContext(feature_context)
                        feature_renderer.startRender(renderContext, feature.fields())
                        qgssymbol = feature_renderer.symbolForFeature(feature, renderContext)
                        symbolScope = None
                        if isinstance(qgssymbol, QgsSymbol):
                            symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                            feature_context.appendScope(QgsExpressionContextScope(symbolScope))
                        feature_renderer.stopRender(renderContext)

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

                add_dt('plotStyle', t0)

                t0 = datetime.datetime.now()
                plot_label = label_expression.evaluate(feature_context)
                plot_tooltip = tooltip_expression.evaluate(feature_context)

                is_selected = fid in selected_fids

                pdi = SpectralProfilePlotDataItem(antialias=antialiasing)
                pdi.setClickable(True, 4)
                pdi.mLayerID = layer_id
                pdi.mFeatureID = fid
                pdi.mField = field_name
                pdi.mFieldIndex = field_index
                pdi.mSelectedStyle = func_selected_style
                if is_candidate:
                    pdi.setZValue(99999)
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
        self.plotWidget().legend().clear()

        add_dt('clear plot', t0)
        t0 = datetime.datetime.now()

        def func_scatter_tip(pi: SpectralProfilePlotDataItem):
            """
            Yea! Currying
            Returns a tip function to generate the scatter plot point tooltip
            :param pi: plotdataitem
            :return: function def(x,y,data)->str
            """

            def tip(x, y, data) -> str:
                lyr = self.project().mapLayer(pi.mLayerID)
                info = f'<i>{pi.name()}</i><br>x: {x}, y: {y}'
                info += f'<br>fid: {pi.mFeatureID} field: {pi.mField}'
                if isinstance(lyr, QgsVectorLayer):
                    info += f'<br>layer: {lyr.name()}'
                    info += f'<br>source: {lyr.source()}'
                return info

            return tip

        def func_curve_tip(*args, **kwds) -> str:
            return 'foobar'

        with PlotUpdateBlocker(self.mPlotWidget) as blocker:
            hoverPen = QPen(self.mCurrentSelectionColor)
            for p in PLOT_ITEMS:
                p: SpectralProfilePlotDataItem
                p.sigClicked.connect(self.onCurveClicked)
                p.sigPointsClicked.connect(self.onPointsClicked)
                p.sigPointsHovered.connect(self.onPointsHovered)
                p.curve.setAcceptHoverEvents(True)

                p.scatter.setAcceptHoverEvents(True)

                p.scatter.setData(  # hoverSymbol=p.scatter.opts['symbol'],
                    hoverPen=hoverPen,
                    hoverable=True,
                    tip=func_scatter_tip(p),
                    hoverSize=p.scatter.opts.get('size', 5) + 2)

                self.mPlotWidget.plotItem.addItem(p)
        add_dt('add plot items', t0)

        infos = ['update durations:']
        for k, dtl in DT.items():
            dtl = np.asarray(dtl)
            infos.append(f'\t{k}: {dtl.sum():.2f} s  {dtl.mean():.3f}s n = {len(dtl)}')
        logger.debug('\n'.join(infos))

        self.updateProfileLabel(len(PLOT_ITEMS), profile_limit_reached)

    def updateProfileLabel(self, n: int, limit_reached: bool):
        propertyItem = self.generalSettings().mP_MaxProfiles

        # with SignalBlocker(propertyItem.signals()) as blocker:
        # with SpectralProfilePlotModel.UpdateBlocker(self) as blocker:
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

    def confirmProfileCandidates(self, update_plot: bool = True):
        """
        Confirms the profile candidates, so that they will not be removed
        when new candidates are added calling addProfileCandidates().
        """
        self.mPROFILE_CANDIDATES.clear()
        if update_plot:
            self.updatePlot()

    def addProfileCandidates(self,
                             candidates: Dict[str, List[QgsFeature]],
                             styles: Optional[Dict[str, Dict[str, PlotStyle]]] = None):
        """
        Adds QgsFeatures to be considered as profile candidates.
        :param candidates: Dictionary with profile candidates as {layer id:[List of QgsFeatures]}.
        :param styles: optional, Dictionary with profile styles for candidate profiles,
                       as {layer id: {field name: PlotStyle}}

        """
        assert isinstance(candidates, dict)

        with SpectralProfilePlotModel.UpdateBlocker(self) as blocker:
            if self.mAddProfileCandidates:
                self.confirmProfileCandidates(update_plot=False)
            else:
                self.clearProfileCandidates()

            visualized_layer_ids = [v.layerId() for v in self.visualizations()]

            # add profile candidates
            for layer_id, features in candidates.items():
                if layer_id in visualized_layer_ids:
                    layer = self.project().mapLayer(layer_id)
                    if isinstance(layer, QgsVectorLayer) and layer.isValid():
                        # insert
                        s = ""
                        stop_editing = layer.startEditing()
                        if not isinstance(features, list):
                            features = list(features)
                        layer.beginEditCommand('Add {} profiles'.format(len(features)))
                        new_fids = SpectralLibraryUtils.addProfiles(layer, features, addMissingFields=True)
                        layer.endEditCommand()

                        def check_commited_features_added(layer_id, idmap_2):
                            new_fids.clear()
                            new_fids.extend([f.id() for f in idmap_2])

                        layer.committedFeaturesAdded.connect(check_commited_features_added)
                        layer.commitChanges(stopEditing=stop_editing)
                        layer.committedFeaturesAdded.disconnect(check_commited_features_added)
                        self.mPROFILE_CANDIDATES[layer_id] = new_fids
                        if isinstance(styles, dict):
                            layer_styles = styles.get(layer_id, {})
                            for field_name, plot_style in layer_styles.items():
                                fid_styles = {fid: plot_style for fid in new_fids}
                                self.mPROFILE_CANDIDATE_STYLES[(layer_id, field_name)] = fid_styles
        self.updatePlot()

    def clearProfileCandidates(self):
        for layer_id, old_fids in list(self.mPROFILE_CANDIDATES.items()):
            layer = self.project().mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer) and len(old_fids) > 0:

                restart_editing: bool = not layer.startEditing()
                layer.beginEditCommand('Remove profile candidates')

                def onFeaturesRemoved(lid: str, fids):
                    s = ""

                del self.mPROFILE_CANDIDATES[layer_id]
                layer.committedFeaturesRemoved.connect(onFeaturesRemoved)
                b = layer.deleteFeatures(old_fids)
                layer.endEditCommand()
                layer.committedFeaturesRemoved.disconnect(onFeaturesRemoved)
                # self.mPROFILE_CANDIDATES[layer_id] = [fid for fid in self.mPROFILE_CANDIDATES[layer_id] if fid not in old_fids]
                if restart_editing:
                    layer.startEditing()

        self.mPROFILE_CANDIDATES.clear()

    def flushProxySignals(self):
        """
        Flushes all SignalProxys
        """
        for _, signals in self.mSignalProxies.items():
            for s in signals:
                s.flush()

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

    def onItemChanged(self, item: QStandardItem, *args):
        """
        Link changes between items, e.g. to react on changes in general settings
        :param item:
        :param args:
        :return:
        """
        if isinstance(item, tuple):
            item = item[0]
        if isinstance(item, PropertyItem):
            grp = item.parent()
        else:
            grp = None

        if isinstance(item, SpectralProfileLayerFieldItem):
            if isinstance(grp, ProfileVisualizationGroup):
                grp.mPColor.emitDataChanged()

        if isinstance(item, RasterRendererGroup):
            s = ""
        elif isinstance(item, ProfileColorPropertyItem):
            if isinstance(grp, ProfileVisualizationGroup):
                style = grp.mPStyle.plotStyle()
                expr = grp.colorExpression()

                context = grp.expressionContextGenerator().createExpressionContext()

                expression = QgsExpression(expr)
                value = expression.evaluate(context)
                if value:
                    color = QColor(value)
                    style.setLineColor(color)
                    style.setMarkerColor(color)

                    grp.setPlotStyle(style)

                    style.setLineColor()
                    grp.setPlotStyle(style)

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

        b = False
        # we need to update the plot if any visualization uses the vector layer's symbol style
        for vis in self.visualizations():
            if vis.isVisible() and 'symbol_color' in vis.colorExpression():
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


def copy_items(items: List[SpectralProfilePlotDataItem],
               mode: str = 'json',
               xUnit: Optional[str] = None):
    mode = mode.lower()
    assert mode in ['json', 'csv', 'excel']

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
    elif mode in ['csv', 'excel']:
        # make one big CSV table
        # sort by x vector
        pairs = []

        names = []
        for i, item in enumerate(items):
            item: SpectralProfilePlotDataItem
            pairs.append((item.xData, item.yData))
            name = item.name()
            if name in [None, '']:
                name = f'profile_{i + 1}'
            names.append(name)

        x_values, Y_Values = xy_pair_matrix(pairs)

        ncol = len(items) + 2
        nrow = len(x_values) + 1
        arr = np.empty((nrow, ncol), dtype=object)
        # header
        arr[0, 0] = 'x'
        arr[0, 1] = 'x unit'
        arr[0, 2:] = np.asarray(names)
        arr[1:, 0] = x_values
        arr[1:, 1] = xUnit
        arr[1:, 2:] = Y_Values

        arr = np.where(np.equal(arr, None), '', arr)
        arr = np.where(arr == np.nan, '', arr)
        output = io.StringIO()

        delimiter = {'excel': '\t',
                     'csv': ','}[mode]
        np.savetxt(output, arr, fmt='%s', delimiter=delimiter)

        # Get the CSV-formatted string
        txt = output.getvalue()

    if txt:
        md = QMimeData()
        md.setText(txt)
        QApplication.clipboard().setMimeData(md)
