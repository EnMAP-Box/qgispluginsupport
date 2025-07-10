import collections
import datetime
import sys
import textwrap
import warnings
from typing import Dict, List, Tuple, Union, Optional

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QPoint, QPointF, Qt
from qgis.PyQt.QtGui import QColor, QDragEnterEvent, QStandardItem
from qgis.PyQt.QtWidgets import QAction, QApplication, QMenu, QSlider, QWidgetAction
from qgis.core import QgsProject
from ...plotstyling.plotstyling import PlotStyle, PlotWidgetStyle
from ...pyqtgraph import pyqtgraph as pg
from ...unitmodel import datetime64, UnitWrapper
from ...utils import HashablePointF, SignalObjectWrapper


class SpectralXAxis(pg.AxisItem):

    def __init__(self, *args, **kwds):
        super(SpectralXAxis, self).__init__(*args, **kwds)
        self.setRange(1, 3000)
        self.enableAutoSIPrefix(True)
        self.labelAngle = 0

        self.mDateTimeFormat = '%D'
        self.mUnit: str = ''

    def tickStrings(self, values, scale, spacing):

        if len(values) == 0:
            return []

        if self.mUnit == 'DateTime':
            values64 = datetime64(np.asarray(values))
            v_min, v_max = min(values64), max(values64)
            if v_min < v_max:
                fmt = '%Y'
                for tscale in ['Y', 'M', 'D', 'h', 'm', 's', 'ms']:
                    scale_type = f'datetime64[{tscale}]'
                    rng = v_max.astype(scale_type) - v_min.astype(scale_type)
                    nscale_units = rng.astype(int)
                    if nscale_units > 0:
                        s = ""
                        break

                if tscale == 'Y':
                    fmt = '%Y'
                elif tscale == 'M':
                    fmt = '%Y-%m'
                elif tscale == 'D':
                    fmt = '%Y-%m-%d'
                elif tscale == 'h':
                    fmt = '%H:%M'
                elif tscale == 's':
                    fmt = '%H:%M:%S'
                else:
                    fmt = '%S.%f'
                self.mDateTimeFormat = fmt

            strns = []
            for v in values64:
                dt = v.astype(object)
                if isinstance(dt, datetime.datetime):
                    strns.append(dt.strftime(self.mDateTimeFormat))
                else:
                    strns.append('')
            return strns
        else:
            return super(SpectralXAxis, self).tickStrings(values, scale, spacing)

    def setUnit(self, unit: Union[str, UnitWrapper], labelName: str = None):
        """
        Sets the unit of this axis
        :param unit: str
        :param labelName: str, defaults to unit
        """
        if isinstance(unit, UnitWrapper):
            unit = unit.unit
        assert unit is None or isinstance(unit, str)
        self.mUnit = unit

        if isinstance(labelName, str):
            self.setLabel(labelName)
        else:
            self.setLabel(unit)

    def unit(self) -> str:
        """
        Returns the unit set for this axis.
        :return:
        """
        return self.mUnit


class SpectralProfilePlotLegend(pg.LegendItem):
    anchorChanged = pyqtSignal(int, int)

    def __init__(self, *args, offset=(-1, 10), max_items=256, **kwds):
        super().__init__(*args, offset=offset, **kwds)
        self.mMaxItems = int(max_items)

    def anchor(self, *args, **kwds):
        super().anchor(*args, **kwds)

        pt = self.__dict__.get('_GraphicsWidgetAnchor__offset', None)
        if pt:
            self.anchorChanged.emit(int(pt[0]), int(pt[1]))

    def addItem(self, item, name):
        if len(self.items) < self.mMaxItems:
            super().addItem(item, name)


