import collections
import datetime
import enum
import re
import sys
import textwrap
import typing
import warnings

import numpy as np
import sip
from PyQt5.QtCore import pyqtSignal, QTimer, QPointF, pyqtSlot, Qt, QModelIndex, QPoint, QObject, QAbstractTableModel, \
    QSortFilterProxyModel, QSize, QVariant
from PyQt5.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter
from PyQt5.QtWidgets import QWidgetAction, QWidget, QGridLayout, QSpinBox, QLabel, QFrame, QAction, QApplication, \
    QTableView, QComboBox, QMenu, QSlider, QStyledItemDelegate, QHBoxLayout
from qgis._core import QgsProcessingModelAlgorithm, QgsProcessingFeedback, QgsProcessingContext, QgsProject, QgsField, \
    QgsVectorLayer, QgsFieldModel, QgsFields, QgsFieldProxyModel, QgsSettings
from qgis._gui import QgsAttributeTableFilterModel, QgsDualView, QgsAttributeTableModel, QgsFieldExpressionWidget

from ...externals import pyqtgraph as pg
from ...externals.pyqtgraph import PlotDataItem, PlotWindow
from ...externals.pyqtgraph import AxisItem
from ...externals.pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu import ViewBoxMenu
from ...models import SettingsModel, SettingsTreeView
from ...plotstyling.plotstyling import PlotStyle, PlotStyleWidget, PlotStyleButton
from .. import speclibUiPath
from ..core.spectrallibrary import SpectralLibrary, SpectralProfileRenderer, spectralValueFields, DEBUG, \
    generateProfileKeys, containsSpeclib
from ..core.spectralprofile import SpectralProfileKey, SpectralProfile, SpectralProfileBlock
from ..processing import is_spectral_processing_model, SpectralProcessingProfiles, \
    SpectralProcessingProfilesOutput, SpectralProcessingModelList, NO_MODEL_MODEL
from ...unitmodel import BAND_INDEX, BAND_NUMBER, UnitConverterFunctionModel, XUnitModel, UnitModel
from ...utils import datetime64, UnitLookup, chunks, loadUi, SignalObjectWrapper


class SPDIFlags(enum.Flag):
    NoProfile = enum.auto()
    NotDisplayable = enum.auto()
    Displayable = enum.auto()


class XAxisWidgetAction(QWidgetAction):
    sigUnitChanged = pyqtSignal(str)

    def __init__(self, parent, unit_model: UnitModel = None, **kwds):
        super().__init__(parent)
        self.mUnitModel: XUnitModel
        if isinstance(unit_model, UnitModel):
            self.mUnitModel = unit_model
        else:
            self.mUnitModel = XUnitModel()
        self.mUnit: str = BAND_INDEX

    def unitModel(self) -> XUnitModel:
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
        l = QGridLayout()
        frame.setLayout(l)

        mCBXAxisUnit = self.createUnitComboBox()

        l.addWidget(QLabel('Unit'), 2, 0)
        l.addWidget(mCBXAxisUnit, 2, 1)
        l.setMargin(0)
        l.setSpacing(6)
        frame.setMinimumSize(l.sizeHint())
        return frame


class SpectralXAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(SpectralXAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(True)
        self.labelAngle = 0

        self.mUnit: str = ''

    def tickStrings(self, values, scale, spacing):

        if len(values) == 0:
            return []

        if self.mUnit == 'DateTime':

            values = datetime64(np.asarray(values)).astype('datetime64[D]')

            rng = max(values) - min(values)
            ndays = rng.astype(int)

            strns = []

            for v in values:
                if ndays == 0:
                    strns.append(v.astype(str))
                else:
                    strns.append(v.astype(str))

            return strns
        else:
            return super(SpectralXAxis, self).tickStrings(values, scale, spacing)

    def setUnit(self, unit: str, labelName: str = None):
        """
        Sets the unit of this axis
        :param unit: str
        :param labelName: str, defaults to unit
        """
        self.mUnit = unit

        if isinstance(labelName, str):
            self.setLabel(labelName)
        else:
            self.setLabel(unit)


class SpectralLibraryPlotItem(pg.PlotItem):
    sigPopulateContextMenuItems = pyqtSignal(SignalObjectWrapper)

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotItem, self).__init__(*args, **kwds)

    def getContextMenus(self, event):
        wrapper = SignalObjectWrapper([])
        self.sigPopulateContextMenuItems.emit(wrapper)
        return wrapper.wrapped_object

    def addItems(self, items: list, *args, **kargs):
        """
        Add a graphics item to the view box.
        If the item has plot data (PlotDataItem, PlotCurveItem, ScatterPlotItem), it may
        be included in analysis performed by the PlotItem.
        """
        if len(items) == 0:
            return

        self.items.extend(items)
        vbargs = {}
        if 'ignoreBounds' in kargs:
            vbargs['ignoreBounds'] = kargs['ignoreBounds']
        self.vb.addItems(items, *args, **vbargs)
        # name = None
        refItem = items[0]
        if hasattr(refItem, 'implements') and refItem.implements('plotData'):
            # name = item.name()
            self.dataItems.extend(items)
            # self.plotChanged()

            for item in items:
                self.itemMeta[item] = kargs.get('params', {})
            self.curves.extend(items)

        if isinstance(refItem, PlotDataItem):
            ## configure curve for this plot
            (alpha, auto) = self.alphaState()

            for item in items:
                item.setAlpha(alpha, auto)
                item.setFftMode(self.ctrl.fftCheck.isChecked())
                item.setDownsampling(*self.downsampleMode())
                item.setClipToView(self.clipToViewMode())
                item.setPointMode(self.pointMode())

            ## Hide older plots if needed
            self.updateDecimation()

            ## Add to average if needed
            self.updateParamList()
            if self.ctrl.averageGroup.isChecked() and 'skipAverage' not in kargs:
                self.addAvgCurve(item)

    def removeItems(self, items):
        """
        Remove an item from the internal ViewBox.
        """
        if len(items) == 0:
            return

        for item in items:
            self.items.remove(item)
            if item in self.dataItems:
                self.dataItems.remove(item)

            # self.vb.removeItem(item)
            """Remove an item from this view."""
            try:
                self.vb.addedItems.remove(item)
            except:
                pass
            scene = self.vb.scene()
            if scene is not None:
                scene.removeItem(item)
            item.setParentItem(None)

            if item in self.curves:
                self.curves.remove(item)

            if self.legend is not None:
                self.legend.removeItem(item)
        # self.updateDecimation()
        # self.updateParamList()


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
        self.mNProfiles = 64

    def createWidget(self, parent: QWidget):
        l = QGridLayout()
        sbMaxProfiles = QSpinBox()
        sbMaxProfiles.setToolTip('Maximum number of profiles to plot.')
        sbMaxProfiles.setRange(0, np.iinfo(np.int16).max)
        sbMaxProfiles.setValue(self.maxProfiles())
        self.sigMaxNumberOfProfilesChanged.connect(lambda n, sb=sbMaxProfiles: sb.setValue(n))
        sbMaxProfiles.valueChanged[int].connect(self.setMaxProfiles)

        l.addWidget(QLabel('Max. Profiles'), 0, 0)
        l.addWidget(sbMaxProfiles, 0, 1)
        frame = QFrame(parent)
        frame.setLayout(l)
        return frame

    def setMaxProfiles(self, n: int):
        assert isinstance(n, int) and n >= 0
        if n != self.mNProfiles:
            self.mNProfiles = n
            self.sigMaxNumberOfProfilesChanged.emit(n)

    def maxProfiles(self) -> int:
        return self.mNProfiles


class SpectralViewBox(pg.ViewBox):
    """
    Subclass of PyQgtGraph ViewBox

    """

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super().__init__(parent, enableMenu=True)

        # self.mCurrentCursorPosition: typing.Tuple[int, int] = (0, 0)
        # define actions

        # create menu
        # menu = SpectralViewBoxMenu(self)

        # widgetXAxis: QWidget = menu.widgetGroups[0]
        # widgetYAxis: QWidget = menu.widgetGroups[1]
        # cbXUnit = self.mActionXAxis.createUnitComboBox()
        # grid: QGridLayout = widgetXAxis.layout()
        # grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        # grid.addWidget(cbXUnit, 0, 2, 1, 2)

        # menuProfileRendering = menu.addMenu('Colors')
        # menuProfileRendering.addAction(self.mActionSpectralProfileRendering)

        # menuOtherSettings = menu.addMenu('Others')
        # menuOtherSettings.addAction(self.mActionMaxNumberOfProfiles)
        # menuOtherSettings.addAction(self.mActionShowSelectedProfilesOnly)
        # menuOtherSettings.addAction(self.mActionShowCrosshair)
        # menuOtherSettings.addAction(self.mActionShowCursorValues)

        # self.menu: SpectralViewBoxMenu = menu
        # self.state['enableMenu'] = True

    def addItems(self, pdis: list, ignoreBounds=False):
        """
        Add multiple QGraphicsItem to this view. The view will include this item when determining how to set its range
        automatically unless *ignoreBounds* is True.
        """
        for i, item in enumerate(pdis):
            if item.zValue() < self.zValue():
                item.setZValue(self.zValue() + 1 + i)

        scene = self.scene()
        if scene is not None and scene is not item.scene():
            for item in pdis:
                scene.addItem(item)  ## Necessary due to Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
                item.setParentItem(self.childGroup)
        if not ignoreBounds:
            self.addedItems.extend(pdis)
        # self.updateAutoRange()



MAX_PDIS_DEFAULT: int = 256


