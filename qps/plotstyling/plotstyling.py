# -*- coding: utf-8 -*-
"""
***************************************************************************
    <file name> - <short description>
    -----------------------------------------------------------------------
    begin                : 2019-01-11
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

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
# noinspection PyPep8Naming
import copy
import enum
import json
import sys
import warnings
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from qgis.PyQt.QtCore import pyqtSignal, QByteArray, QDataStream, QIODevice, QMimeData, QObject, QSize, Qt
from qgis.PyQt.QtGui import QBrush, QClipboard, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QLabel, QMenu, QSpinBox, \
    QToolButton, QVBoxLayout, QWidget, QWidgetAction
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsAction, QgsField, QgsMessageLog, QgsSymbolLayerUtils, QgsVectorLayer
from qgis.gui import QgsColorButton, QgsDialog, QgsEditorConfigWidget, QgsEditorWidgetFactory, QgsEditorWidgetWrapper, \
    QgsGui, QgsPenStyleComboBox, QgsSearchWidgetWrapper
from ..pyqtgraph import pyqtgraph as pg
from ..pyqtgraph.pyqtgraph import mkBrush, mkPen
from ..pyqtgraph.pyqtgraph.graphicsItems.ScatterPlotItem import drawSymbol, renderSymbol
from ..qgisenums import QMETATYPE_QSTRING
from ..utils import findMapLayer, loadUi, SignalBlocker

DEBUG = False

MODULE_IMPORT_PATH = None
XMLTAG_PLOTSTYLENODE = 'PlotStyle'
_PLOTSTYLE_EDITOR_WIDGET_FACTORY = None
EDITOR_WIDGET_REGISTRY_KEY = 'Plot Settings'
MIMEDATA_PLOTSTYLE = 'application/qps.plotstyle'

for name, module in sys.modules.items():
    if hasattr(module, '__file__') and module.__file__ == __file__:
        MODULE_IMPORT_PATH = name
        break


def log(msg: str):
    if DEBUG:
        QgsMessageLog.logMessage(msg, 'plotstyling.py')


def getFirst(input):
    if isinstance(input, (list, np.ndarray)):
        return input[0]
    else:
        return input


def pens_equal(p1, p2):
    assert isinstance(p1, QPen)
    assert isinstance(p2, QPen)
    if p1 == p2:
        return True
    elif p1.brush() != p2.brush():
        return False
    elif p1.capStyle() != p2.capStyle():
        return False
    elif p1.color() != p2.color():
        return False
    elif p1.dashPattern() != p2.dashPattern():
        return False
    elif p1.dashOffset() != p2.dashOffset():
        return False
    elif p1.isCosmetic() != p2.isCosmetic():
        return False
    elif p1.isSolid() != p2.isSolid():
        return False
    elif p1.joinStyle() != p2.joinStyle():
        return False
    elif p1.miterLimit() != p2.miterLimit():
        return False
    elif p1.style() != p2.style():
        return False
    elif p1.width() != p2.width():
        return False
    elif p1.widthF() != p2.widthF():
        return False
    else:
        # it is totally unclear why the inital p1 == p2 returns False!!!
        return True


class MarkerSymbol(enum.Enum):
    No_Symbol = None
    Circle = 'o'
    Triangle = Triangle_Down = 't'
    Triangle_Up = 't1'
    Triangle_Right = 't2'
    Triangle_Left = 't3'
    Pentagon = 'p'
    Hexagon = 'h'
    Square = 's'
    Star = 'star'
    Plus = '+'
    Diamond = 'd'
    Cross = 'x'
    ArrowUp = 'arrow_up'
    ArrowRight = 'arrow_right'
    ArrowDown = 'arrow_down'
    ArrowLeft = 'arrow_left'
    VerticalLine = '|'
    LowLine = '_'
    Crosshair = 'crosshair'

    @staticmethod
    def decode(input: Any) -> 'MarkerSymbol':
        """
        Tries to match a MarkerSymbol with any input
        :param input: any
        :return: MarkerSymbol
        """
        # if input == 'Triangle':
        #    return MarkerSymbol.Triangle_Down

        if isinstance(input, MarkerSymbol):
            return input

        if isinstance(input, str):
            input = str(input).replace(' ', '_')

        for s in MarkerSymbol:
            if input in [s.value, s.name, str(s.value)]:
                return s

        raise Exception('Unable to get MarkerSymbol for input "{}"'.format(input))

    @staticmethod
    def icon(symbol):
        symbol = MarkerSymbol.decode(symbol)
        assert isinstance(symbol, MarkerSymbol)
        # print('render {}'.format(symbol.value))
        pen = QPen(Qt.PenStyle.SolidLine)
        pen.setColor(QColor('black'))
        pen.setWidth(0)
        image = renderSymbol(symbol.value, 10, pen, Qt.BrushStyle.NoBrush)
        return QIcon(QPixmap.fromImage(image))

    @staticmethod
    def encode(symbol) -> str:
        """
        Returns a readable name for the marker symbol, e.g. 'Circle'
        :param value: bool, if True, returns a string like '---' instead 'Line'
        :return: str
        """
        assert isinstance(symbol, MarkerSymbol)
        if symbol in [None, 'None']:
            symbol = MarkerSymbol.No_Symbol
        elif isinstance(symbol, str):
            for s in MarkerSymbol:
                if symbol == s.value or symbol.replace(' ', '_') == s.name:
                    symbol = s
                    break

        assert isinstance(symbol, MarkerSymbol), 'cannot encode {} into MarkerSymbol'.format(symbol)
        return symbol.name.replace('_', ' ')


class MarkerSymbolComboBox(QComboBox):

    def __init__(self, *args, **kwds):
        super(MarkerSymbolComboBox, self).__init__(*args, **kwds)
        for symbol in MarkerSymbol:
            icon = MarkerSymbol.icon(symbol)
            text = MarkerSymbol.encode(symbol)
            self.addItem(icon, text, userData=symbol)
        self.setCurrentIndex(1)

    def markerSymbol(self) -> MarkerSymbol:
        return self.currentData(role=Qt.ItemDataRole.UserRole)

    def markerSymbolString(self) -> str:
        return self.markerSymbol().value

    def setMarkerSymbol(self, symbol):
        symbol = MarkerSymbol.decode(symbol)
        for i in range(self.count()):
            if self.itemData(i, role=Qt.ItemDataRole.UserRole) == symbol:
                self.setCurrentIndex(i)
                return symbol
        s = ""

    def iconForMarkerSymbol(self) -> QIcon():
        return MarkerSymbol.icon(self.markerSymbol())


def brush2list(brush: QBrush) -> list:
    return [
        QgsSymbolLayerUtils.encodeColor(brush.color()),
        # setMatrix
        QgsSymbolLayerUtils.encodeBrushStyle(brush.style())
        # texture
        # transform
    ]


def list2brush(t: list) -> QBrush:
    # log('tuple2brush')
    assert len(t) == 2
    brush = QBrush()
    brush.setColor(QgsSymbolLayerUtils.decodeColor(t[0]))
    brush.setStyle(QgsSymbolLayerUtils.decodeBrushStyle(t[1]))
    return brush


def pen2list(pen: QPen) -> list:
    # log('pen2tuple')
    return [
        pen.width(),
        brush2list(pen.brush()),  # 1
        QgsSymbolLayerUtils.encodePenCapStyle(pen.capStyle()),
        QgsSymbolLayerUtils.encodeColor(pen.color()),
        pen.isCosmetic(),
        pen.dashOffset(),  # 5
        pen.dashPattern(),
        QgsSymbolLayerUtils.encodePenJoinStyle(pen.joinStyle()),
        pen.miterLimit(),
        QgsSymbolLayerUtils.encodePenStyle(pen.style())  # 9
    ]


def list2pen(t: list) -> QPen:
    assert len(t) == 10
    pen = QPen()
    pen.setWidth(t[0])
    pen.setBrush(list2brush(t[1]))
    pen.setCapStyle(QgsSymbolLayerUtils.decodePenCapStyle(t[2]))
    pen.setColor(QgsSymbolLayerUtils.decodeColor(t[3]))
    pen.setCosmetic(t[4])
    pen.setDashOffset(t[5])
    pen.setDashPattern(t[6])
    pen.setJoinStyle(QgsSymbolLayerUtils.decodePenJoinStyle(t[7]))
    pen.setMiterLimit(t[8])
    pen.setStyle(QgsSymbolLayerUtils.decodePenStyle(t[9]))
    return pen


def runPlotStyleActionRoutine(layerID, styleField: str, id: int):
    """
    Is applied to a set of layer features to change the plotStyle JSON string stored in styleField
    :param layerID: QgsVectorLayer or vector id
    :param styleField: str, name of string field in layer.fields() to store the PlotStyle
    :param id: feature id of feature for which the QgsAction was called
    """

    layer = findMapLayer(layerID)
    if isinstance(layer, QgsVectorLayer):
        selectedFIDs = layer.selectedFeatureIds()
        if id in selectedFIDs:
            ids = selectedFIDs
        else:
            ids = [id]
        if len(ids) == 0:
            return

        fieldName = styleField
        fieldIndex = layer.fields().lookupField(fieldName)
        style = None
        features = [f for f in layer.getFeatures(ids)]

        for f in features:
            json = f.attribute(fieldName)
            style = PlotStyle.fromJSON(json)
            if isinstance(style, PlotStyle):
                style = PlotStyle.fromDialog(plotStyle=style)
                break
        if isinstance(style, PlotStyle):
            json = style.json()
            b = layer.isEditable()
            layer.startEditing()
            for f in features:
                f.setAttribute(fieldName, json)
                layer.changeAttributeValues(f.id(), {fieldIndex: json})
            if not b:
                layer.commitChanges()
    else:
        print('Unable to find layer "{}"'.format(layerID))


def createSetPlotStyleAction(field, mapLayerStore='QgsProject.instance()'):
    """
    Creates a QgsAction to set the style field of a QgsVectorLayer
    :param field: QgsField , the field to store the serialized PlotStyle
    :param mapLayerStore: str, code handle to access the relevant QgsMapLayer store
    :return: QgsAction
    """
    assert isinstance(field, QgsField)
    assert field.type() == QMETATYPE_QSTRING

    iconPath = ':/qt-project.org/styles/commonstyle/images/standardbutton-clear-128.png'
    pythonCode = """
