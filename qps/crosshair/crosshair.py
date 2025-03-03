# -*- coding: utf-8 -*-
# noinspection PyPep8Naming

"""
***************************************************************************
    crosshair.py - A Crosshair for the QgsMapCanvas
    -----------------------------------------------------------------------
    begin                : <month and year of creation>
    copyright            : (C) <year> <creator>
    email                : <main address>

    Believe it or not, this module was inspired by the
    ConterStrike CS:GO Crosshair Generator https://tools.dathost.net/

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import math
import pathlib
import warnings
from typing import Union

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QLineF, QPointF, Qt, QRectF, QSizeF
from qgis.PyQt.QtGui import QFont, QColor, QPen, QBrush, QPolygonF, QFontMetrics
from qgis.PyQt.QtWidgets import QHBoxLayout, QPushButton, QDialogButtonBox, QDialog, QWidget
from qgis.core import QgsRectangle, QgsCoordinateReferenceSystem, QgsPointXY, QgsDistanceArea, QgsRasterLayer
from qgis.core import QgsUnitTypes, QgsCoordinateTransform, Qgis, QgsCsException
from qgis.gui import QgsMapCanvas, QgsDialog, QgsMapCanvasItem
from ..utils import loadUi


class CrosshairStyle(object):
    """
    Defines the style settings of a CrossHair
    """

    def __init__(self, **kwds):
        self.mColor = QColor.fromRgb(255, 0, 0, 255)
        self.mThickness = 1  # in px
        self.mSize = 1.0  # normalized
        self.mGap = 0.05  # normalized
        self.mShowDot = True
        self.mDotSize = 1  # in px
        self.mSizePixelBorder = 1
        self.mShow = True
        self.mShowPixelBorder = True
        self.mShowDistanceMarker = True
        self.mShowDistanceLabel = True

    def setColor(self, color: Union[str, QColor]):
        """
        Sets the crosshair color
        :param color: QCoolor
        :return:
        """
        self.mColor = QColor(color)

    def setSize(self, size):
        self.mSize = self._normalize(size)

    def setDotSize(self, size):
        assert size >= 0
        self.mDotSize = size

    def setThickness(self, size):
        """
        Crosshair thickness in px
        :param size:
        :return:
        """
        assert size >= 0
        self.mThickness = size

    def setShowPixelBorder(self, b: bool):
        """
        Sets if the pixel border of underlying raster layer wil be drawn
        :param b:
        :return:
        """
        assert isinstance(b, bool)
        self.mShowPixelBorder = b

    def setGap(self, gapSize):
        """
        Set gap size in % [0, 100] or normalized coordinates [0,1]
        :param gapSize:
        :return:
        """
        self.mGap = self._normalize(gapSize)

    def setShowDistanceMarker(self, b):
        assert isinstance(b, bool)
        self.mShowDistanceMarker = b

    def _normalize(self, size):
        assert size >= 0 and size <= 100
        size = float(size)
        if size > 1:
            size /= 100
        return size

    def setShowDot(self, b):
        assert isinstance(b, bool)
        self.mShowDot = b

    def setShow(self, b):
        warnings.warn('MapCanvas.setShow was replaced by .setVisibility(b:bool)', DeprecationWarning, stacklevel=2)
        assert isinstance(b, bool)
        self.mShow = b

    def setVisibility(self, b: bool):
        assert isinstance(b, bool)
        self.mShow = b


class CrosshairMapCanvasItem(QgsMapCanvasItem):

    def __init__(self, mapCanvas):
        assert isinstance(mapCanvas, QgsMapCanvas)
        super(CrosshairMapCanvasItem, self).__init__(mapCanvas)

        self.mCanvas = mapCanvas
        self.mRasterGridLayer = None
        self.mSizePixelBox = 0
        self.mSizePixelBox = 1
        self.mShow = False
        self.mCrosshairStyle = CrosshairStyle()
        self.mCrosshairStyle.setVisibility(False)
        self.setCrosshairStyle(self.mCrosshairStyle)
        self.mPosition = None

    def setPosition(self, point: QgsPointXY):
        """
        Sets the point on which the Crosshair will be shown.
        :param point: QgsPointXY
        """
        # print('set position')
        self.mPosition = point
        self.mCanvas.update()

    def crosshairStyle(self) -> CrosshairStyle:
        """
        Returns the crosshair style
        :return: CrosshairStyle
        """
        return self.mCrosshairStyle

    def setVisibility(self, b: bool):
        """
        Sets the visibility of a Crosshair
        :param b:
        :return:
        """
        assert isinstance(b, bool)
        old = self.mShow
        self.mShow = b
        self.mCrosshairStyle.setVisibility(b)
        if old != b:
            self.mCanvas.update()

    def visibility(self) -> bool:
        """Returns the Crosshair visibility"""
        return self.mShow

    def setRasterGridLayer(self, qgsRasterLayer: QgsRasterLayer):
        """
        Sets the QgsRasterLayer with the raster grid to show
        :param qgsRasterLayer:
        :return:
        """

        if qgsRasterLayer == self.mRasterGridLayer:
            return

        if isinstance(self.mRasterGridLayer, QgsRasterLayer):
            self.mRasterGridLayer.willBeDeleted.disconnect(self.onLayerWillBeDeleted)

        if isinstance(qgsRasterLayer, QgsRasterLayer):
            self.mRasterGridLayer = qgsRasterLayer
            self.mRasterGridLayer.willBeDeleted.connect(self.onLayerWillBeDeleted)
        else:
            self.mRasterGridLayer = None

    def onLayerWillBeDeleted(self):
        """
        Removes the reference to the map layer
        :return:
        :rtype:
        """
        self.mRasterGridLayer = None

    def rasterGridLayer(self) -> QgsRasterLayer:
        """
        Returns the raster grid layer
        :return: QgsRasterLayer
        """
        return self.mRasterGridLayer

    def setPixelBox(self, nPx: int):
        """
        Sets the box size of the center box
        :param nPx: number of pixel around, need to an odd integer number 1,3, ...
        """
        assert nPx >= 0
        assert nPx == 1 or nPx % 3 == 0, 'Size of pixel box must be an odd integer value (1,3,5...)'
        self.mSizePixelBox = nPx

    def setCrosshairStyle(self, crosshairStyle: CrosshairStyle):
        """
        Sets the CrosshairStyle
        :param crosshairStyle: CrosshairStyle
        :return:
        """
        assert isinstance(crosshairStyle, CrosshairStyle)
        self.mCrosshairStyle = crosshairStyle

        # apply style
        self.mCanvas.update()
        # self.updateCanvas()

    def paint(self, painter, QStyleOptionGraphicsItem=None, QWidget_widget=None):
        """
        Paints the crosshair
        :param painter:
        :param QStyleOptionGraphicsItem:
        :param QWidget_widget:
        :return:
        """

        if isinstance(self.mPosition, QgsPointXY) and self.mShow and self.mCrosshairStyle.mShow:
            # paint the crosshair
            crs: QgsCoordinateReferenceSystem = self.mCanvas.mapSettings().destinationCrs()

            size = self.mCanvas.size()
            m2p = self.mCanvas.mapSettings().mapToPixel()
            centerGeo = self.mPosition

            if not self.mCanvas.extent().contains(centerGeo):
                return

            centerPx = self.toCanvasCoordinates(centerGeo)

            x0 = centerPx.x() * (1.0 - self.mCrosshairStyle.mSize)
            y0 = centerPx.y() * (1.0 - self.mCrosshairStyle.mSize)
            x1 = size.width() - x0
            y1 = size.height() - y0
            gap = min([centerPx.x(), centerPx.y()]) * self.mCrosshairStyle.mGap

            ml = 5  # marker length in pixel, measured from crosshair line
            md = int(round(max([1, self.mCrosshairStyle.mDotSize * 0.5])))

            # this is what we want to draw
            lines = []
            polygons = []

            lines.append(QLineF(x0, centerPx.y(), centerPx.x() - gap, centerPx.y()))
            lines.append(QLineF(x1, centerPx.y(), centerPx.x() + gap, centerPx.y()))
            lines.append(QLineF(centerPx.x(), y0, centerPx.x(), centerPx.y() - gap))
            lines.append(QLineF(centerPx.x(), y1, centerPx.x(), centerPx.y() + gap))

            if self.mCrosshairStyle.mShowDistanceMarker and crs.isValid():
                if Qgis.version() > '3.24':
                    crsLL = crs.toGeographicCrs()
                else:
                    crsLL = QgsCoordinateReferenceSystem('EPSG:4326')

                if crsLL.isValid():
                    transformContext = self.mCanvas.mapSettings().transformContext()
                    distanceArea = QgsDistanceArea()
                    distanceArea.setSourceCrs(crs, transformContext)
                    distanceArea.setEllipsoid(crs.ellipsoidAcronym())

                    extent = self.mCanvas.extent()

                    orientation = Qt.AlignLeft
                    if centerGeo.x() - extent.xMinimum() > 0.2 * extent.width():
                        orientation = Qt.AlignLeft
                        x0_thickmark = QgsPointXY(centerGeo.x() - 0.5 * (centerGeo.x() - extent.xMinimum()),
                                                  centerGeo.y())
                    else:
                        orientation = Qt.AlignRight
                        x0_thickmark = QgsPointXY(centerGeo.x() + 0.5 * (extent.xMaximum() - centerGeo.x()),
                                                  centerGeo.y())

                    x1 = QgsPointXY(centerGeo.x(), centerGeo.y())
                    try:
                        example_distance = distanceArea.measureLine(x0_thickmark, x1)
                        bearing = distanceArea.bearing(x1, x0_thickmark)
                        nice_distance = nicePredecessor(example_distance)
                    except QgsCsException:
                        bearing = float('Inf')

                    # print((example_distance, pred))
                    # rad = -90 * math.pi / 180
                    # print(f'{rad}\n{bearing}')
                    x0 = None
                    if crs.isValid() \
                            and distanceArea.lengthUnits() == QgsUnitTypes.DistanceMeters \
                            and math.isfinite(bearing):
                        transE = QgsCoordinateTransform(crs, crsLL, transformContext)
                        try:
                            e1 = transE.transform(x1)
                            # need a point with x = lat, y = lon
                            if not crsLL.hasAxisInverted():
                                # e0 = distanceArea.computeSpheroidProject(
                                #    QgsPointXY(e1.y(), e1.x()), nice_distance, bearing)
                                # e0 = QgsPointXY(e0.y(), e0.x())
                                e0 = distanceArea.computeSpheroidProject(e1, nice_distance, bearing)
                            else:
                                e0 = distanceArea.computeSpheroidProject(e1, nice_distance, bearing)
                            x0 = transE.transform(e0, Qgis.TransformDirection.Reverse)
                        except QgsCsException as ex:
                            s = ""
                            pass

                    if isinstance(x0, QgsPointXY):
                        # anchor point
                        pt = m2p.transform(x0)

                        line = QLineF(pt.x(), pt.y() - ml, pt.x(), pt.y() + ml)
                        lines.append(line)

                        if self.mCrosshairStyle.mShowDistanceLabel:
                            painter.setFont(QFont('Courier', pointSize=10))
                            font = painter.font()
                            ptLabel = QPointF(pt.x(), pt.y() + (ml + font.pointSize() + 3))

                            labelText = QgsDistanceArea.formatDistance(nice_distance, 0, distanceArea.lengthUnits())
                            pen = QPen(Qt.SolidLine)
                            pen.setWidth(self.mCrosshairStyle.mThickness)
                            pen.setColor(self.mCrosshairStyle.mColor)

                            brush = self.mCanvas.backgroundBrush()
                            c = brush.color()
                            c.setAlpha(170)
                            brush.setColor(c)
                            painter.setBrush(brush)
                            painter.setPen(Qt.NoPen)
                            fm = QFontMetrics(font)
                            backGroundSize = QSizeF(fm.size(Qt.TextSingleLine, labelText))
                            backGroundSize = QSizeF(backGroundSize.width() + 3, -1 * (backGroundSize.height() + 3))
                            backGroundPos = QPointF(ptLabel.x() + 1, ptLabel.y() + 3)
                            ptText = QPointF(ptLabel.x() + 3, ptLabel.y())
                            # backGroundPos = QPointF(ptLabel.x() - 3, ptLabel.y())
                            background = QPolygonF(QRectF(backGroundPos, backGroundSize))
                            painter.drawPolygon(background)
                            painter.setPen(pen)
                            painter.drawText(ptText, labelText)

            if self.mCrosshairStyle.mShowDot:
                p = QRectF()
                p.setTopLeft(QPointF(centerPx.x() - md,
                                     centerPx.y() + md))
                p.setBottomRight(QPointF(centerPx.x() + md,
                                         centerPx.y() - md))

                p = QPolygonF(p)
                polygons.append(p)

            if self.mCrosshairStyle.mShowPixelBorder:
                lyr = self.rasterGridLayer()

                if isinstance(lyr, QgsRasterLayer):

                    ns = lyr.width()  # ns = number of samples = number of image columns
                    nl = lyr.height()  # nl = number of lines
                    ex = lyr.extent()
                    xres = lyr.rasterUnitsPerPixelX()
                    yres = lyr.rasterUnitsPerPixelY()

                    ms = self.mCanvas.mapSettings()
                    centerPxLyr = ms.mapToLayerCoordinates(lyr, centerGeo)

                    # get center pixel pixel index
                    pxX = int(np.floor((centerPxLyr.x() - ex.xMinimum()) / xres).astype(int))
                    pxY = int(np.floor((ex.yMaximum() - centerPxLyr.y()) / yres).astype(int))

                    def px2LayerGeo(x, y):
                        x2 = ex.xMinimum() + (x * xres)
                        y2 = ex.yMaximum() - (y * yres)
                        return QgsPointXY(x2, y2)

                    func = lambda x, y: self.toCanvasCoordinates(
                        ms.layerToMapCoordinates(lyr,
                                                 px2LayerGeo(x, y)))
                    lyrCoord2CanvasPx = func
                    if 0 <= pxX < ns and 0 <= pxY < nl:
                        # get pixel edges in map canvas coordinates

                        lyrGeo = px2LayerGeo(pxX, pxY)
                        mapGeo = ms.layerToMapCoordinates(lyr, lyrGeo)
                        canCor = self.toCanvasCoordinates(mapGeo)

                        ul = lyrCoord2CanvasPx(pxX, pxY)
                        ur = lyrCoord2CanvasPx(pxX + 1, pxY)
                        lr = lyrCoord2CanvasPx(pxX + 1, pxY + 1)
                        ll = lyrCoord2CanvasPx(pxX, pxY + 1)

                        pixelBorder = QPolygonF()
                        pixelBorder.append(ul)
                        pixelBorder.append(ur)
                        pixelBorder.append(lr)
                        pixelBorder.append(ll)
                        pixelBorder.append(ul)
                        polygons.append(pixelBorder)

            pen = QPen(Qt.SolidLine)
            pen.setWidth(self.mCrosshairStyle.mThickness)
            pen.setColor(self.mCrosshairStyle.mColor)
            pen.setBrush(self.mCrosshairStyle.mColor)
            brush = QBrush(Qt.NoBrush)
            brush.setColor(QColor(self.mCrosshairStyle.mColor))
            brush.color().setAlpha(0)
            painter.setBrush(brush)
            painter.setPen(pen)
            for p in polygons:
                painter.drawPolygon(p)
            for p in lines:
                painter.drawLine(p)


def nicePredecessor(number):
    mul = -1 if number < 0 else 1
    number = np.abs(number)
    if number > 1.0:
        exp = np.fix(np.log10(number))
        # normalize to [0.0,1.0]
        l2 = number / 10 ** (exp)
        m = np.fix(l2)
        rest = l2 - m
        if rest >= 0.5:
            m += 0.5
        return mul * m * 10 ** exp

    elif 1.0 > number > 0:
        exp = np.fix(np.log10(number))
        # normalize to [0.0,1.0]
        m = number / 10 ** (exp - 1)
        if m >= 5:
            m = 5.0
        else:
            m = 1.0
        return mul * m * 10 ** (exp - 1)
    else:
        return 0.0


class CrosshairWidget(QWidget):
    """
    A widget to configure a CrossHair
    """
    sigCrosshairStyleChanged = pyqtSignal(CrosshairStyle)

    def __init__(self, title='<#>', parent=None):
        super(CrosshairWidget, self).__init__(parent)
        loadUi(pathlib.Path(__file__).parent / 'crosshairwidget.ui', self)

        self.mapCanvas.setExtent(QgsRectangle(0, 0, 1, 1))  #

        self.mapCanvasItem = CrosshairMapCanvasItem(self.mapCanvas)
        self.mapCanvasItem.setVisibility(True)
        self.mapCanvasItem.setPosition(self.mapCanvas.center())

        self.btnCrosshairColor.colorChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairAlpha.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairThickness.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxCrosshairGap.valueChanged.connect(self.refreshCrosshairPreview)
        self.spinBoxDotSize.valueChanged.connect(self.refreshCrosshairPreview)
        self.cbCrosshairShowDot.toggled.connect(self.refreshCrosshairPreview)
        self.cbShowPixelBoundaries.toggled.connect(self.refreshCrosshairPreview)
        self.cbShowDistanceMarker.toggled.connect(self.refreshCrosshairPreview)
        self.refreshCrosshairPreview()

    def copyCanvas(self, mapCanvas: QgsMapCanvas):
        """
        Copys layers,crs, extent and background color
        :param mapCanvas:
        :return:
        """
        assert isinstance(mapCanvas, QgsMapCanvas)
        # copy layers
        canvas = self.mapCanvas
        lyrs = mapCanvas.layers()
        canvas.setLayers(lyrs)
        canvas.setDestinationCrs(mapCanvas.mapSettings().destinationCrs())
        canvas.setExtent(mapCanvas.extent())
        canvas.setCenter(mapCanvas.center())
        canvas.setCanvasColor(mapCanvas.canvasColor())
        self.mapCanvasItem.setPosition(canvas.center())
        self.refreshCrosshairPreview()

    def setCanvasColor(self, color):
        self.mapCanvas.setBackgroundColor(color)
        self.btnMapCanvasColor.colorChanged.connect(self.onMapCanvasColorChanged)

    def onMapCanvasColorChanged(self, color):
        self.sigMapCanvasColorChanged.emit(color)
        self.refreshCrosshairPreview()

    def mapCanvasColor(self):
        return self.btnMapCanvasColor.color()

    def refreshCrosshairPreview(self, *args):
        style = self.crosshairStyle()
        self.mapCanvasItem.setVisibility(True)
        self.mapCanvasItem.setCrosshairStyle(style)
        self.mapCanvasItem.updateCanvas()
        self.sigCrosshairStyleChanged.emit(style)

    def setCrosshairStyle(self, style):
        assert isinstance(style, CrosshairStyle)
        self.btnCrosshairColor.setColor(style.mColor)
        self.spinBoxCrosshairAlpha.setValue(style.mColor.alpha())
        self.spinBoxCrosshairThickness.setValue(style.mThickness)
        self.spinBoxCrosshairSize.setValue(int(style.mSize * 100))
        self.spinBoxCrosshairGap.setValue(int(style.mGap * 100))
        self.spinBoxDotSize.setValue(style.mDotSize)
        self.cbCrosshairShowDot.setChecked(style.mShowDot)
        self.cbShowPixelBoundaries.setChecked(style.mShowPixelBorder)
        self.cbShowDistanceMarker.setChecked(style.mShowDistanceMarker)

    def crosshairStyle(self):
        style = CrosshairStyle()
        c = self.btnCrosshairColor.color()
        c.setAlpha(self.spinBoxCrosshairAlpha.value())
        style.setColor(c)
        style.setThickness(self.spinBoxCrosshairThickness.value())
        style.setSize(self.spinBoxCrosshairSize.value())
        style.setGap(self.spinBoxCrosshairGap.value())
        style.setDotSize(self.spinBoxDotSize.value())
        style.setShowDot(self.cbCrosshairShowDot.isChecked())
        style.setShowPixelBorder(self.cbShowPixelBoundaries.isChecked())
        style.setShowDistanceMarker(self.cbShowDistanceMarker.isChecked())
        return style


def getCrosshairStyle(*args, **kwds):
    return CrosshairDialog.getCrosshairStyle(*args, **kwds)


class CrosshairDialog(QgsDialog):

    @staticmethod
    def getCrosshairStyle(*args, **kwds):
        """
        Opens a CrosshairDialog.
        :param args:
        :param kwds:
        :return: specified CrosshairStyle if accepted, else None
        """
        d = CrosshairDialog(*args, **kwds)
        d.exec()
        if d.result() == QDialog.Accepted:
            return d.crosshairStyle()
        else:

            return None

    def __init__(self, parent=None, crosshairStyle=None, mapCanvas=None, title='Specify Crosshair'):
        super(CrosshairDialog, self).__init__(parent=parent,
                                              buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.w = CrosshairWidget(parent=self)
        self.setWindowTitle(title)
        self.btOk = QPushButton('Ok')
        self.btCancel = QPushButton('Cance')
        buttonBar = QHBoxLayout()
        # buttonBar.addWidget(self.btCancel)
        # buttonBar.addWidget(self.btOk)
        layout = self.layout()
        layout.addWidget(self.w)
        layout.addLayout(buttonBar)
        # self.setLayout(l)

        if isinstance(mapCanvas, QgsMapCanvas):
            self.copyCanvas(mapCanvas)

        if isinstance(crosshairStyle, CrosshairStyle):
            self.setCrosshairStyle(crosshairStyle)

    def crosshairStyle(self) -> CrosshairStyle:
        """
        Returns the specfied CrosshairStyle
        :return: CrosshairStyle
        """
        return self.w.crosshairStyle()

    def setCrosshairStyle(self, crosshairStyle: CrosshairStyle):
        """
        Sets a new Crosshair Style
        :param crosshairStyle: CrosshairStyle
        :return:
        """
        assert isinstance(crosshairStyle, CrosshairStyle)
        self.w.setCrosshairStyle(crosshairStyle)

    def copyCanvas(self, mapCanvas: QgsMapCanvas):
        """
        Copies the map canvas layers and background color
        :param mapCanvas: QgsMapCanvas
        :return:
        """
        self.w.copyCanvas(mapCanvas)
