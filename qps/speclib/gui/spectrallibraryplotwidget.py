import datetime
import re
import typing

import numpy as np
from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import pyqtSignal, Qt, QModelIndex, QPoint, QSortFilterProxyModel, QSize, \
    QVariant, QAbstractItemModel, QItemSelectionModel, QRect, QMimeData
from qgis.PyQt.QtGui import QColor, QDragEnterEvent, QDropEvent, QPainter, QIcon, QContextMenuEvent
from qgis.PyQt.QtGui import QPen, QBrush, QPixmap
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QWidgetAction, QWidget, QGridLayout, QLabel, QFrame, QAction, QApplication, \
    QTableView, QComboBox, QMenu, QStyledItemDelegate, QHBoxLayout, QTreeView, QStyleOptionViewItem
from qgis.core import QgsField, QgsSingleSymbolRenderer, QgsMarkerSymbol, \
    QgsVectorLayer, QgsFieldModel, QgsFields, QgsSettings, QgsApplication, QgsExpressionContext, \
    QgsFeatureRenderer, QgsRenderContext, QgsSymbol, QgsFeature, QgsFeatureRequest
from qgis.core import QgsProject, QgsMapLayerProxyModel
from qgis.core import QgsProperty, QgsExpressionContextScope
from qgis.core import QgsRasterLayer
from qgis.core import QgsVectorLayerCache
from qgis.gui import QgsDualView
from qgis.gui import QgsFilterLineEdit

from .spectrallibraryplotitems import FEATURE_ID, FIELD_INDEX, MODEL_NAME, \
    SpectralProfilePlotDataItem, SpectralProfilePlotWidget, PlotUpdateBlocker
from .spectrallibraryplotmodelitems import PropertyItemGroup, PropertyItem, RasterRendererGroup, \
    ProfileVisualizationGroup, PlotStyleItem, ProfileCandidateGroup, PropertyItemBase, ProfileCandidateItem, \
    GeneralSettingsGroup, PropertyLabel
from .. import speclibUiPath
from ..core import profile_field_list, profile_field_indices, is_spectral_library, profile_fields
from ..core.spectralprofile import decodeProfileValueDict
from ...externals.htmlwidgets import HTMLStyle
from ...models import SettingsModel
from ...plotstyling.plotstyling import PlotStyle, PlotWidgetStyle
from ...unitmodel import BAND_INDEX, BAND_NUMBER, UnitConverterFunctionModel, UnitModel
from ...utils import datetime64, UnitLookup, loadUi, SignalObjectWrapper, convertDateUnit, qgsField, \
    SelectMapLayerDialog, SignalBlocker, printCaller


