import collections
import copy
import datetime
import enum
import re
import sys
import textwrap
import typing
import warnings
import pickle
import numpy as np
from qgis.PyQt import sip
from PyQt5.QtCore import pyqtSignal, QTimer, QPointF, pyqtSlot, Qt, QModelIndex, QPoint, QObject, QAbstractTableModel, \
    QSortFilterProxyModel, QSize, QVariant, QAbstractItemModel, QItemSelectionModel, QRect, QMimeData, QByteArray
from PyQt5.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter, QIcon, QContextMenuEvent
from PyQt5.QtWidgets import QWidgetAction, QWidget, QGridLayout, QSpinBox, QLabel, QFrame, QAction, QApplication, \
    QTableView, QComboBox, QMenu, QSlider, QStyledItemDelegate, QHBoxLayout, QTreeView, QStyleOptionViewItem, \
    QRadioButton, QSizePolicy, QSplitter
from PyQt5.QtXml import QDomElement, QDomDocument, QDomNode

from qgis.PyQt.QtCore import NULL
from qgis._core import QgsPropertyDefinition
from qgis.gui import QgsColorButton, QgsPropertyOverrideButton, QgsCollapsibleGroupBox

from qgis.core import QgsProperty, QgsExpressionContextScope
from qgis.core import QgsProcessingModelAlgorithm, QgsProcessingFeedback, QgsProcessingContext, QgsProject, QgsField, \
    QgsVectorLayer, QgsFieldModel, QgsFields, QgsFieldProxyModel, QgsSettings, QgsApplication, QgsExpressionContext, \
    QgsExpression, QgsFeatureRenderer, QgsRenderContext, QgsSymbol, QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol, \
    QgsFeature, QgsFeatureRequest, QgsProcessingException
from qgis.gui import QgsAttributeTableFilterModel, QgsDualView, QgsAttributeTableModel, QgsFieldExpressionWidget

from ...externals import pyqtgraph as pg
from ...externals.htmlwidgets import HTMLComboBox
from ...externals.pyqtgraph import PlotDataItem, PlotWindow
from ...externals.pyqtgraph import AxisItem
from ...models import SettingsModel, SettingsTreeView
from ...plotstyling.plotstyling import PlotStyle, PlotStyleWidget, PlotStyleButton
from .. import speclibUiPath, speclibSettings, SpectralLibrarySettingsKey
from ..core.spectrallibrary import SpectralLibrary, DEBUG, containsSpeclib, defaultCurvePlotStyle
from ..core import profile_field_list, profile_field_indices, is_spectral_library
from ..core.spectralprofile import SpectralProfile, SpectralProfileBlock, SpectralProfileLoadingTask
from ..processing import is_spectral_processing_model, SpectralProcessingProfiles, \
    SpectralProcessingProfilesOutput, SpectralProcessingModelList, NULL_MODEL, outputParameterResults, \
    outputParameterResult
from ...unitmodel import BAND_INDEX, BAND_NUMBER, UnitConverterFunctionModel, UnitModel
from ...utils import datetime64, UnitLookup, chunks, loadUi, SignalObjectWrapper, convertDateUnit, nextColor


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

    def unit(self) -> str:
        """
        Returns the unit set for this axis.
        :return:
        """
        return self.mUnit


class SpectralLibraryPlotItem(pg.PlotItem):
    sigPopulateContextMenuItems = pyqtSignal(SignalObjectWrapper)

    def __init__(self, *args, **kwds):
        super(SpectralLibraryPlotItem, self).__init__(*args, **kwds)
        self.mTempList = []

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
                scene.addItem(item)  ## Necessary due to Qt bug: https://bugreports.qt-project.org/browse/QTBUG-18616
                item.setParentItem(self.childGroup)
        if not ignoreBounds:
            self.addedItems.extend(pdis)
        # self.updateAutoRange()


MAX_PDIS_DEFAULT: int = 256

MouseClickData = collections.namedtuple('MouseClickData', ['idx', 'xValue', 'yValue', 'pxDistance', 'pdi'])


class SpectralProfilePlotVisualization(QObject):
    MIME_TYPE = 'application/SpectralProfilePlotVisualization'

    @staticmethod
    def toMimeData(visualizations: typing.List['SpectralProfilePlotVisualization']):

        md = QMimeData()

        doc = QDomDocument()
        root = doc.createElement('profile_visualizations')
        for vis in visualizations:
            vis.writeXml(root, doc)
        doc.appendChild(root)
        md.setData(SpectralProfilePlotVisualization.MIME_TYPE, doc.toByteArray())
        return md

    @staticmethod
    def fromMimeData(mimeData: QMimeData) -> typing.List['SpectralProfilePlotVisualization']:

        if mimeData.hasFormat(SpectralProfilePlotVisualization.MIME_TYPE):
            ba = mimeData.data(SpectralProfilePlotVisualization.MIME_TYPE)
            doc = QDomDocument()
            doc.setContent(ba)
            root = doc.firstChildElement('profile_visualizations')
            if not root.isNull():
                return SpectralProfilePlotVisualization.fromXml(root)

        return []

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mName: str = 'Visualization'
        self.mModelId: str = ''
        self.mSpeclib: QgsVectorLayer = None
        self.mField: QgsField = QgsField()
        self.mNameExpression: QgsExpression = QgsExpression('')
        self.mPlotStyle: PlotStyle = PlotStyle()
        self.mVisible: bool = True
        self.mColorProperty: QgsProperty = QgsProperty()
        self.mColorProperty.setStaticValue(QColor('white'))

    XML_TAG = 'spectralprofileplotvisualization'

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument):
        # appends this visualization to a parent node
        visNode = doc.createElement(self.XML_TAG)
        visNode.setAttribute('name', self.name())
        visNode.setAttribute('field', self.field().name())
        visNode.setAttribute('visible', '1' if self.isVisible() else '0')

        # add speclib node
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            nodeSpeclib = doc.createElement('speclib')
            nodeSpeclib.setAttribute('id', self.speclib().id())
            visNode.appendChild(nodeSpeclib)

        # add name expression node
        label_expr = self.labelExpression()
        if isinstance(label_expr, QgsExpression) and label_expr.expression() != '':
            nodeNameExpr = doc.createElement('label_expression')
            nodeNameExpr.setNodeValue(self.labelExpression().expression())
            visNode.appendChild(nodeNameExpr)

        # add color expression node
        color_expr = self.colorProperty()
        if isinstance(color_expr, QgsExpression) and label_expr.expression() != '':
            nodeColorExpr = doc.createElement('color_expression')
            nodeColorExpr.setNodeValue(self.colorProperty().expression())
            visNode.appendChild(nodeColorExpr)

        # processing model
        model = self.model()
        if isinstance(model, QgsProcessingModelAlgorithm) and not isinstance(model, NULL_MODEL):
            nodeModel = doc.createElement('model')
            nodeModel.setAttribute('name', self.modelName())
            nodeModel.setAttribute('id', self.modelId())
            visNode.appendChild(nodeModel)

        # add plot style node
        self.plotStyle().writeXml(visNode, doc)

        parentNode.appendChild(visNode)

    @staticmethod
    def fromXml(parentNode: QDomElement,
                available_speclibs: typing.List[SpectralLibrary] = []) \
            -> typing.List['SpectralProfilePlotVisualization']:
        # returns all child node visualization that are child nodes
        visualizations = []
        if parentNode.nodeName() == SpectralProfilePlotVisualization.XML_TAG:
            visNodes = [parentNode]
        else:
            visNodes = []
            candidates = parentNode.childNodes()
            for i in range(candidates.count()):
                node = candidates.at(i).toElement()
                if node.nodeName() == SpectralProfilePlotVisualization.XML_TAG:
                    visNodes.append(node)

        for visNode in visNodes:
            visNode: QDomElement

            vis = SpectralProfilePlotVisualization()

            vis.setName(visNode.attribute('name'))

            vis.setVisible(visNode.attribute('visible').lower() in ['1', 'true', 'yes'])

            speclibNode = visNode.firstChildElement('speclib')
            speclib: QgsVectorLayer = None
            if not speclibNode.isNull():
                # try to restore the speclib
                lyrId = speclibNode.attribute('id')

                for sl in available_speclibs:
                    if sl.id() == lyrId:
                        speclib = sl

            if isinstance(speclib, QgsVectorLayer):
                vis.setSpeclib(speclib)

            fieldName = visNode.attribute('field')
            if isinstance(speclib, QgsVectorLayer) and fieldName in speclib.fields().names():
                vis.setField(fieldName)

            nameExprNode = visNode.firstChildElement('label_expression')
            if not nameExprNode.isNull():
                vis.setLabelExpression(nameExprNode.nodeValue())

            colorExprNode = visNode.firstChildElement('color_expression')
            if not colorExprNode.isNull():
                vis.setColorProperty(colorExprNode.nodeValue())

            modelNode = visNode.firstChildElement('model')
            modelId = None
            if not modelNode.isNull():
                # try to restore the model id
                modelId = modelNode.attribute('id')

            if isinstance(modelId, str):
                vis.setModelId(modelId)

            plotStyle = PlotStyle.readXml(visNode)
            if isinstance(plotStyle, PlotStyle):
                vis.setPlotStyle(plotStyle)

            visualizations.append(vis)

        return visualizations

    def __hash__(self):
        return hash(id(self))

    def setColorProperty(self, property: QgsProperty):
        """
        Sets the color property
        :param property:
        :type property:
        :return:
        :rtype:
        """
        assert isinstance(property, QgsProperty)
        self.mColorProperty = property

    def colorProperty(self) -> QgsProperty:
        """
        Returns the color expression
        :return:
        :rtype:
        """
        return self.mColorProperty

    def name(self) -> str:
        """
        Returns the name of this visualization
        :return:
        """
        return self.mName

    def setName(self, name: str):
        self.mName = name

    def setVisible(self, visible: bool):
        assert isinstance(visible, bool)
        self.mVisible = visible

    def isVisible(self) -> bool:
        return self.mVisible

    def setSpeclib(self, speclib: QgsVectorLayer):
        assert isinstance(speclib, QgsVectorLayer)
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def isComplete(self) -> bool:
        speclib = self.speclib()
        field = self.field()
        return isinstance(speclib, QgsVectorLayer) and \
               not sip.isdeleted(speclib) \
               and isinstance(field, QgsField) \
               and field.name() in speclib.fields().names()

    def setLabelExpression(self, expression):
        if isinstance(expression, str):
            self.mNameExpression.setExpression(expression)
        elif isinstance(expression, QgsExpression):
            self.mNameExpression.setExpression(expression.expression())
        else:
            raise NotImplementedError()

    def labelExpression(self) -> QgsExpression:
        """
        Returns the expression that returns the name for a single profile
        :return: str
        """
        return self.mNameExpression

    NULL_MODEL = NULL_MODEL()

    def setModelId(self, modelId: typing.Union[str, QgsProcessingModelAlgorithm]):
        if isinstance(modelId, QgsProcessingModelAlgorithm):
            assert is_spectral_processing_model(modelId) or isinstance(modelId, NULL_MODEL)
            modelId = modelId.id()
        self.mModelId = modelId

    def model(self) -> QgsProcessingModelAlgorithm:
        if self.mModelId == '':
            return self.NULL_MODEL
        else:
            reg = QgsApplication.processingRegistry()

            return reg.algorithmById(self.mModelId)

    def modelId(self) -> str:
        return self.mModelId

    def modelName(self) -> str:
        return self.model().displayName()

    def setField(self, field: typing.Union[QgsField, str]):

        if isinstance(field, str):
            speclib = self.speclib()
            assert isinstance(speclib, QgsVectorLayer), 'Speclib undefined'
            field = speclib.fields().at(speclib.fields().lookupField(field))
        assert isinstance(field, QgsField)
        self.mField = field

    def field(self) -> QgsField:
        return self.mField

    def fieldIdx(self) -> int:
        return self.speclib().fields().lookupField(self.field().name())

    def setPlotStyle(self, style: PlotStyle):
        assert isinstance(style, PlotStyle)
        self.mPlotStyle = style

    def plotStyle(self) -> PlotStyle:
        return self.mPlotStyle


