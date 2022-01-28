import datetime
import re
import typing

import numpy as np
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDialog

from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import pyqtSignal, Qt, QModelIndex, QPoint, QSortFilterProxyModel, QSize, \
    QVariant, QAbstractItemModel, QItemSelectionModel, QRect, QMimeData, QByteArray
from qgis.PyQt.QtGui import QColor, QDragEnterEvent, QDropEvent, QPainter, QIcon, QContextMenuEvent
from qgis.PyQt.QtWidgets import QWidgetAction, QWidget, QGridLayout, QSpinBox, QLabel, QFrame, QAction, QApplication, \
    QTableView, QComboBox, QMenu, QStyledItemDelegate, QHBoxLayout, QTreeView, QStyleOptionViewItem
from qgis.core import QgsProject, QgsMapLayerProxyModel
from qgis.core import QgsRasterLayer
from qgis.core import QgsField, \
    QgsVectorLayer, QgsFieldModel, QgsFields, QgsSettings, QgsApplication, QgsExpressionContext, \
    QgsFeatureRenderer, QgsRenderContext, QgsSymbol, QgsFeature, QgsFeatureRequest
from qgis.core import QgsProperty, QgsExpressionContextScope
from qgis.core import QgsVectorLayerCache
from qgis.gui import QgsDualView
from qgis.gui import QgsFilterLineEdit

from .spectrallibraryplotitems import SpectralLibraryPlotWidgetStyle, FEATURE_ID, FIELD_INDEX, MODEL_NAME, \
    VISUALIZATION_KEY, SpectralProfilePlotDataItem, SpectralProfilePlotWidget
from .spectrallibraryplotmodelitems import PropertyItemGroup, PropertyItem, LayerBandVisualization, \
    ProfileVisualization, PlotStyleItem
from .. import speclibUiPath
from ..core import profile_field_list, profile_field_indices, is_spectral_library, profile_fields
from ..core.spectralprofile import decodeProfileValueDict
from ... import debugLog
from ...externals.htmlwidgets import HTMLStyle

from ...pyqtgraph import pyqtgraph as pg
from ...models import SettingsModel, SettingsTreeView
from ...plotstyling.plotstyling import PlotStyle
from ...unitmodel import BAND_INDEX, BAND_NUMBER, UnitConverterFunctionModel, UnitModel
from ...utils import datetime64, UnitLookup, loadUi, SignalObjectWrapper, convertDateUnit, nextColor, qgsField, \
    SelectMapLayerDialog


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


class SpeclibSettingsWidgetAction(QWidgetAction):
    sigSettingsValueChanged = pyqtSignal(str)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mSettings = QgsSettings()
        self.mModel = SettingsModel(self.mSettings)
        self.mModel.sigSettingsValueChanged.connect(self.sigSettingsValueChanged.emit)

    def createWidget(self, parent: QWidget):
        view = SettingsTreeView(parent)
        view.setModel(self.mModel)
        return view


class MaxNumberOfProfilesWidgetAction(QWidgetAction):
    sigMaxNumberOfProfilesChanged = pyqtSignal(int)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mNProfiles = 256

    def createWidget(self, parent: QWidget):
        gridLayout = QGridLayout()
        sbMaxProfiles = QSpinBox()
        sbMaxProfiles.setToolTip('Maximum number of profiles to plot.')
        sbMaxProfiles.setRange(0, np.iinfo(np.int16).max)
        sbMaxProfiles.setValue(self.maxProfiles())
        self.sigMaxNumberOfProfilesChanged.connect(lambda n, sb=sbMaxProfiles: sb.setValue(n))
        sbMaxProfiles.valueChanged[int].connect(self.setMaxProfiles)

        gridLayout.addWidget(QLabel('Max. Profiles'), 0, 0)
        gridLayout.addWidget(sbMaxProfiles, 0, 1)
        frame = QFrame(parent)
        frame.setLayout(gridLayout)
        return frame

    def setMaxProfiles(self, n: int):
        assert isinstance(n, int) and n >= 0
        if n != self.mNProfiles:
            self.mNProfiles = n
            self.sigMaxNumberOfProfilesChanged.emit(n)

    def maxProfiles(self) -> int:
        return self.mNProfiles


MAX_PDIS_DEFAULT: int = 256