class SpectralProfilePlotXAxisUnitModel(UnitModel):
    """
    A unit model for the SpectralProfilePlot's X Axis
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.addUnit(BAND_NUMBER, description=BAND_NUMBER, tooltip=f'{BAND_NUMBER} (1st band = 1)')
        self.addUnit(BAND_INDEX, description=BAND_INDEX, tooltip=f'{BAND_INDEX} (1st band = 0)')
        for u in ['Nanometer',
                  'Micrometer',
                  'Millimeter',
                  'Meter']:
            baseUnit = UnitLookup.baseUnit(u)
            assert isinstance(baseUnit, str), u
            self.addUnit(baseUnit, description=f'Wavelength [{baseUnit}]', tooltip=f'Wavelength in {u} [{baseUnit}]')

        self.addUnit('DateTime', description='Date Time', tooltip='Date Time in ISO 8601 format')
        self.addUnit('DecimalYear', description='Decimal Year', tooltip='Decimal year')
        self.addUnit('DOY', description='Day of Year', tooltip='Day of Year (DOY)')

    def findUnit(self, unit):
        if unit in [None, NULL]:
            unit = BAND_NUMBER
        return super().findUnit(unit)


class SpectralProfilePlotXAxisUnitWidgetAction(QWidgetAction):
    sigUnitChanged = pyqtSignal(str)

    def __init__(self, parent, unit_model: UnitModel = None, **kwds):
        super().__init__(parent)
        self.mUnitModel: SpectralProfilePlotXAxisUnitModel
        if isinstance(unit_model, UnitModel):
            self.mUnitModel = unit_model
        else:
            self.mUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.mUnit: str = BAND_INDEX

    def unitModel(self) -> SpectralProfilePlotXAxisUnitModel:
        return self.mUnitModel

    def setUnit(self, unit: str):
        unit = self.mUnitModel.findUnit(unit)

        if isinstance(unit, str) and self.mUnit != unit:
            self.mUnit = unit
            self.sigUnitChanged.emit(unit)

    def unit(self) -> str:
        return self.mUnit

    def unitData(self, unit: str, role=Qt.DisplayRole) -> str:
        return self.mUnitModel.unitData(unit, role)

    def createUnitComboBox(self) -> QComboBox:
        unitComboBox = QComboBox()
        unitComboBox.setModel(self.mUnitModel)
        unitComboBox.setCurrentIndex(self.mUnitModel.unitIndex(self.unit()).row())
        unitComboBox.currentIndexChanged.connect(
            lambda: self.setUnit(unitComboBox.currentData(Qt.UserRole))
        )

        self.sigUnitChanged.connect(
            lambda unit, cb=unitComboBox: cb.setCurrentIndex(self.mUnitModel.unitIndex(unit).row()))
        return unitComboBox

    def createWidget(self, parent: QWidget) -> QWidget:
        # define the widget to set X-Axis options
        frame = QFrame(parent)
        gl = QGridLayout()
        frame.setLayout(gl)

        mCBXAxisUnit = self.createUnitComboBox()

        gl.addWidget(QLabel('Unit'), 2, 0)
        gl.addWidget(mCBXAxisUnit, 2, 1)
        gl.setMargin(0)
        gl.setSpacing(6)
        frame.setMinimumSize(gl.sizeHint())
        return frame


MAX_PDIS_DEFAULT: int = 256
FIELD_NAME = str

ATTRIBUTE_ID = typing.Tuple[FEATURE_ID, FIELD_INDEX]
MODEL_DATA_KEY = typing.Tuple[FEATURE_ID, FIELD_INDEX, MODEL_NAME]
PROFILE_DATA_CACHE_KEY = typing.Tuple[FEATURE_ID, FIELD_INDEX]


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

        self.mModelItems: typing.Set[PropertyItemGroup] = set()

        # # workaround https://github.com/qgis/QGIS/issues/45228
        self.mStartedCommitEditWrapper: bool = False

        self.mCACHE_PROFILE_DATA = dict()
        self.mEnableCaching: bool = False
        self.mProfileFieldModel: QgsFieldModel = QgsFieldModel()

        self.mPlotWidget: SpectralProfilePlotWidget = None
        symbol = QgsMarkerSymbol.createSimple({'name': 'square', 'color': 'white'})
        self.mDefaultSymbolRenderer = QgsSingleSymbolRenderer(symbol)

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

        self.mChangedFIDs: typing.Set[int] = set()
        self.mChangedAttributes: typing.Set[typing.Tuple[int, int]] = set()
        self.mLastEditCommand: str = None
        # self.mPlotDataItems: typing.List[SpectralProfilePlotDataItem] = list()

        # Update plot data and colors

        # .mCache2ModelData: typing.Dict[MODEL_DATA_KEY, dict] = dict()
        # mCache2ModelData[(fid, fidx, modelId, xunit))] -> dict
        # self.mCache3PlotData: typing.Dict[PLOT_DATA_KEY, dict] = dict()

        self.mUnitConverterFunctionModel = UnitConverterFunctionModel()
        self.mDualView: QgsDualView = None
        self.mSpeclib: QgsVectorLayer = None

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.mXUnit: str = self.mXUnitModel[0]
        self.mXUnitInitialized: bool = False
        self.mShowSelectedFeaturesOnly: bool = False

        self.mGeneralSettings = GeneralSettingsGroup()

        self.mProfileCandidates = ProfileCandidateGroup()
        self.insertPropertyGroup(0, self.mGeneralSettings)
        self.insertPropertyGroup(1, self.mProfileCandidates)

        # self.mTemporaryProfileIDs: typing.Set[FEATURE_ID] = set()
        # self.mTemporaryProfileColors: typing.Dict[ATTRIBUTE_ID, QColor] = dict()
        # self.mTemporaryProfileStyles: typing.Dict[ATTRIBUTE_ID, PlotStyle] = dict()

        self.mMaxProfilesWidget: QWidget = None

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

    def project(self) -> QgsProject:
        return self.mProject

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
            if d is None or len(d) == 0:
                # no profile
                rawData = None
            else:
                rawData = d
                if rawData.get('x', None) is None:
                    rawData['x'] = list(range(len(rawData['y'])))
                    rawData['xUnit'] = BAND_INDEX
            self.mCACHE_PROFILE_DATA[id_attribute] = rawData
        return self.mCACHE_PROFILE_DATA[id_attribute]

    def plotData(self, feature: QgsFeature, fieldIndex: int, xUnit: str) -> typing.Tuple[dict, bool]:
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

    sigXUnitChanged = pyqtSignal(str)

    def setXUnit(self, unit: str):
        if self.mXUnit != unit:
            unit_ = self.mXUnitModel.findUnit(unit)
            assert unit_, f'Unknown unit for x-axis: {unit}'
            self.mXUnit = unit_

            #  baseUnit = UnitLookup.baseUnit(unit_)
            labelName = self.mXUnitModel.unitData(unit_, Qt.DisplayRole)
            self.mPlotWidget.xAxis().setUnit(unit, labelName=labelName)
            self.mPlotWidget.clearInfoScatterPoints()
            # self.mPlotWidget.xAxis().setLabel(text='x values', unit=unit_)
            for bv in self.layerRendererVisualizations():
                bv.setXUnit(self.mXUnit)
            self.updatePlot()
            self.sigXUnitChanged.emit(self.mXUnit)

    def xUnit(self) -> str:
        return self.mXUnit

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

    def __iter__(self) -> typing.Iterator[ProfileVisualizationGroup]:
        return iter(self.visualizations())

    def profileFieldsModel(self) -> QgsFieldModel:
        return self.mProfileFieldModel

    def propertyGroups(self) -> typing.List[PropertyItemGroup]:
        groups = []
        for r in range(self.rowCount()):
            grp = self.invisibleRootItem().child(r, 0)
            if isinstance(grp, PropertyItemGroup):
                groups.append(grp)
        return groups

    def layerRendererVisualizations(self) -> typing.List[RasterRendererGroup]:
        return [v for v in self.propertyGroups() if isinstance(v, RasterRendererGroup)]

    def visualizations(self) -> typing.List[ProfileVisualizationGroup]:

        return [v for v in self.propertyGroups() if isinstance(v, ProfileVisualizationGroup)]

    def insertPropertyGroup(self,
                            index: typing.Union[int, QModelIndex],
                            items: typing.Union[PropertyItemGroup,
                                                typing.List[PropertyItemGroup]],
                            ):
        if isinstance(index, QModelIndex):
            index = index.row()
        if index == -1:
            index = len(self)

        if isinstance(items, PropertyItemGroup):
            items = [items]

        # map to model index within group of same zValues

        _index = 0

        for i, item in enumerate(items):
            assert isinstance(item, PropertyItemGroup)
            item.signals().requestRemoval.connect(self.onRemovalRequest)
            item.signals().requestPlotUpdate.connect(self.updatePlot)

            new_set: typing.List[PropertyItemGroup] = self.propertyGroups()
            new_set.insert(index + i, item)
            new_set = sorted(new_set, key=lambda g: g.zValue())
            _index = new_set.index(item)

            self.mModelItems.add(item)
            self.insertRow(_index, item)
            # if necessary, this should update the plot
            item.initWithPlotModel(self)

        # self.updatePlot()

    def onRemovalRequest(self):
        sender = self.sender()
        s = ""

    def removePropertyItemGroups(self, groups: typing.Union[PropertyItemGroup,
                                                            typing.List[PropertyItemGroup]]):

        if isinstance(groups, PropertyItemGroup):
            groups = [groups]

        if len(groups) > 0:
            for v in groups:
                if not (isinstance(v, PropertyItemGroup) and v.isRemovable()):
                    continue
                assert v in self.mModelItems

                for r in range(self.rowCount()):
                    if self.invisibleRootItem().child(r, 0) == v:
                        self.mModelItems.remove(v)
                        self.takeRow(r)
                        break

            self.updatePlot()

    def updatePlot(self, fids_to_update=[]):
        if self.updatesBlocked() or self.speclib().isEditCommandActive():
            return

        t0 = datetime.datetime.now()
        if not (isinstance(self.mPlotWidget, SpectralProfilePlotWidget) and isinstance(self.speclib(), QgsVectorLayer)):
            return

        xunit = self.xUnit()

        # Recycle plot items
        old_spdis: typing.List[SpectralProfilePlotDataItem] = self.mPlotWidget.spectralProfilePlotDataItems()

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

        pdiGenerator = PDIGenerator([], onProfileClicked=self.mPlotWidget.onProfileClicked)

        featureRenderer = self.speclib().renderer()
        if isinstance(featureRenderer, QgsFeatureRenderer):
            featureRenderer = featureRenderer.clone()
        else:
            featureRenderer = self.mDefaultSymbolRenderer.clone()

        request = QgsFeatureRequest()
        request.setFilterFids(feature_priority)

        # PROFILE_DATA: typing.Dict[tuple, dict] = dict()

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
            scope = item.createExpressionContextScope()
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
            featureRenderer.startRender(renderContext, feature.fields())
            qgssymbol = featureRenderer.symbolForFeature(feature, renderContext)
            symbolScope = None
            if isinstance(qgssymbol, QgsSymbol):
                symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                context.appendScope(symbolScope)

            for vis in visualizations:
                if len(PLOT_ITEMS) >= max_profiles:
                    profile_limit_reached = True
                    break
                vis: ProfileVisualizationGroup
                fieldIndex = vis.fieldIdx()

                # context.appendScope(vis.createExpressionContextScope())
                context.lastScope().setVariable('field_name', vis.fieldName())
                context.lastScope().setVariable('field_index', fieldIndex)
                context.lastScope().setVariable('visualization_name', vis.name())

                if fid not in selected_fids and vis.filterProperty().expressionString() != '':
                    b, success = vis.filterProperty().valueAsBool(context, defaultValue=False)
                    if b is False:
                        continue
                plot_data: dict = self.plotData(feature, vis.fieldIdx(), xunit)

                if not isinstance(plot_data, dict):
                    # profile data can not be transformed to requested x-unit
                    continue

                plot_style: PlotStyle = vis.generatePlotStyle(context)
                plot_label: str = vis.generateLabel(context)
                plot_tooltip: str = vis.generateTooltip(context)
                pdi = pdiGenerator.__next__()
                pdi: SpectralProfilePlotDataItem
                vis_key = (vis, fid, fieldIndex, xunit)
                pdi.setVisualizationKey(vis_key)
                pdi.setProfileData(plot_data, plot_style,
                                   showBadBands=show_bad_bands,
                                   sortBands=sort_bands,
                                   label=plot_label,
                                   tooltip=plot_tooltip,
                                   zValue=-1 * len(PLOT_ITEMS))

                vis.mPlotDataItems.append(pdi)
                PLOT_ITEMS.append(pdi)

            featureRenderer.stopRender(renderContext)

            if context.lastScope() == symbolScope:
                context.popScope()

        # selectionColor = QColor(self.mPlotWidgetStyle.selectionColor)
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
            #  printCaller(suffix=f'Remove {len(to_remove)} items', dt=t1)
            existing = self.mPlotWidget.items()

            to_add = [p for p in PLOT_ITEMS if p not in existing]

            t2 = datetime.datetime.now()
            for p in to_add:
                self.mPlotWidget.addItem(p)
            #  t3 = printCaller(suffix=f'Add    {len(to_add)} items', dt=t2)

        n_total = len([i for i in self.mPlotWidget.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)])

        self.updateProfileLabel(len(PLOT_ITEMS), profile_limit_reached)

        printCaller(suffix='Total', dt=t1)

    def updateProfileLabel(self, n: int, limit_reached: bool):
        propertyItem = self.generalSettings().mP_MaxProfiles

        with SignalBlocker(propertyItem.signals()) as blocker:
            if limit_reached:
                fg = QColor('red')
                tt = 'Profile limit reached. Increase to show more profiles at the same time (decreases speed)'
            else:
                fg = None
                tt = propertyItem.definition().description()
            propertyItem.setData(tt, Qt.ToolTipRole)
            propertyItem.setData(fg, Qt.ForegroundRole)
            propertyItem.emitDataChanged()

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

    def mimeTypes(self) -> typing.List[str]:
        return [PropertyItemGroup.MIME_TYPE]

    def mimeData(self, indexes: typing.Iterable[QModelIndex]) -> QMimeData:

        groups: typing.List[PropertyItemGroup] = []

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
        Returns None of a conversion is not possible (e.g. from meters to time)
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
        if x is None or len(x) == 0:
            return None
        else:
            # convert date units to float values with decimal year and second precision to make them plotable
            if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                x = convertDateUnit(datetime64(x), 'DecimalYear')

            if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                y = convertDateUnit(datetime64(y), 'DecimalYear')

            profileData['x'] = x
            profileData['y'] = y
            profileData['xUnit'] = xUnit
            return profileData

    def featurePriority(self) -> typing.List[int]:
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

        priority1: typing.List[int] = []  # visible features
        priority2: typing.List[int] = []  # selected features
        priority3: typing.List[int] = []  # any other : not visible / not selected

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
                self.mSpeclib.updatedFields.disconnect(self.updateProfileFieldModel)
                self.mSpeclib.attributeAdded.disconnect(self.updateProfileFieldModel)
                self.mSpeclib.attributeDeleted.disconnect(self.updateProfileFieldModel)

                self.mSpeclib.editCommandStarted.disconnect(self.onSpeclibEditCommandStarted)
                self.mSpeclib.editCommandEnded.disconnect(self.onSpeclibEditCommandEnded)
                self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
                self.mSpeclib.beforeCommitChanges.disconnect(self.onSpeclibBeforeCommitChanges)
                # self.mSpeclib.afterCommitChanges.disconnect(self.onSpeclibAfterCommitChanges)
                self.mSpeclib.committedFeaturesAdded.disconnect(self.onSpeclibCommittedFeaturesAdded)

                self.mSpeclib.featuresDeleted.disconnect(self.onSpeclibFeaturesDeleted)
                self.mSpeclib.selectionChanged.disconnect(self.onSpeclibSelectionChanged)
                self.mSpeclib.styleChanged.disconnect(self.onSpeclibStyleChanged)

            self.mSpeclib = speclib
            self.mVectorLayerCache = QgsVectorLayerCache(speclib, 1000)

            # register signals
            if isinstance(self.mSpeclib, QgsVectorLayer):
                self.mSpeclib.updatedFields.connect(self.updateProfileFieldModel)
                self.mSpeclib.attributeAdded.connect(self.updateProfileFieldModel)
                self.mSpeclib.attributeDeleted.connect(self.updateProfileFieldModel)
                self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
                self.mSpeclib.editCommandStarted.connect(self.onSpeclibEditCommandStarted)
                self.mSpeclib.editCommandEnded.connect(self.onSpeclibEditCommandEnded)
                self.mSpeclib.committedAttributeValuesChanges.connect(self.onSpeclibCommittedAttributeValuesChanges)
                self.mSpeclib.beforeCommitChanges.connect(self.onSpeclibBeforeCommitChanges)
                self.mSpeclib.afterCommitChanges.connect(self.onSpeclibAfterCommitChanges)
                self.mSpeclib.committedFeaturesAdded.connect(self.onSpeclibCommittedFeaturesAdded)

                self.mSpeclib.featuresDeleted.connect(self.onSpeclibFeaturesDeleted)
                self.mSpeclib.selectionChanged.connect(self.onSpeclibSelectionChanged)
                self.mSpeclib.styleChanged.connect(self.onSpeclibStyleChanged)
                self.updateProfileFieldModel()

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

    def updateProfileFieldModel(self, *args):
        fields = QgsFields()
        for f in profile_field_list(self.mSpeclib):
            fields.append(f)
        self.mProfileFieldModel.setFields(fields)

    def onSpeclibStyleChanged(self, *args):
        # self.loadFeatureColors()
        b = False
        for vis in self.visualizations():
            if vis.isVisible() and 'symbol_color' in vis.colorProperty().expressionString():
                b = True
                break
        if b:
            self.updatePlot()

    def onSpeclibSelectionChanged(self, selected: typing.List[int], deselected: typing.List[int], clearAndSelect: bool):
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

    def onSpeclibCommittedAttributeValuesChanges(self, lid: str, changedAttributeValues: typing.Dict[int, dict]):
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
        if len(self.mChangedAttributes) == 0:
            return
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

    def profileFields(self) -> typing.List[QgsField]:
        return profile_field_list(self.speclib())

    def profileFieldIndices(self) -> typing.List[int]:
        return profile_field_indices(self.speclib())

    def profileFieldNames(self) -> typing.List[str]:
        return profile_field_indices()

    PropertyIndexRole = Qt.UserRole + 1
    PropertyDefinitionRole = Qt.UserRole + 2
    PropertyRole = Qt.UserRole + 3


class PDIGenerator(object):
    """
    A generator over SpectralProfilePlotData items.
    Uses existing ones and, if nececessary, creates new ones.
    """

    def __init__(self, existingPDIs: typing.List[SpectralProfilePlotDataItem] = [],
                 onProfileClicked: typing.Callable = None):
        self.pdiList: typing.List[SpectralProfilePlotDataItem] = existingPDIs
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

    def remaining(self) -> typing.List[SpectralProfilePlotDataItem]:
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

    def selectedPropertyGroups(self) -> typing.List[PropertyItemGroup]:
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

    def setModel(self, model: typing.Optional[QAbstractItemModel]) -> None:
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

    def removeItems(self, vis: typing.List[PropertyItemGroup]):

        model = self.model()

        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        if isinstance(model, SpectralProfilePlotModel):
            model.removePropertyItemGroups(vis)

    def copyItems(self, visualizations: typing.List[ProfileVisualizationGroup]):

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

    def userColorsFromSymbolRenderer(self, vis: typing.List[ProfileVisualizationGroup]):
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

        if isinstance(item, PropertyItemBase):
            if item.hasPixmap():
                super().paint(painter, option, index)
                rect = option.rect
                size = QSize(rect.width(), rect.height())
                pixmap = item.previewPixmap(size)
                if isinstance(pixmap, QPixmap):
                    painter.drawPixmap(rect, pixmap)

            elif isinstance(item, ProfileVisualizationGroup):
                super().paint(painter, option, index)
                rect = option.rect
                plot_style: PlotStyle = item.mPStyle.plotStyle()
                html_style = HTMLStyle()
                x0 = rect.height()

                # self.initStyleOption(option, index)

                # [25px warning icon] | 50 px style | html style text
                # rect1, rect2, rect3
                if total_h > 0 and total_w > 0:
                    dy = rect.height()
                    w1 = dy  # warning icon -> square
                    w2 = w1 * 2  # plot style -> rectangle
                    if not item.isComplete():
                        item.isComplete()
                        rect1 = QRect(rect.x() + x0, rect.y(), w1, dy)
                        icon = QIcon(r':/images/themes/default/mIconWarning.svg')
                        # overpaint
                        icon.paint(painter, rect1)
                    else:
                        rect1 = QRect(rect.x() + x0, rect.y(), 0, dy)
                        x0 += dy
                    rect2 = QRect(rect1.x() + rect1.width(), rect.y(), w1, dy)
                    rect3 = QRect(rect2.x() + rect2.width(), rect.y(), total_w - rect2.x() - rect2.width(), dy)
                    # pixmap = style.createPixmap(size=QSize(w - x0, total_h), hline=True, bc=bc)
                    if item.isComplete():
                        pixmap = plot_style.createPixmap(size=rect2.size(), hline=True, bc=bc)
                        painter.drawPixmap(rect2, pixmap)
                    # rect2 = QRect(rect.x() + x0, rect.y(), rect.width() - 2*x0, rect.height())
                    # html_style.drawItemText(painter, rect3, None, item.text(), )

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
        grid: QGridLayout = widgetXAxis.layout()
        grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        grid.addWidget(self.optionXUnit.createUnitComboBox(), 0, 2, 1, 2)

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
                self.createProfileVisualization(field=field)
                # keep in mind if a visualization was created at least once for a profile field
                self.mINITIALIZED_VISUALIZATIONS.add(name)

    def createLayerBandVisualization(self, *args):

        layer = None
        d = SelectMapLayerDialog()
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
                                   field: typing.Union[QgsField, int, str] = None,
                                   color: typing.Union[str, QColor] = None,
                                   style: PlotStyle = None):
        item = ProfileVisualizationGroup()

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
                    if field.type() in [QVariant.String, QVariant.Int] and rx.search(field.name()):
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

    def profileVisualizations(self) -> typing.List[ProfileVisualizationGroup]:
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