class SpectralLibraryPlotWidgetStyle(object):

    @staticmethod
    def default() -> 'SpectralLibraryPlotWidgetStyle':
        """
        Returns the default plotStyle scheme.
        :return:
        :rtype: SpectralLibraryPlotWidgetStyle
        """
        return SpectralLibraryPlotWidgetStyle.dark()

    @staticmethod
    def fromUserSettings() -> 'SpectralLibraryPlotWidgetStyle':
        """
        Returns the SpectralLibraryPlotWidgetStyle last saved in then library settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        style = SpectralLibraryPlotWidgetStyle.default()
        style.backgroundColor = settings.value(SpectralLibrarySettingsKey.BACKGROUND_COLOR,
                                               style.backgroundColor)
        style.foregroundColor = settings.value(SpectralLibrarySettingsKey.FOREGROUND_COLOR,
                                               style.foregroundColor)
        style.textColor = settings.value(SpectralLibrarySettingsKey.INFO_COLOR, style.textColor)
        style.selectionColor = settings.value(SpectralLibrarySettingsKey.SELECTION_COLOR, style.selectionColor)

        return style

    @staticmethod
    def dark() -> 'SpectralLibraryPlotWidgetStyle':
        ps = defaultCurvePlotStyle()
        ps.setLineColor('white')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotWidgetStyle(
            name='Dark',
            fg=QColor('white'),
            bg=QColor('black'),
            ic=QColor('white'),
            sc=QColor('yellow'),
            cc=QColor('yellow'),
            tc=QColor('#aaff00')
        )

    @staticmethod
    def bright() -> 'SpectralLibraryPlotWidgetStyle':
        ps = defaultCurvePlotStyle()
        ps.setLineColor('black')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralLibraryPlotWidgetStyle(
            name='Bright',
            fg=QColor('black'),
            bg=QColor('white'),
            ic=QColor('black'),
            sc=QColor('red'),
            cc=QColor('red'),
            tc=QColor('#aaff00')
        )

    def __init__(self,
                 name: str = 'default_plot_colors',
                 fg: QColor = QColor('white'),
                 bg: QColor = QColor('black'),
                 ic: QColor = QColor('white'),
                 sc: QColor = QColor('yellow'),
                 cc: QColor = QColor('yellow'),
                 tc: QColor = QColor('#aaff00')
                 ):

        self.name: str = name
        self.foregroundColor: QColor = fg
        self.backgroundColor: QColor = bg
        self.textColor: QColor = ic
        self.selectionColor: QColor = sc
        self.crosshairColor: QColor = cc
        self.temporaryColor: QColor = tc

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
        settings = speclibSettings()

        settings.setValue(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE, self.profileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE, self.temporaryProfileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.BACKGROUND_COLOR, self.backgroundColor)
        settings.setValue(SpectralLibrarySettingsKey.FOREGROUND_COLOR, self.foregroundColor)
        settings.setValue(SpectralLibrarySettingsKey.INFO_COLOR, self.textColor)
        settings.setValue(SpectralLibrarySettingsKey.CROSSHAIR_COLOR, self.crosshairColor)
        settings.setValue(SpectralLibrarySettingsKey.TEMPORARY_COLOR, self.temporaryColor)
        settings.setValue(SpectralLibrarySettingsKey.SELECTION_COLOR, self.selectionColor)
        settings.setValue(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS, self.useRendererColors)

    def printDifferences(self, renderer):
        assert isinstance(renderer, SpectralLibraryPlotWidgetStyle)
        keys = [k for k in self.__dict__.keys()
                if not k.startswith('_') and
                k not in ['name', 'mInputSource']]

        differences = []
        for k in keys:
            if self.__dict__[k] != renderer.__dict__[k]:
                differences.append(f'{k}: {self.__dict__[k]} != {renderer.__dict__[k]}')
        if len(differences) == 0:
            print(f'# no differences')
        else:
            print(f'# {len(differences)} differences:')
            for d in differences:
                print(d)
        return True

    def __eq__(self, other):
        if not isinstance(other, SpectralLibraryPlotWidgetStyle):
            return False
        else:
            keys = [k for k in self.__dict__.keys()
                    if not k.startswith('_') and
                    k not in ['name', 'mInputSource']]

            for k in keys:
                if self.__dict__[k] != other.__dict__[k]:
                    return False
            return True


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
            self.btnReset.setEnabled(isinstance(self.mResetStyle, SpectralLibraryPlotWidgetStyle) and
                                     self.spectralProfileWidgetStyle() != self.mResetStyle)
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


class SpectralProfileColorPropertyWidget(QWidget):
    """
    Widget to specify the SpectralProfile colors.

    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mContext: QgsExpressionContext = QgsExpressionContext()
        self.mRenderContext: QgsRenderContext = QgsRenderContext()
        self.mRenderer: QgsFeatureRenderer = None
        self.mDefaultColor = QColor('green')
        self.mColorButton = QgsColorButton()
        self.mColorButton.colorChanged.connect(self.onButtonColorChanged)

        self.mColorButton.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.mPropertyOverrideButton = QgsPropertyOverrideButton()
        self.mPropertyOverrideButton.registerLinkedWidget(self.mColorButton)
        # self.mPropertyOverrideButton.aboutToShowMenu.connect(self.updateOverrideMenu)
        l = QHBoxLayout()
        l.addWidget(self.mColorButton)
        l.addWidget(self.mPropertyOverrideButton)
        l.setSpacing(2)
        l.setContentsMargins(0, 0, 0, 0)
        self.sizePolicy().setHorizontalPolicy(QSizePolicy.Preferred)
        self.setLayout(l)

        self.mPropertyDefinition = QgsPropertyDefinition()
        self.mPropertyDefinition.setName('Profile line color')

    def updateOverrideMenu(self, *args):

        s = ""

    def setLayer(self, layer: QgsVectorLayer):

        self.mPropertyOverrideButton.registerExpressionContextGenerator(layer)
        self.mPropertyOverrideButton.setVectorLayer(layer)
        self.mPropertyOverrideButton.updateFieldLists()

        self.mContext = layer.createExpressionContext()
        feature: QgsFeature = None
        for f in layer.getFeatures():
            feature = f
            break
        if isinstance(feature, QgsFeature):
            self.mContext.setFeature(f)
            self.mRenderContext.setExpressionContext(self.mContext)
            self.mRenderer = layer.renderer().clone()
            # self.mRenderer.startRender(self.mRenderContext, layer.fields())
            # symbol = self.mRenderer.symbolForFeature(feature, self.mRenderContext)
            # scope = symbol.symbolRenderContext().expressionContextScope()
            # self.mContext.appendScope(scope)

            # self.mTMP = [renderContext, scope, symbol, renderer]
            s = ""

    def onButtonColorChanged(self, color: QColor):
        self.mPropertyOverrideButton.setActive(False)

    def setDefaultColor(self, color: QColor):
        self.mDefaultColor = QColor(color)

    def setToProperty(self, property: QgsProperty):
        assert isinstance(property, QgsProperty)

        if property.propertyType() == QgsProperty.StaticProperty:
            self.mColorButton.setColor(property.valueAsColor(self.mContext, self.mDefaultColor)[0])
            self.mPropertyOverrideButton.setActive(False)
        else:
            self.mPropertyOverrideButton.setActive(True)
            self.mPropertyOverrideButton.setToProperty(property)
        # self.mColorButton.setColor(property.valueAsColor())

    def toProperty(self) -> QgsProperty:

        if self.mPropertyOverrideButton.isActive():
            return self.mPropertyOverrideButton.toProperty()
        else:
            prop = QgsProperty()
            prop.setStaticValue(self.mColorButton.color())
            return prop


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


FEATURE_ID = int
FIELD_INDEX = int
MODEL_NAME = str
X_UNIT = str

MODEL_DATA_KEY = typing.Tuple[FEATURE_ID, FIELD_INDEX, MODEL_NAME]
PLOT_DATA_KEY = typing.Tuple[FEATURE_ID, FIELD_INDEX, MODEL_NAME, X_UNIT]
VISUALIZATION_KEY = typing.Tuple[SpectralProfilePlotVisualization, PLOT_DATA_KEY]