class SpectralProfilePlotDataItem(PlotDataItem):
    """
    A pyqtgraph.PlotDataItem to plot a SpectralProfile
    """
    sigProfileClicked = pyqtSignal(SpectralProfileKey, dict)

    def __init__(self, spectralProfile: SpectralProfile):
        assert isinstance(spectralProfile, SpectralProfile)
        super().__init__()

        # self.curve.sigClicked.connect(self.curveClicked)
        # self.scatter.sigClicked.connect(self.scatterClicked)
        self.mCurveMouseClickNativeFunc = self.curve.mouseClickEvent
        self.curve.mouseClickEvent = self.onCurveMouseClickEvent
        self.scatter.sigClicked.connect(self.onScatterMouseClicked)

        # self.mValueConversionIsPossible: bool = True
        # self.mSpectralModel: typing.List[SpectralAlgorithm] = []
        # self.mXValueConversionFunction = lambda v, *args: v
        # self.mYValueConversionFunction = lambda v, *args: v
        self.mSortByXValues: bool = False
        self.mProfileSource = None
        self.mProfile: SpectralProfile = None
        self.mDataX = None
        self.mDataY = None
        if isinstance(spectralProfile, SpectralProfile):
            self.setSpectralProfile(spectralProfile)

    def valueConversionPossible(self) -> bool:
        warnings.warn('Deprecated', DeprecationWarning)
        return self.mValueConversionIsPossible

    def profileSource(self):
        return self.mProfileSource

    def setProfileSource(self, source: typing.Any):
        self.mProfileSource = source

    def onCurveMouseClickEvent(self, ev):
        self.mCurveMouseClickNativeFunc(ev)

        if ev.accepted:
            idx, x, y, pxDistance = self.closestDataPoint(ev.pos())
            data = {'idx': idx,
                    'xValue': x,
                    'yValue': y,
                    'pxDistance': pxDistance,
                    'pdi': self}
            self.sigProfileClicked.emit(self.key(), data)

    def onScatterMouseClicked(self, pts: pg.ScatterPlotItem):

        if isinstance(pts, pg.ScatterPlotItem):
            pdi = pts.parentItem()
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pt = pts.ptsClicked[0]
                i = pt.index()
                data = {'idx': i,
                        'xValue': pdi.xData[i],
                        'yValue': pdi.yData[i],
                        'pxDistance': 0,
                        'pdi': self}
                self.sigProfileClicked.emit(self.key(), data)

    def setSpectralProfile(self, spectralProfile: SpectralProfile):
        """
        Sets the internal SpectralProfile instance.
        Resets the visualization status to SPDIFlags.NoProfile
        :param spectralProfile: SpectralProfile
        """
        assert isinstance(spectralProfile, SpectralProfile)
        self.mProfile = spectralProfile
        self.mDataX = None
        self.mDataY = None

    def visualizationFlags(self) -> SPDIFlags:
        if not isinstance(self.mProfile, SpectralProfile):
            return SPDIFlags.NoProfile
        if self.mDataX is None or self.mDataY is None:
            return SPDIFlags.NotDisplayable
        return SPDIFlags.Displayable

    def spectralProfile(self) -> SpectralProfile:
        """
        Returns the SpectralProfile
        :return: SpectralProfile
        """
        return self.mProfile

    def applySpectralModel(self) -> bool:
        warnings.warn('Update from outside', DeprecationWarning)
        block = SpectralProfileBlock.fromSpectralProfile(self.spectralProfile())
        self.mSpectralModel
        # todo: apply model to profile data
        return
        result = SpectralAlgorithm.applyFunctionStack(self.mSpectralModel, self.spectralProfile())
        if not isinstance(result, SpectralMathResult):
            self.setVisible(False)
            return False

        x, y, x_unit, y_unit = result

        # handle failed removal of NaN
        # see https://github.com/pyqtgraph/pyqtgraph/issues/1057

        # 1. convert to numpy arrays
        if not isinstance(y, np.ndarray):
            y = np.asarray(y, dtype=float)
        if not isinstance(x, np.ndarray):
            x = np.asarray(x)

        if self.mSortByXValues:
            idx = np.argsort(x)
            x = x[idx]
            y = y[idx]

        is_finite = np.isfinite(y)
        connected = np.logical_and(is_finite, np.roll(is_finite, -1))
        keep = is_finite + connected
        # y[np.logical_not(is_finite)] = np.nanmin(y)
        y = y[keep]
        x = x[keep]
        connected = connected[keep]

        # convert date units to float with decimal year and second precision
        if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
            x = convertDateUnit(datetime64(x), 'DecimalYear')

        if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
            y = convertDateUnit(datetime64(y), 'DecimalYear')

        self.setData(x=x, y=y, connect=connected)
        self.setVisible(True)
        return True

    def DEPR_applyMapFunctions(self) -> bool:
        warnings.warn('Use applySpectralMath', DeprecationWarning)
        return
        """
        Applies the two functions defined with `.setMapFunctionX` and `.setMapFunctionY` and updates the plotted values.
        :return: bool, True in case of success
        """
        success = False
        if len(self.mInitialDataX) > 0 and len(self.mInitialDataY) > 0:
            x = None
            y = None

            try:
                x = self.mXValueConversionFunction(self.mInitialDataX, self)
                y = self.mYValueConversionFunction(self.mInitialDataY, self)
                if isinstance(x, (list, np.ndarray)) and \
                        isinstance(y, (list, np.ndarray)) and len(x) > 0 and len(
                    y) > 0:
                    success = True

            except Exception as ex:
                print(ex)
                pass

        self.mValueConversionIsPossible = success
        if success:
            if True:
                # handle failed removal of NaN
                # see https://github.com/pyqtgraph/pyqtgraph/issues/1057

                # 1. convert to numpy arrays
                if not isinstance(y, np.ndarray):
                    y = np.asarray(y, dtype=float)
                if not isinstance(x, np.ndarray):
                    x = np.asarray(x)

                if self.mSortByXValues:
                    idx = np.argsort(x)
                    x = x[idx]
                    y = y[idx]

                is_finite = np.isfinite(y)
                connected = np.logical_and(is_finite, np.roll(is_finite, -1))
                keep = is_finite + connected
                # y[np.logical_not(is_finite)] = np.nanmin(y)
                y = y[keep]
                x = x[keep]
                connected = connected[keep]

                # convert date units to float with decimal year and second precision
                if isinstance(x[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                    x = convertDateUnit(datetime64(x), 'DecimalYear')

                if isinstance(y[0], (datetime.datetime, datetime.date, datetime.time, np.datetime64)):
                    y = convertDateUnit(datetime64(y), 'DecimalYear')

                self.setData(x=x, y=y, connect=connected)
            else:
                self.setData(x=x, y=y, connect='finite')

            self.setVisible(True)
        else:
            # self.setData(x=[], y=[])
            self.setVisible(False)

        return success

    def closestDataPoint(self, pos) -> typing.Tuple[int, float, float, float]:
        x = pos.x()
        y = pos.y()
        pw = self.pixelWidth()
        ph = self.pixelHeight()
        pts = []
        dataX, dataY = self.getData()
        distX = np.abs(dataX - x) / pw
        distY = np.abs(dataY - y) / ph

        dist = np.sqrt(distX ** 2 + distY ** 2)
        idx = np.nanargmin(dist)
        return idx, dataX[idx], dataY[idx], dist[idx]

    def plot(self) -> PlotWindow:
        """
        Opens a PlotWindow and plots this SpectralProfilePlotDataItem to
        :return:
        :rtype:
        """
        pw = pg.plot(title=self.name())
        pw.getPlotItem().addItem(self)
        return pw

    def updateItems(self, *args, **kwds):
        if not self.signalsBlocked():
            super().updateItems(*args, **kwds)
        else:
            s = ""

    def viewRangeChanged(self, *args, **kwds):
        if not self.signalsBlocked():
            super().viewRangeChanged()
        else:
            s = ""

    def key(self) -> SpectralProfileKey:
        return self.mProfile.key()

    def id(self) -> int:
        warnings.warn('Use key instead', DeprecationWarning)
        """
        Returns the profile fid
        :return: int
        """
        return self.mProfile.id()

    def name(self) -> str:
        """
        Returns the profile name
        :return:
        :rtype:
        """
        return self.mProfile.name()

    def setClickable(self, b: bool, width=None):
        """
        :param b:
        :param width:
        :return:
        """
        assert isinstance(b, bool)
        self.curve.setClickable(b, width=width)

    def raiseContextMenu(self, ev):
        menu = self.contextMenu()

        # Let the scene add on to the end of our context menu
        # (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, ev)

        pos = ev.screenPos()
        menu.popup(QPoint(pos.x(), pos.y()))
        return True

    # This method will be called when this item's _children_ want to raise
    # a context menu that includes their parents' menus.
    def contextMenu(self, event=None):

        self.menu = QMenu()
        self.menu.setTitle(self.name + " options..")

        green = QAction("Turn green", self.menu)
        green.triggered.connect(self.setGreen)
        self.menu.addAction(green)
        self.menu.green = green

        blue = QAction("Turn blue", self.menu)
        blue.triggered.connect(self.setBlue)
        self.menu.addAction(blue)
        self.menu.green = blue

        alpha = QWidgetAction(self.menu)
        alphaSlider = QSlider()
        alphaSlider.setOrientation(Qt.Horizontal)
        alphaSlider.setMaximum(255)
        alphaSlider.setValue(255)
        alphaSlider.valueChanged.connect(self.setAlpha)
        alpha.setDefaultWidget(alphaSlider)
        self.menu.addAction(alpha)
        self.menu.alpha = alpha
        self.menu.alphaSlider = alphaSlider
        return self.menu


class SpectralProfilePlotWidget(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    sigPopulateContextMenuItems = pyqtSignal(SignalObjectWrapper)

    def __init__(self, parent=None):

        mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=mViewBox
        )
        plotItem.sigPopulateContextMenuItems.connect(self.populateContextMenu)
        super().__init__(parent, plotItem=plotItem)
        pi: SpectralLibraryPlotItem = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem) and pi == self.plotItem

        self.mCurrentMousePosition: QPointF = None
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoScatterPoint = pg.ScatterPlotItem()
        self.mInfoScatterPoint.sigClicked.connect(self.onInfoScatterClicked)
        self.mInfoScatterPoint.setZValue(9999999)
        self.mInfoScatterPoint.setBrush(QColor('red'))

        self.mInfoScatterPointHtml: str = ""

        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)
        pi.addItem(self.mInfoScatterPoint)
        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)
        # self.proxy2D2 = pg.SignalProxy(self.scene().sigMouseClicked, rateLimit=100, slot=self.onMouseClicked)

        # set default axis unit
        # self.updateXUnit()
        # self.setYLabel('Y (Spectral Value)')

        # self.actionXAxis().sigUnitChanged.connect(self.updateXUnit)

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.setInterval(500)
        self.mUpdateTimer.setSingleShot(False)
        # self.mUpdateTimer.timeout.connect(self.updatePlot)
        # self.mUpdateTimer.start()

        # self.actionSpectralProfileRendering().sigProfileRendererChanged.connect(self.setProfileRenderer)
        # self.actionProfileSettings().sigMaxNumberOfProfilesChanged.connect(self.updatePlot)

        # define common plot options and settings

        self.mOptionShowCursorPosition = QAction('Show Cursor Position')
        self.mOptionShowCursorPosition.setToolTip('Activate to show the values related to the cursor position.')
        self.mOptionShowCrosshair = QAction('Show Crosshair')
        self.mOptionShowCrosshair.setToolTip('Activate to show a crosshair')

        for o in [self.mOptionShowCursorPosition, self.mOptionShowCrosshair]:
            o.setIconVisibleInMenu(True)
            o.setCheckable(True)
            o.setChecked(True)

        self.mOptionXUnit = XAxisWidgetAction(self)
        widgetXAxis: QWidget = self.viewBox().menu.widgetGroups[0]
        widgetYAxis: QWidget = self.viewBox().menu.widgetGroups[1]
        cbXUnit = self.mOptionXUnit.createUnitComboBox()
        grid: QGridLayout = widgetXAxis.layout()
        grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        grid.addWidget(cbXUnit, 0, 2, 1, 2)

        self.mActionSpectralProfileRendering: SpectralProfileRendererWidgetAction \
            = SpectralProfileRendererWidgetAction(None)
        self.mActionSpectralProfileRendering.setDefaultWidget(
            self.mActionSpectralProfileRendering.createWidget(None))
        self.mActionSpectralProfileRendering.sigProfileRendererChanged.connect(self.setRenderStyle)

        self.mOptionUseVectorSymbology: QAction = \
            self.mActionSpectralProfileRendering.defaultWidget().optionUseColorsFromVectorRenderer
        self.mOptionUseVectorSymbology.setChecked(True)

        self.mContextMenuItems: list = []
        self.mMenuColors = QMenu('Colors')
        self.mMenuColors.addAction(self.mActionSpectralProfileRendering)

        self.mMenuOthers = QMenu('Others')
        # self.mMenuOthers.setVisible(True)
        self.mMenuOthers.addAction(self.mOptionShowCursorPosition)
        self.mMenuOthers.addAction(self.mOptionShowCrosshair)

        self.mContextMenuItems.extend([self.mMenuColors, self.mMenuOthers])

    def setRenderStyle(self, profile_renderer: SpectralProfileRenderer):

        s = ""

    def populateContextMenu(self, listWrapper: SignalObjectWrapper):
        itemList: list = listWrapper.wrapped_object
        # update current renderer
        self.mActionSpectralProfileRendering.setResetRenderer(self.mActionSpectralProfileRendering.profileRenderer())

        itemList.extend(self.mContextMenuItems)

    def xAxis(self) -> SpectralXAxis:
        return self.plotItem.getAxis('bottom')

    def yAxis(self) -> AxisItem:
        return self.plotItem.getAxis('left')

    def viewBox(self) -> SpectralViewBox:
        return self.plotItem.getViewBox()

    def updatePositionInfo(self):
        x, y = self.mCurrentMousePosition.x(), self.mCurrentMousePosition.y()
        positionInfoHtml = '<html><body>'
        if self.xAxis().mUnit == 'DateTime':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(datetime64(x), y)
        elif self.xAxis().mUnit == 'DOY':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(int(x), y)
        else:
            positionInfoHtml += 'x:{:0.5f}\ny:{:0.5f}'.format(x, y)

        positionInfoHtml += '<br/>' + self.mInfoScatterPointHtml
        positionInfoHtml += '</body></html>'
        self.mInfoLabelCursor.setHtml(positionInfoHtml)

    def onInfoScatterClicked(self, a, b):
        self.mInfoScatterPoint.setVisible(False)
        self.mInfoScatterPointHtml = ""

    def onMouseClicked(self, event):
        # print(event[0].accepted)
        s = ""

    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, SpectralLibraryPlotItem)
        vb = plotItem.vb
        assert isinstance(vb, SpectralViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            self.mCurrentMousePosition = mousePoint

            nearest_item = None
            nearest_index = -1
            nearest_distance = sys.float_info.max
            sx, sy = self.mInfoScatterPoint.getData()

            self.updatePositionInfo()

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(self.mOptionShowCursorPosition.isChecked())
            self.mInfoLabelCursor.setPos(pos)

            b = self.mOptionShowCrosshair.isChecked()
            self.mCrosshairLineH.setVisible(b)
            self.mCrosshairLineV.setVisible(b)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            vb.setToolTip('')
            self.mCrosshairLineH.setVisible(False)
            self.mCrosshairLineV.setVisible(False)
            self.mInfoLabelCursor.setVisible(False)


class SpectralProfilePlotWidget_OLD(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    def __init__(self, parent=None):

        mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=mViewBox
        )

        super().__init__(parent, plotItem=plotItem)

        self.mSelectedIds = set()
        self.mXAxisUnitInitialized: bool = False
        self.mViewBox: SpectralViewBox = mViewBox
        self.setMaxProfiles(MAX_PDIS_DEFAULT)
        self.mDualView = None

        self.mNumberOfValueErrorsProfiles: int = 0
        self.mNumberOfEmptyProfiles: int = 0

        self.mMaxInfoLength: int = 30

        # self.centralWidget.setParent(None)
        # self.centralWidget = None
        self.setCentralWidget(plotItem)

        self.plotItem: SpectralLibraryPlotItem
        self.plotItem.sigRangeChanged.connect(self.viewRangeChanged)

        pi = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem) and pi == plotItem and pi == self.plotItem
        self.mXAxis: SpectralXAxis = pi.getAxis('bottom')
        assert isinstance(self.mXAxis, SpectralXAxis)

        self.mSpeclib: SpectralLibrary = None
        self.mSpeclibSignalConnections = []

        self.mXUnitInitialized = False
        self.setXUnit(BAND_NUMBER)

        # describe functions to convert wavelength units from unit a to unit b
        self.mUnitConverter = UnitConverterFunctionModel()
        from ..processingalgorithms import SpectralXUnitConversion
        self.mUnitConverterAlg = SpectralXUnitConversion()
        self.mUnitConverterAlg.initAlgorithm({})

        # self.mXUnitMathFunc = XUnitConversion(self.xUnit())

        self.mSpectralModel: QgsProcessingModelAlgorithm = None

        self.mSPDICache: typing.Dict[SpectralProfileKey, SpectralProfilePlotDataItem] = dict()
        self.mPlotOverlayItems = []
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoScatterPoint = pg.ScatterPlotItem()
        self.mInfoScatterPoint.sigClicked.connect(self.onInfoScatterClicked)
        self.mInfoScatterPoint.setZValue(9999999)
        self.mInfoScatterPoint.setBrush(QColor('red'))

        self.mInfoScatterPointHtml: str = ""

        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)
        pi.addItem(self.mInfoScatterPoint)
        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)
        # self.proxy2D2 = pg.SignalProxy(self.scene().sigMouseClicked, rateLimit=100, slot=self.onMouseClicked)

        # set default axis unit
        self.updateXUnit()
        self.setYLabel('Y (Spectral Value)')

        self.actionXAxis().sigUnitChanged.connect(self.updateXUnit)
        self.mSPECIFIC_PROFILE_STYLES: typing.Dict[SpectralProfileKey, PlotStyle] = dict()
        self.mTEMPORARY_PROFILES: typing.Set[SpectralProfileKey] = set()
        self.mDefaultProfileRenderer: SpectralProfileRenderer
        self.mDefaultProfileRenderer = SpectralProfileRenderer.default()

        self.mUpdateTimer = QTimer()
        self.mUpdateTimer.setInterval(500)
        self.mUpdateTimer.setSingleShot(False)
        self.mUpdateTimer.timeout.connect(self.updatePlot)
        self.mUpdateTimer.start()

        self.actionSpectralProfileRendering().sigProfileRendererChanged.connect(self.setProfileRenderer)
        self.actionProfileSettings().sigMaxNumberOfProfilesChanged.connect(self.updatePlot)

        self.setProfileRenderer(self.mDefaultProfileRenderer)
        self.setAcceptDrops(True)

    def temporaryProfileKeys(self) -> typing.List[SpectralProfileKey]:
        return sorted(self.mTEMPORARY_PROFILES)

    def temporaryProfileIds(self) -> typing.List[int]:
        return sorted(set([k.fid for k in self.temporaryProfileKeys()]))

    def currentProfiles(self) -> typing.List[SpectralProfile]:
        keys = self.temporaryProfileKeys()
        return list(self.speclib().profiles(profile_keys=keys))

    def onInfoScatterClicked(self, a, b):
        self.mInfoScatterPoint.setVisible(False)
        self.mInfoScatterPointHtml = ""

    def setUpdateInterval(self, msec: int):
        """
        Sets the update interval
        :param msec:
        :type msec:
        :return:
        :rtype:
        """
        self.mUpdateTimer.setInterval(msec)

    def closeEvent(self, *args, **kwds):
        """
        Stop the time to avoid calls on freed / deleted C++ object references
        """
        self.mUpdateTimer.stop()
        super(SpectralProfilePlotWidget, self).closeEvent(*args, **kwds)

    def viewBox(self) -> SpectralViewBox:
        return self.mViewBox

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        """Sets and applies the SpectralProfileRenderer"""
        assert isinstance(profileRenderer, SpectralProfileRenderer)
        if isinstance(self.speclib(), SpectralLibrary):
            profileRenderer = profileRenderer.clone()
            profileRenderer.setInput(self.speclib())
            self.speclib().setProfileRenderer(profileRenderer)

            self.actionSpectralProfileRendering().setProfileRenderer(profileRenderer)

    def updatePlot(self, *args):

        try:
            dv = self.dualView()
            if isinstance(dv, QgsDualView) and dv.tableView().verticalScrollBar().underMouse():
                return

            self.mUpdateTimer.stop()
            # t0 = datetime.datetime.now()
            self.updatePlotDataItems()
            # print(f'Plot update: {datetime.datetime.now() - t0}')
            self.mUpdateTimer.start()
        except RuntimeError as ex:
            print(ex, file=sys.stderr)
            self.mUpdateTimer.start()

    def leaveEvent(self, ev):
        super(SpectralProfilePlotWidget, self).leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def enterEvent(self, ev):
        super(SpectralProfilePlotWidget, self).enterEvent(ev)

    def foregroundInfoColor(self) -> QColor:
        return self.plotItem.axes['bottom']['item'].pen().color()

    def hoverEvent(self, ev):
        if ev.enter:
            self.mouseHovering = True
        if ev.exit:
            self.mouseHovering = False

    def updatePositionInfo(self):
        x, y = self.viewBox().mCurrentCursorPosition
        positionInfoHtml = '<html><body>'
        if self.mXAxis.mUnit == 'DateTime':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(datetime64(x), y)
        elif self.mXAxis.mUnit == 'DOY':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(int(x), y)
        else:
            positionInfoHtml += 'x:{:0.5f}\ny:{:0.5f}'.format(x, y)

        positionInfoHtml += '<br/>' + self.mInfoScatterPointHtml
        positionInfoHtml += '</body></html>'
        self.mInfoLabelCursor.setHtml(positionInfoHtml)

    def onMouseClicked(self, event):
        # print(event[0].accepted)
        s = ""

    def onMouseMoved2D(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, SpectralLibraryPlotItem)
        vb = plotItem.vb
        assert isinstance(vb, SpectralViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()

            vb.updateCurrentPosition(x, y)

            nearest_item = None
            nearest_index = -1
            nearest_distance = sys.float_info.max
            sx, sy = self.mInfoScatterPoint.getData()

            self.updatePositionInfo()

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(self.actionShowCursorValues().isChecked())
            self.mInfoLabelCursor.setPos(pos)

            b = self.actionShowCrosshair().isChecked()
            self.mCrosshairLineH.setVisible(b)
            self.mCrosshairLineV.setVisible(b)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            vb.setToolTip('')
            self.mCrosshairLineH.setVisible(False)
            self.mCrosshairLineV.setVisible(False)
            self.mInfoLabelCursor.setVisible(False)

    def actionSpectralProfileRendering(self):
        return self.viewBox().mActionSpectralProfileRendering

    def optionUseVectorSymbology(self) -> QAction:
        return self.viewBox().mOptionUseVectorSymbology

    def actionProfileSettings(self) -> MaxNumberOfProfilesWidgetAction:
        return self.viewBox().mActionMaxNumberOfProfiles

    def actionXAxis(self) -> XAxisWidgetAction:
        return self.viewBox().mActionXAxis

    def actionShowCursorValues(self) -> QAction:
        return self.viewBox().mActionShowCursorValues

    def actionShowCrosshair(self) -> QAction:
        return self.viewBox().mActionShowCrosshair

    def actionShowSelectedProfilesOnly(self) -> QAction:
        return self.viewBox().mActionShowSelectedProfilesOnly

    def setPlotOverlayItems(self, items):
        """
        Adds a list of PlotItems to be overlayed
        :param items:
        :return:
        """
        if not isinstance(items, list):
            items = [items]
        assert isinstance(items, list)

        for item in items:
            assert isinstance(item, PlotDataItem)

        toRemove = self.mPlotOverlayItems[:]
        for item in toRemove:
            if item in self.plotItem.items:
                item
                self.plotItem.removeItem(item)

        self.mPlotOverlayItems.clear()
        self.mPlotOverlayItems.extend(items)
        for item in items:
            self.plotItem.addItem(item)

        if not self.mXUnitInitialized:

            xUnit = None
            for item in self.mPlotOverlayItems:
                if isinstance(item, SpectralProfilePlotDataItem):
                    if item.mInitialUnitX != self.mXUnit:
                        xUnit = item.mInitialUnitX
                        break

            if xUnit is not None:
                self.setXUnit(xUnit)
                self.mXUnitInitialized = True

    def plottedProfilePlotDataItems(self, flags: SPDIFlags = None) -> typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItems
        """
        items = [i for i in self.getPlotItem().items if isinstance(i, SpectralProfilePlotDataItem)]
        if flags is None:
            return items
        else:
            return [i for i in items if bool(i.visualizationFlags() | flags)]

    def cachedProfilePlotDataItems(self, flags: SPDIFlags = None) -> typing.List[SpectralProfilePlotDataItem]:
        items = [i for i in self.mSPDICache.values() if isinstance(i, SpectralProfilePlotDataItem)]
        if flags is None:
            return items
        else:
            return [i for i in items if bool(i.visualizationFlags() | flags)]

    def cachedProfileKeys(self, flags: SPDIFlags = None) -> typing.Set[SpectralProfileKey]:
        return set([i.key() for i in self.cachedProfilePlotDataItems(flags=flags)])

    def removeSPDIs(self, keys_to_remove: typing.List[SpectralProfileKey], updateScene: bool = True):
        """
        :param updateScene:
        :param keys_to_remove: feature ids to remove
        :type keys_to_remove:
        :return:
        :rtype:
        """
        if len(keys_to_remove) == 0:
            return

        def disconnect(sig, slot):
            while True:
                try:
                    r = sig.disconnect(slot)
                    s = ""
                except:
                    break

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, pg.PlotItem)
        plotted = [pdi for pdi in self.plottedProfilePlotDataItems() if pdi.key() in keys_to_remove]
        pdis_to_remove: typing.List[SpectralProfilePlotDataItem] = []
        for k in keys_to_remove:
            pdi = self.mSPDICache.get(k, None)
            if isinstance(pdi, SpectralProfilePlotDataItem):
                del self.mSPDICache[k]
                pdi.setClickable(False)
                disconnect(pdi, self.onProfileClicked)
                if pdi in plotted:
                    pdis_to_remove.append(pdi)

        if len(pdis_to_remove) > 0:
            pi = self.getPlotItem()
            pi.removeItems(pdis_to_remove)
            if updateScene:
                self.scene().update()

    def resetProfileStyles(self):
        """
        Resets the profile colors
        """
        self.profileRenderer().reset()

    def setProfileStyles(self,
                         style: PlotStyle,
                         fids: typing.List[int]):
        """
        Sets the style of single features
        :param style:
        :type style:
        """
        updatedFIDs = self.profileRenderer().setProfilePlotStyle(style, fids)
        self.updatePlotDataItemStyles(updatedFIDs)

    def setMaxProfiles(self, n: int):
        """
        Sets the maximum number of profiles to be displayed at the same time
        :param n: maximum number of profiles visualized
        :type n: int
        """
        self.actionProfileSettings().setMaxProfiles(n)

    def maxProfiles(self) -> int:
        return self.actionProfileSettings().maxProfiles()

    def setSpeclib(self, speclib: SpectralLibrary):
        """
        Sets the SpectralLibrary to be visualized
        :param speclib: SpectralLibrary
        """
        if isinstance(speclib, SpectralLibrary) and speclib == self.speclib():
            return
        self.mUpdateTimer.stop()

        # remove old spectra
        self.removeSPDIs(list(self.mSPDICache.keys()))
        self.disconnectSpeclibSignals()
        self.mSpeclib = None

        if isinstance(speclib, SpectralLibrary):
            self.mSpeclib = speclib
            self.connectSpeclibSignals()
            self.onProfileRendererChanged()

        self.mUpdateTimer.start()

    def setDualView(self, dualView: QgsDualView):
        assert isinstance(dualView, QgsDualView)
        speclib = dualView.masterModel().layer()
        assert isinstance(speclib, SpectralLibrary)
        self.mDualView = dualView
        self.mDualView.tableView().selectionModel().selectionChanged.connect(self.onCellCelectionChanged)
        if self.speclib() != speclib:
            self.setSpeclib(speclib)

    def dualView(self) -> QgsDualView:
        return self.mDualView

    def connectSpeclibSignals(self):
        """

        """
        if isinstance(self.mSpeclib, SpectralLibrary):
            self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
            self.mSpeclib.committedAttributeValuesChanges.connect(self.onCommittedAttributeValuesChanges)
            self.mSpeclib.rendererChanged.connect(self.onProfileRendererChanged)
            self.mSpeclib.sigProfileRendererChanged.connect(self.onProfileRendererChanged)
            self.setProfileRenderer(self.mSpeclib.profileRenderer())
            # additional security to disconnect
            self.mSpeclib.willBeDeleted.connect(self.onWillBeDeleted)

    def onWillBeDeleted(self):
        self.setSpeclib(None)

    def disconnectSpeclibSignals(self):
        """
        Savely disconnects all signals from the linked SpectralLibrary
        """
        if isinstance(self.mSpeclib, SpectralLibrary) and not sip.isdeleted(self.mSpeclib):
            def disconnect(sig, slot):
                while True:
                    try:
                        r = sig.disconnect(slot)
                        s = ""
                    except:
                        break

            disconnect(self.mSpeclib.featureAdded, self.onProfilesAdded)
            disconnect(self.mSpeclib.featuresDeleted, self.onProfilesRemoved)
            disconnect(self.mSpeclib.selectionChanged, self.onSelectionChanged)
            disconnect(self.mSpeclib.committedAttributeValuesChanges, self.onCommittedAttributeValuesChanges)
            disconnect(self.mSpeclib.rendererChanged, self.onProfileRendererChanged)
            disconnect(self.mSpeclib.sigProfileRendererChanged, self.onProfileRendererChanged)
            disconnect(self.mSpeclib.willBeDeleted, self.onWillBeDeleted)

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary this widget is linked to.
        :return: SpectralLibrary
        """
        return self.mSpeclib

    def onCommittedAttributeValuesChanges(self, layerID, featureMap):
        """
        Reacts on changes in spectral values
        """
        s = ""

        if layerID != self.speclib().id():
            return
        speclib: SpectralLibrary = self.speclib()
        PROFILE_FIELDS = {speclib.fields().indexOf(f.name()): f.name() for f in spectralValueFields(speclib)}

        # maybee better to simply update generally all profiles of an ID?
        for fid, fieldMap in featureMap.items():
            for field_num, field_name in PROFILE_FIELDS.items():
                if field_num in fieldMap.keys():
                    # remove these keys from SPDI cache, so that they need to be reloaded from the Speclib
                    # during next scheduled update
                    key = SpectralProfileKey(fid, field_name)
                    if key in self.mSPDICache.keys():
                        del self.mSPDICache[key]

    @pyqtSlot()
    def onProfileRendererChanged(self):
        """
        Updates all SpectralProfilePlotDataItems
        """
        profileRenderer: SpectralProfileRenderer = self.profileRenderer()
        self.actionSpectralProfileRendering().setProfileRenderer(profileRenderer)
        # set Background color
        self.setBackground(profileRenderer.backgroundColor)

        # set Foreground color
        for axis in self.plotItem.axes.values():
            ai: pg.AxisItem = axis['item']
            if isinstance(ai, pg.AxisItem):
                ai.setPen(profileRenderer.foregroundColor)
                ai.setTextPen(profileRenderer.foregroundColor)

                # set info color
                self.mInfoLabelCursor.setColor(profileRenderer.infoColor)
                self.mCrosshairLineH.pen.setColor(profileRenderer.infoColor)
                self.mCrosshairLineV.pen.setColor(profileRenderer.infoColor)

        # set Info Color
        self.mInfoLabelCursor.setColor(profileRenderer.infoColor)
        self.mCrosshairLineH.pen.setColor(profileRenderer.infoColor)
        self.mCrosshairLineV.pen.setColor(profileRenderer.infoColor)

        self.updatePlotDataItemStyles()

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.speclib().profileRenderer()

    def onSelectionChanged(self, selected, deselected, clearAndSelect):

        # fidsBefore = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

        self.updatePlotDataItems()

        # fidsAfter = [pdi.id() for pdi in self.allSpectralProfilePlotDataItems()]

    def onCellCelectionChanged(self, *args):
        s = ""

    """
    def syncLibrary(self):
        s = ""
        # see https://groups.google.com/forum/#!topic/pyqtgraph/kz4U6dswEKg
        # speed problems in case of too many line items
        #profiles = list(self.speclib().profiles())
        self.disableAutoRange()
        self.blockSignals(True)
        self.setViewportUpdateMode(QGraphicsView.NoViewportUpdate)

        self.updateSpectralProfilePlotItems()
        self.updateProfileStyles()
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.blockSignals(False)
        self.enableAutoRange()
        self.viewport().update()
    """

    def unitConversionFunction(self, unitSrc, unitDst):
        """
        Returns a function to convert a numeric value from unitSrc to unitDst.
        :param unitSrc: str, e.g. `micrometers` or `um` (case insensitive)
        :param unitDst: str, e.g. `nanometers` or `nm` (case insensitive)
        :return: callable, a function of pattern `mappedValues = func(value:list, pdi:SpectralProfilePlotDataItem)`
        """

        return self.mUnitConverter.convertFunction(unitSrc, unitDst)

    def setXUnit(self, unit: str):
        """
        Sets the unit or mapping function to be shown on x-axis.
        :param unit: str, e.g. `nanometers`
        """
        # unit = UnitLookup.baseUnit(unit)
        self.actionXAxis().setUnit(unit)

    def xUnit(self) -> str:
        """
        Returns the unit to be shown on x-axis
        :return: str
        """
        return self.actionXAxis().unit()

    def xAxisUnitModel(self) -> XUnitModel:
        return self.actionXAxis().unitModel()

    def allPlotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns all PlotDataItems (not only SpectralProfilePlotDataItems)
        :return: [list-of-PlotDataItems]
        """
        return list(self.mSPDICache.values()) + self.mPlotOverlayItems

    def allSpectralProfilePlotDataItems(self) -> typing.List[SpectralProfilePlotDataItem]:
        """
        Returns all SpectralProfilePlotDataItem, including those used as temporary overlays.
        :return: [list-of-SpectralProfilePlotDataItem]
        """
        return [pdi for pdi in self.allPlotDataItems() if isinstance(pdi, SpectralProfilePlotDataItem)]

    def updateXUnit(self):

        unit = self.xUnit()
        label = self.xAxisUnitModel().unitData(unit, role=Qt.DisplayRole)

        # update axis label
        if unit in UnitLookup.metric_units():
            label = 'Wavelength [{}]'.format(unit)
        elif unit in UnitLookup.time_units():
            label = 'Time [{}]'.format(unit)

        elif unit in UnitLookup.date_units():
            if unit == 'DateTime':
                label = 'Date'
            else:
                label = 'Date [{}]'.format(unit)

        self.mXAxis.setUnit(unit, label)
        # self.mUnitConverterAlg
        # self.mXUnitMathFunc.setTargetUnit(unit)
        # update x values
        self.updatePlotDataItemValues()

    def updatePlotDataItemValues(self, pdis: typing.List[SpectralProfilePlotDataItem] = None) \
            -> typing.List[SpectralProfilePlotDataItem]:
        """
        Updates values to be displayed, including x-unit conversions and further SpectralProcessingModels.
        :param pdis: list of SpectralProfilePlotDataItems
        """

        DTIME = collections.OrderedDict()
        DTIME[0] = (datetime.datetime.now(), 'start')

        def measure(step: str):
            nonlocal DTIME
            k = max(DTIME.keys()) + 1
            DTIME[k] = (datetime.datetime.now(), step)

        if pdis is None:
            pdis = self.allSpectralProfilePlotDataItems()

        assert isinstance(pdis, list)
        if len(pdis) == 0:
            return

        LUT: typing.Dict[SpectralProfileKey, SpectralProfilePlotDataItem] = {pdi.key(): pdi for pdi in pdis}

        measure('until blocks 0')
        plot_pdis = self.plottedProfilePlotDataItems()
        measure('plot_dis')
        pi: SpectralLibraryPlotItem = self.getPlotItem()
        pi.removeItems(plot_pdis)
        measure('removeItems')
        for pdi in LUT.values():
            # set visualization vectors to none
            pdi.mDataX = pdi.mDataY = None
            # pdi.blockSignals(True)
        measure('until blocks 1')
        blocks = list(SpectralProfileBlock.fromSpectralProfiles(
            [pdi.spectralProfile() for pdi in pdis]
        ))
        measure('create blocks')

        # 1. read PDI profiles
        # 2. convert to target unit
        # 3. apply spectral model
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)

        parameters = {self.mUnitConverterAlg.INPUT: blocks,
                      self.mUnitConverterAlg.TARGET_XUNIT: self.xUnit()}
        results = self.mUnitConverterAlg.processAlgorithm(parameters, context, feedback)
        blocks = results[self.mUnitConverterAlg.OUTPUT]

        measure('convert units')
        # todo: apply other spectral processing things
        model = self.spectralModel()
        if is_spectral_processing_model(model):
            parameters = {}
            for p in model.parameterDefinitions():
                if isinstance(p, SpectralProcessingProfiles):
                    parameters[p.name()] = blocks

            results2 = model.processAlgorithm(parameters, context, feedback)
            if isinstance(results2, dict):
                for p in model.outputDefinitions():
                    if isinstance(p, SpectralProcessingProfilesOutput):
                        suffix = f':{p.name()}'
                        for k in results2.keys():
                            if k.endswith(suffix):
                                blocks = results2[k]

            measure('run model units')

        # self.blockSignals(True)
        for block in blocks:
            data = block.data()
            xvalues = block.xValues()

            for key in block.profileKeys():
                assert key in LUT.keys()

            keys = block.profileKeys()
            key_indices = np.unravel_index(np.arange(len(keys)), data.shape[1:])
            for key, y, x in zip(keys, key_indices[0], key_indices[1]):
                yvalues = data[:, y, x]
                pdi = LUT[key]
                # pdi.blockSignals(True)
                pdi.mDataX = xvalues
                pdi.mDataY = yvalues
                pdi.setData(x=pdi.mDataX, y=pdi.mDataY)
                # pdi.setVisible(SPDIFlags.Displayable in pdi.visualizationFlags())
                # pdi.blockSignals(False)

        measure('set pdi data')
        pi.addItems(plot_pdis)
        measure('addItems(plot_pdis)')

        if True:
            msg = []
            for k, t in DTIME.items():
                dt, step = t
                if k == 0:
                    continue
                dt = dt - DTIME[k - 1][0]
                msg.append(f'{step}= {dt}')
            print('#Step Report\n' + '\n'.join(msg))

    def _update_to_display(self,
                           keys_to_display: typing.List[SpectralProfileKey],
                           key_order: typing.List[SpectralProfileKey],
                           limit: int) -> bool:
        """
        Updates the list 'keys_to_display' in order of 'key_order'
        Returns True if
            (i) len(keys_to_display) >= limit, or
            (ii) all keys in key_order have been checked for displayability
        else:
            False, which means new SpectralProfileDataItems need to be loaded and added with a SpectralProfileKey
        :param keys_to_display:
        :param key_order:
        :param limit:
        :return: bool
        """
        assert len(keys_to_display) <= len(key_order)
        if len(key_order) == 0:
            return True
        i_start = len(keys_to_display)
        for k in key_order[i_start:]:
            if len(keys_to_display) >= limit:
                return True

            if k not in self.mSPDICache.keys():
                # profile misses key in cache.
                # return to force loading from Speclib
                return False

            item = self.mSPDICache[k]
            if isinstance(item, SpectralProfilePlotDataItem) and SPDIFlags.Displayable in item.visualizationFlags():
                keys_to_display.append(k)
            else:
                # a key exists but not profile for in the database.
                # or profile data exists, but is not displayable in current mode
                # continue to next key
                continue

        return len(keys_to_display) >= limit or k == key_order[-1]

    def updatePlotDataItems(self):
        """
        1. create new PDI instances for potential keys
        2. update PDI data based on model
        3. update PDI styles
        """
        t0 = datetime.datetime.now()
        pi: SpectralLibraryPlotItem = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem)
        n_max = self.maxProfiles()

        # problems:
        # 1. too many PlotDataItems? -> plot becomes too unresponsive
        #    => we need to limit the number of plot data items to self.maxProfiles()
        # 2. reading SpectralProfiles from SpectralLibrary needs time (NULL values?, decoding ByteArrays, ...)
        #    => read SpectralProfiles in chunks
        # 3.

        CHUNK_SIZE = min(1024, n_max)

        self.mNumberOfValueErrorsProfiles = 0
        self.mNumberOfEmptyProfiles = 0

        sort_x_values: bool = self.xUnit() in ['DOI']
        keys_plotted = self.plottedProfileKeys()
        keys_all = self.potentialProfileKeys()
        keys_missing = [k for k in keys_all if k not in self.mSPDICache.keys()]
        keys_to_display: typing.List[SpectralProfileKey] = []

        if DEBUG:
            for k in keys_all:
                assert isinstance(k, SpectralProfileKey)
            for k in self.mSPDICache.keys():
                assert isinstance(k, SpectralProfileKey)

        if not self._update_to_display(keys_to_display, keys_all, n_max):
            for keys_block in chunks(keys_missing, CHUNK_SIZE):
                keys_block = list(keys_block)
                block_pdis: typing.Dict[SpectralProfileKey, SpectralProfilePlotDataItem] = {k: None for k in keys_block}

                new_pdis: typing.List[SpectralProfilePlotDataItem] = []
                for profile in self.speclib().profiles(profile_keys=keys_block):
                    pdi = SpectralProfilePlotDataItem(profile)
                    pdi.setProfileSource(self.speclib())
                    pdi.setClickable(True)
                    pdi.sigProfileClicked.connect(self.onProfileClicked)
                    block_pdis[pdi.key()] = pdi
                    new_pdis.append(pdi)
                # update display values
                self.updatePlotDataItemValues(new_pdis)
                # update plot style
                # self.updatePlotDataItemStyles(new_pdis)

                # update cache
                self.mSPDICache.update(block_pdis)

                # stop loading profiles, if we can display n_max profiles in order of keys in keys_all
                if self._update_to_display(keys_to_display, keys_all, n_max):
                    break

        # keys_to_display now contains all visible keys in order of keys in keys_all

        t1 = datetime.datetime.now()
        # remove pdis from plot item that we dont want to show
        to_remove = []
        to_add = []

        for pdi in self.plottedProfilePlotDataItems():
            if isinstance(pdi, SpectralProfilePlotDataItem) and pdi.key() not in keys_to_display:
                to_remove.append(pdi)
        if len(to_remove) > 0:
            pi.removeItems(to_remove)

        t2 = datetime.datetime.now()
        # add missing keys
        plotted = self.plottedProfileKeys()

        for z, k in enumerate(keys_to_display):
            if k not in plotted:
                pdi = self.mSPDICache.get(k, None)
                if isinstance(pdi, SpectralProfilePlotDataItem):
                    pdi.setZValue(-1 * z)
                    to_add.append(pdi)

        if len(to_add) > 0:
            pi.addItems(to_add)
            # self.updatePlotDataItemStyles(to_add)

        t3 = datetime.datetime.now()
        if isinstance(self.mDualView, QgsDualView):
            TV = self.mDualView.tableView()
            selected_fids = TV.selectedFeaturesIds()
            selected_cell: SpectralProfileKey = None
            cIdx = TV.selectionModel().currentIndex()
            if isinstance(cIdx, QModelIndex):
                cField = cIdx.data(QgsAttributeTableModel.FieldIndexRole)
                cFID = cIdx.data(QgsAttributeTableModel.FeatureIdRole)
                if isinstance(cField, int) and cField >= 0:
                    cField: QgsField = self.speclib().fields().at(cField)
                    if cField in self.speclib().spectralValueFields():
                        selected_cell = SpectralProfileKey(cFID, cField.name())
                        s = ""

        # self.updatePlotDataItemStyles()
        if DEBUG and len(to_remove) + len(to_add) > 0:
            print(f'A:{len(to_add)} R: {len(to_remove)}')
            print(f'tP:{t1 - t0} tR:{t2 - t1} tA:{t3 - t2}')
            fids = ' '.join([str(k.fid) for k in keys_to_display])
            # self.update()
            print(fids)
            # if len(to_remove) > 0:
            #    for p in to_remove: print(p.key())

        """
        selectionChanged = list(selectedNow.symmetric_difference(self.mSelectedIds))
        self.mSelectedIds = selectedNow

        key_to_update_style = [pkey for pkey in keys_to_visualize if pkey[0] in selectionChanged or pkey in keys_new]
        self.updatePlotDataItemStyles(key_to_update_style)

        if len(keys_new) > 0 or len(keys_to_remove) > 0 or len(key_to_update_style) > 0:
            pi.update()
        """

    def spectralModel(self) -> QgsProcessingModelAlgorithm:
        return self.mSpectralModel

    def setSpectralModel(self, model: QgsProcessingModelAlgorithm):
        assert is_spectral_processing_model(model)
        self.mSpectralModel = model
        self.updatePlotDataItemValues()

    def updatePlotDataItemStyles(self, pdis: typing.List[SpectralProfilePlotDataItem] = None):
        """
        Updates the styles for a set of SpectralProfilePlotDataItems specified by its feature keys
        :param keys: list of SpectralProfileKeys to update
        """

        if not isinstance(self.speclib(), QgsVectorLayer):
            return

        profileRenderer = self.profileRenderer()

        if pdis is None:
            pdis = self.plottedProfilePlotDataItems()
        if len(pdis) == 0:
            return
        if isinstance(pdis[0], SpectralProfileKey):
            pdis = [self.mSPDICache[k] for k in pdis
                    if isinstance(self.mSPDICache.get(k, None), SpectralProfilePlotDataItem)]
        # update line colors
        keys2 = [pdi.key() for pdi in pdis]
        styles = profileRenderer.profilePlotStyles(keys2)
        for pdi in pdis:
            style = styles.get(pdi.key())
            if isinstance(style, PlotStyle):
                style.apply(pdi,
                            updateItem=False,
                            visibility=SPDIFlags.Displayable in pdi.visualizationFlags()
                                       and style.isVisible())

        # finally, update items
        for pdi in pdis:
            pdi.updateItems()
            pass
            # z = 1 if pdi.id() in self.mSelectedIds else 0
            # pdi.setZValue(z)
            # pdi.updateItems()
        s = ""

    def onProfileClicked(self, fid: int, data: dict):
        """
        Slot to react to mouse-clicks on SpectralProfilePlotDataItems
        :param fid: Feature ID
        :param pdi: SpectralProfilePlotDataItem
        """
        modifiers = QApplication.keyboardModifiers()

        pdi: SpectralProfilePlotDataItem = data.get('pdi')
        if modifiers == Qt.AltModifier:
            x = data['xValue']
            y = data['yValue']
            b = data['idx'] + 1

            if isinstance(pdi, SpectralProfilePlotDataItem):
                profile: SpectralProfile = pdi.spectralProfile()
                if isinstance(profile, SpectralProfile):
                    ptColor: QColor = self.mInfoScatterPoint.opts['brush'].color()
                    self.mInfoScatterPointHtml = f'<span style="color:{ptColor.name()}">' + \
                                                 f'FID:{fid} Bnd:{b}<br/>' + \
                                                 f'x:{x}\ny:{y}<br/>' + \
                                                 textwrap.shorten(profile.name(),
                                                                  width=self.mMaxInfoLength,
                                                                  placeholder='...') + \
                                                 f'</span>'
            else:
                s = ""
            self.mInfoScatterPoint.setData(x=[x],
                                           y=[y],
                                           symbol='o')
            self.mInfoScatterPoint.setVisible(True)

        else:

            if isinstance(pdi, SpectralProfilePlotDataItem) and isinstance(pdi.profileSource(), SpectralLibrary):
                speclib: SpectralLibrary = pdi.profileSource()
                fids = speclib.selectedFeatureIds()

                if modifiers == Qt.NoModifier:
                    fids = [fid]
                elif modifiers == Qt.ShiftModifier or modifiers == Qt.ControlModifier:
                    if fid in fids:
                        fids.remove(fid)
                    else:
                        fids.append(fid)

                speclib.selectByIds(fids)

        self.updatePositionInfo()

    def setYLabel(self, label: str):
        """
        Sets the name of the Y axis
        :param label: str, name
        """
        pi = self.getPlotItem()
        pi.getAxis('left').setLabel(label)

    def yLabel(self) -> str:
        return self.getPlotItem().getAxis('left').label

    def xLabel(self) -> str:
        return self.getPlotItem().getAxis('bottom').label

    def profileStats(self):
        """
        Returns stats related to existing and visualized SpectralProfiles
        """
        stats = SpectralLibraryPlotStats()
        stats.profiles_plotted_max = self.maxProfiles()

        if isinstance(self.speclib(), SpectralLibrary) and not sip.isdeleted(self.speclib()):
            stats.features_total = self.speclib().featureCount()
            stats.features_selected = self.speclib().selectedFeatureCount()

            stats.filter_mode = self.dualView().filterMode()

            filtered_fids = self.dualView().filteredFeatures()
            selected_fids = self.speclib().selectedFeatureIds()

            stats.features_filtered = len(filtered_fids)

            stats.profiles_total = stats.features_total * len(self.speclib().spectralValueFields())
            stats.profiles_filtered = stats.features_filtered * len(self.speclib().spectralValueFields())
            stats.profiles_error = self.mNumberOfValueErrorsProfiles
            stats.profiles_empty = self.mNumberOfEmptyProfiles

            for pdi in self.allSpectralProfilePlotDataItems():
                fid, value_field = pdi.key()
                if pdi.isVisible():
                    stats.profiles_plotted += 1

                    if fid in selected_fids:
                        stats.profiles_selected += 1

        return stats

    def plottedProfileKeys(self, flags: SPDIFlags = None) -> typing.Set[SpectralProfileKey]:
        return set([pdi.key() for pdi in self.plottedProfilePlotDataItems(flags=flags)])

    def value_fields(self) -> typing.List[QgsField]:
        """
        Returns the speclib field to show profiles from
        :return:
        """
        return self.speclib().spectralValueFields()

    def potentialProfileKeys(self) -> typing.List[SpectralProfileKey]:
        """
        Returns the list of potential profile/feature keys to be visualized, ordered by its importance.
        Can contain keys to "empty" profiles, where the value field BLOB is NULL
        1st position = most important, should be plotted on top of all other profiles
        Last position = can be skipped if n_max is reached
        """
        if not isinstance(self.speclib(), SpectralLibrary):
            return []

        fieldNames = self.value_fields()

        if len(fieldNames) == 0:
            return []

        selectedOnly = self.actionShowSelectedProfilesOnly().isChecked()
        selectedIds = self.speclib().selectedFeatureIds()

        dualView = self.dualView()
        if isinstance(dualView, QgsDualView) and dualView.filteredFeatureCount() > 0:
            allIDs = dualView.filteredFeatures()
            selectedIds = [fid for fid in allIDs if fid in selectedIds]
        else:
            allIDs = self.speclib().allFeatureIds()

        # Order:
        # 1. Highlighted
        # 1. Visible in table
        # 2. Selected
        # 3. others

        # overlaid features / current spectral

        priority0: typing.List[SpectralProfileKey] = self.temporaryProfileKeys()
        priority1: typing.List[SpectralProfileKey] = []  # visible features
        priority2: typing.List[SpectralProfileKey] = []  # selected features
        priority3: typing.List[SpectralProfileKey] = []  # any other : not visible / not selected

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

                    priority1.extend(generateProfileKeys(visible_fids, fieldNames))
            priority2 = generateProfileKeys(self.dualView().masterModel().layer().selectedFeatureIds(),
                                            fieldNames)
            if not selectedOnly:
                priority3 = generateProfileKeys(dualView.filteredFeatures(), fieldNames)
        else:
            priority2 = generateProfileKeys(selectedIds, fieldNames)
            if not selectedOnly:
                priority3 = generateProfileKeys(allIDs, fieldNames)

        toVisualize = sorted(set(priority0 + priority1 + priority2 + priority3),
                             key=lambda k: (k not in priority0, k not in priority1, k not in priority2, k))

        return toVisualize

    def dragEnterEvent(self, event: QDragEnterEvent):
        if containsSpeclib(event.mimeData()):
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if not containsSpeclib(event.mimeData()):
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        assert isinstance(event, QDropEvent)
        mimeData = event.mimeData()
        if containsSpeclib(mimeData) and isinstance(self.speclib(), SpectralLibrary):
            speclib = SpectralLibrary.readFromMimeData(mimeData)
            # print(f'DROP SPECLIB {speclib}')
            if isinstance(speclib, SpectralLibrary) and len(speclib) > 0:

                b = self.speclib().isEditable()
                self.speclib().startEditing()
                self.speclib().addSpeclib(speclib)
                if not b:
                    self.speclib().commitChanges()
            event.accept()
        else:
            super().dropEvent(event)


class SpectralLibraryPlotStats(object):

    def __init__(self):
        self.features_total: int = 0
        self.features_selected: int = 0
        self.features_filtered: int = 0
        self.filter_mode: QgsAttributeTableFilterModel.FilterMode = QgsAttributeTableFilterModel.ShowAll

        self.profiles_plotted_max: int = 0
        self.profiles_total: int = 0
        self.profiles_empty: int = 0
        self.profiles_plotted: int = 0
        self.profiles_selected: int = 0
        self.profiles_filtered: int = 0
        self.profiles_error: int = 0

    def __eq__(self, other) -> bool:
        if not isinstance(other, SpectralLibraryPlotStats):
            return False
        for k in self.__dict__.keys():
            if self.__dict__[k] != other.__dict__[k]:
                return False
        return True


class SpectralProfileRendererWidget(QWidget):
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        path_ui = speclibUiPath('spectralprofilerendererwidget.ui')
        loadUi(path_ui, self)

        self.mBlocked: bool = False

        self.mLastRenderer: SpectralProfileRenderer = None
        self.mResetRenderer: SpectralProfileRenderer = None

        self.btnColorBackground.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorForeground.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorInfo.colorChanged.connect(self.onProfileRendererChanged)
        self.btnColorSelection.colorChanged.connect(self.onProfileRendererChanged)

        self.optionUseColorsFromVectorRenderer.toggled.connect(self.onUseColorsFromVectorRendererChanged)
        self.btnUseColorsFromVectorRenderer.setDefaultAction(self.optionUseColorsFromVectorRenderer)

        self.wDefaultProfileStyle.setPreviewVisible(False)
        self.wDefaultProfileStyle.cbIsVisible.setVisible(False)
        self.wDefaultProfileStyle.sigPlotStyleChanged.connect(self.onProfileRendererChanged)
        self.wDefaultProfileStyle.setMinimumSize(self.wDefaultProfileStyle.sizeHint())
        self.btnReset.setDisabled(True)
        self.btnReset.clicked.connect(self.reset)

        self.btnColorSchemeBright.setDefaultAction(self.actionActivateBrightTheme)
        self.btnColorSchemeDark.setDefaultAction(self.actionActivateDarkTheme)
        self.actionActivateBrightTheme.triggered.connect(
            lambda: self.setRendererTheme(SpectralProfileRenderer.bright()))
        self.actionActivateDarkTheme.triggered.connect(lambda: self.setRendererTheme(SpectralProfileRenderer.dark()))

    def setResetRenderer(self, profileRenderer: SpectralProfileRenderer):
        self.mResetRenderer = profileRenderer

    def resetRenderer(self) -> SpectralProfileRenderer:
        return self.mResetRenderer

    def reset(self, *args):

        if isinstance(self.mResetRenderer, SpectralProfileRenderer):
            self.setProfileRenderer(self.mResetRenderer)

    def onUseColorsFromVectorRendererChanged(self, checked: bool):

        w: PlotStyleWidget = self.wDefaultProfileStyle
        assert isinstance(w, PlotStyleWidget)
        w.btnLinePenColor.setDisabled(checked)
        w.btnMarkerBrushColor.setDisabled(checked)
        w.btnMarkerPenColor.setDisabled(checked)

        self.onProfileRendererChanged()

    def setRendererTheme(self, profileRenderer: SpectralProfileRenderer):

        profileRenderer = profileRenderer.clone()
        # do not overwrite the following settings:
        profileRenderer.useRendererColors = self.optionUseColorsFromVectorRenderer.isChecked()
        if isinstance(self.mLastRenderer, SpectralProfileRenderer):
            profileRenderer.mProfileKey2Style = self.mLastRenderer.mProfileKey2Style

        self.setProfileRenderer(profileRenderer)

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        assert isinstance(profileRenderer, SpectralProfileRenderer)

        if self.mResetRenderer is None:
            self.mResetRenderer = profileRenderer.clone()

        self.mLastRenderer = profileRenderer
        self.btnReset.setEnabled(True)

        changed = profileRenderer != self.spectralProfileRenderer()

        self.mBlocked = True

        self.btnColorBackground.setColor(profileRenderer.backgroundColor)
        self.btnColorForeground.setColor(profileRenderer.foregroundColor)
        self.btnColorInfo.setColor(profileRenderer.infoColor)
        self.btnColorSelection.setColor(profileRenderer.selectionColor)
        self.wDefaultProfileStyle.setPlotStyle(profileRenderer.profileStyle)
        self.optionUseColorsFromVectorRenderer.setChecked(profileRenderer.useRendererColors)
        self.mBlocked = False
        if changed:
            self.sigProfileRendererChanged.emit(self.spectralProfileRenderer())

    def onProfileRendererChanged(self, *args):
        if not self.mBlocked:
            self.btnReset.setEnabled(isinstance(self.mResetRenderer, SpectralProfileRenderer) and
                                     self.spectralProfileRenderer() != self.mResetRenderer)
            self.sigProfileRendererChanged.emit(self.spectralProfileRenderer())

    def spectralProfileRenderer(self) -> SpectralProfileRenderer:
        if isinstance(self.mLastRenderer, SpectralProfileRenderer):
            cs = self.mLastRenderer.clone()
        else:
            cs = SpectralProfileRenderer()
        cs.backgroundColor = self.btnColorBackground.color()
        cs.foregroundColor = self.btnColorForeground.color()
        cs.infoColor = self.btnColorInfo.color()
        cs.selectionColor = self.btnColorSelection.color()
        cs.profileStyle = self.wDefaultProfileStyle.plotStyle()
        # if isinstance(self.mLastRenderer, SpectralProfileRenderer):
        #    cs.temporaryProfileStyle = self.mLastRenderer.temporaryProfileStyle.clone()
        #    cs.mProfileKey2Style.update(self.mLastRenderer.mProfileKey2Style)
        cs.useRendererColors = self.optionUseColorsFromVectorRenderer.isChecked()
        return cs


class SpectralProfileRendererWidgetAction(QWidgetAction):
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)
    sigResetRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self, parent, **kwds):
        super().__init__(parent)
        self.mProfileRenderer: SpectralProfileRenderer = SpectralProfileRenderer.default()
        self.mResetRenderer: SpectralProfileRenderer = self.mProfileRenderer

    def setResetRenderer(self, profileRenderer: SpectralProfileRenderer):
        self.mResetRenderer = profileRenderer
        self.sigResetRendererChanged.emit(self.mResetRenderer)

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        if self.mProfileRenderer != profileRenderer:
            # print(self.mProfileRenderer.printDifferences(profileRenderer))
            self.mProfileRenderer = profileRenderer
            self.sigProfileRendererChanged.emit(profileRenderer)

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.mProfileRenderer

    def createWidget(self, parent: QWidget) -> SpectralProfileRendererWidget:
        w = SpectralProfileRendererWidget(parent)
        w.setProfileRenderer(self.profileRenderer())
        w.sigProfileRendererChanged.connect(self.setProfileRenderer)
        self.sigProfileRendererChanged.connect(w.setProfileRenderer)
        self.sigResetRendererChanged.connect(w.setResetRenderer)
        return w


class SpectralProfilePlotVisualization(QObject):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mModel: QgsProcessingModelAlgorithm = NO_MODEL_MODEL()
        self.mSpeclib: QgsVectorLayer = None
        self.mField: QgsField = QgsField()
        self.mNameExpression: str = ''
        self.mPlotStyle: PlotStyle = PlotStyle()
        self.mVisible: bool = True

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def nameExpression(self) -> str:
        """
        Returns the expression that returns the name for a single profile
        :return: str
        """
        return self.mNameExpression

    def modelId(self) -> str:
        if isinstance(self.mModel, QgsProcessingModelAlgorithm):
            return self.mModel.id()
        else:
            return ''

    def plotStyle(self) -> PlotStyle:
        return self.mPlotStyle


class SpectralProfilePlotControl(QAbstractTableModel):
    CIX_FIELD = 0
    CIX_MODEL = 1
    CIX_NAME = 2
    CIX_STYLE = 3

    # CIX_MARKER = 4

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mProfileVisualizations: typing.List[SpectralProfilePlotVisualization] = []
        self.mModelList: SpectralProcessingModelList = SpectralProcessingModelList(allow_empty=True)
        self.mProfileFieldModel: QgsFieldModel = QgsFieldModel()
        self.mMaxPDIs: int = 64
        self.mPlotWidget: SpectralProfilePlotWidget = None

        self.mColumnNames = {self.CIX_FIELD: 'Field',
                             self.CIX_MODEL: 'Model',
                             self.CIX_NAME: 'Name',
                             self.CIX_STYLE: 'Style',
                             # self.CIX_MARKER: 'Marker'
                             }

        self.mColumnTooltips = {
            self.CIX_FIELD: 'This column specifies the binary source field that stores the spectral profiles information',
            self.CIX_MODEL: 'This column is used to either show spectral profiles or modify them with a Spectral processing model',
            self.CIX_NAME: 'This column allow to specify how the profile names are generated',
            self.CIX_STYLE: 'Here you can specify the line style for each profile type',
            # self.CIX_MARKER: 'Here you can specify the marker symbol ofr each profile type'
            }

        self.mPlotDataItems: typing.List[SpectralProfilePlotDataItem] = list()
        self.mFID_VIS_Mapper: typing.Dict[typing.Tuple[int, SpectralProfilePlotVisualization], SpectralProfilePlotDataItem]
        self.mProfileDataCache: typing.Dict[typing.Tuple[int, str, str], SpectralProfile] = dict()
        self.mDualView: QgsDualView = None
        self.mSpeclib: QgsVectorLayer = None

        self.mActionMaxNumberOfProfiles: MaxNumberOfProfilesWidgetAction = MaxNumberOfProfilesWidgetAction(None)
        self.mActionShowSelectedProfilesOnly: QAction = QAction('Show Selected Profiles Only', None)
        self.mActionShowSelectedProfilesOnly.setToolTip('Activate to show selected profiles only, '
                                                        'e.g. those selected in the attribute table')
        self.mActionShowSelectedProfilesOnly.setCheckable(True)

    def setPlotWidget(self, plotWidget: SpectralProfilePlotWidget):
        self.mPlotWidget = plotWidget

    def setNumberOfPlotDataItems(self, n: int):
        assert n >= 0
        self.mMaxPDIs = n

        if len(self.mPlotDataItems) > self.mMaxPDIs:
            s = ""

    def __len__(self) -> int:
        return len(self.mProfileVisualizations)

    def __iter__(self) -> typing.Iterator[SpectralProfilePlotVisualization]:
        return iter(self.mProfileVisualizations)

    def profileFieldsModel(self) -> QgsFieldModel:
        return self.mProfileFieldModel

    def insertVisualizations(self,
                             index: typing.Union[int, QModelIndex],
                             vis: typing.Union[SpectralProfilePlotVisualization,
                                               typing.List[SpectralProfilePlotVisualization]],
                             ):
        if isinstance(index, QModelIndex):
            index = index.row()
        if index == -1:
            index = len(self)
        if isinstance(vis, SpectralProfilePlotVisualization):
            vis = [vis]
        for v in vis:
            assert isinstance(v, SpectralProfilePlotVisualization)
        n = len(vis)
        i1 = index + n - 1
        self.beginInsertRows(QModelIndex(), index, i1)
        self.mProfileVisualizations[index:i1] = vis
        self.endInsertRows()

        self.updatePlot()

    def removeVisualizations(self, vis: typing.Union[SpectralProfilePlotVisualization,
                                                     typing.List[SpectralProfilePlotVisualization]]):

        if isinstance(vis, SpectralProfilePlotVisualization):
            vis = [vis]
        for v in vis:
            assert isinstance(v, SpectralProfilePlotVisualization)
            assert v in self.mProfileVisualizations
            i = self.mProfileVisualizations.index(v)
            self.beginRemoveRows(QModelIndex(), i, i)
            del self.mProfileVisualizations[i]
            self.endRemoveRows()

        self.updatePlot()

    def updatePlot(self):

        if not isinstance(self.mPlotWidget, SpectralProfilePlotWidget):
            return
        SL: QgsVectorLayer = self.speclib()
        n = 0
        n_max = self.mActionMaxNumberOfProfiles.maxProfiles()
        NAME2FIELDIDX = {SL.fields().at(i).name():i for i in range(SL.fields().count())}

        for fid in self.featurePriority():

            for vis in self:
                n += 1
                if n >= n_max:
                    return

                fidx = NAME2FIELDIDX[vis.mField.name()]
                modelId = vis.modelId()
                dataKey = (fid, vis.mField.name(), modelId)
                s = ""
                if dataKey not in self.mProfileDataCache.keys():
                    s = "load / calculate"



        s = ""

    def featurePriority(self) -> typing.List[int]:
        """
        Returns the list of potential feature keys to be visualized, ordered by its importance.
        Can contain keys to "empty" profiles, where the value field BLOB is NULL
        1st position = most important, should be plotted on top of all other profiles
        Last position = can be skipped if n_max is reached
        """
        if not isinstance(self.speclib(), SpectralLibrary):
            return []

        selectedOnly = self.mActionShowSelectedProfilesOnly.isChecked()
        selectedIds = self.speclib().selectedFeatureIds()

        dualView = self.dualView()
        if isinstance(dualView, QgsDualView) and dualView.filteredFeatureCount() > 0:
            allIDs = dualView.filteredFeatures()
            selectedIds = [fid for fid in allIDs if fid in selectedIds]
        else:
            allIDs = self.speclib().allFeatureIds()

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

        return toVisualize


    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mProfileVisualizations)

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.mColumnNames)

    def index(self, row, col, parent: QModelIndex = None, *args, **kwargs) -> QModelIndex:
        vis = self.mProfileVisualizations[row]
        return self.createIndex(row, col, vis)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable
        if index.column() == self.CIX_FIELD:
            flags = flags | Qt.ItemIsUserCheckable
        return flags

    def dualView(self) -> QgsDualView:
        return self.mDualView

    def setDualView(self, dualView: QgsDualView):

        if self.mDualView != dualView:
            if isinstance(self.mDualView, QgsDualView):
                self.mDualView.tableView().selectionModel().selectionChanged.disconnect(self.onDualViewSelectionChanged)

            self.mDualView = dualView
            self.mDualView.tableView().selectionModel().selectionChanged.connect(self.onDualViewSelectionChanged)
            speclib = dualView.masterModel().layer()

            if self.mSpeclib != speclib:
                if isinstance(self.mSpeclib, QgsVectorLayer):
                    self.mSpeclib.attributeDeleted.disconnect(self.onSpeclibAttributesChanged)
                    self.mSpeclib.attributeAdded.disconnect(self.onSpeclibAttributesChanged)

                self.mSpeclib = speclib
                self.mSpeclib.attributeDeleted.connect(self.onSpeclibAttributesChanged)
                self.mSpeclib.attributeAdded.connect(self.onSpeclibAttributesChanged)
                self.onSpeclibAttributesChanged()

    def onDualViewSelectionChanged(self, *args):
        s = ""

    def onSpeclibAttributesChanged(self):
        fields = QgsFields()
        for field in spectralValueFields(self.mSpeclib):
            fields.append(field)
        self.mProfileFieldModel.setFields(fields)

        # remove visualization for deleted fields
        to_remove = [f for f in self if f.mField.name() not in fields.names()]
        self.removeVisualizations(to_remove)

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        vis: SpectralProfilePlotVisualization = self.mProfileVisualizations[index.row()]

        if role == Qt.UserRole:
            return vis

        if index.column() == self.CIX_FIELD:
            if role == Qt.CheckStateRole:
                return Qt.Checked if vis.mVisible else Qt.Unchecked
            if role == Qt.DisplayRole:
                return vis.mField.name()
            if role == Qt.ToolTipRole:
                return vis.mField.name()

        if index.column() == self.CIX_MODEL:
            if role == Qt.DisplayRole:
                return vis.modelId()
            if role == Qt.ToolTipRole:
                return vis.modelId()

        if index.column() == self.CIX_NAME:
            if role == Qt.DisplayRole:
                return vis.mNameExpression
            if role == Qt.ToolTipRole:
                return vis.mNameExpression

        if index.column() == self.CIX_STYLE:
            if role == Qt.ToolTipRole:
                return 'Line and Symbol style'

        if role == Qt.ForegroundRole and not vis.mVisible:
            return QColor('grey')

        return None

    def setData(self, index: QModelIndex, value: typing.Any, role=Qt.EditRole):

        if not index.isValid():
            return

        changed = False
        visibility_changed = False
        vis: SpectralProfilePlotVisualization = self.mProfileVisualizations[index.row()]
        if index.column() == self.CIX_FIELD:
            if role == Qt.CheckStateRole:
                set_visible = value == Qt.Checked
                if set_visible != vis.mVisible:
                    vis.mVisible = set_visible
                    changed = True
                    visibility_changed = True

            elif role == Qt.EditRole:
                assert isinstance(value, QgsField)
                vis.mField = value
                changed = True

        if index.column() == self.CIX_NAME:
            assert isinstance(value, str)
            if value != vis.mNameExpression:
                vis.mNameExpression = value
                changed = True

        if index.column() == self.CIX_MODEL:
            assert isinstance(value, QgsProcessingModelAlgorithm)
            assert value in self.modelList()
            if vis.mModel != value:
                vis.mModel = value
                changed = True

        if index.column() == self.CIX_STYLE:
            assert isinstance(value, PlotStyle)
            if value != vis.mPlotStyle:
                vis.mPlotStyle = value
                changed = True

        if changed:
            if visibility_changed:
                self.dataChanged.emit(
                    self.index(index.row(), 0),
                    self.index(index.row(), self.columnCount() - 1,
                               [role, Qt.ForegroundRole])
                )
            else:
                self.dataChanged.emit(index, index, [role])

        return changed

    def headerData(self, col: int, orientation, role):
        if orientation == Qt.Horizontal:

            if role == Qt.DisplayRole:
                return self.mColumnNames.get(col, f'{col + 1}')
            elif role == Qt.ToolTipRole:
                return self.mColumnTooltips.get(col, None)

        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col + 1

        return None

    def removeModel(self, model: QgsProcessingModelAlgorithm):
        self.mModelList.removeModel(model)
        # todo: disconnect model from visualiszations

    def addModel(self, model: QgsProcessingModelAlgorithm):
        assert is_spectral_processing_model(model)
        self.mModelList.addModel(model)

    def modelList(self) -> SpectralProcessingModelList:
        return self.mModelList


class SpectralProfilePlotControlView(QTableView):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotControlView, self).__init__(*args, **kwds)
        self.horizontalHeader().setStretchLastSection(True)
        # self.horizontalHeader().setResizeMode(QHeaderView.Stretch)

    def controlTable(self) -> SpectralProfilePlotControl:
        return self.model()


class SpectralProfilePlotControlViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, tableView: QTableView, parent=None):
        assert isinstance(tableView, QTableView)
        super(SpectralProfilePlotControlViewDelegate, self).__init__(parent=parent)
        self.mTableView = tableView

    def model(self) -> QAbstractTableModel:
        return self.mTableView.model()

    def paint(self, painter: QPainter, option: 'QStyleOptionViewItem', index: QModelIndex):
        # cName = self.mTableView.model().headerData(index.column(), Qt.Horizontal)
        c = index.column()

        vis: SpectralProfilePlotVisualization = index.data(Qt.UserRole)

        if c == SpectralProfilePlotControl.CIX_STYLE:
            style: PlotStyle = vis.mPlotStyle
            h = self.mTableView.verticalHeader().sectionSize(index.row())
            w = self.mTableView.horizontalHeader().sectionSize(index.column())
            if h > 0 and w > 0:
                px = style.createPixmap(size=QSize(w, h))
                painter.drawPixmap(option.rect, px)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def setItemDelegates(self, tableView: QTableView):
        for c in range(tableView.model().columnCount()):
            tableView.setItemDelegateForColumn(c, self)

    def onRowsInserted(self, parent, idx0, idx1):
        nameStyleColumn = self.bridge().cnPlotStyle

        for c in range(self.mTableView.model().columnCount()):
            cname = self.mTableView.model().headerData(c, Qt.Horizontal, Qt.DisplayRole)
            if cname == nameStyleColumn:
                for r in range(idx0, idx1 + 1):
                    idx = self.mTableView.model().index(r, c, parent=parent)
                    self.mTableView.openPersistentEditor(idx)

    def plotControl(self) -> SpectralProfilePlotControl:
        return self.mTableView.model().sourceModel()

    def createEditor(self, parent, option, index):
        # cname = self.bridgeColumnName(index)
        # bridge = self.bridge()
        # pmodel = self.sortFilterProxyModel()

        w = None
        if index.isValid():
            plotControl = self.plotControl()

            c: int = index.column()
            vis: SpectralProfilePlotVisualization = index.data(Qt.UserRole)

            if c == SpectralProfilePlotControl.CIX_FIELD:
                w = QComboBox(parent=parent)
                w.setModel(plotControl.profileFieldsModel())
                w.setToolTip('Select a field with profile data')

            if c == SpectralProfilePlotControl.CIX_MODEL:
                w = QComboBox(parent=parent)
                w.setModel(plotControl.modelList())
                w.setToolTip('Select a model or show raw profiles')

            if c == SpectralProfilePlotControl.CIX_NAME:
                w = QgsFieldExpressionWidget(parent=parent)
                w.setExpressionDialogTitle('Profile Name')
                w.setToolTip('Set an expression to specify the profile name')
                w.setExpression(vis.nameExpression())
                w.setLayer(vis.speclib())
                w.setFilters(QgsFieldProxyModel.String | QgsFieldProxyModel.Numeric)

            if c == SpectralProfilePlotControl.CIX_STYLE:
                w = PlotStyleButton(parent=parent)
                w.setMinimumSize(5, 5)
                w.setPlotStyle(vis.plotStyle())
                w.setToolTip('Set curve style')

        return w

    def checkData(self, index, w, value):
        assert isinstance(index, QModelIndex)
        bridge = self.bridge()
        if index.isValid() and isinstance(bridge, SpectralProfileBridge):
            #  todo: any checks?
            self.commitData.emit(w)

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        self.mTableView.model().sourceModel().mProfileFieldModel
        if index.isValid():
            vis: SpectralProfilePlotVisualization = index.data(Qt.UserRole)

            if index.column() == SpectralProfilePlotControl.CIX_FIELD:
                assert isinstance(editor, QComboBox)
                idx = editor.model().indexFromName(vis.mField.name()).row()
                if idx == -1:
                    idx = 0
                editor.setCurrentIndex(idx)

            if index.column() == SpectralProfilePlotControl.CIX_MODEL:
                assert isinstance(editor, QComboBox)
                idx = editor.model().indexFromModelId(vis.modelId())
                if idx == -1:
                    idx = 0
                editor.setCurrentIndex(idx)

            if index.column() == SpectralProfilePlotControl.CIX_NAME:
                assert isinstance(editor, QgsFieldExpressionWidget)
                editor.setProperty('lastexpr', vis.nameExpression())
                editor.setLayer(vis.speclib())
                editor.setField(vis.nameExpression())

            if index.column() == SpectralProfilePlotControl.CIX_STYLE:
                assert isinstance(editor, PlotStyleButton)
                editor.setPlotStyle(vis.plotStyle())

    def setModelData(self, w, bridge, index):
        model = self.mTableView.model()

        if index.isValid():
            vis: SpectralProfilePlotVisualization = index.data(Qt.UserRole)

            if index.column() == SpectralProfilePlotControl.CIX_FIELD:
                assert isinstance(w, QComboBox)
                field: QgsField = w.model().fields().at(w.currentIndex())
                model.setData(index, field, Qt.EditRole)

            if index.column() == SpectralProfilePlotControl.CIX_MODEL:
                assert isinstance(w, QComboBox)
                pmodel = w.currentData(Qt.UserRole)
                model.setData(index, pmodel, Qt.EditRole)

            if index.column() == SpectralProfilePlotControl.CIX_NAME:
                assert isinstance(w, QgsFieldExpressionWidget)
                expr = w.asExpression()
                exprLast = vis.nameExpression()

                if w.isValidExpression():
                    model.setData(index, w.asExpression(), Qt.EditRole)

            if index.column() == SpectralProfilePlotControl.CIX_STYLE:
                assert isinstance(w, PlotStyleButton)
                bridge.setData(index, w.plotStyle(), Qt.EditRole)


class SpectralLibraryPlotWidget(QWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryplotwidget.ui'), self)

        assert isinstance(self.plotWidget, SpectralProfilePlotWidget)
        assert isinstance(self.tableView, SpectralProfilePlotControlView)
        self.plotWidget: SpectralProfilePlotWidget
        # self.plotWidget.sigPopulateContextMenuItems.connect(self.onPopulatePlotContextMenu)
        self.mPlotControlModel = SpectralProfilePlotControl()
        self.mPlotControlModel.setPlotWidget(self.plotWidget)
        self.mCurrentModel: QgsProcessingModelAlgorithm = None
        self.setCurrentModel(self.mPlotControlModel.modelList()[0])
        self.plotWidget.mMenuOthers.addAction(self.mPlotControlModel.mActionMaxNumberOfProfiles)
        self.plotWidget.mMenuOthers.addAction(self.mPlotControlModel.mActionShowSelectedProfilesOnly)

        self.mProxyModel = QSortFilterProxyModel()
        self.mProxyModel.setSourceModel(self.mPlotControlModel)
        self.tableView.setModel(self.mProxyModel)
        self.tableView.selectionModel().selectionChanged.connect(self.onVisSelectionChanged)

        self.mViewDelegate = SpectralProfilePlotControlViewDelegate(self.tableView)
        self.mViewDelegate.setItemDelegates(self.tableView)

        self.mDualView: QgsDualView = None
        self.mSettingsModel = SettingsModel(QgsSettings('qps'), key_filter='qps/spectrallibrary')
        self.btnAddProfileVis.setDefaultAction(self.actionAddProfileVis)
        self.btnRemoveProfileVis.setDefaultAction(self.actionRemoveProfileVis)
        self.actionAddProfileVis.triggered.connect(self.createProfileVis)
        self.actionRemoveProfileVis.triggered.connect(self.removeSelectedProfileVis)

        self.mActionSpeclib = SpeclibSettingsWidgetAction(None)
        self.mActionSpeclib.setDefaultWidget(self.mActionSpeclib.createWidget(None))
        self.plotWidget.mMenuOthers.addAction(self.mActionSpeclib)
        # actions
        self.visButtonLayout: QHBoxLayout

        self.visButtonLayout.addWidget(self.mPlotControlModel.mActionMaxNumberOfProfiles.createWidget(self))

    def readSettings(self):
        pass


    def writeSettings(self):
        pass

    def onVisSelectionChanged(self):

        rows = self.tableView.selectionModel().selectedRows()
        self.actionRemoveProfileVis.setEnabled(len(rows) > 0)

    def createProfileVis(self, *args):
        item = SpectralProfilePlotVisualization()

        # set defaults
        # set speclib
        item.mSpeclib = self.speclib()

        # set profile source in speclib
        for field in spectralValueFields(item.mSpeclib):
            item.mField = field
            break

        # get a good guess for the name expression
        # 1. "<source_field_name>_name"
        # 2. "name"
        # 3. $id (fallback)
        name_field = None
        source_field_name = item.mField.name()
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
            item.mNameExpression = f'"{name_field.name()}"'
        else:
            item.mNameExpression = '$id'

        item.mModel = self.currentModel()

        item.mPlotStyle = self.defaultStyle()

        self.mPlotControlModel.insertVisualizations(-1, item)

    def defaultStyle(self) -> PlotStyle:

        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        style.setLineColor('white')
        style.setMarkerColor('white')
        style.setMarkerSymbol(None)
        # style.markerSymbol = MarkerSymbol.No_Symbol.value
        # style.markerPen.setColor(style.linePen.color())
        return style

    def removeSelectedProfileVis(self, *args):
        rows = self.tableView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows]
        self.mPlotControlModel.removeVisualizations(to_remove)

    def setDualView(self, dualView):
        # self.plotWidget.setDualView(dualView)
        self.mDualView = dualView

        self.mPlotControlModel.setDualView(dualView)

    def speclib(self) -> QgsVectorLayer:
        return self.mPlotControlModel.speclib()

    def addSpectralModel(self, model):
        self.mPlotControlModel.addModel(model)

    def currentModel(self) -> QgsProcessingModelAlgorithm:
        return self.mCurrentModel

    def setCurrentModel(self, model: QgsProcessingModelAlgorithm):
        assert isinstance(model, QgsProcessingModelAlgorithm)

        if model not in self.mPlotControlModel.modelList():
            self.addSpectralModel(model)
        else:
            self.mCurrentModel = model

    def removeModel(self, model):
        self.mPlotControlModel.removeModel(model)