from {modulePath} import runPlotStyleActionRoutine
layerId = '[% @layer_id %]'
runPlotStyleActionRoutine(layerId, '{styleField}' , [% $id %])
""".format(modulePath=MODULE_IMPORT_PATH, styleField=field.name())

    return QgsAction(QgsAction.ActionType.GenericPython, 'Set PlotStyle', pythonCode, iconPath, True,
                     notificationMessage='msgSetPlotStyle',
                     actionScopes={'Feature'})


class PlotStyle(QObject):
    """
    A class to store PyQtGraph specific plot settings
    """
    sigUpdated = pyqtSignal()

    @staticmethod
    def fromPlotDataItem(pdi: pg.PlotDataItem):
        """
        Reads a PlotDataItems' styling
        :param pdi: PlotDataItem
        """

        ps = PlotStyle()
        ps.setLinePen(pg.mkPen(pdi.opts['pen']))
        ps.setMarkerSymbol(getFirst(pdi.opts['symbol']))
        ps.setMarkerBrush(pg.mkBrush(getFirst(pdi.opts['symbolBrush'])))
        ps.setMarkerPen(pg.mkPen(getFirst(pdi.opts['symbolPen'])))
        ps.markerSize = getFirst(pdi.opts['symbolSize'])
        ps.setVisibility(pdi.isVisible())

        return ps

    def __init__(self, **kwds):
        plotStyle = kwds.get('plotStyle')
        if plotStyle:
            kwds.pop('plotStyle')
        super(PlotStyle, self).__init__()
        self.mCosmeticPens: bool = True

        self.antialias: bool = False

        self.markerSymbol: str = MarkerSymbol.Circle.value
        self.markerSize: int = 5
        self.markerBrush: QBrush = QBrush()
        self.markerBrush.setColor(Qt.GlobalColor.green)
        self.markerBrush.setStyle(Qt.BrushStyle.SolidPattern)

        self.backgroundColor: QColor = QColor(Qt.GlobalColor.black)

        self.markerPen: QPen = QPen()
        self.markerPen.setCosmetic(True)
        self.markerPen.setStyle(Qt.PenStyle.NoPen)
        self.markerPen.setColor(Qt.GlobalColor.white)
        self.markerPen.setWidthF(0)

        self.linePen: QPen = QPen()
        self.linePen.setCosmetic(True)
        self.linePen.setStyle(Qt.PenStyle.NoPen)
        self.linePen.setWidthF(0)
        self.linePen.setColor(QColor(74, 75, 75))

        self.mIsVisible: bool = True

        if plotStyle:
            self.copyFrom(plotStyle)

    def setMarkerSymbol(self, symbol):
        """
        Sets the marker type
        :param symbol:
        :type symbol:
        :return:
        :rtype:
        """
        symbol = getFirst(symbol)
        self.markerSymbol = MarkerSymbol.decode(symbol).value

    def setMarkerPen(self, pen):
        pen = getFirst(pen)
        self.markerPen = mkPen(pen)
        if self.mCosmeticPens:
            self.markerPen.setCosmetic(True)

    def setLinePen(self, pen):
        pen = getFirst(pen)
        self.linePen = mkPen(pen)
        if self.mCosmeticPens:
            self.linePen.setCosmetic(True)

    def setMarkerBrush(self, brush):
        brush = getFirst(brush)
        self.markerBrush = mkBrush(brush)

    def setMarkerColor(self, color: Union[str, QColor]):
        """
        Sets the marker symbol color
        :param color:
        :type color:
        :return:
        :rtype:
        """
        if isinstance(color, (list, np.ndarray)):
            color = color[0]
        self.markerBrush.setColor(pg.mkColor(color))

    def markerColor(self) -> QColor:
        """
        Returns the marker symbol color
        :return:
        :rtype:
        """
        return self.markerBrush.color()

    def setMarkerLinecolor(self, *color: QColor):
        """
        Sets the marker symbols line color
        :return:
        """
        self.markerPen.setColor(QColor(*color))

    def markerLineColor(self) -> QColor:
        """
        Returns the marker symbol line color
        :return: QColor
        """
        return self.markerPen.color()

    def lineWidth(self) -> int:
        """
        Returns the line width in px
        """
        return self.linePen.width()

    def setLineWidth(self, width: int):
        """
        Sets the profile's line in px
        :param width: line width in px
        """
        self.linePen.setWidth(width)

    def setLineStyle(self, style: Qt.PenStyle):
        """
        Sets the profile line style
        """
        self.linePen.setStyle(style)

    def lineColor(self) -> QColor:
        """
        Returns the line color
        :return: QColor
        """
        return self.linePen.color()

    def setBackgroundColor(self, *color):
        self.backgroundColor = QColor(*color)

    def setLineColor(self, *color: Union[QColor, str]):
        """
        Sets the line color
        :param color: QColor
        """
        self.linePen.setColor(QColor(*color))

    def apply(self, pdi: pg.PlotDataItem, updateItem: bool = True, visibility: bool = None):
        """
        Applies this PlotStyle to a PlotDataItem by setting
        the line pen (line type, line color) and the marker/symbol (marker/symbol type,
        marker/symbol pen line and color, marker/symbol brush)

        :param pdi: PlotDataItem
        :param updateItem: if True, will update the PlotDataItem
        :type updateItem:
        :param visibility: use this keyword to overwrite the style's visibility.
        :return:
        :rtype:
        """

        if isinstance(pdi, pg.PlotDataItem):
            pdi.setPen(pg.mkPen(self.linePen))
            pdi.setSymbol(self.markerSymbol)
            pdi.setSymbolPen(pg.mkPen(self.markerPen))
            pdi.setSymbolBrush(pg.mkBrush(self.markerBrush))
            pdi.setSymbolSize(self.markerSize)

        # pdi.opts['pen'] = pg.mkPen(self.linePen)
        # pdi.opts['symbol'] = self.markerSymbol
        # pdi.opts['symbolPen'] = pg.mkPen(self.markerPen)
        # pdi.opts['symbolBrush'] = pg.mkBrush(self.markerBrush)
        # pdi.opts['symbolSize'] = self.markerSize

        if isinstance(visibility, bool):
            pdi.setVisible(visibility)
        else:
            pdi.setVisible(self.mIsVisible)

        if updateItem:
            pdi.updateItems()

    XML_TAG = XMLTAG_PLOTSTYLENODE

    def writeXml(self, node: QDomElement, doc: QDomDocument) -> bool:
        """
        Writes the PlotStyle to a QDomNode
        :param node:
        :param doc:
        :return:
        """

        plotStyleNode = doc.createElement(self.XML_TAG)
        cdata = doc.createCDATASection(self.json().replace('\n', ''))
        plotStyleNode.appendChild(cdata)
        node.appendChild(plotStyleNode)

        return True

    @staticmethod
    def readXml(node: QDomElement, *args):
        """
        Reads the PlotStyle from a QDomElement (XML node)
        :param self:
        :param node:
        :param args:
        :return:
        """
        node = node if node.nodeName() == XMLTAG_PLOTSTYLENODE else node.firstChildElement(XMLTAG_PLOTSTYLENODE)
        if node.isNull():
            return None

        cdata = node.firstChild()
        assert cdata.isCDATASection()
        return PlotStyle.fromJSON(cdata.nodeValue())

    @classmethod
    def fromMap(cls, obj: Dict[str, Any]) -> 'PlotStyle':
        """
        Creates a PlotStyle from a dictionary
        :param map: dict
        :return: PlotStyle
        """
        plotStyle = PlotStyle()

        if 'markerPen' in obj.keys():
            plotStyle.markerPen = list2pen(obj['markerPen'])
        if 'markerBrush' in obj.keys():
            plotStyle.markerBrush = list2brush(obj['markerBrush'])
        if 'markerSymbol' in obj.keys():
            plotStyle.markerSymbol = obj['markerSymbol']
        if 'markerSize' in obj.keys():
            plotStyle.markerSize = obj['markerSize']
        if 'linePen' in obj.keys():
            plotStyle.linePen = list2pen(obj['linePen'])
        if 'isVisible' in obj.keys():
            plotStyle.setVisibility(obj['isVisible'])
        if 'backgroundColor' in obj.keys():
            plotStyle.backgroundColor = QgsSymbolLayerUtils.decodeColor(obj['backgroundColor'])
        # log('END fromJSON')
        if 'antialias' in obj.keys():
            plotStyle.antialias = obj['antialias'] in [True, 1, 'true']
        return plotStyle

    @classmethod
    def fromJSON(cls, jsonString: Optional[str]) -> Optional['PlotStyle']:
        """
        Takes a json string and returns a PlotStyle if any plot-style attribute was set
        see https://www.gdal.org/ogr_feature_style.html for details

        :param jsonString:
        :return: [list-of-PlotStyles], usually of length = 1
        """
        if not isinstance(jsonString, str):
            return None
        try:
            obj = json.loads(jsonString)
            assert isinstance(obj, dict)
            return PlotStyle.fromMap(obj)
        except Exception:
            return None

    @classmethod
    def fromDialog(cls, *args, **kwds) -> Optional['PlotStyle']:
        """
        Selects a PlotStyle from a user dialog
        :param self:
        :param args:
        :param kwds:
        :return: PlotStyle
        """
        return PlotStyleDialog.getPlotStyle(*args, **kwds)

    def json(self) -> str:
        """Returns a JSON representation of this plot style
        """
        # log('START json()')
        dump = json.dumps(self.map(), sort_keys=True, ensure_ascii=False, indent=-1, separators=(',', ':'))
        # log('END json()')
        return dump

    def map(self) -> Dict[str, Any]:
        """
        Returns a dictionary representation of this plot style
        :return: dict
        """
        style = dict()
        style['markerPen'] = pen2list(self.markerPen)
        style['markerBrush'] = brush2list(self.markerBrush)
        style['markerSymbol'] = self.markerSymbol
        style['markerSize'] = self.markerSize
        style['linePen'] = pen2list(self.linePen)
        style['isVisible'] = self.mIsVisible
        style['backgroundColor'] = QgsSymbolLayerUtils.encodeColor(self.backgroundColor)
        style['antialias'] = self.antialias
        return style

    @classmethod
    def fromClipboard(cls) -> Optional['PlotStyle']:
        """
        Copies a style from the clipboard
        :return:
        """
        cb: QClipboard = QApplication.instance().clipboard()
        md = cb.mimeData()
        if isinstance(md, QMimeData):

            try:
                if MIMEDATA_PLOTSTYLE in md.formats():
                    dump = md.data(MIMEDATA_PLOTSTYLE)
                    dump = bytes(dump).decode('utf-8')
                else:
                    dump = md.text()

                return PlotStyle.fromJSON(dump)

            except Exception:
                pass
        return None

    def toClipboard(self):

        txt = self.json()
        dump = QByteArray(txt.encode("utf-8"))

        md = QMimeData()
        md.setData(MIMEDATA_PLOTSTYLE, dump)
        md.setText(txt)

        cb: QClipboard = QApplication.instance().clipboard()
        cb.setMimeData(md)

    def setAntialias(self, b: bool):
        """
        Set the antialias flag
        :param b:
        :return:
        """
        assert isinstance(b, bool)
        self.antialias = b

    def setVisibility(self, b: bool):
        """
        Sets the visibility of a plot item
        :param b: bool
        """
        # log('setVisibility')
        b = bool(b)
        assert isinstance(b, bool)
        old = self.mIsVisible
        self.mIsVisible = b

        if b != old:
            self.update()

    def update(self):
        """
        Calls the sigUpdated signal
        :return:
        """
        self.sigUpdated.emit()

    def isVisible(self) -> bool:
        """
        Visibility of the plot item
        :return: bool
        """
        return self.mIsVisible

    def __copy__(self):
        style = PlotStyle()
        style.copyFrom(self)
        return style

    def clone(self):
        return copy.copy(self)

    def copyFrom(self, plotStyle):
        """
        Copy plot settings from another plot style
        :param plotStyle: PlotStyle
        """
        # log('copyFrom')
        assert isinstance(plotStyle, PlotStyle)

        self.mCosmeticPens = plotStyle.mCosmeticPens

        self.markerSymbol = plotStyle.markerSymbol
        self.markerBrush = QBrush(plotStyle.markerBrush)
        self.markerPen = QPen(plotStyle.markerPen)
        self.markerSize = plotStyle.markerSize
        self.backgroundColor = QColor(plotStyle.backgroundColor)
        self.linePen = QPen(plotStyle.linePen)
        self.antialias = plotStyle.antialias
        self.setVisibility(plotStyle.isVisible())

    def createIcon(self, size=None) -> QIcon:
        """
        Creates a QIcon to show this PlotStyle
        :param size: QSize
        :return: QIcon
        """
        return QIcon(self.createPixmap(size=size))

    def createPixmap(self,
                     size: QSize = None,
                     hline: bool = False,
                     bc: Optional[QColor] = None,
                     antialias: Optional[bool] = None) -> QPixmap:
        """
        Creates a QPixmap to show this PlotStyle
        :param size: QSize
        :return: QPixmap
        """

        if not isinstance(size, QSize):
            size = QSize(60, 60)

        if bc is None:
            bc = self.backgroundColor

        if antialias is None:
            antialias = self.antialias

        pm = QPixmap(size)
        if self.isVisible():
            pm.fill(bc)

            p = QPainter(pm)
            if antialias:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            # draw the line

            p.setPen(self.linePen)

            w, h = pm.width(), pm.height()
            path = QPainterPath()
            if hline:
                xvec = [0.0, 0.5, 1.0]
                yvec = [0.5, 0.5, 0.5]
            else:
                xvec = [0.0, 0.5, 1.0]
                yvec = [0.8, 0.5, 0.7]

            path.moveTo(xvec[0] * w, yvec[0] * h)
            for x, y in zip(xvec, yvec):
                path.lineTo(x * w, y * h)
            p.drawPath(path)
            p.translate(0.5 * pm.width(), 0.5 * pm.height())
            drawSymbol(p, self.markerSymbol, self.markerSize, self.markerPen, self.markerBrush)
            p.end()
        else:
            # transparent background
            pm.fill(QColor(0, 255, 0, 0))
            p = QPainter(pm)
            p.setPen(QPen(QColor(100, 100, 100)))
            p.drawLine(0, 0, pm.width(), pm.height())
            p.drawLine(0, pm.height(), pm.width(), 0)
            p.end()
        return pm

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        if not isinstance(other, PlotStyle):
            return False
        return self.map() == other.map()

    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        result = self.__dict__.copy()

        ba = QByteArray()
        s = QDataStream(ba, QIODevice.OpenModeFlag.WriteOnly)
        s.writeQVariant(self.linePen)
        s.writeQVariant(self.markerPen)
        s.writeQVariant(self.markerBrush)
        result['__pickleStateQByteArray__'] = ba
        result.pop('linePen')
        result.pop('markerPen')
        result.pop('markerBrush')

        return result

    def __setstate__(self, state):
        ba = state['__pickleStateQByteArray__']
        s = QDataStream(ba)
        state['linePen'] = s.readQVariant()
        state['markerPen'] = s.readQVariant()
        state['markerBrush'] = s.readQVariant()
        state.pop('__pickleStateQByteArray__')
        self.__dict__.update(state)

    def __str__(self):
        return f'{self.markerSymbol}{self.markerPen.width()}{self.markerPen.color()};{self.linePen.style()}{self.lineWidth()}'


class PlotStyleWidget(QWidget):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    class VisibilityFlags(enum.IntFlag):
        Type = enum.auto()
        Color = enum.auto()
        Size = enum.auto()
        Symbol = enum.auto()
        SymbolPen = enum.auto()
        Line = enum.auto()
        Visibility = enum.auto()
        Preview = enum.auto()
        All = Type | Color | Size | Symbol | SymbolPen | Line | Visibility | Preview

    def __init__(self, title='<#>', parent=None, x=None, y=None,
                 plotStyle: PlotStyle = PlotStyle()):
        super(PlotStyleWidget, self).__init__(parent)

        ui_file = Path(__file__).parent / 'plotstylewidget.ui'
        assert ui_file.is_file()
        loadUi(ui_file, self)

        assert isinstance(self.plotWidget, pg.PlotWidget)

        self.mBlockUpdates = False
        # self.plotWidget.disableAutoRange()
        # self.plotWidget.setAspectLocked()
        self.plotWidget.setRange(xRange=[0, 1], yRange=[0, 1], update=True)
        self.plotWidget.setLimits(xMin=0, xMax=1, yMin=0, yMax=1)
        self.plotWidget.setMouseEnabled(x=False, y=False)

        self.mVisibility = self.VisibilityFlags.All

        for ax in self.plotWidget.plotItem.axes:
            self.plotWidget.plotItem.hideAxis(ax)
        # self.plotWidget.disableAutoRange()

        if x is None or y is None:
            # some arbitrary values
            x = [0.10, 0.5, 0.9]
            y = [0.25, 0.9, 0.5]
        assert len(x) == len(y), 'x and y need to be lists of same length.'

        self.plotDataItem = self.plotWidget.plot(x=x, y=y)
        self.legend = pg.LegendItem((100, 60), offset=(70, 30))  # args are (size, offset)
        self.legend.setParentItem(self.plotDataItem.topLevelItem())  # Note we do NOT call plt.addItem in this case
        self.legend.hide()

        assert isinstance(self.cbSymbol, MarkerSymbolComboBox)
        assert isinstance(self.cbSymbolPen, QgsPenStyleComboBox)
        assert isinstance(self.cbLinePen, QgsPenStyleComboBox)

        # connect signals
        for cb in [self.cbSymbol, self.cbSymbolPen, self.cbLinePen]:
            cb: QComboBox
            cb.currentIndexChanged.connect(self.onStyleChanged)

        for bt in [self.btnSymbolColor, self.btnSymbolPenColor, self.btnLinePenColor]:
            bt: QgsColorButton
            bt.colorChanged.connect(self.onStyleChanged)

        for sb in [self.sbSymbolSize, self.sbSymbolPenWidth, self.sbLinePenWidth]:
            sb: QSpinBox
            sb.valueChanged.connect(self.onStyleChanged)

        self.mAntialias = plotStyle.antialias
        self.mLastPlotStyle = plotStyle
        self.cbIsVisible.toggled.connect(self.onStyleChanged)
        self.setPlotStyle(plotStyle)

        self.refreshPreview()

    def onStyleChanged(self, color: QColor):
        self.toggleWidgetEnabled()
        self.refreshPreview()
        ps = self.plotStyle()
        if self.mLastPlotStyle != ps:
            self.sigPlotStyleChanged.emit(ps)

    def setVisibilityFlag(self, flag, b: bool):
        """
        Allows to enable or disable components of the widget
        :param flag:
        :param b:
        :return:
        """
        flags = self.visibilityFlags()
        if b:
            flags = flags | flag
        else:
            flags = flags & ~flag
        self.setVisibilityFlags(flags)

    def setVisibilityFlags(self, flags: 'PlotStyleWidget.VisibilityFlags'):
        F = self.VisibilityFlags
        any_col = any([f in flags for f in [F.Type, F.Color, F.Size]])

        showSymbol = F.Symbol in flags
        showSymbolPen = showSymbol and F.SymbolPen in flags

        self.labelSymbol.setVisible(showSymbol and any_col)
        self.labelSymbolPen.setVisible(showSymbolPen and any_col)
        self.labelLine.setVisible(F.Line in flags and any_col)

        # 1st col - types
        self.cbSymbol.setVisible(showSymbol and F.Type in flags)
        self.cbSymbolPen.setVisible(showSymbolPen and F.Type in flags)
        self.cbLinePen.setVisible(F.Line in flags and F.Type in flags)

        # 2nd col - colors
        self.btnSymbolColor.setVisible(showSymbol and F.Color in flags)
        self.btnSymbolPenColor.setVisible(showSymbolPen and F.Color in flags)
        self.btnLinePenColor.setVisible(F.Line in flags and F.Color in flags)

        # 3rd col - pixel size
        self.sbSymbolSize.setVisible(showSymbol and F.Size in flags)
        self.sbSymbolPenWidth.setVisible(showSymbolPen and F.Size in flags)
        self.sbLinePenWidth.setVisible(F.Line in flags and F.Size in flags)

        #
        self.cbIsVisible.setVisible(F.Visibility in flags)
        self.plotWidget.setVisible(F.Preview in flags)

        self.mVisibility = flags
        self.refreshPreview()

    def visibilityFlags(self) -> 'PlotStyleWidget.VVisibilityFlags':
        return self.mVisibility

    def setColorWidgetVisibility(self, b: bool):
        assert isinstance(b, bool)
        warnings.warn('Use .setVisibilitFlag', DeprecationWarning, stacklevel=2)
        F = self.VisibilityFlags
        self.setVisibilityFlag(F.Color, b)

    def toggleWidgetEnabled(self):
        """
        Toggles if widgets are enabled according to the QComboBox text values
        :param cb: QComboBox
        :param widgets: [list-of-QWidgets]
        """
        cb: QComboBox = self.cbSymbol
        has_symbol = self.cbSymbol.currentData() != MarkerSymbol.No_Symbol
        has_symbol_pen = self.cbSymbolPen.currentData() != Qt.PenStyle.NoPen
        has_line = self.cbLinePen.currentData() != Qt.PenStyle.NoPen

        for w in [self.btnSymbolColor, self.sbSymbolSize,
                  self.labelSymbolPen, self.cbSymbolPen]:
            w.setEnabled(has_symbol)

        for w in [self.btnSymbolPenColor, self.sbSymbolPenWidth]:
            w.setEnabled(has_symbol and has_symbol_pen)

        for w in [self.btnLinePenColor, self.sbLinePenWidth]:
            w.setEnabled(has_line)

    def setVisibilityCheckboxVisible(self, b: bool):
        """
        Sets the visibility of the visibility checkbox.
        :param b:
        :type b: bool
        :return:
        :rtype:
        """
        warnings.warn('Use .setVisibilityFlag', DeprecationWarning, stacklevel=2)

        self.setVisibilityFlag(self.VisibilityFlags.Visibility, b)

    def setPreviewVisible(self, b: bool):
        """
        Sets the visibility of the preview window.
        :param b:
        :type b:
        """
        assert isinstance(b, bool)
        warnings.warn('Use .setVisibilityFlag', DeprecationWarning, stacklevel=2)

        self.plotWidget.setVisible(b)

    def refreshPreview(self, *args):
        if not self.mBlockUpdates:
            style = self.plotStyle()
            assert isinstance(style, PlotStyle)
            # todo: set style to style preview
            pi = self.plotDataItem
            pi.setSymbol(style.markerSymbol)
            pi.setSymbolSize(style.markerSize)
            pi.setSymbolBrush(style.markerBrush)
            pi.setSymbolPen(style.markerPen)
            pi.setPen(style.linePen)
            pi.setVisible(style.isVisible())
            pi.update()
            self.plotWidget.update()

    def setPlotStyle(self, style: PlotStyle):
        assert isinstance(style, PlotStyle)
        # set widget values
        self.mLastPlotStyle = style
        self.mBlockUpdates = True
        self.sbSymbolSize.setValue(style.markerSize)
        self.cbSymbol.setMarkerSymbol(style.markerSymbol)
        self.mAntialias = style.antialias

        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)

        self.btnSymbolPenColor.setColor(style.markerPen.color())
        self.cbSymbolPen.setPenStyle(style.markerPen.style())
        self.sbSymbolPenWidth.setValue(style.markerPen.width())
        self.btnSymbolColor.setColor(style.markerBrush.color())
        self.btnLinePenColor.setColor(style.linePen.color())
        self.cbLinePen.setPenStyle(style.linePen.style())
        self.sbLinePenWidth.setValue(style.linePen.width())

        if self.cbIsVisible.isVisible():
            self.cbIsVisible.setChecked(style.isVisible())
        self.plotWidget.setBackground(style.backgroundColor)
        self.mBlockUpdates = False

        self.refreshPreview()

    def plotStyle(self) -> PlotStyle:
        style = PlotStyle(plotStyle=self.mLastPlotStyle)

        # read plotstyle values from widgets
        F = self.VisibilityFlags
        visFlags = self.visibilityFlags()

        assert isinstance(style.markerPen, QPen)
        assert isinstance(style.markerBrush, QBrush)
        assert isinstance(style.linePen, QPen)

        if F.Symbol in visFlags:
            if F.Type in visFlags:
                style.setMarkerSymbol(self.cbSymbol.markerSymbol())
            if F.Color in visFlags:
                style.markerBrush.setColor(self.btnSymbolColor.color())
            if F.Size in visFlags:
                style.markerSize = self.sbSymbolSize.value()

            if F.SymbolPen in visFlags:
                if F.Type in visFlags:
                    style.markerPen.setStyle(self.cbSymbolPen.penStyle())
                if F.Color in visFlags:
                    style.markerPen.setColor(self.btnSymbolPenColor.color())
                if F.Size in visFlags:
                    style.markerPen.setWidth(self.sbSymbolPenWidth.value())
            else:
                style.markerPen.setStyle(Qt.PenStyle.NoPen)

        else:
            style.setMarkerSymbol(MarkerSymbol.No_Symbol)

        if F.Line in visFlags:
            style.linePen.setCosmetic(True)  # line width = pixel width
            if F.Type in visFlags:
                style.linePen.setStyle(self.cbLinePen.penStyle())
            if F.Color in visFlags:
                style.linePen.setColor(self.btnLinePenColor.color())
            if F.Size in visFlags:
                style.linePen.setWidth(self.sbLinePenWidth.value())

        else:
            style.linePen.setStyle(Qt.PenStyle.NoPen)

        # style.markerSize = self.sbSymbolSize.value()
        # style.setMarkerSymbol(self.cbSymbol.markerSymbol())

        # style.markerPen.setColor(self.btnSymbolPenColor.color())
        # style.markerPen.setWidth(self.sbSymbolPenWidth.value())
        # style.markerPen.setStyle(self.cbSymbolPen.penStyle())
        # style.markerBrush.setColor(self.btnSymbolColor.color())
        # style.linePen.setColor(self.btnLinePenColor.color())
        # style.linePen.setWidth(self.sbLinePenWidth.value())
        # style.linePen.setStyle(self.cbLinePen.penStyle())

        if self.cbIsVisible.isVisible():
            style.setVisibility(self.cbIsVisible.isChecked())

        style.setAntialias(self.mAntialias)
        return style


class PlotStyleButton(QToolButton):
    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self, *args, **kwds):
        super(PlotStyleButton, self).__init__(*args, **kwds)

        self.mInitialButtonSize = None

        self.setMinimumSize(5, 5)
        self.setMaximumHeight(75)

        self.mMenu = QMenu(parent=self)
        self.mMenu.triggered.connect(self.onAboutToShowMenu)

        self.mDialog: PlotStyleDialog = PlotStyleDialog()

        self.mDialog.setModal(False)
        # self.mDialog.setPlotStyle(self.mPlotStyle)
        self.mDialog.accepted.connect(self.onAccepted)
        self.mDialog.rejected.connect(self.onCanceled)
        self.mDialog.sigPlotStyleChanged.connect(self.onPlotStyleChanged)
        self.mDialog.plotStyleWidget().setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Preview, False)
        self.mDialog.setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Visibility, self.isCheckable())
        # self.mDialog.plotStyleWidget().setVisibilityCheckboxVisible(False)
        self.mWA = QWidgetAction(self.mMenu)
        self.mWA.setDefaultWidget(self.mDialog)
        self.mMenu.addAction(self.mWA)
        self.mMenu.aboutToShow.connect(self.onAboutToShowMenu)
        self.setMenu(self.mMenu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        self.clicked.connect(lambda: self.activateWindow())
        self.toggled.connect(self.onToggled)
        self.updateIcon()

    def onPlotStyleChanged(self, style: PlotStyle):
        if self.isCheckable():
            self.setChecked(style.isVisible())
        self.updateIcon()

    def onToggled(self, b: bool):
        # self.mPlotStyle.setVisibility(b)
        self.sigPlotStyleChanged.emit(self.plotStyle())
        self.updateIcon()

    def setVisibilityFlag(self, flag: PlotStyleWidget.VisibilityFlags, b: bool):
        self.mDialog.setVisibilityFlag(flag, b)

    def setVisibilityFlags(self, flags: PlotStyleWidget.VisibilityFlags):
        self.mDialog.setVisibilityFlags(flags)

    def onAboutToShowMenu(self, *args):
        self.mWA.setVisible(True)
        self.mDialog.setVisible(True)
        ps = self.plotStyle()
        self.mDialog.setPlotStyle(ps)
        # self.mDialog.setPlotStyle(self.mPlotStyle.clone())
        self.mDialog.activateWindow()

    def setColorWidgetVisibility(self, b: bool):
        self.mDialog.setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Color, b)

    def setVisibilityCheckboxVisible(self, b: bool):
        self.mDialog.setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Visibility, b)

    def setPreviewVisible(self, b: bool):
        self.mDialog.setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Preview, b)

    def onAccepted(self, *args):
        ps = self.plotStyle()
        self.updateIcon()

        if self.isCheckable():
            self.setChecked(ps.isVisible())

        self.mWA.setVisible(False)

    def onCanceled(self, *args):
        self.mWA.setVisible(False)

    def plotStyle(self) -> PlotStyle:
        ps = self.mDialog.plotStyle()
        if self.isCheckable():
            ps.setVisibility(self.isChecked())
        else:
            ps.setVisibility(True)
        return ps

    def setCheckable(self, b: bool) -> None:
        super().setCheckable(b)
        # self.mDialog.setVisibilityCheckboxVisible(b)
        self.mDialog.setVisibilityFlag(PlotStyleWidget.VisibilityFlags.Visibility, b)
        self.onToggled(b)

    def setPlotStyle(self, plotStyle):
        oldStyle = self.plotStyle()

        if isinstance(plotStyle, PlotStyle):
            with SignalBlocker(self.mDialog) as block:
                self.mDialog.setPlotStyle(plotStyle)
            self.updateIcon()

            if oldStyle != plotStyle:
                self.sigPlotStyleChanged.emit(self.plotStyle())

    def resizeEvent(self, arg):
        self.updateIcon()

    def updateIcon(self):
        self.setIconSize(self.size())
        ps = self.plotStyle()
        if self.isCheckable():
            ps.setVisibility(self.isChecked())
        icon = ps.createIcon(self.iconSize())
        self.setIcon(icon)
        self.update()


class PlotStyleDialog(QgsDialog):

    @staticmethod
    def getPlotStyle(*args, **kwds):
        """
        Opens a dialog to specify a PlotStyle.
        :param args:
        :param kwds:
        :return: specified PlotStyle if accepted, else None
        """
        d = PlotStyleDialog(*args, **kwds)

        if d.exec() == QDialog.DialogCode.Accepted:
            return d.plotStyle()
        else:
            return None

    sigPlotStyleChanged = pyqtSignal(PlotStyle)

    def __init__(self,
                 parent=None,
                 plotStyle: PlotStyle = PlotStyle(),
                 title: str = 'Specify Plot Style',
                 **kwds):
        super(PlotStyleDialog, self).__init__(parent=parent,
                                              buttons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                                              **kwds)
        self.w: PlotStyleWidget = PlotStyleWidget(parent=self, plotStyle=plotStyle)
        self.w.sigPlotStyleChanged.connect(self.onPlotStyleChanged)
        self.setWindowTitle(title)
        layout = self.layout()
        layout.addWidget(self.w)
        if isinstance(plotStyle, PlotStyle):
            self.setPlotStyle(plotStyle)

    def setVisibilityFlag(self, flag: PlotStyleWidget.VisibilityFlags, b: bool):
        self.w.setVisibilityFlag(flag, b)

    def setVisibilityFlags(self, flags: PlotStyleWidget.VisibilityFlags):
        self.w.setVisibilityFlags(flags)

    def onPlotStyleChanged(self, plotStyle: PlotStyle):

        if not self.isActiveWindow():
            pMenu = self.parent()
            if isinstance(pMenu, QMenu) and not pMenu.pos().isNull():
                pMenu.setVisible(True)

            self.setVisible(True)
            self.activateWindow()

    def setColorWidgetVisibility(self, b: bool):
        warnings.warn(DeprecationWarning('Use setVisibilityFlags'))
        self.w.setColorWidgetVisibility(b)

    def setVisibilityCheckboxVisible(self, b: bool):
        warnings.warn(DeprecationWarning('Use setVisibilityFlags'))
        self.w.setVisibilityCheckboxVisible(b)

    def plotStyleWidget(self) -> PlotStyleWidget:
        return self.w

    def accept(self):
        ps = self.plotStyle()

        if ps != self.w.mLastPlotStyle:
            self.sigPlotStyleChanged.emit(ps)

        super().accept()

    def reject(self):
        if self.w.mLastPlotStyle:
            self.w.setPlotStyle(self.w.mLastPlotStyle)
        super().reject()

    def plotStyle(self) -> PlotStyle:
        return self.w.plotStyle()

    def setPlotStyle(self, plotStyle: PlotStyle):
        assert isinstance(plotStyle, PlotStyle)
        last = self.w.mLastPlotStyle
        self.w.setPlotStyle(plotStyle)
        ps = self.plotStyle()
        if ps != last:
            self.sigPlotStyleChanged.emit(ps)

    def setPreviewVisible(self, b: bool):
        warnings.warn(DeprecationWarning('Use setVisibilityFlags'))
        self.w.setPreviewVisible(b)


class PlotStyleEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(PlotStyleEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mEditorWidget = None
        self.mEditorButton = None
        self.mLabel = None
        self.mDefaultValue = None

    def createWidget(self, parent: QWidget) -> PlotStyleWidget:
        # log('createWidget')
        w = None
        if not self.isInTable(parent):
            w = PlotStyleWidget(parent=parent)
        else:
            # w = PlotStyleButton(parent)
            w = QLabel(parent)

        return w

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        if isinstance(editor, PlotStyleWidget):
            self.mEditorWidget = editor
            self.mEditorWidget.sigPlotStyleChanged.connect(self.onValueChanged)
            s = ""
        if isinstance(editor, PlotStyleButton):
            self.mEditorButton = editor
            self.mEditorButton.sigPlotStyleChanged.connect(self.onValueChanged)

        if isinstance(editor, QLabel):
            self.mLabel = editor
            self.mLabel.setToolTip('Use Form View to edit values')

    def setEnabled(self, enabled: bool):
        # log(' setEnabled={}'.format(enabled))

        if isinstance(self.mEditorWidget, PlotStyleWidget):
            self.mEditorWidget.setEnabled(enabled)
        if isinstance(self.mEditorButton, PlotStyleButton):
            self.mEditorButton.setEnabled(enabled)
        if isinstance(self.mLabel, QLabel):
            self.mLabel.setEnabled(enabled)

    def onValueChanged(self, *args):
        # log(' onValueChangedFORM')

        self.valueChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs) -> bool:
        return any([isinstance(w, QWidget) for w in [self.mLabel, self.mEditorButton, self.mEditorWidget]])

    def value(self, *args, **kwargs):
        value = self.mDefaultValue
        if isinstance(self.mEditorWidget, PlotStyleWidget):
            value = self.mEditorWidget.plotStyle()
        if isinstance(value, PlotStyle):
            value = value.json()
        return value

    def setValue(self, value):

        if not isinstance(value, str):
            style = PlotStyle()
        else:
            style = PlotStyle.fromJSON(value)

        if isinstance(style, PlotStyle):
            self.mDefaultValue = value
            if isinstance(self.mEditorWidget, PlotStyleWidget):
                self.mEditorWidget.setPlotStyle(style)
            # if isinstance(self.mEditorButton, PlotStyleButton):
            #    self.mEditorButton.setPlotStyle(style)
            if isinstance(self.mLabel, QLabel):
                self.mLabel.setPixmap(style.createPixmap(self.mLabel.size()))
        else:
            # log('STYLE IS NONE!')
            pass
        # log(' setValue() END')


class PlotStyleEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):
        super(PlotStyleEditorConfigWidget, self).__init__(vl, fieldIdx, parent)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(QLabel('Shows a dialog to specify a PlotStyle'))
        self.mConfig = {}

    def config(self, *args, **kwargs) -> dict:
        log(' config()')
        config = {}

        return config

    def setConfig(self, *args, **kwargs):
        log(' setConfig()')
        self.mConfig = {}


class PlotStyleEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name: str):

        super(PlotStyleEditorWidgetFactory, self).__init__(name)
        self._wrappers = []
        s = ""

    def configWidget(self, vl: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> QgsEditorConfigWidget:
        # print('configWidget()')
        w = PlotStyleEditorConfigWidget(vl, fieldIdx, parent)
        self._wrappers.append(w)
        return w

    def create(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> PlotStyleEditorWidgetWrapper:
        # log(': create(...)')
        w = PlotStyleEditorWidgetWrapper(vl, fieldIdx, editor, parent)
        self._wrappers.append(w)
        return w

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain field.
        0: not supported: none String fields
        5: maybe support String fields with length <= 400
        20: specialized support: String fields with length > 400

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if field.type() == QMETATYPE_QSTRING and field.length() > 400 and field.name().upper() == 'STYLE':
            return 20
        elif field.type() == QMETATYPE_QSTRING:
            return 5
        else:
            return 0  # no support

    def createSearchWidget(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget) -> QgsSearchWidgetWrapper:
        log(' createSearchWidget()')
        return super(PlotStyleEditorWidgetFactory, self).createSearchWidget(vl, fieldIdx, parent)

    def writeConfig(self, config, configElement, doc, layer, fieldIdx):

        s = ""

    def readConfig(self, configElement, layer, fieldIdx):

        d = {}
        return d


def plotStyleEditorWidgetFactory(register: bool = True) -> PlotStyleEditorWidgetFactory:
    global _PLOTSTYLE_EDITOR_WIDGET_FACTORY
    if not isinstance(_PLOTSTYLE_EDITOR_WIDGET_FACTORY, PlotStyleEditorWidgetFactory):
        _PLOTSTYLE_EDITOR_WIDGET_FACTORY = PlotStyleEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
    reg = QgsGui.editorWidgetRegistry()
    if register and EDITOR_WIDGET_REGISTRY_KEY not in reg.factories().keys():
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, _PLOTSTYLE_EDITOR_WIDGET_FACTORY)
    return reg.factory(EDITOR_WIDGET_REGISTRY_KEY)


def registerPlotStyleEditorWidget():
    warnings.warn(DeprecationWarning('Use plotstyling.plotStyleEditorWidgetFactory(True)'),
                  stacklevel=2)
    return plotStyleEditorWidgetFactory(True)


def registerPlotStyleEditorWidgetFactory():
    warnings.warn(DeprecationWarning('Use plotstyling.plotStyleEditorWidgetFactory(True)'), stacklevel=2)
    return plotStyleEditorWidgetFactory(True)


class PlotWidgetStyle(object):
    PLOT_WIDGET_STYLES: Dict[str, 'PlotWidgetStyle'] = dict()

    @staticmethod
    def registerPlotWidgetStyle(style: 'PlotWidgetStyle', overwrite: bool = False):
        assert isinstance(style, PlotWidgetStyle)
        key = style.name.lower()
        if overwrite or key not in PlotWidgetStyle.PLOT_WIDGET_STYLES.keys():
            PlotWidgetStyle.PLOT_WIDGET_STYLES[key] = style

    @staticmethod
    def plotWidgetStyle(name: str) -> 'PlotWidgetStyle':
        if len(PlotWidgetStyle.PLOT_WIDGET_STYLES) == 0:
            PlotWidgetStyle.initializeStandardStyles()
        key = name.lower()
        return PlotWidgetStyle.PLOT_WIDGET_STYLES.get(key, None)

    @staticmethod
    def plotWidgetStyles() -> List['PlotWidgetStyle']:
        if len(PlotWidgetStyle.PLOT_WIDGET_STYLES) == 0:
            PlotWidgetStyle.initializeStandardStyles()
        return list(PlotWidgetStyle.PLOT_WIDGET_STYLES.values())

    @staticmethod
    def default() -> 'PlotWidgetStyle':
        """
        Returns the default plotStyle scheme.
        :return:
        :rtype: PlotWidgetStyle
        """
        style = PlotWidgetStyle.plotWidgetStyle('dark')
        if not isinstance(style, PlotWidgetStyle):
            style = PlotWidgetStyle()
        return style

    @staticmethod
    def fromUserSettings() -> 'PlotWidgetStyle':
        """
        Returns the SpectralLibraryPlotWidgetStyle last saved in then library settings
        :return:
        :rtype:
        """
        raise NotImplementedError()

    @staticmethod
    def dark() -> 'PlotWidgetStyle':
        return PlotWidgetStyle.plotWidgetStyle('dark')

    @staticmethod
    def bright() -> 'PlotWidgetStyle':
        return PlotWidgetStyle.plotWidgetStyle('bright')

    def __init__(self,
                 name: str = 'default',
                 fg: QColor = QColor('white'),
                 bg: QColor = QColor('black'),
                 ic: QColor = QColor('white'),
                 sc: QColor = QColor('yellow'),
                 cc: QColor = QColor('yellow'),
                 tc: QColor = QColor('#aaff00'),
                 icon: str = ':/images/themes/default/propertyicons/stylepreset.svg',
                 ):
        assert isinstance(icon, str)
        self.icon: str = str(icon)
        self.name: str = str(name)
        self.foregroundColor: QColor = QColor(fg)
        self.backgroundColor: QColor = QColor(bg)
        self.textColor: QColor = QColor(ic)
        self.selectionColor: QColor = QColor(sc)
        self.crosshairColor: QColor = QColor(cc)
        self.temporaryColor: QColor = QColor(tc)

    def __eq__(self, other):
        if not isinstance(other, PlotWidgetStyle):
            return False
        for k, v in self.__dict__.items():
            if k.startswith('_'):
                continue
            if v != other.__dict__[k]:
                return False
        return True

    def toVariantMap(self) -> dict:

        MAP = dict()
        for k, v in self.__dict__.items():
            if k.startswith('_'):
                continue
            if isinstance(v, QColor):
                v = v.name()

            if isinstance(v, str):
                MAP[k] = v
        return MAP

    def fromVariantMap(self, map: dict) -> bool:
        keys = [k for k in self.__dict__.keys() if not k.startswith('_') and k in map.keys()]
        if len(keys) == 0:
            return False
        for k in keys:
            v0 = self.__dict__[k]
            v1 = map[k]
            if isinstance(v0, QColor):
                v1 = QColor(v1)
            self.__dict__[k] = v1

    @staticmethod
    def readXml(node: QDomElement, *args):
        """
        Reads the SpectralLibraryPlotWidgetStyle from a QDomElement (XML node)
        :param self:
        :param node:
        :param args:
        :return:
        """
        """
        from .spectrallibrary import XMLNODE_PROFILE_RENDERER
        if node.tagName() != XMLNODE_PROFILE_RENDERER:
            node = node.firstChildElement(XMLNODE_PROFILE_RENDERER)
        if node.isNull():
            return None

        default: SpectralLibraryPlotWidgetStyle = SpectralLibraryPlotWidgetStyle.default()

        renderer = SpectralLibraryPlotWidgetStyle()
        renderer.backgroundColor = QColor(node.attribute('bg', renderer.backgroundColor.name()))
        renderer.foregroundColor = QColor(node.attribute('fg', renderer.foregroundColor.name()))
        renderer.selectionColor = QColor(node.attribute('sc', renderer.selectionColor.name()))
        renderer.textColor = QColor(node.attribute('ic', renderer.textColor.name()))

        nodeName = node.firstChildElement('name')
        renderer.name = nodeName.firstChild().nodeValue()
        """
        return None

    def writeXml(self, node: QDomElement, doc: QDomDocument) -> bool:
        """
        Writes the PlotStyle to a QDomNode
        :param node:
        :param doc:
        :return:
        """
        """
        from .spectrallibrary import XMLNODE_PROFILE_RENDERER
        profileRendererNode = doc.createElement(XMLNODE_PROFILE_RENDERER)
        profileRendererNode.setAttribute('bg', self.backgroundColor.name())
        profileRendererNode.setAttribute('fg', self.foregroundColor.name())
        profileRendererNode.setAttribute('sc', self.selectionColor.name())
        profileRendererNode.setAttribute('ic', self.textColor.name())

        nodeName = doc.createElement('name')
        nodeName.appendChild(doc.createTextNode(self.name))
        profileRendererNode.appendChild(nodeName)

        node.appendChild(profileRendererNode)
        """
        return True

    def clone(self):
        # todo: avoid refs
        return copy.copy(self)

    def saveToUserSettings(self):
        """
        Saves this plotStyle scheme to the user Qt user settings
        :return:
        :rtype:
        """
        raise NotImplementedError()

    @staticmethod
    def writeJson(path, styles: List['PlotWidgetStyle']):
        path = Path(path)

        JSON = []
        for s in styles:
            assert isinstance(s, PlotWidgetStyle)
            JSON.append(s.toVariantMap())
        if len(JSON) > 0:
            with open(path, 'w', encoding='utf-8') as fp:
                json.dump(JSON, fp, indent=4)

    @staticmethod
    def fromJson(path) -> List['PlotWidgetStyle']:
        path = Path(path)
        styles = []
        with open(path, 'r', encoding='utf8') as fp:
            JSON = json.load(fp)
            for MAP in JSON:
                style = PlotWidgetStyle()
                style.fromVariantMap(MAP)
                styles.append(style)
        return styles

    @staticmethod
    def initializeStandardStyles():
        # initialize standard styles
        pathStandardStyle = Path(__file__).parent / 'standardstyles.json'

        if not pathStandardStyle.is_file():
            warnings.warn(f'Missing file: {pathStandardStyle}')
            PlotWidgetStyle.registerPlotWidgetStyle(PlotWidgetStyle.default())
        else:
            try:
                for style in PlotWidgetStyle.fromJson(pathStandardStyle):
                    PlotWidgetStyle.registerPlotWidgetStyle(style, True)
            except JSONDecodeError as ex:
                warnings.warn(f'Unable to load standard plot widget styles: {ex}')
                PlotWidgetStyle.registerPlotWidgetStyle(PlotWidgetStyle.default())