class SpectralProfilePlotDataItem(PlotDataItem):
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
        self.mVisualizationKey: VISUALIZATION_KEY = None

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

    def visualization(self) -> SpectralProfilePlotVisualization:
        return self.mVisualizationKey[0]

    def plotDataKey(self) -> PLOT_DATA_KEY:
        return self.mVisualizationKey[1]

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
    sigPlotDataItemSelected = pyqtSignal(SpectralProfilePlotDataItem, Qt.Modifier)

    def __init__(self, parent=None):

        mViewBox = SpectralViewBox()
        plotItem = SpectralLibraryPlotItem(
            axisItems={'bottom': SpectralXAxis(orientation='bottom')}
            , viewBox=mViewBox
        )

        super().__init__(parent, plotItem=plotItem)
        pi: SpectralLibraryPlotItem = self.getPlotItem()
        assert isinstance(pi, SpectralLibraryPlotItem) and pi == self.plotItem

        self.mCurrentMousePosition: QPointF = None
        self.setAntialiasing(True)
        self.setAcceptDrops(True)

        self.mCrosshairLineV = pg.InfiniteLine(angle=90, movable=False)
        self.mCrosshairLineH = pg.InfiniteLine(angle=0, movable=False)

        self.mInfoLabelCursor = pg.TextItem(text='<cursor position>', anchor=(1.0, 0.0))
        self.mInfoScatterPoint: pg.ScatterPlotItem = pg.ScatterPlotItem()
        self.mInfoScatterPoint.sigClicked.connect(self.onInfoScatterClicked)
        self.mInfoScatterPoint.setZValue(9999999)
        self.mInfoScatterPoint.setBrush(self.mCrosshairLineH.pen.color())

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

        # self.mUpdateTimer = QTimer()
        # self.mUpdateTimer.setInterval(500)
        # self.mUpdateTimer.setSingleShot(False)

        self.mMaxInfoLength: int = 30
        self.mShowCrosshair: bool = True
        self.mShowCursorInfo: bool = True

    def dragEnterEvent(self, ev: QDragEnterEvent):

        s = ""

    def onProfileClicked(self, data: MouseClickData):
        """
        Slot to react to mouse-clicks on SpectralProfilePlotDataItems
        :param data: MouseClickData
        """
        modifiers = QApplication.keyboardModifiers()

        pdi: SpectralProfilePlotDataItem = data.pdi
        vis, dataKey = pdi.visualizationKey()
        fid, fieldIndex, model, xUnit = dataKey
        name = pdi.name()
        if not isinstance(name, str):
            name = ''

        if modifiers == Qt.AltModifier:
            x = data.xValue
            y = data.yValue

            if isinstance(pdi, SpectralProfilePlotDataItem):
                ptColor: QColor = self.mInfoScatterPoint.opts['brush'].color()
                self.mInfoScatterPointHtml = f'<div style="color:{ptColor.name()}; text-align:right;">' + \
                                             f'{vis.field().name()},{fid} [{data.idx}]<br/>' + \
                                             f'x={x} {xUnit}<br/>' + \
                                             f'y={y}<br/>' + \
                                             textwrap.shorten(name, width=self.mMaxInfoLength, placeholder='...') + \
                                             f'</div>'
            else:
                s = ""
            self.mInfoScatterPoint.setData(x=[x],
                                           y=[y],
                                           symbol='o')
            self.mInfoScatterPoint.setVisible(True)

        else:
            if isinstance(pdi, SpectralProfilePlotDataItem):
                self.sigPlotDataItemSelected.emit(pdi, modifiers)

        self.updatePositionInfo()

    def setShowCrosshair(self, b: bool):
        assert isinstance(b, bool)
        self.mShowCrosshair = b

    def setShowCursorInfo(self, b: bool):
        assert isinstance(b, bool)
        self.mShowCursorInfo = b

    def xAxis(self) -> SpectralXAxis:
        return self.plotItem.getAxis('bottom')

    def yAxis(self) -> AxisItem:
        return self.plotItem.getAxis('left')

    def viewBox(self) -> SpectralViewBox:
        return self.plotItem.getViewBox()

    def clearInfoScatterPoint(self):
        self.mInfoScatterPoint.setVisible(False)
        self.mInfoScatterPointHtml = ''

    def spectralProfilePlotDataItems(self) -> typing.List[SpectralProfilePlotDataItem]:
        return [item for item in self.plotItem.listDataItems()
                if isinstance(item, SpectralProfilePlotDataItem)]

    def setWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):

        self.mInfoLabelCursor.setColor(style.textColor)
        self.mInfoScatterPoint.opts['pen'].setColor(QColor(style.selectionColor))
        self.mInfoScatterPoint.opts['brush'].setColor(QColor(style.selectionColor))
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

    def updatePositionInfo(self):
        x, y = self.mCurrentMousePosition.x(), self.mCurrentMousePosition.y()
        positionInfoHtml = '<html><body>'
        if self.xAxis().mUnit == 'DateTime':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(datetime64(x), y)
        elif self.xAxis().mUnit == 'DOY':
            positionInfoHtml += 'x:{}\ny:{:0.5f}'.format(int(x), y)
        else:
            positionInfoHtml += 'x:{:0.5f}\ny:{:0.5f}'.format(x, y)

        positionInfoHtml += self.mInfoScatterPointHtml
        positionInfoHtml += '</body></html>'
        self.mInfoLabelCursor.setHtml(positionInfoHtml)

    def leaveEvent(self, ev):
        super().leaveEvent(ev)

        # disable mouse-position related plot items
        self.mCrosshairLineH.setVisible(False)
        self.mCrosshairLineV.setVisible(False)
        self.mInfoLabelCursor.setVisible(False)

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