class SpectralProfilePlotItem(pg.PlotItem):
    sigPopulateContextMenuItems = pyqtSignal(SignalObjectWrapper)

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotItem, self).__init__(*args, **kwds)

        # self.addLegend()
        self.mTempList = []

    def addLegend(self, *args, **kwargs) -> SpectralProfilePlotLegend:

        if self.legend is None:
            self.legend = SpectralProfilePlotLegend(*args, **kwargs)
            self.legend.setParentItem(self.vb)

            # add existing items
            for item in self.items:
                if isinstance(item, SpectralProfilePlotDataItem) and item.name() != '':
                    self.legend.addItem(item, name=item.name())

        return self.legend

    def removeLegend(self):
        if self.legend and self.legend.parentItem():
            self.legend.opts['offset'] = None
            self.legend.parentItem().removeItem(self.legend)
            self.legend = None

    def getContextMenus(self, event):
        wrapper = SignalObjectWrapper([])
        self.sigPopulateContextMenuItems.emit(wrapper)
        self.mTempList.clear()
        self.mTempList.append(wrapper.wrapped_object)
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

        if isinstance(refItem, pg.PlotDataItem):
            # configure curve for this plot
            (alpha, auto) = self.alphaState()

            for item in items:
                item.setAlpha(alpha, auto)
                item.setFftMode(self.ctrl.fftCheck.isChecked())
                item.setDownsampling(*self.downsampleMode())
                item.setClipToView(self.clipToViewMode())
                item.setPointMode(self.pointMode())

            # Hide older plots if needed
            self.updateDecimation()

            # Add to average if needed
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
            except ValueError:
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


class SpectralViewBox(pg.ViewBox):
    """
    Subclass of PyQgtGraph ViewBox

    """

    def __init__(self, parent=None):
        """
        Constructor of the CustomViewBox
        """
        super().__init__(parent, enableMenu=True)

        # self.mCurrentCursorPosition: Tuple[int, int] = (0, 0)
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
        # menuOtherSettings.addAction(self.mOptionMaxNumberOfProfiles)
        # menuOtherSettings.addAction(self.mOptionShowSelectedProfilesOnly)
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
                scene.addItem(item)  # Necessary due to Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
                item.setParentItem(self.childGroup)
        if not ignoreBounds:
            self.addedItems.extend(pdis)
        # self.updateAutoRange()


MouseClickData = collections.namedtuple('MouseClickData', ['idx', 'xValue', 'yValue', 'pxDistance', 'pdi'])

FEATURE_ID = int
FIELD_INDEX = int
MODEL_NAME = str
X_UNIT = str
PLOT_DATA_KEY = Tuple[FEATURE_ID, FIELD_INDEX, X_UNIT]
VISUALIZATION_KEY = Tuple[QStandardItem, FEATURE_ID, FIELD_INDEX, X_UNIT]


class SpectralProfilePlotDataItem(pg.PlotDataItem):
    """
    A pyqtgraph.PlotDataItem to plot a SpectralProfile
    """
    sigProfileClicked = pyqtSignal(MouseClickData)

    def __init__(self):
        super().__init__()

        # self.curve.sigClicked.connect(self.curveClicked)
        # self.scatter.sigClicked.connect(self.scatterClicked)
        self.mCurveMouseClickNativeFunc = self.curve.mouseClickEvent
        self.curve.mouseClickEvent = self.onCurveMouseClickEvent
        self.scatter.sigClicked.connect(self.onScatterMouseClicked)
        self.mVisualizationKey: Optional[VISUALIZATION_KEY] = None

        self.mIsSelected: bool = False
        self.mLayerID: Optional[str] = None
        self.mFeatureID: Optional[int] = None
        self.mField: Optional[str] = None

    def setProfileData(self,
                       plot_data: dict,
                       plot_style: PlotStyle,
                       showBadBands: bool = True,
                       sortBands: bool = False,
                       zValue: int = None,
                       label: str = None,
                       tooltip: str = None):

        y = plot_data.get('y')

        if y is None:
            self.clear()
            return

        x = plot_data.get('x', list(range(len(y))))

        linePen = pg.mkPen(plot_style.linePen)
        symbolPen = pg.mkPen(plot_style.markerPen)
        symbolBrush = pg.mkBrush(plot_style.markerBrush)

        symbol = plot_style.markerSymbol
        symbolSize = plot_style.markerSize

        if isinstance(x[0], (datetime.date, datetime.datetime)):
            x = np.asarray(x, dtype=np.datetime64)

        # replace None by NaN
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        if sortBands:
            idx = np.argsort(x)
            x = x[idx]
            y = y[idx]

        if not showBadBands and 'bbl' in plot_data.keys():
            valid = np.array(plot_data['bbl'], dtype=float) > 0
            valid = valid & np.isfinite(valid)
            y = np.where(valid, y, np.nan)

        connect = np.isfinite(x) & np.isfinite(y)

        self.setData(x=x, y=y, z=zValue,
                     name=label,
                     connect=connect,
                     pen=linePen,
                     symbol=symbol,
                     symbolPen=symbolPen,
                     symbolBrush=symbolBrush,
                     symbolSize=symbolSize)

        self.setToolTip(tooltip)
        self.curve.setToolTip(tooltip)
        self.scatter.setToolTip(tooltip)

    def setPlotStyle(self, plotStyle: PlotStyle):
        assert isinstance(plotStyle, PlotStyle)

        self.opts['pen'] = pg.mkPen(plotStyle.linePen)
        self.opts['symbol'] = plotStyle.markerSymbol
        self.opts['symbolPen'] = pg.mkPen(plotStyle.markerPen)
        self.opts['symbolBrush'] = pg.mkBrush(plotStyle.markerBrush)
        self.opts['symbolSize'] = plotStyle.markerSize
        self.updateItems(styleUpdate=True)

    def onCurveMouseClickEvent(self, ev):
        self.mCurveMouseClickNativeFunc(ev)

        if ev.accepted:
            idx, x, y, pxDistance = self.closestDataPoint(ev.pos())
            data = MouseClickData(idx=idx, xValue=x, yValue=y, pxDistance=pxDistance, pdi=self)
            self.sigProfileClicked.emit(data)

    def onScatterMouseClicked(self, pts: pg.ScatterPlotItem):

        if isinstance(pts, pg.ScatterPlotItem):
            pdi = pts.parentItem()
            if isinstance(pdi, SpectralProfilePlotDataItem):
                pt = pts.ptsClicked[0]
                i = pt.index()
                data = MouseClickData(idx=i, xValue=pdi.xData[i], yValue=pdi.yData[i], pxDistance=0, pdi=self)
                self.sigProfileClicked.emit(data)

    def setVisualizationKey(self, key: VISUALIZATION_KEY):
        self.mVisualizationKey = key

    def visualizationKey(self) -> VISUALIZATION_KEY:
        return self.mVisualizationKey

    def closestDataPoint(self, pos) -> Tuple[int, float, float, float]:
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

    def plot(self) -> pg.PlotWidget:
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