class SpectralLibraryPlotWidgetStyleWidget(QWidget):
    sigStyleChanged = pyqtSignal(SpectralLibraryPlotWidgetStyle)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        path_ui = speclibUiPath('spectrallibraryplotwidgetstylewidget.ui')
        loadUi(path_ui, self)

        self.mBlocked: bool = False
        self.btnColorBackground.colorChanged.connect(self.onStyleChanged)
        self.btnColorForeground.colorChanged.connect(self.onStyleChanged)
        self.btnColorCrosshair.colorChanged.connect(self.onStyleChanged)
        self.btnColorText.colorChanged.connect(self.onStyleChanged)
        self.btnColorSelection.colorChanged.connect(self.onStyleChanged)
        self.btnColorTemporary.colorChanged.connect(self.onStyleChanged)
        self.btnReset.setDisabled(True)
        self.btnReset.clicked.connect(self.resetStyle)

        self.actionActivateDarkTheme: QAction
        self.actionActivateDarkTheme.setIcon(QIcon(r':/qps/ui/icons/profiletheme_dark.svg'))

        self.actionActivateBrightTheme: QAction
        self.actionActivateBrightTheme.setIcon(QIcon(r':/qps/ui/icons/profiletheme_bright.svg'))

        self.btnColorSchemeBright.setDefaultAction(self.actionActivateBrightTheme)
        self.btnColorSchemeDark.setDefaultAction(self.actionActivateDarkTheme)
        self.actionActivateBrightTheme.triggered.connect(
            lambda: self.setProfileWidgetTheme(SpectralLibraryPlotWidgetStyle.bright()))
        self.actionActivateDarkTheme.triggered.connect(
            lambda: self.setProfileWidgetTheme(SpectralLibraryPlotWidgetStyle.dark()))
        self.mResetStyle: SpectralLibraryPlotWidgetStyle = None
        self.mLastStyle: SpectralLibraryPlotWidgetStyle = None

    def setResetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        self.mResetStyle = style

    def getResetStyle(self) -> SpectralLibraryPlotWidgetStyle:
        return self.mResetStyle

    def resetStyle(self, *args):
        if isinstance(self.mResetStyle, SpectralLibraryPlotWidgetStyle):
            self.setProfileWidgetStyle(self.mResetStyle)

    def setProfileWidgetTheme(self, style: SpectralLibraryPlotWidgetStyle):

        newstyle = self.spectralProfileWidgetStyle()

        # overwrite colors
        newstyle.crosshairColor = style.crosshairColor
        newstyle.textColor = style.textColor
        newstyle.backgroundColor = style.backgroundColor
        newstyle.foregroundColor = style.foregroundColor
        newstyle.selectionColor = style.selectionColor
        newstyle.temporaryColor = style.temporaryColor

        self.setProfileWidgetStyle(newstyle)

    def setProfileWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        assert isinstance(style, SpectralLibraryPlotWidgetStyle)

        if self.mResetStyle is None:
            self.mResetStyle = style.clone()

        self.mLastStyle = style
        self.btnReset.setEnabled(True)

        changed = style != self.spectralProfileWidgetStyle()

        self.mBlocked = True

        self.btnColorBackground.setColor(style.backgroundColor)
        self.btnColorForeground.setColor(style.foregroundColor)
        self.btnColorText.setColor(style.textColor)
        self.btnColorCrosshair.setColor(style.crosshairColor)
        self.btnColorSelection.setColor(style.selectionColor)
        self.btnColorTemporary.setColor(style.temporaryColor)

        self.mBlocked = False
        if changed:
            self.sigStyleChanged.emit(self.spectralProfileWidgetStyle())

    def onStyleChanged(self, *args):
        if not self.mBlocked:
            self.btnReset.setEnabled(isinstance(self.mResetStyle, SpectralLibraryPlotWidgetStyle)
                                     and self.spectralProfileWidgetStyle() != self.mResetStyle)
            self.sigStyleChanged.emit(self.spectralProfileWidgetStyle())

    def spectralProfileWidgetStyle(self) -> SpectralLibraryPlotWidgetStyle:
        if isinstance(self.mLastStyle, SpectralLibraryPlotWidgetStyle):
            cs = self.mLastStyle.clone()
        else:
            cs = SpectralLibraryPlotWidgetStyle()
        cs: SpectralLibraryPlotWidgetStyle
        assert isinstance(cs, SpectralLibraryPlotWidgetStyle)

        cs.backgroundColor = self.btnColorBackground.color()
        cs.foregroundColor = self.btnColorForeground.color()
        cs.crosshairColor = self.btnColorCrosshair.color()
        cs.textColor = self.btnColorText.color()
        cs.selectionColor = self.btnColorSelection.color()
        cs.temporaryColor = self.btnColorTemporary.color()
        return cs