class SpectralProfilePlotControlModel(QAbstractItemModel):
    PIX_FIELD = 0
    PIX_MODEL = 1
    PIX_LABEL = 2
    PIX_COLOR = 3
    PIX_STYLE = 4

    CIX_NAME = 0
    CIX_VALUE = 1

    class PropertyHandle(object):
        def __init__(self, parentObject):
            self.mParentObject = parentObject

        def parentVisualization(self) -> SpectralProfilePlotVisualization:
            return self.mParentObject

        def __hash__(self):
            return hash(id(self.mParentObject))

    # CIX_MARKER = 4

    sigProgressChanged = pyqtSignal(float)

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mProfileVisualizations: typing.List[SpectralProfilePlotVisualization] = []
        self.mNodeHandles: typing.Dict[object, SpectralProfilePlotControlModel.PropertyHandle] = dict()

        # # workaround https://github.com/qgis/QGIS/issues/45228
        self.mStartedCommitEditWrapper: bool = False

        self.mModelList: SpectralProcessingModelList = SpectralProcessingModelList(allow_empty=True)
        self.mProfileFieldModel: QgsFieldModel = QgsFieldModel()

        self.mPlotWidget: SpectralProfilePlotWidget = None

        self.mColumnNames = {self.CIX_NAME: 'Name',
                             self.CIX_VALUE: 'Value'
                             }

        self.mColumnTooltips = {
            self.CIX_NAME: 'Visualization property names',
            self.CIX_VALUE: 'Visualization property values',

            # self.CIX_MARKER: 'Here you can specify the marker symbol ofr each profile type'
        }

        self.mPropertyNames = {self.PIX_FIELD: 'Field',
                               self.PIX_MODEL: 'Model',
                               self.PIX_LABEL: 'Label',
                               self.PIX_COLOR: 'Color',
                               self.PIX_STYLE: 'Style',
                               }
        self.mPropertyTooltips = {
            self.PIX_FIELD: 'Field with profile values.',
            self.PIX_MODEL: 'Model to process profile values "on-the-fly". Can be empty.',
            self.PIX_LABEL: 'Field/Expression to generate profile names.',
            self.PIX_COLOR: 'Field/Expression to generate profile colors.',
            self.PIX_STYLE: 'Profile styling.',

        }

        self.mChangedFIDs: typing.Set[int] = set()
        # self.mPlotDataItems: typing.List[SpectralProfilePlotDataItem] = list()
        self.mFID_VIS_Mapper: typing.Dict[
            typing.Tuple[FEATURE_ID, SpectralProfilePlotVisualization], SpectralProfilePlotDataItem]

        # Update plot data and colors

        # mCache3PlotData[(fid, fidx, modelId, xunit)] -> model data, but converted to the requested plot units
        # mCache1FeatureData[fid] -> QgsFeature
        self.mCache1FeatureData: typing.Dict[FEATURE_ID, SpectralProfile] = dict()
        # mCache1FeatureData[fid] -> QColor
        self.mCache1FeatureColors: typing.Dict[FEATURE_ID, QColor] = dict()
        # mCache2ModelData[(fid, fidx, modelId))] -> model /  raw profile data
        self.mCache2ModelData: typing.Dict[MODEL_DATA_KEY, dict] = dict()
        # mCache2ModelData[(fid, fidx, modelId, xunit))] -> dict
        self.mCache3PlotData: typing.Dict[PLOT_DATA_KEY, dict] = dict()

        self.mUnitConverterFunctionModel = UnitConverterFunctionModel()
        self.mDualView: QgsDualView = None
        self.mSpeclib: QgsVectorLayer = None

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.mXUnit: str = self.mXUnitModel[0]
        self.mXUnitInitialized: bool = False
        self.mMaxProfiles: int = 64
        self.mShowSelectedFeaturesOnly: bool = False
        self.mUseFeatureRenderer: bool = True

        self.mPlotWidgetStyle: SpectralLibraryPlotWidgetStyle = SpectralLibraryPlotWidgetStyle.dark()
        self.mTemporaryProfileIDs: typing.Set[FEATURE_ID] = set()
        # self.mSelectedDataColor: QColor = QColor('yellow')
        # self.mTemporaryDataColor: QColor = QColor('green')
        # self.mBackgroundColor
        # self.mExampleContext: QgsExpressionContext = QgsExpressionContext()
        # self.updateExampleContext()

    def createPropertyColor(self, property: QgsProperty, fid: int = 1) -> QColor:
        assert isinstance(property, QgsProperty)
        defaultColor = QColor('white')
        renderer: QgsFeatureRenderer = None
        context = QgsExpressionContext()
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            context = speclib.createExpressionContext()
            if speclib.featureCount() > 0:
                feature: QgsFeature = speclib.getFeature(fid)
                if not isinstance(feature, QgsFeature):
                    for f in speclib.getFeatures():
                        feature = f
                        break
                context.setFeature(feature)

                renderContext = QgsRenderContext()
                renderer = speclib.renderer().clone()

                renderer.startRender(renderContext, speclib.fields())
                symbol = renderer.symbolForFeature(feature, renderContext)
                symbol.symbolRenderContext().expressionContextScope()
                context.appendScope(QgsExpressionContextScope(symbol.symbolRenderContext().expressionContextScope()))
                # return defaultColor

        color, success = property.valueAsColor(context, defaultColor=defaultColor)
        if isinstance(renderer, QgsFeatureRenderer):
            renderer.stopRender(renderContext)

        return color

    def setPlotWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        self.mPlotWidgetStyle = style
        if self.rowCount() > 0:
            # set background color to each single plotstyle
            for vis in self.mProfileVisualizations:
                vis.plotStyle().setBackgroundColor(style.backgroundColor)

            # update plot backgrounds
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0)
            )

    def parent(self, index: QModelIndex):
        if not index.isValid():
            return QModelIndex()

        content = index.internalPointer()
        if isinstance(content, SpectralProfilePlotVisualization):
            return QModelIndex()
        elif isinstance(content, SpectralProfilePlotControlModel.PropertyHandle):
            parentObj = content.parentVisualization()
            if isinstance(parentObj, SpectralProfilePlotVisualization):
                # this is a property node, so return the index of its parent SpectralProfilePlotVisualization
                r = self.mProfileVisualizations.index(parentObj)
                return self.createIndex(r, 0, parentObj)
            else:
                raise NotImplementedError()

    def setTemporaryProfiles(self, profiles: typing.Dict[SpectralProfile, QColor]):
        self.mTemporaryProfileIDs = set()

    sigShowSelectedFeaturesOnlyChanged = pyqtSignal(bool)

    def setShowSelectedFeaturesOnly(self, b: bool):
        if self.mShowSelectedFeaturesOnly != b:
            self.mShowSelectedFeaturesOnly = b
            self.updatePlot()
            self.sigShowSelectedFeaturesOnlyChanged.emit(self.mShowSelectedFeaturesOnly)

    def showSelectedFeaturesOnly(self) -> bool:
        return self.mShowSelectedFeaturesOnly

    sigUseFeatureRendererChanged = pyqtSignal(bool)

    def setUseFeatureRenderer(self, b: bool):
        if self.mUseFeatureRenderer != b:
            self.mUseFeatureRenderer = b
            self.updatePlot()
            self.sigUseFeatureRendererChanged.emit(self.mUseFeatureRenderer)

    def useFeatureRenderer(self) -> bool:
        return self.mUseFeatureRenderer

    sigXUnitChanged = pyqtSignal(str)

    def setXUnit(self, unit: str):
        if self.mXUnit != unit:
            unit_ = self.mXUnitModel.findUnit(unit)
            assert unit_, f'Unknown unit for x-axis: {unit}'
            self.mXUnit = unit_

            #  baseUnit = UnitLookup.baseUnit(unit_)
            labelName = self.mXUnitModel.unitData(unit_, Qt.DisplayRole)
            self.mPlotWidget.xAxis().setUnit(unit, labelName=labelName)
            self.mPlotWidget.clearInfoScatterPoint()
            # self.mPlotWidget.xAxis().setLabel(text='x values', unit=unit_)
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
        if n != self.mMaxProfiles:
            self.mMaxProfiles = n
            self.updatePlot()
            self.sigMaxProfilesChanged.emit(self.mMaxProfiles)

    def maxProfiles(self) -> int:
        return self.mMaxProfiles

    def __len__(self) -> int:
        return len(self.mProfileVisualizations)

    def __iter__(self) -> typing.Iterator[SpectralProfilePlotVisualization]:
        return iter(self.mProfileVisualizations)

    def __getitem__(self, slice):
        return self.mProfileVisualizations[slice]

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
        for v in vis:
            self.mNodeHandles[v] = SpectralProfilePlotControlModel.PropertyHandle(v)
        self.endInsertRows()

        self.updatePlot()

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            v = self[row]
            assert isinstance(v, SpectralProfilePlotVisualization)
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.mProfileVisualizations[row]
            self.mNodeHandles.pop(v)
            self.endRemoveRows()
            return True
        return False

    def removeVisualizations(self, vis: typing.Union[SpectralProfilePlotVisualization,
                                                     typing.List[SpectralProfilePlotVisualization]]):

        if isinstance(vis, SpectralProfilePlotVisualization):
            vis = [vis]
        for v in vis:
            assert isinstance(v, SpectralProfilePlotVisualization)
            assert v in self.mProfileVisualizations
            i = self.mProfileVisualizations.index(v)
            self.removeRows(i, 1)

        self.updatePlot()

    def updateData(self, fids: typing.List[int], models: typing.List[QgsProcessingModelAlgorithm]):
        # loads SpectralProfiles for the requested FIDs and calculates the model results on it
        pass

    def updatePlot(self, fids=[]):

        if not (isinstance(self.mPlotWidget, SpectralProfilePlotWidget) and isinstance(self.speclib(), QgsVectorLayer)):
            return
        SL: QgsVectorLayer = self.speclib()
        n = 0
        n_max_pdis = self.maxProfiles()
        NAME2FIELDIDX = {SL.fields().at(i).name(): i for i in range(SL.fields().count())}
        FIELDIDX2NAME = {i: SL.fields().at(i).name() for i in range(SL.fields().count())}
        VIS2FIELD_INDEX = {v: SL.fields().lookupField(v.field().name()) for v in self}
        PFIELDS = {SL.fields().lookupField(f.name()): f for f in profile_field_list(SL)}

        # get the data to display
        PROFILES_TO_LOAD: typing.Set[int] = set()
        # COLORS_TO_LOAD: typing.Set[int] = set()
        MODELDATA_TO_LOAD: typing.Dict[str, set] = dict()

        feature_priority = self.featurePriority()
        visualizations = [v for v in self if v.isVisible() and v.isComplete() and v.speclib() == self.mSpeclib]

        xunit = self.xUnit()

        DATA_TO_VISUALIZE = list()

        for fid in feature_priority:
            if len(DATA_TO_VISUALIZE) >= n_max_pdis:
                break

            profile: SpectralProfile = self.mCache1FeatureData.get(fid, None)
            if not isinstance(profile, SpectralProfile):
                PROFILES_TO_LOAD.add(fid)
                continue

            for vis in visualizations:
                if len(DATA_TO_VISUALIZE) >= n_max_pdis:
                    break
                # this key describes the actually plotted values
                # plotDataKey = (fid, fidx, mid, xunit)
                plotDataKey = (fid, VIS2FIELD_INDEX[vis], vis.modelId(), xunit)

                # this key describes what is visualized by a Plot Data Item (PDI)
                # Visualization + Plot Data Key
                visKey = (vis, plotDataKey)

                #
                modelDataKey = (fid, VIS2FIELD_INDEX[vis], vis.modelId())
                modeldata = self.mCache2ModelData.get(modelDataKey, None)
                if not isinstance(modeldata, dict):
                    loadKey = (modelDataKey[1], modelDataKey[2])
                    fids = MODELDATA_TO_LOAD.get(loadKey, set())
                    fids.add(fid)
                    MODELDATA_TO_LOAD[loadKey] = fids
                    continue

                if modeldata['y'] is None:
                    # empty profile, nothing to plot
                    continue

                if self.mXUnitInitialized is False and modeldata.get('xUnit', None) is not None:
                    self.mXUnitInitialized = True
                    # this will call updatePlot agai, so we can return afterwards
                    self.setXUnit(modeldata['xUnit'])
                    return

                if plotDataKey not in self.mCache3PlotData.keys():
                    # convert model data to unit
                    convertedData = self.modelDataToXUnitPlotData(modeldata, xunit)
                    self.mCache3PlotData[plotDataKey] = convertedData
                else:
                    convertedData = self.mCache3PlotData[plotDataKey]

                if convertedData is None:
                    continue

                DATA_TO_VISUALIZE.append(visKey)

        # Update plot items
        spdis: typing.List[SpectralProfilePlotDataItem] = self.mPlotWidget.spectralProfilePlotDataItems()

        PLOT_DATA_ITEMS: typing.Dict[VISUALIZATION_KEY, SpectralProfilePlotDataItem] = {i.visualizationKey(): i for i in
                                                                                        spdis}
        FREE = []
        for k in list(PLOT_DATA_ITEMS.keys()):
            if k not in DATA_TO_VISUALIZE:
                pdi = PLOT_DATA_ITEMS.pop(k)
                FREE.append(pdi)

        pdiGenerator = PDIGenerator(FREE[:], onProfileClicked=self.mPlotWidget.onProfileClicked)
        context = QgsExpressionContext()

        if self.mShowSelectedFeaturesOnly:
            selected_fids = set()
        else:
            selected_fids = self.speclib().selectedFeatureIds()

        VIS_RENDERERS: typing.Dict[SpectralProfilePlotVisualization,
                                   typing.Tuple[QgsFeatureRenderer, QgsRenderContext]] = dict()

        for vis in visualizations:
            vis: SpectralProfilePlotVisualization

            renderer: QgsFeatureRenderer = self.speclib().renderer().clone()
            renderContext = QgsRenderContext()
            # renderer.startRender(renderContext, self.speclib().fields())
            renderContext.setExpressionContext(self.speclib().createExpressionContext())

            VIS_RENDERERS[vis] = (renderer, renderContext)

        context = self.speclib().createExpressionContext()

        for zValue, k in enumerate(DATA_TO_VISUALIZE):
            vis, plotDataKey = k
            fid, idx, modelName, xUnit = plotDataKey

            profile = self.mCache1FeatureData[fid]
            context.setFeature(profile)
            plotData = self.mCache3PlotData[plotDataKey]
            expr: QgsExpression = vis.labelExpression()
            name = expr.evaluate(context)
            if not isinstance(name, str):
                name = None
            style: PlotStyle = vis.plotStyle()
            linePen = pg.mkPen(style.linePen)
            symbolPen = pg.mkPen(style.markerPen)
            symbolBrush = pg.mkBrush(style.markerBrush)

            featureColor: QColor = vis.plotStyle().lineColor()

            if fid in self.mTemporaryProfileIDs:
                # special color
                featureColor = self.mPlotWidgetStyle.temporaryColor
                linePen.setColor(featureColor)
                symbolPen.setColor(featureColor)
                symbolBrush.setColor(featureColor)

            elif fid in selected_fids:

                # show all profiles, special highlight of selected

                linePen.setColor(self.mPlotWidgetStyle.selectionColor)
                linePen.setWidth(style.lineWidth() + 2)
                symbolPen.setColor(self.mPlotWidgetStyle.selectionColor)
                symbolBrush.setColor(self.mPlotWidgetStyle.selectionColor)
            else:

                renderer, renderContext = VIS_RENDERERS[vis]
                renderContext.expressionContext().setFeature(profile)

                renderer.startRender(renderContext, profile.fields())
                qgssymbol = renderer.symbolForFeature(profile, renderContext)
                if isinstance(qgssymbol, QgsSymbol):
                    symbolScope = qgssymbol.symbolRenderContext().expressionContextScope()
                    context.appendScope(symbolScope)

                prop = vis.colorProperty()
                featureColor, success = prop.valueAsColor(context, defaultColor=QColor('white'))
                renderer.stopRender(renderContext)
                if isinstance(qgssymbol, QgsSymbol):
                    context.popScope()
                    pass
                if not success:
                    s = ""
                linePen.setColor(featureColor)
                symbolPen.setColor(featureColor)
                symbolBrush.setColor(featureColor)

            symbol = style.markerSymbol
            symbolSize = style.markerSize

            x = plotData['x']
            y = plotData['y']
            if isinstance(x[0], (datetime.date, datetime.datetime)):
                x = np.asarray(x, dtype=np.datetime64)
            if k in PLOT_DATA_ITEMS.keys():
                pdi = PLOT_DATA_ITEMS[k]
            else:
                pdi = pdiGenerator.__next__()
                pdi: SpectralProfilePlotDataItem
                pdi.setVisualizationKey(k)
            assert isinstance(pdi, SpectralProfilePlotDataItem)

            # replace None by NaN
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            connect = np.isfinite(x) & np.isfinite(y)
            pdi.setData(x=x, y=y, z=-1 * zValue,
                        connect=connect,
                        name=name, pen=linePen,
                        symbol=symbol, symbolPen=symbolPen, symbolBrush=symbolBrush, symbolSize=symbolSize)

            tooltip = f'<html><body><table>' \
                      f'<tr><td>name</td><td>{name}</td></tr>' \
                      f'<tr><td>fid</td><td>{fid}</td></tr>' \
                      f'<tr><td>field</td><td>{FIELDIDX2NAME[idx]}</td></tr>' \
                      f'</table></body></html>'

            pdi.setToolTip(tooltip)
            pdi.curve.setToolTip(tooltip)
            pdi.scatter.setToolTip(tooltip)
            pdi.setZValue(-1 * zValue)

            PLOT_DATA_ITEMS[k] = pdi
        for v, t in VIS_RENDERERS.items():
            renderer, renderContext = t
            # renderer.stopRender(renderContext)

        to_remove = [pdi for pdi in spdis if pdi not in PLOT_DATA_ITEMS.values()]
        for pdi in to_remove:
            self.mPlotWidget.removeItem(pdi)

        to_add = [pdi for pdi in PLOT_DATA_ITEMS.values() if pdi not in spdis]
        for pdi in to_add:
            self.mPlotWidget.addItem(pdi)

        # load missing data

        self.loadProfiles(PROFILES_TO_LOAD)
        self.loadModelData(MODELDATA_TO_LOAD)
        # self.loadFeatureColors(COLORS_TO_LOAD)

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int,
                        parent: QModelIndex) -> bool:

        return data.hasFormat(SpectralProfilePlotVisualization.MIME_TYPE)

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:

        if action == Qt.IgnoreAction:
            return True

        visualizations = SpectralProfilePlotVisualization.fromMimeData(data)
        if len(visualizations) > 0:
            self.insertVisualizations(row, visualizations)
            return True
        else:
            return False

    VIS_MIME_TYPE = 'application/spectrallibraryplotwidget-items'

    def mimeTypes(self) -> typing.List[str]:
        return [SpectralProfilePlotVisualization.MIME_TYPE]

    def mimeData(self, indexes: typing.Iterable[QModelIndex]) -> QMimeData:



        visualizations = []
        rows = []
        for idx in indexes:
            vis = self.data(idx, role=Qt.UserRole)
            if isinstance(vis, SpectralProfilePlotVisualization) and vis not in visualizations:
                visualizations.append(vis)
                rows.append(idx.row())
        mimeData = SpectralProfilePlotVisualization.toMimeData(visualizations)

        return mimeData

    def modelDataToXUnitPlotData(self, modelData: dict, xUnit: str) -> dict:
        modelData = modelData.copy()

        func = self.mUnitConverterFunctionModel.convertFunction(modelData['xUnit'], xUnit)
        x = func(modelData['x'])
        y = modelData['y']
        if x is None:
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

    def loadProfiles(self, fids):
        if len(fids) > 0:
            # load core data
            task = SpectralProfileLoadingTask(self.speclib(), fids=fids, callback=self.onProfilesLoaded)
            task.progressChanged.connect(self.sigProgressChanged.emit)
            if False:
                tm: QgsTaskManager = QgsApplication.instance().taskManager()
                tm.addTask(task)
            else:
                task.finished(task.run())

    def loadModelData(self, jobs: dict):
        if len(jobs) == 0:
            return

        feedback = QgsProcessingFeedback()
        for job_key, fids in jobs.items():
            context = QgsProcessingContext()
            context.setFeedback(feedback)

            profile_field, model_id = job_key
            request = QgsFeatureRequest()
            request.setFilterFids(list(fids))
            model = self.mModelList.modelId2model(model_id)

            blockList = list(SpectralProfileBlock.fromSpectralProfiles(self.speclib().getFeatures(request),
                                                                       profile_field,
                                                                       feedback))
            parameters = {model.parameterDefinitions()[0].name(): blockList}
            assert model.prepareAlgorithm(parameters, context, feedback)
            try:
                results = model.processAlgorithm(parameters, context, feedback)
                for p in model.outputDefinitions():
                    if isinstance(p, SpectralProcessingProfilesOutput):
                        parameterResult: typing.List[SpectralProfileBlock] = outputParameterResult(results, p.name())
                        if isinstance(parameterResult, list):
                            for block in parameterResult:
                                if isinstance(block, SpectralProfileBlock):
                                    for fid, d in block.profileValueDictionaries():
                                        # MODEL_DATA_KEY = typing.Tuple[FEATURE_ID, FIELD_INDEX, MODEL_NAME]
                                        model_data_key: MODEL_DATA_KEY = (fid, profile_field, model_id)

                                        self.mCache2ModelData[model_data_key] = d
                                        block.fids()
                        break
            except QgsProcessingException as ex:
                feedback.reportError(str(ex))
            s = ""
        s = ""

    def onProfilesLoaded(self, success: bool, task: SpectralProfileLoadingTask):

        if not success:
            print(f'{task.exception}', file=sys.stderr)
        if len(task.RESULTS) == 0:
            return

        updated = self.mCache1FeatureData.keys()
        # save the entire spectral profiles
        self.mCache1FeatureData.update(task.RESULTS)

        profile_field_indices = self.profileFieldIndices()
        for fid, sp in task.RESULTS.items():
            for fidx in profile_field_indices:
                # create the default model spectrum
                self.mCache2ModelData[(fid, fidx, '')] = sp.values(profile_field_index=fidx)

        if len(updated) > 0:
            # self.loadFeatureColors(fids=updated)
            self.updatePlot(fids=updated)
            pass

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

    def rowCount(self, parent=QModelIndex(), *args, **kwargs):

        if not parent.isValid():
            return len(self.mProfileVisualizations)
        obj = parent.internalPointer()
        if isinstance(obj, SpectralProfilePlotVisualization):
            return len(self.mPropertyNames)
        return 0

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.mColumnNames)

    def index(self, row, col, parent: QModelIndex = QModelIndex(), *args, **kwargs) -> QModelIndex:

        obj = None
        if not parent.isValid():
            obj = self.mProfileVisualizations[row]
        else:
            # sub-node ->
            vis = self.mProfileVisualizations[parent.row()]
            obj = self.mNodeHandles[vis]
            # obj = (vis, self.mPropertyNames[row])
        return self.createIndex(row, col, obj)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        obj = index.internalPointer()
        if isinstance(obj, SpectralProfilePlotVisualization):
            flags = flags | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
            if index.column() == self.CIX_NAME:
                flags = flags | Qt.ItemIsUserCheckable
        if index.column() == self.CIX_VALUE:
            flags = flags | Qt.ItemIsEditable
        return flags

    def dualView(self) -> QgsDualView:
        return self.mDualView

    def setDualView(self, dualView: QgsDualView):
        speclib = None
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
                self.mSpeclib.attributeDeleted.disconnect(self.onSpeclibAttributesChanged)
                self.mSpeclib.attributeAdded.disconnect(self.onSpeclibAttributesChanged)
                self.mSpeclib.editCommandEnded.disconnect(self.onSpeclibEditCommandEnded)
                # self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
                self.mSpeclib.beforeCommitChanges.disconnect(self.onSpeclibBeforeCommitChanges)
                self.mSpeclib.afterCommitChanges.disconnect(self.onSpeclibAfterCommitChanges)
                self.mSpeclib.committedFeaturesAdded.disconnect(self.onSpeclibCommittedFeaturesAdded)

                self.mSpeclib.featuresDeleted.disconnect(self.onSpeclibFeaturesDeleted)
                self.mSpeclib.selectionChanged.disconnect(self.onSpeclibSelectionChanged)
                self.mSpeclib.rendererChanged.disconnect(self.onSpeclibRendererChanged)

            self.mSpeclib = speclib

            # register signals
            if isinstance(self.mSpeclib, QgsVectorLayer):
                self.mSpeclib.attributeDeleted.connect(self.onSpeclibAttributesChanged)
                self.mSpeclib.attributeAdded.connect(self.onSpeclibAttributesChanged)
                self.mSpeclib.editCommandEnded.connect(self.onSpeclibEditCommandEnded)
                # self.mSpeclib.attributeValueChanged.connect(self.onSpeclibAttributeValueChanged)
                self.mSpeclib.beforeCommitChanges.connect(self.onSpeclibBeforeCommitChanges)
                self.mSpeclib.afterCommitChanges.connect(self.onSpeclibAfterCommitChanges)
                self.mSpeclib.committedFeaturesAdded.connect(self.onSpeclibCommittedFeaturesAdded)

                self.mSpeclib.featuresDeleted.connect(self.onSpeclibFeaturesDeleted)
                self.mSpeclib.selectionChanged.connect(self.onSpeclibSelectionChanged)
                self.mSpeclib.rendererChanged.connect(self.onSpeclibRendererChanged)
                self.onSpeclibAttributesChanged()


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

    def onSpeclibCommittedFeaturesAdded(self, id, features):

        if id != self.speclib().id():
            return

        newFIDs = [f.id() for f in features]
        # see qgsvectorlayereditbuffer.cpp
        oldFIDs = list(reversed(list(self.speclib().editBuffer().addedFeatures().keys())))

        OLD2NEW = {o: n for o, n in zip(oldFIDs, newFIDs)}
        updates = dict()

        # rename fid in cache1
        for o in [k for k in oldFIDs if k in self.mCache1FeatureData.keys()]:
            self.mCache1FeatureData[OLD2NEW[o]] = self.mCache1FeatureData.pop(o)

        # rename fid in cache2
        for modelDataKey in [mk for mk in self.mCache2ModelData.keys() if mk[0] in oldFIDs]:
            self.mCache2ModelData[(OLD2NEW[modelDataKey[0]], modelDataKey[1], modelDataKey[2])] = \
                self.mCache2ModelData.pop(modelDataKey)

        # rename fid in cache3
        for plotDataKey in [pk for pk in self.mCache3PlotData.keys() if pk[0] in oldFIDs]:
            self.mCache3PlotData[(OLD2NEW[plotDataKey[0]], plotDataKey[1], plotDataKey[2], plotDataKey[3])] = \
                self.mCache3PlotData.pop(plotDataKey)

        # rename fids in feature color cache
        for o in [k for k in self.mCache1FeatureColors if k in oldFIDs]:
            self.mCache1FeatureColors[OLD2NEW[o]] = self.mCache1FeatureColors.pop(o)

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
        self.updatePlot(fids=OLD2NEW.values())

    def onSpeclibAttributeValueChanged(self, fid: int, fidx: int, value):
        feature = self.mCache1FeatureData.get(fid, None)
        if isinstance(feature, QgsFeature):
            feature.setAttribute(fidx, value)

    def onSpeclibRendererChanged(self, *args):
        # self.loadFeatureColors()
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
        self.mCache1FeatureColors = {k: v for k, v in self.mCache1FeatureColors.items() if k not in fids_removed}
        self.mCache1FeatureData = {k: v for k, v in self.mCache1FeatureData.items() if k not in fids_removed}
        self.mCache2ModelData = {k: v for k, v in self.mCache2ModelData.items() if k[0] not in fids_removed}
        self.mCache3PlotData = {k: v for k, v in self.mCache3PlotData.items() if k[0] not in fids_removed}

        self.updatePlot()

    def onSpeclibEditCommandEnded(self, *args):
        # changedFIDs1 = list(self.speclib().editBuffer().changedAttributeValues().keys())
        changedFIDs2 = self.mChangedFIDs
        self.onSpeclibFeaturesDeleted(sorted(changedFIDs2))
        self.mChangedFIDs.clear()

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
            vis: SpectralProfilePlotVisualization
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

    def onSpeclibAttributesChanged(self):
        fields = QgsFields()
        for field in profile_field_list(self.mSpeclib):
            fields.append(field)
        self.mProfileFieldModel.setFields(fields)

        # remove visualization for deleted fields
        to_remove = [f for f in self if f.field().name() not in fields.names()]
        self.removeVisualizations(to_remove)

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def profileFields(self) -> typing.List[QgsField]:
        return profile_field_list(self.speclib())

    def profileFieldIndices(self) -> typing.List[int]:
        return profile_field_indices(self.speclib())

    def profileFieldNames(self) -> typing.List[str]:
        return profile_field_indices()

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        # two cases:
        handle = index.internalPointer()
        col = index.column()
        row = index.row()

        if role == Qt.UserRole:
            return handle

        if isinstance(handle, SpectralProfilePlotVisualization):
            # to node level: provide an overview
            # provide a summary only
            if role == Qt.UserRole:
                return handle
            if col == self.CIX_NAME and role == Qt.CheckStateRole:
                if role == Qt.CheckStateRole:
                    return Qt.Checked if handle.isVisible() else Qt.Unchecked
            if col == self.CIX_VALUE:
                if role == Qt.DisplayRole:
                    return handle.name()
                if role == Qt.EditRole:
                    return handle.name()

            if role == Qt.ToolTipRole:
                return f'{handle.name()}:<br/>field: {handle.field().name()}<br/>model: {handle.modelName()}'

            if role == Qt.ForegroundRole and not handle.isVisible():
                return QColor('grey')

        elif isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle):
            # sub-node level: provide details
            vis = handle.parentVisualization()
            vis: SpectralProfilePlotVisualization
            if role == Qt.ForegroundRole and not vis.isVisible():
                return QColor('grey')

            if col == self.CIX_NAME:
                if role == Qt.DisplayRole:
                    return self.mPropertyNames[row]
                if role == Qt.ToolTipRole:
                    return self.mPropertyTooltips[row]

                if role == Qt.DecorationRole:
                    if row == self.PIX_FIELD:
                        if not (isinstance(vis.field(), QgsField)
                                and isinstance(vis.speclib(), QgsVectorLayer)
                                and vis.field().name() in self.speclib().fields().names()):
                            return QIcon(r':/images/themes/default/mIconWarning.svg')

            if col == self.CIX_VALUE:
                if role == Qt.DisplayRole:
                    if row == self.PIX_FIELD:
                        return vis.field().name()
                    if row == self.PIX_COLOR:
                        property = vis.colorProperty()
                        if property.propertyType() == QgsProperty.ExpressionBasedProperty:
                            return property.expressionString()
                        elif property.propertyType() == QgsProperty.FieldBasedProperty:
                            return property.field()
                        else:
                            return self.createPropertyColor(vis.colorProperty())
                    if row == self.PIX_MODEL:
                        return vis.modelName()
                    if row == self.PIX_LABEL:
                        return vis.mNameExpression.expression()

                if role == Qt.ToolTipRole:
                    if row == self.PIX_FIELD:
                        return vis.field().name()
                    if row == self.PIX_MODEL:
                        return vis.modelName()
                    if row == self.PIX_LABEL:
                        return vis.mNameExpression.expression()
                    if row == self.PIX_COLOR:
                        return 'Line and Symbol color'

                    if row == self.PIX_STYLE:
                        return 'Line and Symbol style'

                if role == Qt.SizeHintRole:
                    if row == self.PIX_STYLE:
                        return QSize(75, 50)

        if role == Qt.DisplayRole:
            s = ""
        return None

    def setData(self, index: QModelIndex, value: typing.Any, role=Qt.EditRole):

        if not index.isValid():
            return

        handle = index.internalPointer()
        changed = False
        visibility_changed = False

        if isinstance(handle, SpectralProfilePlotVisualization):
            if index.column() == self.CIX_NAME and role == Qt.CheckStateRole:
                set_visible = value == Qt.Checked
                if set_visible != handle.isVisible():
                    handle.mVisible = set_visible
                    changed = True
                    visibility_changed = True

            elif index.column() == self.CIX_VALUE and role == Qt.EditRole:
                # value is string? -> use as name
                if isinstance(value, str) and value != handle.name():
                    handle.setName(str(value))
                    changed = True

                # value is QgsProcessingModelAlgorithm? -> use as model
                if isinstance(value, QgsProcessingModelAlgorithm) and value in self.modelList():
                    handle.setModelId(value)

        elif isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle):
            vis: SpectralProfilePlotVisualization = handle.parentVisualization()
            if index.column() == self.CIX_VALUE:
                if role == Qt.EditRole:
                    if index.row() == self.PIX_FIELD:
                        assert isinstance(value, QgsField)
                        vis.setField(value)
                        changed = True

                    if index.row() == self.PIX_LABEL:
                        assert isinstance(value, str)
                        if value != vis.labelExpression():
                            vis.setLabelExpression(value)
                            changed = True

                    if index.row() == self.PIX_COLOR:
                        assert isinstance(value, QgsProperty)
                        if value != vis.colorProperty():
                            vis.setColorProperty(value)

                            featureColor = self.createPropertyColor(value)

                            vis.plotStyle().setLineColor(featureColor)
                            vis.plotStyle().setMarkerLinecolor(featureColor)
                            vis.plotStyle().setMarkerColor(featureColor)

                            changed = True

                    if index.row() == self.PIX_MODEL:
                        if isinstance(value, QgsProcessingModelAlgorithm):
                            modelId = value.id()
                        else:
                            modelId = str(value)
                        assert modelId in self.modelList()
                        if vis.modelId() != modelId:
                            vis.setModelId(modelId)
                            changed = True

                    if index.row() == self.PIX_STYLE:
                        if value != vis.mPlotStyle:
                            vis.setPlotStyle(value)
                            changed = True

        if changed:
            if visibility_changed:
                self.dataChanged.emit(
                    self.index(index.row(), 0),
                    self.index(index.row(), self.columnCount() - 1),
                    [role, Qt.ForegroundRole]
                )
            else:
                self.dataChanged.emit(index, index, [role])
            self.updatePlot()
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

    # def removeModel(self, model: QgsProcessingModelAlgorithm):
    #    self.mModelList.removeModel(model)
    # todo: disconnect model from visualiszations

    # def addModel(self, model: QgsProcessingModelAlgorithm):
    #    assert is_spectral_processing_model(model)
    #    self.mModelList.addModel(model)

    def modelList(self) -> SpectralProcessingModelList:
        return self.mModelList