class PlotUpdateBlocker(object):
    """
    A blocker for plot updates
    """

    def __init__(self, plot: pg.PlotWidget):
        isinstance(plot, pg.PlotWidget)
        self.mPlotWidget: pg.PlotWidget = plot

    def __enter__(self):
        plotItem = self.mPlotWidget.getPlotItem()
        legend: pg.LegendItem = plotItem.legend

        if isinstance(legend, pg.LegendItem):
            legend.size = 'dummy'
        plotItem.getViewBox()._updatingRange = True

    def __exit__(self, exc_type, exc_value, tb):

        plotItem = self.mPlotWidget.getPlotItem()
        legend: pg.LegendItem = plotItem.legend

        vb = plotItem.getViewBox()
        vb._updatingRange = False
        vb.updateAutoRange()

        if isinstance(legend, pg.LegendItem):
            legend.size = None
            legend.updateSize()


class SpectralProfilePlotWidget(pg.PlotWidget):
    """
    A widget to PlotWidget SpectralProfiles
    """

    sigPopulateContextMenuItems = pyqtSignal(SignalObjectWrapper)
    sigPlotDataItemSelected = pyqtSignal(SpectralProfilePlotDataItem, Qt.Modifier)

    def __init__(self, parent=None):

        mViewBox = SpectralViewBox()
        plotItem = SpectralProfilePlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}, viewBox=mViewBox
        )

        super().__init__(parent, plotItem=plotItem)
        self.mProject: QgsProject = QgsProject.instance()
        pi: SpectralProfilePlotItem = self.getPlotItem()
        assert isinstance(pi, SpectralProfilePlotItem) and pi == self.plotItem

        self.mCurrentMousePosition: QPointF = QPointF()
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoScatterPoints: pg.ScatterPlotItem = pg.ScatterPlotItem()
        self.mInfoScatterPoints.sigClicked.connect(self.onInfoScatterClicked)
        self.mInfoScatterPoints.setZValue(9999999)
        self.mInfoScatterPoints.setBrush(self.mCrosshairLineH.pen.color())

        self.mInfoScatterPointHtml: Dict[pg.Point, str] = dict()

        self.mCrosshairLineH.pen.setWidth(2)
        self.mCrosshairLineV.pen.setWidth(2)
        self.mCrosshairLineH.setZValue(9999999)
        self.mCrosshairLineV.setZValue(9999999)
        self.mInfoLabelCursor.setZValue(9999999)

        self.scene().addItem(self.mInfoLabelCursor)
        self.mInfoLabelCursor.setParentItem(self.getPlotItem())

        pi.addItem(self.mCrosshairLineV, ignoreBounds=True)
        pi.addItem(self.mCrosshairLineH, ignoreBounds=True)
        pi.addItem(self.mInfoScatterPoints)
        self.proxy2D = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=100, slot=self.onMouseMoved2D)

        # self.mUpdateTimer = QTimer()
        # self.mUpdateTimer.setInterval(500)
        # self.mUpdateTimer.setSingleShot(False)

        self.mMaxInfoLength: int = 30
        self.mShowCrosshair: bool = True
        self.mShowCursorInfo: bool = True

        # activate option "Visible Data Only" for y-axis to ignore a y-value, when the x-value is nan
        self.setAutoVisible(y=True)

    def setProject(self, project: QgsProject):
        self.mProject = project

    def dragEnterEvent(self, ev: QDragEnterEvent):

        s = ""

    def onProfileClicked(self, data: MouseClickData):
        """
        Slot to react to mouse-clicks on SpectralProfilePlotDataItems
        :param data: MouseClickData
        """
        modifiers = QApplication.keyboardModifiers()

        pdi: SpectralProfilePlotDataItem = data.pdi
        vis, fid, fieldIndex, xUnit = pdi.visualizationKey()
        name = pdi.name()
        if not isinstance(name, str):
            name = ''

        if modifiers == Qt.AltModifier:
            x = data.xValue
            y = data.yValue
            pt = HashablePointF(x, y)
            if pt not in self.mInfoScatterPointHtml.keys():

                if isinstance(pdi, SpectralProfilePlotDataItem):
                    ptColor: QColor = self.mInfoScatterPoints.opts['brush'].color()
                    ptInfo = f'<div ' \
                             f'style="color:{ptColor.name()}; ' \
                             f'text-align:right;">{x} {xUnit},{y} ' \
                             f'{textwrap.shorten(name, width=self.mMaxInfoLength, placeholder="...")}' \
                             f'</div>'

                    self.mInfoScatterPointHtml[pt] = ptInfo

                    existingpoints = self.existingInfoScatterPoints()
                    if pt not in existingpoints:
                        existingpoints.append(pt)
                        self.mInfoScatterPoints.setData(x=[p.x() for p in existingpoints],
                                                        y=[p.y() for p in existingpoints],
                                                        symbol='o')
                        # self.mInfoScatterPoints.setData(x=xcoords, y=ycoords, symbol='o')
                    self.mInfoScatterPoints.setPointsVisible(len(existingpoints) > 0)

        else:
            if isinstance(pdi, SpectralProfilePlotDataItem):
                self.sigPlotDataItemSelected.emit(pdi, modifiers)

        self.updatePositionInfo()

    def existingInfoScatterPoints(self) -> List[HashablePointF]:
        return [HashablePointF(p.pos()) for p in self.mInfoScatterPoints.points()]

    def setShowCrosshair(self, b: bool):
        assert isinstance(b, bool)
        self.mShowCrosshair = b

    def setForegroundColor(self, color: QColor):
        c = QColor(color)

        # set Foreground color
        for axis in self.plotItem.axes.values():
            ai: pg.AxisItem = axis['item']
            if isinstance(ai, pg.AxisItem):
                ai.setPen(c)
                ai.setTextPen(c)
                ai.label.setDefaultTextColor(c)

    def setCrosshairColor(self, color: QColor):

        self.mCrosshairLineH.pen.setColor(QColor(color))
        self.mCrosshairLineV.pen.setColor(QColor(color))

    def setSelectionColor(self, color: QColor):
        self.mInfoScatterPoints.opts['pen'].setColor(QColor(color))
        self.mInfoScatterPoints.opts['brush'].setColor(QColor(color))

    def setInfoColor(self, color: QColor):
        self.mInfoLabelCursor.setColor(QColor(color))

    def setShowCursorInfo(self, b: bool):
        assert isinstance(b, bool)
        self.mShowCursorInfo = b

    def xAxis(self) -> SpectralXAxis:
        return self.plotItem.getAxis('bottom')

    def yAxis(self) -> pg.AxisItem:
        return self.plotItem.getAxis('left')

    def viewBox(self) -> SpectralViewBox:
        return self.plotItem.getViewBox()

    def clearInfoScatterPoints(self):

        self.mInfoScatterPointHtml.clear()
        self.mInfoScatterPoints.setData(x=[], y=[])
        self.mInfoScatterPoints.setPointsVisible(False)

    def onInfoScatterClicked(self, a, spotItems):
        # remove info point
        existing_points = self.existingInfoScatterPoints()
        for spotItem in spotItems:
            if isinstance(spotItem, pg.SpotItem):
                pt = HashablePointF(spotItem.pos())
                if pt in existing_points:
                    existing_points.remove(pt)

        for pt in [p for p in list(self.mInfoScatterPointHtml.keys()) if p not in existing_points]:
            self.mInfoScatterPointHtml.pop(pt)

        self.mInfoScatterPoints.setData(x=[p.x() for p in existing_points],
                                        y=[p.y() for p in existing_points],
                                        symbol='o')
        self.mInfoScatterPoints.setPointsVisible(len(existing_points) > 0)

    def updatePositionInfo(self):
        x, y = self.mCurrentMousePosition.x(), self.mCurrentMousePosition.y()
        positionInfoHtml = '<html><body>'
        if self.xAxis().mUnit == 'DateTime':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(datetime64(x), y)
        elif self.xAxis().mUnit == 'DOY':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(int(x), y)
        else:
            positionInfoHtml += 'x:{:0.5f}\ny:{:0.5f}'.format(x, y)

        for pt, v in self.mInfoScatterPointHtml.items():
            positionInfoHtml += f'{v}'
        positionInfoHtml += '</body></html>'
        self.mInfoLabelCursor.setHtml(positionInfoHtml)

    def spectralProfilePlotDataItems(self) -> List[SpectralProfilePlotDataItem]:
        return [item for item in self.plotItem.listDataItems()
                if isinstance(item, SpectralProfilePlotDataItem)]

    def setWidgetStyle(self, style: PlotWidgetStyle):
        warnings.warn(DeprecationWarning(), stacklevel=2)
        self.mInfoLabelCursor.setColor(style.textColor)
        self.mInfoScatterPoints.opts['pen'].setColor(QColor(style.selectionColor))
        self.mInfoScatterPoints.opts['brush'].setColor(QColor(style.selectionColor))
        self.mCrosshairLineH.pen.setColor(style.crosshairColor)
        self.mCrosshairLineV.pen.setColor(style.crosshairColor)
        self.setBackground(style.backgroundColor)

        # set Foreground color
        for axis in self.plotItem.axes.values():
            ai: pg.AxisItem = axis['item']
            if isinstance(ai, pg.AxisItem):
                ai.setPen(style.foregroundColor)
                ai.setTextPen(style.foregroundColor)
                ai.label.setDefaultTextColor(style.foregroundColor)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

    def onMouseClicked(self, event):
        # print(event[0].accepted)
        s = ""

    def onMouseMoved2D(self, evt):
        pos = evt[0]  # using signal proxy turns original arguments into a tuple

        plotItem = self.getPlotItem()
        assert isinstance(plotItem, SpectralProfilePlotItem)
        vb = plotItem.vb
        assert isinstance(vb, SpectralViewBox)
        if plotItem.sceneBoundingRect().contains(pos) and self.underMouse():
            mousePoint = vb.mapSceneToView(pos)
            self.mCurrentMousePosition = mousePoint

            nearest_item = None
            nearest_index = -1
            nearest_distance = sys.float_info.max
            sx, sy = self.mInfoScatterPoints.getData()

            self.updatePositionInfo()

            s = self.size()
            pos = QPointF(s.width(), 0)
            self.mInfoLabelCursor.setVisible(self.mShowCursorInfo)
            self.mInfoLabelCursor.setPos(pos)

            self.mCrosshairLineH.setVisible(self.mShowCrosshair)
            self.mCrosshairLineV.setVisible(self.mShowCrosshair)
            self.mCrosshairLineV.setPos(mousePoint.x())
            self.mCrosshairLineH.setPos(mousePoint.y())
        else:
            vb.setToolTip('')
            self.mCrosshairLineH.setVisible(False)
            self.mCrosshairLineV.setVisible(False)
            self.mInfoLabelCursor.setVisible(False)