class SpectralProfileWidgetStyleAction(QWidgetAction):
    sigProfileWidgetStyleChanged = pyqtSignal(SpectralLibraryPlotWidgetStyle)
    sigResetStyleChanged = pyqtSignal(SpectralLibraryPlotWidgetStyle)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mStyle: SpectralLibraryPlotWidgetStyle = SpectralLibraryPlotWidgetStyle.default()
        self.mResetStyle: SpectralLibraryPlotWidgetStyle = self.mStyle

    def setResetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        self.mResetStyle = style
        self.sigResetStyleChanged.emit(self.mResetStyle)

    def setProfileWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        if self.mStyle != style:
            # print(self.mStyle.printDifferences(style))
            self.mStyle = style
            self.sigProfileWidgetStyleChanged.emit(style)

    def profileWidgetStyle(self) -> SpectralLibraryPlotWidgetStyle:
        return self.mStyle

    def createWidget(self, parent: QWidget) -> SpectralLibraryPlotWidgetStyleWidget:
        w = SpectralLibraryPlotWidgetStyleWidget(parent)
        w.setProfileWidgetStyle(self.profileWidgetStyle())
        w.sigStyleChanged.connect(self.setProfileWidgetStyle)
        self.sigProfileWidgetStyleChanged.connect(w.setProfileWidgetStyle)
        self.sigResetStyleChanged.connect(w.setResetStyle)
        return w


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

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mProject: QgsProject = QgsProject.instance()

        self.mModelItems: typing.Set[PropertyItemGroup] = set()

        # # workaround https://github.com/qgis/QGIS/issues/45228
        self.mStartedCommitEditWrapper: bool = False

        self.mCACHE_PROFILE_DATA = dict()

        self.mProfileFieldModel: QgsFieldModel = QgsFieldModel()

        self.mPlotWidget: SpectralProfilePlotWidget = None

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
        self.mMaxProfiles: int = 200
        self.mShowSelectedFeaturesOnly: bool = False

        self.mPlotWidgetStyle: SpectralLibraryPlotWidgetStyle = SpectralLibraryPlotWidgetStyle.dark()
        self.mTemporaryProfileIDs: typing.Set[FEATURE_ID] = set()
        self.mTemporaryProfileColors: typing.Dict[ATTRIBUTE_ID, QColor] = dict()
        self.mTemporaryProfileStyles: typing.Dict[ATTRIBUTE_ID, PlotStyle] = dict()

        self.mMaxProfilesWidget: QWidget = None

    def setMaxProfilesWidget(self, w: QWidget):
        self.mMaxProfilesWidget = w

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

    def setPlotWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        self.mPlotWidgetStyle = style
        if self.rowCount() > 0:
            # set background color to each single plotstyle
            for vis in self.visualizations():
                vis.plotStyle().setBackgroundColor(style.backgroundColor)

            # update plot backgrounds
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0)
            )
        if self.mPlotWidget:
            self.mPlotWidget.setWidgetStyle(style)
        self.sigPlotWidgetStyleChanged.emit()

    def plotWidgetStyle(self) -> SpectralLibraryPlotWidgetStyle:
        return self.mPlotWidgetStyle

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

    sigMaxProfilesChanged = pyqtSignal(int)

    def setMaxProfiles(self, n: int):
        assert n >= 0
        if n != self.mMaxProfiles:
            if n < self.mMaxProfiles:
                # remove spdis
                spdis = sorted(self.mPlotWidget.spectralProfilePlotDataItems(), key=lambda k: k.zValue())
                while len(spdis) > n:
                    self.mPlotWidget.removeItem(spdis.pop())
                self.mMaxProfiles = n
            else:
                self.mMaxProfiles = n
                self.updatePlot()

            self.sigMaxProfilesChanged.emit(self.mMaxProfiles)

    def maxProfiles(self) -> int:
        return self.mMaxProfiles

    def __len__(self) -> int:
        return len(self.visualizations())

    def __iter__(self) -> typing.Iterator[ProfileVisualization]:
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

    def layerRendererVisualizations(self) -> typing.List[LayerBandVisualization]:
        return [v for v in self.propertyGroups() if isinstance(v, LayerBandVisualization)]

    def visualizations(self) -> typing.List[ProfileVisualization]:

        return [v for v in self.propertyGroups() if isinstance(v, ProfileVisualization)]

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

        for i, item in enumerate(items):
            assert isinstance(item, PropertyItemGroup)
            item.signals().requestRemoval.connect(self.onRemovalRequest)
            item.signals().requestPlotUpdate.connect(self.updatePlot)
            item.initWithProfilePlotModel(self)

            self.mModelItems.add(item)
            self.insertRow(index + i, item)

        self.updatePlot()

    """
    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            v = self[row]
            assert isinstance(v, ControlModelItem)
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.mModelItems[row]
            self.mNodeHandles.pop(v)
            self.endRemoveRows()
            if isinstance(v, LayerRendererVisualization):
                for bar in v.bandPlotItems():
                    self.mPlotWidget.plotItem.removeItem(bar)
            return True
        return False
    """

    def onRemovalRequest(self):
        sender = self.sender()
        s = ""

    def removeVisualizations(self, vis: typing.Union[PropertyItemGroup,
                                                     typing.List[PropertyItemGroup]]):

        if isinstance(vis, PropertyItemGroup):
            vis = [vis]

        if len(vis) > 0:
            for v in vis:
                if not isinstance(v, PropertyItemGroup):
                    s = ""
                assert isinstance(v, PropertyItemGroup)
                assert v in self.mModelItems

                for r in range(self.rowCount()):
                    if self.invisibleRootItem().child(r, 0) == v:
                        self.mModelItems.remove(v)
                        self.takeRow(r)
                        break

            self.updatePlot()

    def updatePlot(self, fids_to_update=[]):

        t0 = datetime.datetime.now()
        if not (isinstance(self.mPlotWidget, SpectralProfilePlotWidget) and isinstance(self.speclib(), QgsVectorLayer)):
            return

        feature_priority = self.featurePriority()

        if self.mShowSelectedFeaturesOnly:
            selected_fids = set()
            # feature_priority already contains selected fids only
        else:
            selected_fids = self.speclib().selectedFeatureIds()

        temporal_fids = self.mTemporaryProfileIDs
        visualizations = [v for v in self.visualizations() if
                          v.isVisible() and v.isComplete() and v.speclib() == self.mSpeclib]

        xunit = self.xUnit()

        # Recycle plot items
        old_spdis: typing.List[SpectralProfilePlotDataItem] = self.mPlotWidget.spectralProfilePlotDataItems()
        new_spdis: typing.List[SpectralProfilePlotDataItem] = []

        pdiGenerator = PDIGenerator(old_spdis, onProfileClicked=self.mPlotWidget.onProfileClicked)

        # init renderers
        VIS_RENDERERS: typing.Dict[ProfileVisualization,
                                   typing.Tuple[QgsFeatureRenderer, QgsRenderContext]] = dict()

        VIS_HAS_FILTER: typing.Dict[ProfileVisualization, bool] = dict()
        for vis in visualizations:
            vis: ProfileVisualization

            renderer: QgsFeatureRenderer = self.speclib().renderer()
            if isinstance(renderer, QgsFeatureRenderer):
                renderer = renderer.clone()
                renderContext = QgsRenderContext()
                # renderer.startRender(renderContext, self.speclib().fields())
                renderContext.setExpressionContext(self.speclib().createExpressionContext())

                VIS_RENDERERS[vis] = (renderer, renderContext)
            else:
                VIS_RENDERERS[vis] = (None, None)

            VIS_HAS_FILTER[vis] = vis.filterProperty().expressionString().strip() != ''

        request = QgsFeatureRequest()
        request.setFilterFids(feature_priority)

        # PROFILE_DATA: typing.Dict[tuple, dict] = dict()

        profile_limit_reached: bool = False
        context: QgsExpressionContext = self.speclib().createExpressionContext()

        NOT_INITIALIZED = -1

        for fid in feature_priority:
            # self.mVectorLayerCache.getFeatures(feature_priority):
            feature: QgsFeature = self.mVectorLayerCache.getFeature(fid)
            assert fid == feature.id()
            # fid = feature.id()
            if profile_limit_reached:
                break

            context.setFeature(feature)

            for vis in visualizations:

                vis: ProfileVisualization
                id_plot_data = (fid, vis.fieldIdx(), xunit)
                id_attribute = (fid, vis.fieldIdx())
                id_attributeN = (fid, vis.field().name())
                # context.appendScope(vis.createExpressionContextScope())

                if not (fid in selected_fids or fid in temporal_fids) and VIS_HAS_FILTER[vis]:
                    b, success = vis.filterProperty().valueAsBool(context, defaultValue=False)
                    if not b:
                        # feature does not match with visualization filter
                        continue

                # mCACHE_PROFILE_DATA keys:
                #   None -> no binary data / cannot be decoded
                # (fid, field index) = dict -> raw value dict, decoded as is
                # (fid, field index, '<x unit>') = dict -> converted to x unit

                plotData = self.mCACHE_PROFILE_DATA.get(id_plot_data, NOT_INITIALIZED)
                if plotData == NOT_INITIALIZED:

                    rawData = self.mCACHE_PROFILE_DATA.get(id_attribute, NOT_INITIALIZED)
                    if rawData == NOT_INITIALIZED:
                        # load profile data
                        byteArray: QByteArray = feature.attribute(vis.fieldIdx())
                        rawData = None
                        if isinstance(byteArray, QByteArray):
                            rawData = decodeProfileValueDict(byteArray)
                            if rawData['y'] is None:
                                # empty profile, nothing to plot
                                # create empty entries (=None)
                                rawData = None
                            elif rawData['x'] is None:
                                rawData['x'] = list(range(len(rawData['y'])))
                                rawData['xUnit'] = BAND_INDEX
                        self.mCACHE_PROFILE_DATA[id_attribute] = rawData

                    if rawData is None:
                        # cannot load raw data
                        self.mCACHE_PROFILE_DATA[id_plot_data] = None
                        continue

                    if not isinstance(rawData, dict):
                        s = ""
                    assert isinstance(rawData, dict)
                    if self.mXUnitInitialized is False and self.mXUnitModel.findUnit(rawData['xUnit']):
                        self.mXUnitInitialized = True
                        self.setXUnit(rawData['xUnit'])
                        # this will call updatePlot again, so we can return afterwards
                        return

                    # convert profile data to xUnit
                    # if not possible, entry will be set to None
                    self.mCACHE_PROFILE_DATA[id_plot_data] = self.modelDataToXUnitPlotData(rawData, xunit)
                    plotData = self.mCACHE_PROFILE_DATA[id_plot_data]

                if not isinstance(plotData, dict):
                    # profile data can not be transformed to requested x-unit
                    continue

                label, success = vis.labelProperty().valueAsString(context, defaultString='')

                style: PlotStyle = vis.plotStyle()
                linePen = pg.mkPen(style.linePen)
                symbolPen = pg.mkPen(style.markerPen)
                symbolBrush = pg.mkBrush(style.markerBrush)

                # featureColor: QColor = vis.plotStyle().lineColor()

                if fid in selected_fids:

                    # show all profiles, special highlight of selected

                    linePen.setColor(self.mPlotWidgetStyle.selectionColor)
                    linePen.setWidth(style.lineWidth() + 2)
                    symbolPen.setColor(self.mPlotWidgetStyle.selectionColor)
                    symbolBrush.setColor(self.mPlotWidgetStyle.selectionColor)

                elif fid in temporal_fids:
                    # special color
                    featureColor = self.mTemporaryProfileColors.get(id_attributeN, self.mPlotWidgetStyle.temporaryColor)
                    linePen.setColor(featureColor)
                    linePen.setWidth(style.lineWidth() + 2)
                    symbolPen.setColor(featureColor)
                    symbolBrush.setColor(featureColor)

                else:
                    qgssymbol = None
                    renderer, renderContext = VIS_RENDERERS[vis]

                    if isinstance(renderer, QgsFeatureRenderer):
                        renderContext.expressionContext().setFeature(feature)
                        renderer.startRender(renderContext, feature.fields())
                        qgssymbol = renderer.symbolForFeature(feature, renderContext)

                        if isinstance(qgssymbol, QgsSymbol):
                            symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                            context.appendScope(symbolScope)

                    prop = vis.colorProperty()
                    featureColor, success = prop.valueAsColor(context, defaultColor=QColor('white'))

                    if isinstance(renderer, QgsFeatureRenderer):
                        renderer.stopRender(renderContext)

                    if isinstance(qgssymbol, QgsSymbol):
                        context.popScope()
                        pass
                    if not success:
                        # no color, no profile, e.g. if profile
                        continue
                    linePen.setColor(featureColor)
                    symbolPen.setColor(featureColor)
                    symbolBrush.setColor(featureColor)

                if len(new_spdis) == self.maxProfiles():
                    profile_limit_reached = True
                    break

                symbol = style.markerSymbol
                symbolSize = style.markerSize

                x = plotData['x']
                y = plotData['y']
                if isinstance(x[0], (datetime.date, datetime.datetime)):
                    x = np.asarray(x, dtype=np.datetime64)

                pdi = pdiGenerator.__next__()
                pdi: SpectralProfilePlotDataItem

                zValue = pdiGenerator.zValue()

                k = (vis, (fid, vis.fieldIdx(), '', xunit))
                pdi.setVisualizationKey(k)
                assert isinstance(pdi, SpectralProfilePlotDataItem)

                # replace None by NaN
                x = np.asarray(x, dtype=float)
                y = np.asarray(y, dtype=float)
                connect = np.isfinite(x) & np.isfinite(y)
                pdi.setData(x=x, y=y, z=-1 * zValue,
                            connect=connect,
                            name=label, pen=linePen,
                            symbol=symbol, symbolPen=symbolPen, symbolBrush=symbolBrush, symbolSize=symbolSize)

                tooltip = f'<html><body><table>' \
                          f'<tr><td>Label</td><td>{label}</td></tr>' \
                          f'<tr><td>FID</td><td>{fid}</td></tr>' \
                          f'<tr><td>Field</td><td>{vis.field().name()}</td></tr>' \
                          f'</table></body></html>'

                pdi.setToolTip(tooltip)
                pdi.curve.setToolTip(tooltip)
                pdi.scatter.setToolTip(tooltip)
                pdi.setZValue(-1 * zValue)

                new_spdis.append(pdi)

        s = ""

        to_remove = [p for p in old_spdis if p not in new_spdis]
        for p in to_remove:
            self.mPlotWidget.removeItem(p)

        existing = self.mPlotWidget.items()
        for p in new_spdis:
            if p not in existing:
                self.mPlotWidget.addItem(p)

        self.updateProfileLabel(len(new_spdis), profile_limit_reached)

        debugLog(f'updatePlot: {datetime.datetime.now() - t0} {len(new_spdis)} plot data items')

    def updateProfileLabel(self, n: int, limit_reached: bool):

        if isinstance(self.mMaxProfilesWidget, QWidget):

            if limit_reached:
                css = 'color: rgb(255, 0, 0);'
                tt = 'Profile limit reached. Increase to show more profiles at the same time (decreases speed)'
            else:
                css = ''
                tt = ''
            self.mMaxProfilesWidget.setStyleSheet(css)
            self.mMaxProfilesWidget.setToolTip(tt)

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

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

    def modelDataToXUnitPlotData(self, modelData: dict, xUnit: str) -> dict:
        modelData = modelData.copy()

        func = self.mUnitConverterFunctionModel.convertFunction(modelData['xUnit'], xUnit)
        x = func(modelData['x'])
        y = modelData['y']
        if x is None or len(x) == 0:
            return None
        else:
            # convert date units to float values with decimal year and second precision to make them plotable
            if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                x = convertDateUnit(datetime64(x), 'DecimalYear')

            if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                y = convertDateUnit(datetime64(y), 'DecimalYear')

            modelData['x'] = x
            modelData['y'] = y
            modelData['xUnit'] = xUnit
            return modelData

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
                self.mSpeclib.updatedFields.disconnect(self.onSpeclibAttributesUpdated)
                # self.mSpeclib.attributeAdded.disconnect(self.onSpeclibAttributeDeleted)
                self.mSpeclib.editCommandEnded.disconnect(self.onSpeclibEditCommandEnded)
                # self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
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
                self.mSpeclib.updatedFields.connect(self.onSpeclibAttributesUpdated)
                # self.mSpeclib.attributeAdded.connect(self.onSpeclibAttributeDeleted)
                self.mSpeclib.editCommandEnded.connect(self.onSpeclibEditCommandEnded)
                self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
                self.mSpeclib.committedAttributeValuesChanges.connect(self.onSpeclibCommittedAttributeValuesChanges)
                self.mSpeclib.beforeCommitChanges.connect(self.onSpeclibBeforeCommitChanges)
                self.mSpeclib.afterCommitChanges.connect(self.onSpeclibAfterCommitChanges)
                self.mSpeclib.committedFeaturesAdded.connect(self.onSpeclibCommittedFeaturesAdded)

                self.mSpeclib.featuresDeleted.connect(self.onSpeclibFeaturesDeleted)
                self.mSpeclib.selectionChanged.connect(self.onSpeclibSelectionChanged)
                self.mSpeclib.styleChanged.connect(self.onSpeclibStyleChanged)
                self.onSpeclibAttributesUpdated()

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
        self.mChangedAttributes.add((fid, idx))
        # self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if (k[0], k[1]) != fid_idx}
        # self.updatePlot([fid])

    def onSpeclibCommittedFeaturesAdded(self, id, features):

        if id != self.speclib().id():
            return

        newFIDs = [f.id() for f in features]
        # see qgsvectorlayereditbuffer.cpp
        oldFIDs = list(reversed(list(self.speclib().editBuffer().addedFeatures().keys())))

        OLD2NEW = {o: n for o, n in zip(oldFIDs, newFIDs)}
        updates = dict()

        # rename fids in plot data items
        for pdi in self.mPlotWidget.spectralProfilePlotDataItems():
            visKey: VISUALIZATION_KEY = pdi.visualizationKey()
            old_fid = visKey[1][0]
            if old_fid in oldFIDs:
                new_vis_key = (visKey[0], (OLD2NEW[old_fid], visKey[1][1], visKey[1][2], visKey[1][3]))
                pdi.setVisualizationKey(new_vis_key)

        # rename fids for temporary profiles
        # self.mTemporaryProfileIDs = {t for t in self.mTemporaryProfileIDs if t not in oldFIDs}
        self.mTemporaryProfileIDs = {OLD2NEW.get(fid, fid) for fid in self.mTemporaryProfileIDs}
        self.updatePlot(fids_to_update=OLD2NEW.values())

    def onSpeclibAttributesUpdated(self, *args):
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

    def onSpeclibEditCommandEnded(self, *args):
        # changedFIDs1 = list(self.speclib().editBuffer().changedAttributeValues().keys())
        changedFIDs2 = self.mChangedFIDs

        self.mCACHE_PROFILE_DATA = {k: v for k, v in self.mCACHE_PROFILE_DATA.items() if
                                    (k[0], k[1]) not in self.mChangedAttributes}

        # self.mCACHE_PROFILE_DATA.clear()
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
            vis, dataKey = pdi.visualizationKey()
            fid, field, modelName, xUnit = dataKey
            vis: ProfileVisualization
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

    def selectVisualizations(self, visualizations):
        if isinstance(visualizations, ProfileVisualization):
            visualizations = [visualizations]

        model = self.model()
        rows = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            vis = model.data(idx, Qt.UserRole)
            if isinstance(vis, ProfileVisualization) and vis in visualizations:
                self.selectionModel().select(idx, QItemSelectionModel.Rows)

    def setModel(self, model: typing.Optional[QAbstractItemModel]) -> None:
        super().setModel(model)
        if isinstance(model, QAbstractItemModel):
            model.rowsInserted.connect(self.onRowsInserted)

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        for r in range(first, last + 1):
            idx = self.model().index(r, 0, parent=parent)
            item = idx.data(Qt.UserRole)
            if isinstance(item, PropertyItemGroup):
                self.setFirstColumnSpanned(r, parent, 1)
        s = ""

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        idx = self.currentIndex()

        selected_items = []
        for idx in self.selectedIndexes():
            v = self.idx2vis(idx)
            if isinstance(v, PropertyItemGroup) and v not in selected_items:
                selected_items.append(v)

        selected_vis = [item for item in selected_items if isinstance(item, ProfileVisualization)]

        a = menu.addAction('Remove Selected')
        a.setIcon(QIcon(r':/images/themes/default/mActionDeleteSelected.svg'))
        a.triggered.connect(lambda *args, v=selected_items: self.removeModelItems(v))
        a.setEnabled(len(selected_items) > 0)

        b = len(selected_items) > 0
        a = menu.addAction('Copy visualization')
        a.setIcon(QIcon(r':/images/themes/default/mActionEditCopy.svg'))
        a.triggered.connect(lambda *args, v=selected_items: self.copyVis(v))
        a.setEnabled(b)

        a = menu.addAction('Paste visualization')
        a.setIcon(QIcon(r':/images/themes/default/mActionEditPaste.svg'))
        a.setEnabled(QApplication.clipboard().mimeData().hasFormat(ProfileVisualization.MIME_TYPE))
        a.triggered.connect(lambda *args: self.pasteVis())
        a.setEnabled(
            QApplication.clipboard().mimeData().hasFormat(ProfileVisualization.MIME_TYPE)
        )

        a = menu.addAction('Use vector symbol colors')
        a.setToolTip('Use map vector symbol colors as profile color.')
        a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
        a.triggered.connect(lambda *args, v=selected_items: self.userColorsFromSymbolRenderer(v))

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def removeModelItems(self, vis: typing.List[PropertyItemGroup]):

        model = self.model()

        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        if isinstance(model, SpectralProfilePlotModel):
            model.removeVisualizations(vis)

    def copyVis(self, visualizations: typing.List[ProfileVisualization]):

        indices = []
        for vis in visualizations:
            idx = self.vis2index(vis)
            if idx.isValid():
                indices.append(idx)
        if len(indices) > 0:
            mimeData = self.model().mimeData(indices)
            QApplication.clipboard().setMimeData(mimeData)

    def pasteVis(self):

        md: QMimeData = QApplication.clipboard().mimeData()

        idx = self.currentIndex()
        self.model().dropMimeData(md, Qt.CopyAction, idx.row(), idx.column(), idx.parent())

    def vis2index(self, vis: ProfileVisualization) -> QModelIndex:
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

    def userColorsFromSymbolRenderer(self, vis: typing.List[ProfileVisualization]):

        for v in vis:
            assert isinstance(v, ProfileVisualization)
            parentIdx = self.vis2index(v)
            if not parentIdx.isValid():
                return

            property = QgsProperty(v.colorProperty())
            property.setExpressionString('@symbol_color')

            model: QAbstractItemModel = self.model()
            idx = model.index(SpectralProfilePlotModel.PIX_COLOR, SpectralProfilePlotModel.CIX_VALUE,
                              parentIdx)
            self.model().setData(idx, property, role=Qt.EditRole)
        pass


class SpectralProfilePlotViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manange input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: SpectralProfilePlotView, parent=None):
        assert isinstance(treeView, SpectralProfilePlotView)
        super(SpectralProfilePlotViewDelegate, self).__init__(parent=parent)
        self.mTreeView: SpectralProfilePlotView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: PropertyItem = index.data(Qt.UserRole)
        bc = QColor(self.plotControl().plotWidgetStyle().backgroundColor)
        if isinstance(item, ProfileVisualization):
            super().paint(painter, option, index)
            rect = option.rect
            plot_style: PlotStyle = item.plotStyle()
            html_style = HTMLStyle()
            x0 = 25
            total_h = self.mTreeView.rowHeight(index)
            total_w = self.mTreeView.columnWidth(index.column())
            w = self.mTreeView.columnWidth(index.column()) - 25
            # self.initStyleOption(option, index)

            # [25px warning icon] | 50 px style | html style text
            # rect1, rect2, rect3
            if total_h > 0 and total_w > 0:
                dy = rect.height()
                w1 = dy  # warning icon -> square
                w2 = w1 * 2  # plot style -> rectangle
                if not item.isComplete():
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
                pixmap = plot_style.createPixmap(size=rect2.size(), hline=True, bc=bc)
                painter.drawPixmap(rect2, pixmap)
                # rect2 = QRect(rect.x() + x0, rect.y(), rect.width() - 2*x0, rect.height())
                # html_style.drawItemText(painter, rect3, None, item.text(), )

        elif isinstance(item, PlotStyleItem):
            # self.initStyleOption(option, index)
            plot_style: PlotStyle = item.plotStyle()

            total_h = self.mTreeView.rowHeight(index)
            w = self.mTreeView.columnWidth(index.column())
            if total_h > 0 and w > 0:
                px = plot_style.createPixmap(size=QSize(w, total_h), bc=bc)
                painter.drawPixmap(option.rect, px)
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
        self.mPlotControlModel.setMaxProfiles(self.sbMaxProfiles.value())
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

        self.sbMaxProfiles: QSpinBox
        self.sbMaxProfiles.valueChanged.connect(self.mPlotControlModel.setMaxProfiles)
        self.labelMaxProfiles: QLabel
        self.mPlotControlModel.setMaxProfilesWidget(self.sbMaxProfiles)

        # self.optionMaxNumberOfProfiles: MaxNumberOfProfilesWidgetAction = MaxNumberOfProfilesWidgetAction(None)
        # self.optionMaxNumberOfProfiles.sigMaxNumberOfProfilesChanged.connect(self.mPlotControlModel.setMaxProfiles)

        self.optionSpeclibSettings: SpeclibSettingsWidgetAction = SpeclibSettingsWidgetAction(None)
        self.optionSpeclibSettings.setDefaultWidget(self.optionSpeclibSettings.createWidget(None))

        self.optionCursorCrosshair: QAction
        self.optionCursorCrosshair.toggled.connect(self.plotWidget.setShowCrosshair)

        self.optionCursorPosition: QAction
        self.optionCursorPosition.toggled.connect(self.plotWidget.setShowCursorInfo)

        self.optionXUnit = SpectralProfilePlotXAxisUnitWidgetAction(self, self.mPlotControlModel.mXUnitModel)
        self.optionXUnit.setUnit(self.mPlotControlModel.xUnit())
        self.optionXUnit.setDefaultWidget(self.optionXUnit.createUnitComboBox())
        self.optionXUnit.sigUnitChanged.connect(self.mPlotControlModel.setXUnit)
        self.mPlotControlModel.sigXUnitChanged.connect(self.optionXUnit.setUnit)
        self.optionSpectralProfileWidgetStyle: SpectralProfileWidgetStyleAction = SpectralProfileWidgetStyleAction(None)
        self.optionSpectralProfileWidgetStyle.setDefaultWidget(self.optionSpectralProfileWidgetStyle.createWidget(None))
        self.optionSpectralProfileWidgetStyle.sigProfileWidgetStyleChanged.connect(self.setPlotWidgetStyle)

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

        # set the default style
        self.setPlotWidgetStyle(SpectralLibraryPlotWidgetStyle.dark())

    def setProject(self, project: QgsProject):
        self.plotWidget.setProject(project)
        self.plotControlModel().setProject(project)

    def setPlotWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        assert isinstance(style, SpectralLibraryPlotWidgetStyle)

        self.mPlotControlModel.setPlotWidgetStyle(style)

    def plotWidgetStyle(self) -> SpectralLibraryPlotWidgetStyle:
        return self.mPlotControlModel.plotWidgetStyle()

    def populateProfilePlotContextMenu(self, listWrapper: SignalObjectWrapper):
        itemList: list = listWrapper.wrapped_object
        # update current renderer
        self.optionSpectralProfileWidgetStyle.setResetStyle(self.optionSpectralProfileWidgetStyle.profileWidgetStyle())
        m1 = QMenu('Colors')
        m1.addAction(self.optionSpectralProfileWidgetStyle)

        # m2 = QMenu('Others')

        itemList.extend([m1])

    def plotControlModel(self) -> SpectralProfilePlotModel:
        return self.mPlotControlModel

    def updatePlot(self):
        self.mPlotControlModel.updatePlot()

    def readSettings(self):
        pass

    def writeSettings(self):
        pass

    def onVisSelectionChanged(self):

        rows = self.treeView.selectionModel().selectedRows()
        self.actionRemoveProfileVis.setEnabled(len(rows) > 0)

    def onSpeclibFieldsUpdated(self, *args):

        profilefields = profile_fields(self.speclib())
        to_remove = []
        to_add = []

        # remove visualizations for removed fields
        for vis in self.profileVisualizations():
            if not isinstance(vis.field(), QgsField) or vis.field().name() not in profilefields.names():
                to_remove.append(vis)

        self.mPlotControlModel.removeVisualizations(to_remove)

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

        if isinstance(layer, QgsRasterLayer):
            lvis = LayerBandVisualization(layer=layer)

            self.mPlotControlModel.insertPropertyGroup(0, lvis)

    def createProfileVisualization(self, *args,
                                   name: str = None,
                                   field: typing.Union[QgsField, int, str] = None,
                                   color: typing.Union[str, QColor] = None):
        item = ProfileVisualization()

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

            if item.fieldName() is None and len(existing_fields) > 0:
                item.setField(existing_fields[-1])

        if name is None:
            if isinstance(item.field(), QgsField):
                _name = f'Profiles "{item.field().name()}"'
            else:
                _name = 'Profiles'

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

        item.setPlotStyle(self.defaultStyle())

        if color is None:
            color = QColor(self.plotControlModel().mPlotWidgetStyle.foregroundColor)
            if False:
                if len(self.mPlotControlModel) > 0:
                    lastVis = self.mPlotControlModel[-1]
                    lastColor = lastVis.color()
                    color = nextColor(lastColor, mode='cat')

        item.setColor(color)

        self.mPlotControlModel.insertPropertyGroup(-1, item)

    def profileVisualizations(self) -> typing.List[ProfileVisualization]:
        return self.mPlotControlModel.visualizations()

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.sigDragEnterEvent.emit(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.sigDropEvent.emit(event)

    def defaultStyle(self) -> PlotStyle:

        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        style.setLineColor('white')
        style.setMarkerColor('white')
        style.setMarkerSymbol(None)
        # style.markerSymbol = MarkerSymbol.No_Symbol.value
        # style.markerPen.setColor(style.linePen.color())
        return style

    def removeSelectedPropertyGroups(self, *args):
        rows = self.treeView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows if isinstance(r.data(Qt.UserRole), PropertyItemGroup)]
        self.mPlotControlModel.removeVisualizations(to_remove)

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