class PDIGenerator(object):
    """
    Returns existing
    """

    def __init__(self, existingPDIs: typing.List[SpectralProfilePlotDataItem] = [],
                 onProfileClicked: typing.Callable = None):
        self.pdiList: typing.List[SpectralProfilePlotDataItem] = existingPDIs
        self.onProfileClicked = onProfileClicked

    def __iter__(self):
        return self

    def __next__(self):
        if len(self.pdiList) > 0:
            return self.pdiList.pop(0)
        else:
            # create new
            pdi = SpectralProfilePlotDataItem()
            if self.onProfileClicked:
                pdi.setClickable(True)
                pdi.sigProfileClicked.connect(self.onProfileClicked)

            return pdi


class SpectralProfilePlotControlView(QTreeView):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotControlView, self).__init__(*args, **kwds)
        # self.horizontalHeader().setStretchLastSection(True)
        # self.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def controlTable(self) -> SpectralProfilePlotControlModel:
        return self.model()

    def selectVisualizations(self, visualizations):
        if isinstance(visualizations, SpectralProfilePlotVisualization):
            visualizations = [visualizations]

        model = self.model()
        rows = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            vis = model.data(idx, Qt.UserRole)
            if isinstance(vis, SpectralProfilePlotVisualization) and vis in visualizations:
                self.selectionModel().select(idx, QItemSelectionModel.Rows)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        idx = self.currentIndex()

        selected_vis = []
        for idx in self.selectedIndexes():
            v = self.idx2vis(idx)
            if isinstance(v, SpectralProfilePlotVisualization) and v not in selected_vis:
                selected_vis.append(v)
        if len(selected_vis) == 0:
            return

        a = menu.addAction('Remove visualization')
        a.setIcon(QIcon(r':/images/themes/default/mActionDeleteSelected.svg'))
        a.triggered.connect(lambda *args, v=selected_vis: self.removeVis(v))

        a = menu.addAction('Copy visualization')
        a.setIcon(QIcon(r':/images/themes/default/mActionEditCopy.svg'))
        a.triggered.connect(lambda *args, v=selected_vis: self.copyVis(v))

        a = menu.addAction('Paste visualization')
        a.setIcon(QIcon(r':/images/themes/default/mActionEditPaste.svg'))
        a.setEnabled(QApplication.clipboard().mimeData().hasFormat(SpectralProfilePlotVisualization.MIME_TYPE))
        a.triggered.connect(lambda *args: self.pasteVis())

        a = menu.addAction('Use vector symbol colors')
        a.setToolTip('Use map vector symbol colors as profile color.')
        a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
        a.triggered.connect(lambda *args, v=selected_vis: self.userColorsFromSymbolRenderer(v))

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def removeVis(self, vis: typing.List[SpectralProfilePlotVisualization]):

        model = self.model()

        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        if isinstance(model, SpectralProfilePlotControlModel):
            model.removeVisualizations(vis)

    def copyVis(self, visualizations: typing.List[SpectralProfilePlotVisualization]):

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

    def vis2index(self, vis: SpectralProfilePlotVisualization) -> QModelIndex:
        for r in range(self.model().rowCount()):
            idx = self.model().index(r, 0)
            if self.model().data(idx, Qt.UserRole) == vis:
                return idx
        return QModelIndex()

    def idx2vis(self, index: QModelIndex) -> SpectralProfilePlotVisualization:

        if index.isValid():
            obj = self.model().data(index, role=Qt.UserRole)
            if isinstance(obj, SpectralProfilePlotVisualization):
                return obj
            elif isinstance(obj, SpectralProfilePlotControlModel.PropertyHandle):
                return obj.parentVisualization()

        return None

    def userColorsFromSymbolRenderer(self, vis: typing.List[SpectralProfilePlotVisualization]):

        for v in vis:
            assert isinstance(v, SpectralProfilePlotVisualization)
            parentIdx = self.vis2index(v)
            if not parentIdx.isValid():
                return

            property = QgsProperty(v.colorProperty())
            property.setExpressionString('@symbol_color')

            model: QAbstractItemModel = self.model()
            idx = model.index(SpectralProfilePlotControlModel.PIX_COLOR, SpectralProfilePlotControlModel.CIX_VALUE, parentIdx)
            self.model().setData(idx, property, role=Qt.EditRole)
        pass


class SpectralProfilePlotControlViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, treeView: SpectralProfilePlotControlView, parent=None):
        assert isinstance(treeView, SpectralProfilePlotControlView)
        super(SpectralProfilePlotControlViewDelegate, self).__init__(parent=parent)
        self.mTreeView: SpectralProfilePlotControlView = treeView

    def model(self) -> SpectralProfilePlotControlModel:
        return self.mTreeView.model()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        handle = index.data(Qt.UserRole)
        # bc = self.model().mPlotWidgetStyle.backgroundColor
        if True and isinstance(handle, SpectralProfilePlotVisualization) and \
                index.column() == SpectralProfilePlotControlModel.CIX_NAME:
            super().paint(painter, option, index)
            r = option.rect
            style: PlotStyle = handle.plotStyle()
            s_x = 25
            h = self.mTreeView.rowHeight(index)
            w = self.mTreeView.columnWidth(index.column()) - 25
            # self.initStyleOption(option, index)
            if h > 0 and w > 0:
                if not handle.isComplete():
                    dy = r.height()
                    rect1 = QRect(r.x() + s_x, r.y(), dy, dy)
                    icon = QIcon(r':/images/themes/default/mIconWarning.svg')
                    icon.paint(painter, rect1)
                    s_x += dy

                pixmap = style.createPixmap(size=QSize(w - s_x, h), hline=True)
                rect2 = QRect(r.x() + s_x, r.y(), r.width() - s_x, r.height())
                painter.drawPixmap(rect2, pixmap)

        elif isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle) and \
                index.column() == SpectralProfilePlotControlModel.CIX_VALUE and \
                index.row() == SpectralProfilePlotControlModel.PIX_STYLE:
            # self.initStyleOption(option, index)
            style: PlotStyle = handle.parentVisualization().plotStyle()
            h = self.mTreeView.rowHeight(index)
            w = self.mTreeView.columnWidth(index.column())
            if h > 0 and w > 0:
                px = style.createPixmap(size=QSize(w, h))
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

    def plotControl(self) -> SpectralProfilePlotControlModel:
        return self.mTreeView.model().sourceModel()

    def createEditor(self, parent, option, index):
        # cname = self.bridgeColumnName(index)
        # bridge = self.bridge()
        # pmodel = self.sortFilterProxyModel()

        w = None
        if index.isValid() and index.column() == SpectralProfilePlotControlModel.CIX_VALUE:
            handle = index.data(Qt.UserRole)
            plotControl = self.plotControl()
            if isinstance(handle, SpectralProfilePlotVisualization):
                return super().createEditor(parent, option, index)

            elif isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle):
                row: int = index.row()
                vis: SpectralProfilePlotVisualization = handle.parentVisualization()
                speclib = vis.speclib()
                if row == SpectralProfilePlotControlModel.PIX_FIELD:
                    w = HTMLComboBox(parent=parent)
                    w.setModel(plotControl.profileFieldsModel())
                    w.setToolTip('Select a profile_field with profile data')

                if row == SpectralProfilePlotControlModel.PIX_MODEL:
                    w = HTMLComboBox(parent=parent)
                    w.setModel(plotControl.modelList())
                    w.setToolTip('Select a model or show raw profiles')

                if row == SpectralProfilePlotControlModel.PIX_LABEL:
                    w = QgsFieldExpressionWidget(parent=parent)
                    w.setExpressionDialogTitle('Profile Name')
                    w.setToolTip('Set an expression to specify the profile name')
                    w.setExpression(vis.labelExpression().expression())

                    w.setLayer(vis.speclib())
                    w.setFilters(QgsFieldProxyModel.String | QgsFieldProxyModel.Numeric)

                if row == SpectralProfilePlotControlModel.PIX_COLOR:
                    w = SpectralProfileColorPropertyWidget(parent=parent)
                    if isinstance(speclib, QgsVectorLayer):
                        w.setLayer(speclib)

                if row == SpectralProfilePlotControlModel.PIX_STYLE:
                    w = PlotStyleButton(parent=parent)
                    w.setMinimumSize(5, 5)
                    w.setPlotStyle(vis.plotStyle())
                    w.setColorWidgetVisibility(False)
                    w.setToolTip('Set curve style')

        return w

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        if not index.isValid():
            return

        handle = index.data(Qt.UserRole)

        if isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle) and \
                index.column() == SpectralProfilePlotControlModel.CIX_VALUE:
            vis: SpectralProfilePlotVisualization = handle.parentVisualization()
            speclib: QgsVectorLayer = vis.speclib()
            if index.row() == SpectralProfilePlotControlModel.PIX_FIELD:
                assert isinstance(editor, QComboBox)
                idx = editor.model().indexFromName(vis.field().name()).row()
                if idx == -1:
                    idx = 0
                editor.setCurrentIndex(idx)

            if index.row() == SpectralProfilePlotControlModel.PIX_MODEL:
                assert isinstance(editor, QComboBox)
                idx, _ = editor.model().findModelId(vis.modelId())
                if idx is None:
                    idx = 0
                editor.setCurrentIndex(idx)

            if index.row() == SpectralProfilePlotControlModel.PIX_LABEL:
                assert isinstance(editor, QgsFieldExpressionWidget)
                editor.setProperty('lastexpr', vis.labelExpression().expression())
                if isinstance(speclib, QgsVectorLayer):
                    editor.setLayer(speclib)
                    editor.setField(vis.labelExpression().expression())

            if index.row() == SpectralProfilePlotControlModel.PIX_COLOR:
                assert isinstance(editor, SpectralProfileColorPropertyWidget)
                if isinstance(speclib, QgsVectorLayer):
                    editor.setLayer(speclib)
                    editor.setToProperty(vis.colorProperty())

            if index.row() == SpectralProfilePlotControlModel.PIX_STYLE:
                assert isinstance(editor, PlotStyleButton)
                editor.setPlotStyle(vis.plotStyle())
        else:
            super().setEditorData(editor, index)

    def setModelData(self, w, bridge, index):
        model = self.mTreeView.model()
        if not index.isValid():
            return
        handle = index.data(Qt.UserRole)
        if isinstance(handle, SpectralProfilePlotControlModel.PropertyHandle):
            vis: SpectralProfilePlotVisualization = handle.parentVisualization()

            if index.row() == SpectralProfilePlotControlModel.PIX_FIELD:
                assert isinstance(w, QComboBox)
                i = w.currentIndex()
                if i >= 0:
                    field: QgsField = w.model().fields().at(i)
                    model.setData(index, field, Qt.EditRole)

            if index.row() == SpectralProfilePlotControlModel.PIX_MODEL:
                assert isinstance(w, QComboBox)
                pmodel = w.currentData(Qt.UserRole)
                model.setData(index, pmodel, Qt.EditRole)

            if index.row() == SpectralProfilePlotControlModel.PIX_LABEL:
                assert isinstance(w, QgsFieldExpressionWidget)
                if w.isValidExpression():
                    model.setData(index, w.asExpression(), Qt.EditRole)

            if index.row() == SpectralProfilePlotControlModel.PIX_COLOR:
                assert isinstance(w, SpectralProfileColorPropertyWidget)
                prop: QgsProperty = w.toProperty()
                model.setData(index, prop, Qt.EditRole)

            if index.row() == SpectralProfilePlotControlModel.PIX_STYLE:
                assert isinstance(w, PlotStyleButton)
                bridge.setData(index, w.plotStyle(), Qt.EditRole)
        else:
            super().setModelData(w, bridge, index)


class SpectralLibraryPlotWidget(QWidget):
    sigDragEnterEvent = pyqtSignal(QDragEnterEvent)
    sigDropEvent = pyqtSignal(QDropEvent)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryplotwidget.ui'), self)

        assert isinstance(self.gbVisualization, QgsCollapsibleGroupBox)

        assert isinstance(self.plotWidget, SpectralProfilePlotWidget)
        assert isinstance(self.treeView, SpectralProfilePlotControlView)
        self.plotWidget: SpectralProfilePlotWidget
        assert isinstance(self.plotWidget, SpectralProfilePlotWidget)
        # self.plotWidget.sigPopulateContextMenuItems.connect(self.onPopulatePlotContextMenu)
        self.mPlotControlModel = SpectralProfilePlotControlModel()
        self.mPlotControlModel.setPlotWidget(self.plotWidget)
        # self.mPlotControlModel.sigProgressChanged.connect(self.onProgressChanged)
        self.mCurrentModelId: str = None
        self.setCurrentModel('')
        self.setAcceptDrops(True)

        self.mProxyModel = QSortFilterProxyModel()
        self.mProxyModel.setSourceModel(self.mPlotControlModel)
        self.treeView.setModel(self.mProxyModel)
        self.treeView.selectionModel().selectionChanged.connect(self.onVisSelectionChanged)

        self.mViewDelegate = SpectralProfilePlotControlViewDelegate(self.treeView)
        self.mViewDelegate.setItemDelegates(self.treeView)

        self.mDualView: QgsDualView = None
        self.mSettingsModel = SettingsModel(QgsSettings('qps'), key_filter='qps/spectrallibrary')

        self.actionAddProfileVis: QAction
        self.actionAddProfileVis.triggered.connect(self.createProfileVis)
        self.actionAddProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionAdd.svg'))

        self.actionRemoveProfileVis: QAction
        self.actionRemoveProfileVis.triggered.connect(self.removeSelectedProfileVis)
        self.actionRemoveProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionRemove.svg'))

        self.optionSelectedFeaturesOnly: QAction
        self.optionSelectedFeaturesOnly.toggled.connect(self.mPlotControlModel.setShowSelectedFeaturesOnly)
        self.optionSelectedFeaturesOnly.setIcon(QgsApplication.getThemeIcon("/mActionShowSelectedLayers.svg"))
        self.mPlotControlModel.sigShowSelectedFeaturesOnlyChanged.connect(self.optionSelectedFeaturesOnly.setChecked)

        self.optionColorsFromFeatureRenderer: QAction
        self.optionColorsFromFeatureRenderer.toggled.connect(self.mPlotControlModel.setUseFeatureRenderer)
        self.optionColorsFromFeatureRenderer.setIcon(QIcon(':/qps/ui/icons/speclib_usevectorrenderer.svg'))
        self.mPlotControlModel.sigUseFeatureRendererChanged.connect(self.optionColorsFromFeatureRenderer.setChecked)

        self.optionMaxNumberOfProfiles: MaxNumberOfProfilesWidgetAction = MaxNumberOfProfilesWidgetAction(None)
        self.optionMaxNumberOfProfiles.sigMaxNumberOfProfilesChanged.connect(self.mPlotControlModel.setMaxProfiles)

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
        self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1, self.optionXUnit.createUnitComboBox())
        self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1,
                                          self.optionMaxNumberOfProfiles.createWidget(self))

        widgetXAxis: QWidget = self.plotWidget.viewBox().menu.widgetGroups[0]
        widgetYAxis: QWidget = self.plotWidget.viewBox().menu.widgetGroups[1]
        grid: QGridLayout = widgetXAxis.layout()
        grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        grid.addWidget(self.optionXUnit.createUnitComboBox(), 0, 2, 1, 2)

        self.plotWidget.plotItem.sigPopulateContextMenuItems.connect(self.populateProfilePlotContextMenu)

        # connect actions with buttons
        self.btnAddProfileVis.setDefaultAction(self.actionAddProfileVis)
        self.btnRemoveProfileVis.setDefaultAction(self.actionRemoveProfileVis)
        self.btnSelectedFeaturesOnly.setDefaultAction(self.optionSelectedFeaturesOnly)
        # self.btnColorsFromFeatureRenderer.setDefaultAction(self.optionColorsFromFeatureRenderer)

        # set the default style
        self.setPlotWidgetStyle(SpectralLibraryPlotWidgetStyle.dark())

    def visualizationSettingsBox(self) -> QgsCollapsibleGroupBox:
        return self.gbVisualization

    def setPlotWidgetStyle(self, style: SpectralLibraryPlotWidgetStyle):
        assert isinstance(style, SpectralLibraryPlotWidgetStyle)
        self.plotWidget.setWidgetStyle(style)
        self.mPlotControlModel.setPlotWidgetStyle(style)
        # self.mPlotControlModel.mSelectedDataColor = QColor(style.selectionColor)
        # self.mPlotControlModel.mTemporaryDataColor = QColor(style.temporaryColor)
        # self.mPlotControlModel.mBackgroundColor = QColor(style.backgroundColor)
        s = ""

    def populateProfilePlotContextMenu(self, listWrapper: SignalObjectWrapper):
        itemList: list = listWrapper.wrapped_object
        # update current renderer
        self.optionSpectralProfileWidgetStyle.setResetStyle(self.optionSpectralProfileWidgetStyle.profileWidgetStyle())
        m1 = QMenu('Colors')
        m1.addAction(self.optionSpectralProfileWidgetStyle)

        # m2 = QMenu('Others')

        itemList.extend([m1])

    def plotControlModel(self) -> SpectralProfilePlotControlModel:
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

    def createProfileVis(self, *args):
        item = SpectralProfilePlotVisualization()

        existing_names = [v.name() for v in self.mPlotControlModel]
        n = 1
        name = 'Profile Type 1'
        while name in existing_names:
            n += 1
            name = f'Profile Type {n}'
        item.setName(name)

        # set defaults
        # set speclib
        item.mSpeclib = self.speclib()

        # set profile source in speclib
        for field in profile_field_list(item.mSpeclib):
            item.mField = field
            break

        if isinstance(item.mSpeclib, QgsVectorLayer):
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
                item.setLabelExpression(f'"{name_field.name()}"')
            else:
                item.setLabelExpression('$id')

        item.mModelId = self.currentModel()

        item.mPlotStyle = self.defaultStyle()

        if len(self.mPlotControlModel) > 0:
            lastVis = self.mPlotControlModel[-1]
            color = lastVis.plotStyle().lineColor()
            item.plotStyle().setLineColor(nextColor(color, mode='cat'))
        self.mPlotControlModel.insertVisualizations(-1, item)

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

    def removeSelectedProfileVis(self, *args):
        rows = self.treeView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows]
        self.mPlotControlModel.removeVisualizations(to_remove)

    def setDualView(self, dualView):
        # self.plotWidget.setDualView(dualView)
        self.mDualView = dualView

        self.mPlotControlModel.setDualView(dualView)
        self.createProfileVis()

    def speclib(self) -> QgsVectorLayer:
        return self.mPlotControlModel.speclib()

    # def addSpectralModel(self, model):
    #    self.mPlotControlModel.addModel(model)

    def currentModel(self) -> str:
        return self.mCurrentModelId

    def setCurrentModel(self, modelId: str):
        if isinstance(modelId, QgsProcessingModelAlgorithm):
            modelId = modelId.id()
        assert isinstance(modelId, str)
        # if modelId not in self.mPlotControlModel.modelList():
        #    return
        assert modelId in self.mPlotControlModel.modelList(), f'Model "{modelId}" is unknown'
        self.mCurrentModelId = modelId

    # def removeModel(self, model):
    #    self.mPlotControlModel.removeModel(model)

    def setTemporaryProfiles(self, profiles: typing.Dict[SpectralProfile, QColor]):
        self.mPlotControlModel.setTemporaryProfile(profiles)
        pass
