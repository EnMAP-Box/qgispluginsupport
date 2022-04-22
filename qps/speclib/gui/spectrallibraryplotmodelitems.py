import sys
import typing

import numpy as np
from qgis.PyQt.QtCore import Qt, QModelIndex, pyqtSignal, QMimeData, QObject, QSize, QSignalBlocker
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel, QColor, QIcon, QPen, QPixmap
from qgis.PyQt.QtWidgets import QWidget, QComboBox, QSizePolicy, QHBoxLayout, QCheckBox, QDoubleSpinBox, \
    QSpinBox, QMenu
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsField, QgsPropertyDefinition, QgsProperty, QgsExpressionContext, QgsRasterLayer, \
    QgsRasterRenderer, QgsMultiBandColorRenderer, QgsHillshadeRenderer, QgsSingleBandPseudoColorRenderer, \
    QgsPalettedRasterRenderer, QgsRasterContourRenderer, QgsSingleBandColorDataRenderer, QgsSingleBandGrayRenderer, \
    QgsVectorLayer, QgsExpression, QgsExpressionContextScope, QgsRenderContext, QgsFeatureRenderer, QgsFeature, \
    QgsXmlUtils, QgsTextFormat
from qgis.gui import QgsFieldExpressionWidget, QgsColorButton, QgsPropertyOverrideButton, \
    QgsSpinBox, QgsDoubleSpinBox

from .spectrallibraryplotitems import SpectralProfilePlotLegend, SpectralProfilePlotItem
from ..core import is_profile_field
from ...externals.htmlwidgets import HTMLComboBox
from ...plotstyling.plotstyling import PlotStyle, PlotStyleButton, PlotWidgetStyle
from ...pyqtgraph.pyqtgraph import InfiniteLine, PlotDataItem
from ...speclib.core import create_profile_field
from ...unitmodel import UnitConverterFunctionModel, BAND_NUMBER, BAND_INDEX
from ...utils import parseWavelength, SignalBlocker

WARNING_ICON = QIcon(r':/images/themes/default/mIconWarning.svg')


class SpectralProfileColorPropertyWidget(QWidget):
    """
    Widget to specify the SpectralProfile colors.

    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setWindowIcon(QIcon(':/images/themes/default/mIconColorBox.svg'))
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
        hl = QHBoxLayout()
        hl.addWidget(self.mColorButton)
        hl.addWidget(self.mPropertyOverrideButton)
        hl.setSpacing(2)
        hl.setContentsMargins(0, 0, 0, 0)
        self.sizePolicy().setHorizontalPolicy(QSizePolicy.Preferred)
        self.setLayout(hl)

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


class PropertyItemBase(QStandardItem):
    """
    Base class to be used by others
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        # QObject.__init__(self)
        # QStandardItem.__init__(self, *args, **kwds)

        s = ""

    def firstColumnSpanned(self) -> bool:
        return len(self.propertyRow()) == 1

    def propertyRow(self) -> typing.List[QStandardItem]:
        return [self]

    def readXml(self, parentNode: QDomElement):
        pass

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument):
        pass

    def model(self) -> QStandardItemModel:
        return super().model()

    def populateContextMenu(self, menu: QMenu):
        pass

    def previewPixmap(self, size: QSize) -> QPixmap:
        return None

    def hasPixmap(self) -> bool:
        return False

    def data(self, role: int = ...) -> typing.Any:

        if role == Qt.UserRole:
            return self
        else:
            return super().data(role)


class PropertyLabel(QStandardItem):
    """
    The label lined to a PropertyItem
    """

    class Signals(QObject):
        sigCheckedChanged = pyqtSignal(bool)

        def __init__(self):
            super().__init__()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setCheckable(False)
        self.setEditable(False)
        self.setDropEnabled(False)
        self.setDragEnabled(False)
        self.mSignals = PropertyLabel.Signals()

    def setData(self, value, role=None, *args, **kwargs):
        value = super().setData(value, role)
        if role == Qt.CheckStateRole and self.isCheckable():
            self.mSignals.sigCheckedChanged.emit(self.checkState() == Qt.Checked)
        return value

    def propertyItem(self) -> 'PropertyItem':
        """
        Returns the PropertyItem paired with this PropertyLabel.
        Should be in the column left to it
        """
        item = self.model().index(self.row(), self.column() + 1,
                                  parent=self.parent().index()).data(Qt.UserRole)

        if isinstance(item, PropertyItem) and item.label() == self:
            return item

    def data(self, role: int = ...) -> typing.Any:
        if role == Qt.UserRole:
            return self
        return super().data(role)


class PropertyItem(PropertyItemBase):
    """
    Controls a single property parameter.
    Is paired with a PropertyLabel.
    .propertRow() -> [PropertyLabel, PropertyItem]
    """

    class Signals(QObject):
        """
        Signales for the PropertyItem
        """
        dataChanged = pyqtSignal()
        checkedChanged = pyqtSignal(bool)

        def __init__(self, *args, **kwds):
            super().__init__(*args, **kwds)

    def __init__(self, key: str, *args, labelName: str = None, **kwds):
        super().__init__(*args, **kwds)
        assert isinstance(key, str) and ' ' not in key
        self.mKey = key
        self.setEditable(False)
        self.setDragEnabled(False)
        self.setDropEnabled(False)
        if labelName is None:
            labelName = key
        self.mLabel = PropertyLabel(labelName)
        self.mSignals = PropertyItem.Signals()
        self.mLabel.mSignals.sigCheckedChanged.connect(self.mSignals.checkedChanged)

    def itemIsChecked(self) -> bool:

        if self.label().isCheckable():
            return self.label().checkState() == Qt.Checked
        return None

    def setItemCheckable(self, b: bool):
        self.label().setCheckable(b)
        self.label().setEditable(b)

    def setItemChecked(self, b: bool):
        self.label().setCheckState(Qt.Checked if b is True else Qt.Unchecked)

    def signals(self):
        return self.mSignals

    def speclib(self) -> QgsVectorLayer:
        model = self.model()
        from ...speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
        if isinstance(model, SpectralProfilePlotModel):
            return model.speclib()
        else:
            return model

    def createEditor(self, parent):

        return None

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        pass

    def setModelData(self, w, bridge, index):
        pass

    def key(self) -> str:
        return self.mKey

    def label(self) -> PropertyLabel:
        return self.mLabel

    def propertyRow(self) -> typing.List[QStandardItem]:
        return [self.label(), self]

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument, attribute: bool = False):
        xml_tag = self.key()
        if attribute:
            parentNode.setAttribute(xml_tag, self.text())
        else:
            node = doc.createElement(xml_tag)
            node.setNodeValue(self.text())
            parentNode.appendChild(node)

    def readXml(self, parentNode: QDomElement, attribute: bool = False):
        xml_tag = self.key()
        if attribute:
            if parentNode.hasAttribute(xml_tag):
                self.setText(parentNode.attribute(xml_tag))
        else:
            node = parentNode.firstChildElement(xml_tag)
            if not node.isNull():
                self.setText(node.nodeValue())

    def emitDataChanged(self) -> None:
        super().emitDataChanged()
        self.signals().dataChanged.emit()


class PropertyItemGroup(PropertyItemBase):
    """
    Represents a group of properties.

    """
    XML_FACTORIES: typing.Dict[str, 'PropertyItemGroup'] = dict()

    class Signals(PropertyItem.Signals):
        """
        Signals for PropertyItemGroup
        """

        def __init__(self, *args, **kwds):
            super().__init__(*args, **kwds)

        requestRemoval = pyqtSignal()
        requestPlotUpdate = pyqtSignal()

    @staticmethod
    def registerXmlFactory(grp: 'PropertyItemGroup', xml_tag: str = None):
        assert isinstance(grp, PropertyItemGroup)
        if xml_tag is None:
            xml_tag = grp.__class__.__name__
        assert xml_tag not in PropertyItemGroup.XML_FACTORIES.keys()
        PropertyItemGroup.XML_FACTORIES[xml_tag] = grp.__class__

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mMissingValues: bool = False
        self.mZValue = 0
        self.mSignals = PropertyItemGroup.Signals()
        self.mFirstColumnSpanned = True

    def disconnectGroup(self):
        """
        Should implement all actions required to remove this property item from the plot
        """
        pass

    def isRemovable(self) -> bool:
        return True

    def zValue(self) -> int:
        return self.mZValue

    def createPlotStyle(self, feature: QgsFeature, fieldIndex: int) -> PlotStyle:

        return None

    def plotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns a list with all pyqtgraph plot data items
        """
        return []

    def initWithPlotModel(self, model):
        """
        This method should implement a basic initialization based on the plot model state
        """
        pass

    def propertyItems(self) -> typing.List['PropertyItem']:
        items = []
        for r in range(self.rowCount()):
            child = self.child(r, 1)
            if isinstance(child, PropertyItem):
                items.append(child)
        return items

    def initBasicSettings(self):
        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        # connect requestPlotUpdate signal
        for propertyItem in self.propertyItems():
            propertyItem: PropertyItem
            propertyItem.signals().dataChanged.connect(self.signals().requestPlotUpdate.emit)

    def signals(self) -> 'PropertyItemGroup.Signals':
        return self.mSignals

    def __hash__(self):
        return hash(id(self))

    def setValuesMissing(self, missing: bool):
        self.mMissingValues = missing

    def setCheckState(self, checkState: Qt.CheckState) -> None:
        super().setCheckState(checkState)

        c = QColor() if self.isVisible() else QColor('grey')

        for r in range(self.rowCount()):
            self.child(r, 0).setForeground(c)

    def setVisible(self, visible: bool):
        if visible in [Qt.Checked, visible is True]:
            self.setCheckState(Qt.Checked)
        else:
            self.setCheckState(Qt.Unchecked)

    def isVisible(self) -> bool:
        """
        Returns True if plot items related to this control item should be visible in the plot
        """
        return self.checkState() == Qt.Checked

    def data(self, role: int = ...) -> typing.Any:

        if role == Qt.ForegroundRole:
            if not self.isVisible():
                return QColor('grey')
        if role == Qt.DecorationRole and self.mMissingValues:
            return QIcon(WARNING_ICON)

        return super().data(role)

    def setData(self, value: typing.Any, role: int = ...) -> None:
        value = super().setData(value, role)

        if role == Qt.CheckStateRole:
            # self.mSignals.requestPlotUpdate.emit()
            is_visible = self.isVisible()
            for item in self.plotDataItems():
                item.setVisible(is_visible)
            self.emitDataChanged()
            if is_visible:
                self.mSignals.requestPlotUpdate.emit()
        return value

    def update(self):
        pass

    MIME_TYPE = 'application/SpectralProfilePlot/PropertyItems'

    @staticmethod
    def toMimeData(propertyGroups: typing.List['PropertyItemGroup']):

        for g in propertyGroups:
            assert isinstance(g, PropertyItemGroup)

        md = QMimeData()

        doc = QDomDocument()
        root = doc.createElement('PropertyItemGroups')
        for grp in propertyGroups:
            for xml_tag, cl in PropertyItemGroup.XML_FACTORIES.items():
                if cl == grp.__class__:
                    grpNode = doc.createElement(xml_tag)
                    grp.writeXml(grpNode, doc)
                    root.appendChild(grpNode)
                    break

        doc.appendChild(root)
        md.setData(PropertyItemGroup.MIME_TYPE, doc.toByteArray())
        return md

    @staticmethod
    def fromMimeData(mimeData: QMimeData) -> typing.List['ProfileVisualizationGroup']:
        groups = []
        if mimeData.hasFormat(PropertyItemGroup.MIME_TYPE):
            ba = mimeData.data(PropertyItemGroup.MIME_TYPE)
            doc = QDomDocument()
            doc.setContent(ba)
            root = doc.firstChildElement('PropertyItemGroups')
            if not root.isNull():
                grpNode = root.firstChild().toElement()
                while not grpNode.isNull():
                    classname = grpNode.nodeName()
                    class_ = PropertyItemGroup.XML_FACTORIES.get(classname)
                    if class_:
                        grp = class_()
                        if isinstance(grp, PropertyItemGroup):
                            grp.readXml(grpNode)
                        groups.append(grp)
                    grpNode = grpNode.nextSibling()
        return groups


class GeneralSettingsGroup(PropertyItemGroup):
    """
    General Plot Settings
    """
    DEFAULT_STYLES: typing.Dict[str, object] = dict()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = -1
        self.setText('General Settings')
        self.setCheckable(False)
        self.setEnabled(True)
        self.setEditable(False)
        self.setIcon(QIcon(':/images/themes/default/console/iconSettingsConsole.svg'))

        self.mP_SortBands = QgsPropertyItem('SortBands')
        self.mP_SortBands.setDefinition(
            QgsPropertyDefinition(
                'Sort Bands', 'Sort bands by increasing X values',
                QgsPropertyDefinition.StandardPropertyTemplate.Boolean)
        )
        self.mP_SortBands.setValue(QgsProperty.fromValue(True))

        self.mP_BadBands = QgsPropertyItem('BadBands')
        self.mP_BadBands.setDefinition(
            QgsPropertyDefinition(
                'Bad Bands', 'Show bad band values', QgsPropertyDefinition.StandardPropertyTemplate.Boolean)

        )
        self.mP_BadBands.setProperty(QgsProperty.fromValue(True))

        self.mP_MaxProfiles = QgsPropertyItem('MaxProfiles')
        self.mP_MaxProfiles.setDefinition(QgsPropertyDefinition(
            'Max. Profiles', 'Maximum Number of Profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositive))
        self.mP_MaxProfiles.setProperty(QgsProperty.fromValue(516))

        self.mPLegend = LegendGroup()
        self.mPLegend.setVisible(False)

        self.mP_BG = QgsPropertyItem('BG')
        self.mP_BG.setDefinition(QgsPropertyDefinition(
            'Background', 'Plot Background Color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_BG.setProperty(QgsProperty.fromValue(QColor('black')))

        self.mP_FG = QgsPropertyItem('FG')
        self.mP_FG.setDefinition(QgsPropertyDefinition(
            'Foreground', 'Plot Foreground Color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_FG.setProperty(QgsProperty.fromValue(QColor('white')))

        self.mP_SC = QgsPropertyItem('SC')
        self.mP_SC.setDefinition(QgsPropertyDefinition(
            'Selection', 'Selection Color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_SC.setProperty(QgsProperty.fromValue(QColor('yellow')))

        self.mP_CH = QgsPropertyItem('CH')
        self.mP_CH.setDefinition(QgsPropertyDefinition(
            'Crosshair', 'Crosshair Color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_CH.setProperty(QgsProperty.fromValue(QColor('yellow')))
        self.mP_CH.setItemCheckable(True)
        self.mP_CH.setItemChecked(True)

        for pItem in [# self.mPLegend,
                      self.mP_MaxProfiles,
                      self.mP_SortBands, self.mP_BadBands,
                      self.mP_BG, self.mP_FG, self.mP_SC, self.mP_CH]:
            self.appendRow(pItem.propertyRow())

        self.mP_MaxProfiles.signals().dataChanged.connect(self.signals().requestPlotUpdate)
        self.mP_SortBands.signals().dataChanged.connect(self.signals().requestPlotUpdate)
        self.mP_BadBands.signals().dataChanged.connect(self.signals().requestPlotUpdate)

        for pItem in [# self.mPLegend,
                      self.mP_BG, self.mP_FG, self.mP_SC, self.mP_CH]:
            pItem.signals().dataChanged.connect(self.applyGeneralSettings)

        self.mP_CH.signals().checkedChanged.connect(self.applyGeneralSettings)

        self.mContext: QgsExpressionContext = QgsExpressionContext()

        self.mMissingValues = False

    def populateContextMenu(self, menu: QMenu):

        m = menu.addMenu('Color Theme')

        for style in PlotWidgetStyle.plotWidgetStyles():
            a = m.addAction(style.name)
            a.setIcon(QIcon(style.icon))
            a.triggered.connect(lambda *args, s=style: self.setPlotWidgetStyle(s))

    def initWithPlotModel(self, model):

        from .spectrallibraryplotwidget import SpectralProfilePlotModel, SpectralProfilePlotWidget
        if isinstance(model, SpectralProfilePlotModel) and isinstance(model.plotWidget(), SpectralProfilePlotWidget):
            plotWidget: SpectralProfilePlotWidget = model.plotWidget()
            bg = plotWidget.backgroundBrush().color()
            fg = plotWidget.xAxis().pen().color()
            self.mP_BG.setProperty(QgsProperty.fromValue(bg))
            self.mP_FG.setProperty(QgsProperty.fromValue(fg))

            plotWidget.xAxis()

    def applyGeneralSettings(self, *args):

        from .spectrallibraryplotwidget import SpectralProfilePlotModel
        from .spectrallibraryplotitems import SpectralProfilePlotWidget
        model: SpectralProfilePlotModel = self.model()

        if not isinstance(model, SpectralProfilePlotModel):
            return
        w: SpectralProfilePlotWidget = model.mPlotWidget

        w.setSelectionColor(self.selectionColor())
        w.setCrosshairColor(self.crosshairColor())
        w.setShowCrosshair(self.mP_CH.itemIsChecked())
        w.setForegroundColor(self.foregroundColor())
        w.setBackground(self.backgroundColor())
        legend = w.getPlotItem().legend
        if isinstance(legend, SpectralProfilePlotLegend):
            pen = legend.pen()
            pen.setColor(self.foregroundColor())
            legend.setPen(pen)
            legend.setLabelTextColor(self.foregroundColor())
            legend.update()

        model.sigPlotWidgetStyleChanged.emit()

    def maximumProfiles(self) -> int:
        return self.mP_MaxProfiles.value()

    def setMaximumProfiles(self, n: int):
        assert n >= 0
        self.mP_MaxProfiles.setProperty(QgsProperty.fromValue(n))

    def expressionContext(self) -> QgsExpressionContext:
        return self.mContext

    def plotWidgetStyle(self) -> PlotWidgetStyle:

        style = PlotWidgetStyle(bg=self.backgroundColor(),
                                fg=self.foregroundColor(),
                                tc=self.foregroundColor(),
                                cc=self.crosshairColor(),
                                sc=self.selectionColor())

        return style

    def setPlotWidgetStyle(self, style: PlotWidgetStyle):

        self.mP_BG.setProperty(QgsProperty.fromValue(style.backgroundColor))
        self.mP_FG.setProperty(QgsProperty.fromValue(style.foregroundColor))
        self.mP_CH.setProperty(QgsProperty.fromValue(style.crosshairColor))
        self.mP_SC.setProperty(QgsProperty.fromValue(style.selectionColor))

        from .spectrallibraryplotwidget import SpectralProfilePlotModel
        model: SpectralProfilePlotModel = self.model()
        if isinstance(model, SpectralProfilePlotModel):
            model.mDefaultSymbolRenderer.symbol().setColor(style.foregroundColor)

            b = False
            for vis in model.visualizations():
                if vis.color() == style.backgroundColor:
                    vis.setColor(style.foregroundColor)
                    vis.update()

    def defaultProfileStyle(self) -> PlotStyle:
        """
        Returns the default PlotStyle for spectral profiles
        """
        style = PlotStyle()
        style.linePen.setStyle(Qt.SolidLine)
        fg = self.foregroundColor()
        style.setLineColor(fg)
        style.setMarkerColor(fg)
        style.setMarkerSymbol(None)
        style.setBackgroundColor(self.backgroundColor())
        # style.markerSymbol = MarkerSymbol.No_Symbol.value
        # style.markerPen.setColor(style.linePen.color())
        return style

    def backgroundColor(self) -> QColor:
        return self.mP_BG.property().valueAsColor(self.expressionContext())[0]

    def foregroundColor(self) -> QColor:
        return self.mP_FG.property().valueAsColor(self.expressionContext())[0]

    def selectionColor(self) -> QColor:
        return self.mP_SC.value(self.expressionContext())

    def crosshairColor(self) -> QColor:
        return self.mP_CH.value(self.expressionContext())

    def showBadBands(self) -> bool:
        return self.mP_BadBands.value(self.expressionContext(), False)

    def sortBands(self) -> bool:
        return self.mP_SortBands.value(self.expressionContext(), True)

    def isRemovable(self) -> bool:
        return False

    def isVisible(self) -> bool:
        return True


class SpectralProfilePlotDataItemGroup(PropertyItemGroup):
    """
    A PropertyItemGroup that controls SpectralProfilePlotDataItems
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def generateLabel(self, context: QgsExpressionContext) -> str:
        raise NotImplementedError()

    def generatePlotStyle(self, context: QgsExpressionContext) -> PlotStyle:
        raise NotImplementedError()

    def generateTooltip(self, context: QgsExpressionContext) -> str:
        raise NotImplementedError()


class LegendGroup(PropertyItemGroup):
    """
    Settings for the plot legend
    """

    def __init__(self, *args, **kwds):
        super(LegendGroup, self).__init__(*args, **kwds)
        self.setText('Legend')
        self.setCheckable(True)
        self.setCheckState(Qt.Unchecked)

        self.mLegendOffset = (-1, 10)

        if False:
            self.mOffsetX = QgsPropertyItem('OffsetX')
            self.mOffsetX.setDefinition(
                QgsPropertyDefinition('Offset X', 'Legend offset X',
                                      QgsPropertyDefinition.StandardPropertyTemplate.Integer))
            self.mOffsetX.setProperty(QgsProperty.fromValue(0))

            self.mOffsetY = QgsPropertyItem('OffsetY')
            self.mOffsetY.setDefinition(
                QgsPropertyDefinition('Offset Y', 'Legend offset Y',
                                      QgsPropertyDefinition.StandardPropertyTemplate.Integer))
            self.mOffsetY.setProperty(QgsProperty.fromValue(0))

        self.mHSpacing = QgsPropertyItem('HSpacing')
        self.mHSpacing.setDefinition(
            QgsPropertyDefinition('H. Spacing',
                                  'Specifies the spacing between the line symbol and the label',
                                  QgsPropertyDefinition.StandardPropertyTemplate.Integer)
        )
        self.mHSpacing.setProperty(QgsProperty.fromValue(25))

        self.mVSpacing = QgsPropertyItem('VSpacing')
        self.mVSpacing.setDefinition(
            QgsPropertyDefinition('V. Spacing',
                                  'Specifies the spacing between individual entries of the legend vertically. '
                                  + '(Can also be negative to have them really close)',
                                  QgsPropertyDefinition.StandardPropertyTemplate.Integer)
        )
        self.mVSpacing.setProperty(QgsProperty.fromValue(0))

        self.mColCount = QgsPropertyItem('Columns')
        self.mColCount.setDefinition(
            QgsPropertyDefinition('Columns',
                                  'Number of legend columns',
                                  QgsPropertyDefinition.StandardPropertyTemplate.Integer)
        )
        self.mColCount.setProperty(QgsProperty.fromValue(1))

        for pItem in [self.mHSpacing,
                      self.mVSpacing,
                      self.mColCount]:
            self.appendRow(pItem.propertyRow())
            pItem.signals().dataChanged.connect(self.signals().dataChanged)

        self.signals().dataChanged.connect(self.applySettings)

    def setData(self, value: typing.Any, role: int = ...) -> None:
        super().setData(value, role)

    def emitDataChanged(self):
        super().emitDataChanged()
        self.applySettings()

    def initWithPlotModel(self, model):
        self.applySettings()

    def applySettings(self, *args):
        return

        from .spectrallibraryplotwidget import SpectralProfilePlotModel
        from .spectrallibraryplotitems import SpectralProfilePlotWidget
        from .spectrallibraryplotitems import SpectralProfilePlotItem
        model: SpectralProfilePlotModel = self.model()

        if not isinstance(model, SpectralProfilePlotModel):
            return

        w: SpectralProfilePlotWidget = model.mPlotWidget

        plotItem: SpectralProfilePlotItem = w.getPlotItem()
        showLegend = self.isVisible()

        group = self.parent()
        fg = QColor('white')
        if isinstance(group, GeneralSettingsGroup):
            fg = group.foregroundColor()

        if True:
            legend: SpectralProfilePlotLegend = plotItem.addLegend(
                labelTextColor=fg,
                max_items=256,
                offset=self.mLegendOffset)
            assert isinstance(legend, SpectralProfilePlotLegend)
            legend.setVisible(self.isVisible())
            legend.layout.setHorizontalSpacing(self.mHSpacing.value(defaultValue=25))
            legend.layout.setVerticalSpacing(self.mVSpacing.value(defaultValue=0))
            legend.setColumnCount(self.mColCount.value(defaultValue=1))
            legend.setLabelTextColor(fg)

        else:
            if showLegend:
                group = self.parent()
                fg = QColor('white')
                if isinstance(group, GeneralSettingsGroup):
                    fg = group.foregroundColor()

                legend: SpectralProfilePlotLegend = plotItem.addLegend(labelTextColor=fg, offset=self.mLegendOffset)
                legend.setVisible(self.isVisible())
                # legend.setOffset((self.mOffsetX.value(defaultValue=0),
                #                   self.mOffsetY.value(defaultValue=0)))
                legend.layout.setHorizontalSpacing(self.mHSpacing.value(defaultValue=25))
                legend.layout.setVerticalSpacing(self.mVSpacing.value(defaultValue=0))
                legend.setColumnCount(self.mColCount.value(defaultValue=1))
                legend.setLabelTextColor(fg)

                legend.update()
                # legend.anchorChanged.connect(self.updateLegendAnchor)
            else:
                legend = plotItem.legend
                if isinstance(legend, SpectralProfilePlotLegend):
                    R = legend.__dict__
                    off1 = legend.opts['offset']
                    off2 = legend.__dict__['_GraphicsWidgetAnchor__offset']

                    self.mLegendOffset = legend.opts['offset']
                plotItem.removeLegend()

    def plotItem(self) -> SpectralProfilePlotItem:
        return self.model().mPlotWidget.getPlotItem()

    def legend(self) -> SpectralProfilePlotLegend:
        return self.plotItem().legend

    def updateLegendAnchor(self, x: int, y: int):

        offset = (self.mOffsetX.value(), self.mOffsetY.value())
        if offset != (x, y):
            with QSignalBlocker(self.signals()) as blocker:
                self.mOffsetX.setValue(x)
                self.mOffsetY.setValue(y)


class PlotStyleItem(PropertyItem):
    """
    A property item to control a PlotStyle
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mPlotStyle = PlotStyle()
        self.setEditable(True)

        self.mEditColors: bool = False

    def setEditColors(self, b):
        self.mEditColors = b is True

    def setPlotStyle(self, plotStyle):
        self.mPlotStyle = plotStyle
        self.emitDataChanged()

    def plotStyle(self) -> PlotStyle:
        return self.mPlotStyle

    def createEditor(self, parent):
        w = PlotStyleButton(parent=parent)
        w.setMinimumSize(5, 5)
        w.setPlotStyle(self.plotStyle())
        w.setColorWidgetVisibility(self.mEditColors)
        w.setVisibilityCheckboxVisible(False)
        w.setToolTip('Set curve style')
        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        if isinstance(editor, PlotStyleButton):
            editor.setPlotStyle(self.plotStyle())

    def setModelData(self, w, bridge, index):
        if isinstance(w, PlotStyleButton):
            self.setPlotStyle(w.plotStyle())

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument, attribute: bool = False):
        xml_tag = self.key()
        node = doc.createElement(xml_tag)
        self.mPlotStyle.writeXml(node, doc)
        parentNode.appendChild(node)

    def readXml(self, parentNode: QDomElement, attribute: bool = False):
        node = parentNode.firstChildElement(self.key()).toElement()
        if not node.isNull():
            style = PlotStyle.readXml(node)
            if isinstance(style, PlotStyle):
                self.setPlotStyle(style)


class QgsTextFormatItem(PropertyItem):

    def __init__(self, *args, **kwds):
        super(self).__init__(*args, **kwds)
        self.mTextFormat = QgsTextFormat()
        self.setEditable(True)


class QgsPropertyItem(PropertyItem):

    def __init__(self, *args, **kwds):
        self.mProperty = None
        super().__init__(*args, **kwds)
        self.mProperty: QgsProperty = None
        self.mDefinition: QgsPropertyDefinition = None
        self.setEditable(True)

        self.mIsSpectralProfileField: bool = False

    def __eq__(self, other):
        return isinstance(other, QgsPropertyItem) \
               and self.mDefinition == other.definition() \
               and self.mProperty == other.property()

    def update(self):
        self.setText(self.mProperty.valueAsString(QgsExpressionContext()))

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument, attribute: bool = False):
        xml_tag = self.key()
        node = QgsXmlUtils.writeVariant(self.property(), doc)
        node.setTagName(xml_tag)
        parentNode.appendChild(node)

    def readXml(self, parentNode: QDomElement, attribute: bool = False) -> bool:

        xml_tag = self.key()
        child = parentNode.firstChildElement(xml_tag).toElement()
        if not child.isNull():
            property = QgsXmlUtils.readVariant(child)
            if isinstance(property, QgsProperty):
                # workaround https://github.com/qgis/QGIS/issues/47127
                property.setActive(True)
                self.setProperty(property)
                return True
        return False

    def value(self, context=QgsExpressionContext(), defaultValue=None):
        return self.mProperty.value(context, defaultValue)[0]

    def setValue(self, value):
        p = self.property()
        if isinstance(value, QgsProperty):
            self.setProperty(value)
        elif p.propertyType() == QgsProperty.StaticProperty:
            self.setProperty(QgsProperty.fromValue(value))
        elif p.propertyType() == QgsProperty.FieldBasedProperty:
            self.setProperty(QgsProperty.fromField(value))
        elif p.propertyType() == QgsProperty.ExpressionBasedProperty:
            self.setProperty(QgsProperty.fromExpression(str(value)))

    def property(self) -> QgsProperty:
        return self.mProperty

    def setProperty(self, property: QgsProperty):
        assert isinstance(property, QgsProperty)
        assert isinstance(self.mDefinition, QgsPropertyDefinition), 'Call setDefinition(propertyDefinition) first'
        b = self.mProperty != property
        self.mProperty = property
        if b:
            # print(self.key())
            self.emitDataChanged()

    def setDefinition(self, propertyDefinition: QgsPropertyDefinition):
        assert isinstance(propertyDefinition, QgsPropertyDefinition)
        assert self.mDefinition is None, 'property definition is immutable and already set'
        self.mDefinition = propertyDefinition
        self.label().setText(propertyDefinition.name())
        self.label().setToolTip(propertyDefinition.description())

    def definition(self) -> QgsPropertyDefinition:
        return self.mDefinition

    def data(self, role: int = ...) -> typing.Any:

        if self.mProperty is None:
            return None
        p = self.property()

        if role == Qt.DisplayRole:
            if p.propertyType() == QgsProperty.ExpressionBasedProperty:
                return p.expressionString()
            elif p.propertyType() == QgsProperty.FieldBasedProperty:
                return p.field()
            else:
                v, success = p.value(QgsExpressionContext())
                if success:
                    if isinstance(v, QColor):
                        return v.name()
                    else:
                        return v
        if role == Qt.DecorationRole:
            if self.isColorProperty():
                v, success = p.value(QgsExpressionContext())
                if success and isinstance(v, QColor):
                    return v

        if role == Qt.ToolTipRole:
            return self.definition().description()

        return super().data(role)

    def setIsProfileFieldProperty(self, b: bool):
        self.mIsSpectralProfileField = b is True

    def isProfileFieldProperty(self) -> bool:
        return self.mIsSpectralProfileField

    def isColorProperty(self) -> bool:
        return self.definition().standardTemplate() in [QgsPropertyDefinition.ColorWithAlpha,
                                                        QgsPropertyDefinition.ColorNoAlpha]

    def createEditor(self, parent):
        speclib: QgsVectorLayer = self.speclib()
        template = self.definition().standardTemplate()

        if self.isColorProperty():
            w = SpectralProfileColorPropertyWidget(parent=parent)

        elif self.isProfileFieldProperty():
            w = HTMLComboBox(parent=parent)
            model = self.model()
            from ...speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
            if isinstance(model, SpectralProfilePlotModel):
                w.setModel(model.profileFieldsModel())
            w.setToolTip(self.definition().description())

        elif template == QgsPropertyDefinition.StandardPropertyTemplate.Boolean:
            w = QComboBox(parent=parent)
            w.addItem('True', True)
            w.addItem('False', False)

        elif template in [QgsPropertyDefinition.StandardPropertyTemplate.Integer,
                          QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositive,
                          QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositiveGreaterZero]:

            w = QgsSpinBox(parent=parent)

        elif template in [QgsPropertyDefinition.StandardPropertyTemplate.Double,
                          QgsPropertyDefinition.StandardPropertyTemplate.DoublePositive,
                          QgsPropertyDefinition.StandardPropertyTemplate.Double0To1]:
            w = QgsDoubleSpinBox(parent=parent)
        else:

            w = QgsFieldExpressionWidget(parent=parent)
            w.setAllowEmptyFieldName(True)
            w.setExpressionDialogTitle(self.definition().name())
            w.setToolTip(self.definition().description())
            w.setExpression(self.property().expressionString())

            if isinstance(speclib, QgsVectorLayer):
                w.setLayer(speclib)

        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):

        speclib: QgsVectorLayer = self.speclib()

        if isinstance(editor, QgsFieldExpressionWidget):
            editor.setProperty('lastexpr', self.property().expressionString())
            if isinstance(speclib, QgsVectorLayer):
                editor.setLayer(speclib)

        elif isinstance(editor, SpectralProfileColorPropertyWidget):
            editor.setToProperty(self.property())
            if isinstance(speclib, QgsVectorLayer):
                editor.setLayer(speclib)

        elif isinstance(editor, (QSpinBox, QgsSpinBox)):
            template = self.definition().standardTemplate()

            if template == QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositive:
                v_min = 0
            elif template == QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositiveGreaterZero:
                v_min = 1
            else:
                v_min = -2147483648

            v_max = 2147483647
            editor.setMinimum(v_min)
            editor.setMaximum(v_max)
            value = self.value(defaultValue=v_min)
            if isinstance(editor, QgsSpinBox):
                editor.setClearValue(0)
                editor.setShowClearButton(True)
            editor.setValue(value)

        elif isinstance(editor, (QDoubleSpinBox, QgsDoubleSpinBox)):
            template = self.definition().standardTemplate()

            if template in [QgsPropertyDefinition.StandardPropertyTemplate.DoublePositive,
                            QgsPropertyDefinition.StandardPropertyTemplate.Double0To1]:
                v_min = 0.0
            else:
                v_min = sys.float_info.min

            if template in [QgsPropertyDefinition.StandardPropertyTemplate.Double0To1]:
                v_max = 1.0
            else:
                v_max = sys.float_info.max

            editor.setMinimum(v_min)
            editor.setMaximum(v_max)
            value = self.value(defaultValue=0.0)
            if isinstance(editor, QgsDoubleSpinBox):
                editor.setShowClearButton(True)
                editor.setClearValue(value)
            editor.setValue(value)

        elif isinstance(editor, QCheckBox):
            b = self.property().valueAsBool(QgsExpressionContext())
            editor.setCheckState(Qt.Checked if b else Qt.Unchecked)

        elif self.isProfileFieldProperty() and isinstance(editor, QComboBox):
            fieldName = self.property().field()
            idx = editor.model().indexFromName(fieldName).row()
            if idx == -1:
                idx = 0
            editor.setCurrentIndex(idx)
        elif isinstance(editor, QComboBox):
            value, success = self.property().value(QgsExpressionContext())
            if success:
                for r in range(editor.count()):
                    if editor.itemData(r) == value:
                        editor.setCurrentIndex(r)
                        break

    def setModelData(self, w, bridge, index):
        property: QgsProperty = None

        if isinstance(w, QgsFieldExpressionWidget):
            expr = w.asExpression()
            if w.isValidExpression() or expr == '' and w.allowEmptyFieldName():
                property = QgsProperty.fromExpression(expr)

        elif isinstance(w, SpectralProfileColorPropertyWidget):
            property = w.toProperty()

        elif isinstance(w, QCheckBox):
            property = QgsProperty.fromValue(w.isChecked())

        elif self.isProfileFieldProperty() and isinstance(w, QComboBox):
            i = w.currentIndex()
            if i >= 0:
                field: QgsField = w.model().fields().at(i)
                property = QgsProperty.fromField(field.name())

        elif isinstance(w, QComboBox):
            property = QgsProperty.fromValue(w.currentData(Qt.UserRole))

        elif isinstance(w, (QgsSpinBox, QgsDoubleSpinBox)):
            property = QgsProperty.fromValue(w.value())

        if isinstance(property, QgsProperty):
            self.setProperty(property)


class ProfileColorPropertyItem(QgsPropertyItem):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

    def populateContextMenu(self, menu: QMenu):

        if self.isColorProperty():
            a = menu.addAction('Use vector symbol color')
            a.setToolTip('Use map vector symbol colors as profile color.')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
            a.triggered.connect(self.setToSymbolColor)

    def setToSymbolColor(self, *args):
        if self.isColorProperty():
            self.setProperty(QgsProperty.fromExpression('@symbol_color'))


class ProfileCandidateItem(PlotStyleItem):
    """
    Controls the Style of a single profile candidate / current profile.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.label().setCheckable(False)
        self.setEditColors(True)
        # self.label().setCheckState(Qt.Checked)
        self.mCellKey: typing.Tuple[int, str] = None

        from .spectrallibraryplotitems import SpectralProfilePlotDataItem
        self.mPlotItem = SpectralProfilePlotDataItem()

    def emitDataChanged(self):
        super().emitDataChanged()
        self.mPlotItem.setPlotStyle(self.plotStyle())

    def setCellKey(self, fid: int, field: str):
        self.mCellKey = (fid, field)
        self.label().setText(f'{fid} {field}')

    def createExpressionContextScope(self) -> QgsExpressionContextScope:
        scope = QgsExpressionContextScope()
        scope.setVariable('field_name', self.featureField())
        scope.setVariable('field_index', self.featureFieldIndex())
        return scope

    def cellKey(self) -> typing.Tuple[int, str]:
        return self.mCellKey

    def featureId(self) -> int:
        return self.mCellKey[0]

    def featureField(self) -> str:
        return self.mCellKey[1]

    def featureFieldIndex(self) -> int:
        return self.speclib().fields().lookupField(self.mCellKey[1])

    def plotItem(self) -> PlotDataItem:
        return self.mPlotItem


class RasterRendererGroup(PropertyItemGroup):
    """
    Visualizes the bands of a QgsRasterRenderer
    """

    def __init__(self, *args, layer: QgsRasterLayer = None, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = 0
        self.setIcon(QIcon(':/images/themes/default/rendererCategorizedSymbol.svg'))
        self.setData('Renderer', Qt.DisplayRole)
        self.setData('Raster Layer Renderer', Qt.ToolTipRole)

        # self.mPropertyNames[LayerRendererVisualization.PIX_TYPE] = 'Renderer'
        # self.mPropertyTooltips[LayerRendererVisualization.PIX_TYPE] = 'raster layer renderer type'

        self.mLayer: QgsRasterLayer = None
        self.mUnitConverter: UnitConverterFunctionModel = UnitConverterFunctionModel()
        self.mIsVisible: bool = True

        self.mBarR: InfiniteLine = InfiniteLine(pos=1, angle=90, movable=True)
        self.mBarB: InfiniteLine = InfiniteLine(pos=2, angle=90, movable=True)
        self.mBarG: InfiniteLine = InfiniteLine(pos=3, angle=90, movable=True)
        self.mBarA: InfiniteLine = InfiniteLine(pos=3, angle=90, movable=True)

        self.mXUnit: str = BAND_NUMBER
        self.mBarR.sigPositionChangeFinished.connect(self.updateToRenderer)
        self.mBarG.sigPositionChangeFinished.connect(self.updateToRenderer)
        self.mBarB.sigPositionChangeFinished.connect(self.updateToRenderer)
        self.mBarA.sigPositionChangeFinished.connect(self.updateToRenderer)

        self.mItemRenderer = PropertyItem('Renderer')
        self.mItemBandR = PropertyItem('Red')
        self.mItemBandG = PropertyItem('Green')
        self.mItemBandB = PropertyItem('Blue')
        self.mItemBandA = PropertyItem('Alpha')

        for item in self.bandPlotItems():
            item.setVisible(False)

        if isinstance(layer, QgsRasterLayer):
            self.setLayer(layer)

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        self.updateLayerName()

    def updateBarVisiblity(self):
        model = self.model()
        from ...speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
        if isinstance(model, SpectralProfilePlotModel):
            plotItem = model.mPlotWidget.plotItem
            for bar in self.bandPlotItems():

                if True:
                    if bar.isVisible() and bar not in plotItem.items:
                        plotItem.addItem(bar)
                    elif not bar.isVisible() and bar in plotItem.items:
                        plotItem.removeItem(bar)
                else:
                    if bar not in plotItem.items:
                        plotItem.addItem(bar)
                    bar.setEnabled(bar.isVisible())

            s = ""

    def initWithPlotModel(self, model):
        from ...speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
        assert isinstance(model, SpectralProfilePlotModel)
        self.setXUnit(model.xUnit())
        # self.updateBarVisiblity()
        for bar in self.bandPlotItems():
            model.mPlotWidget.plotItem.addItem(bar)

    def clone(self) -> QStandardItem:
        item = RasterRendererGroup()
        item.setLayer(self.layer())
        item.setVisible(self.isVisible())
        return item

    def setXUnit(self, xUnit: str):
        if xUnit is None:
            xUnit = BAND_NUMBER
        self.mXUnit = xUnit
        self.updateFromRenderer()

    def layerId(self) -> str:
        return self.mLayer.id()

    def layer(self) -> QgsRasterLayer:
        return self.mLayer

    def setLayer(self, layer: QgsRasterLayer):

        if layer == self.mLayer:
            return

        if isinstance(self.mLayer, QgsRasterLayer) and layer is None:
            self.onLayerRemoved()

        if isinstance(self.mLayer, QgsRasterLayer):
            self.disconnectGroup()

        assert isinstance(layer, QgsRasterLayer)
        self.mLayer = layer
        layer.rendererChanged.connect(self.updateFromRenderer)
        layer.willBeDeleted.connect(self.onLayerRemoved)
        layer.nameChanged.connect(self.updateLayerName)
        # layer.destroyed.connect(self.onLayerRemoved)

        self.updateFromRenderer()
        self.updateLayerName()

    def onLayerRemoved(self):
        if isinstance(self.mLayer, QgsRasterLayer):
            self.disconnectGroup()
            self.signals().requestRemoval.emit()

    def disconnectGroup(self):
        pw = self.model().plotWidget()
        for bar in self.bandPlotItems():
            if bar in pw.items():
                pw.removeItem(bar)

        self.mLayer = None

    def updateToRenderer(self):
        if not (isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.renderer(), QgsRasterRenderer):
            return
        renderer: QgsRasterRenderer = self.mLayer.renderer().clone()

        if self.mBarA.isVisible():
            bandA = self.xValueToBand(self.mBarA.pos().x())
            if bandA:
                renderer.setAlphaBand(bandA)

        bandR = self.xValueToBand(self.mBarR.pos().x())
        if isinstance(renderer, QgsMultiBandColorRenderer):
            bandG = self.xValueToBand(self.mBarG.pos().x())
            bandB = self.xValueToBand(self.mBarB.pos().x())
            if bandR:
                renderer.setRedBand(bandR)
            if bandG:
                renderer.setGreenBand(bandG)
            if bandB:
                renderer.setBlueBand(bandB)

        elif isinstance(renderer, (QgsHillshadeRenderer, QgsSingleBandPseudoColorRenderer)):
            if bandR:
                renderer.setBand(bandR)
        elif isinstance(renderer, QgsPalettedRasterRenderer):
            pass
        elif isinstance(renderer, QgsRasterContourRenderer):
            if bandR:
                renderer.setInputBand(bandR)
        elif isinstance(renderer, QgsSingleBandColorDataRenderer):
            pass
        elif isinstance(renderer, QgsSingleBandGrayRenderer):
            if bandR:
                renderer.setGrayBand(bandR)

        self.layer().setRenderer(renderer)
        self.layer().triggerRepaint()
        # convert to band unit

    def xValueToBand(self, pos: float) -> int:
        if not isinstance(self.mLayer, QgsRasterLayer):
            return None

        band = None
        if self.mXUnit == BAND_NUMBER:
            band = int(round(pos))
        elif self.mXUnit == BAND_INDEX:
            band = int(round(pos)) + 1
        else:
            wl, wlu = parseWavelength(self.mLayer)
            if wlu:
                func = self.mUnitConverter.convertFunction(self.mXUnit, wlu)
                new_wlu = func(pos)
                if new_wlu is not None:
                    band = np.argmin(np.abs(wl - new_wlu)) + 1
        if isinstance(band, int):
            band = max(band, 0)
            band = min(band, self.mLayer.bandCount())
        return band

    def bandToXValue(self, band: int) -> float:

        if not isinstance(self.mLayer, QgsRasterLayer):
            return None

        if self.mXUnit == BAND_NUMBER:
            return band
        elif self.mXUnit == BAND_INDEX:
            return band - 1
        else:
            wl, wlu = parseWavelength(self.mLayer)
            if wlu:
                func = self.mUnitConverter.convertFunction(wlu, self.mXUnit)
                return func(wl[band - 1])

        return None

    def setData(self, value: typing.Any, role: int = ...) -> None:
        super(RasterRendererGroup, self).setData(value, role)

    def plotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns the activated plot data items
        Note that bandPlotItems() returns all plot items, even those that are not used and should be hidden.
        """
        plotItems = []

        activeItems = self.propertyItems()
        if self.mItemBandR in activeItems:
            plotItems.append(self.mBarR)
        if self.mItemBandG in activeItems:
            plotItems.append(self.mBarG)
        if self.mItemBandB in activeItems:
            plotItems.append(self.mBarB)
        if self.mItemBandA in activeItems:
            plotItems.append(self.mBarA)

        return plotItems

    def setBandPosition(self, band: int, bandBar: InfiniteLine, bandItem: PropertyItem) -> bool:
        bandBar.setToolTip(bandBar.name())
        bandItem.setData(band, Qt.DisplayRole)
        if isinstance(band, int) and band > 0:
            xValue = self.bandToXValue(band)
            if xValue:
                bandBar.setPos(xValue)
                return True
        return False

    def updateLayerName(self):
        if isinstance(self.layer(), QgsRasterLayer):
            self.setText(self.layer().name())
        else:
            self.setText('<layer not set>')

    def updateFromRenderer(self):

        for r in reversed(range(self.rowCount())):
            self.takeRow(r)

        is_checked = self.isVisible()
        if not (isinstance(self.mLayer, QgsRasterLayer)
                and isinstance(self.mLayer.renderer(), QgsRasterRenderer)):
            for b in self.bandPlotItems():
                b.setVisible(False)

            self.setValuesMissing(True)
            return
        else:
            self.setValuesMissing(False)

        layerName = self.mLayer.name()
        renderer = self.mLayer.renderer()
        renderer: QgsRasterRenderer
        rendererName = renderer.type()

        bandR = bandG = bandB = bandA = None

        if renderer.alphaBand() > 0:
            bandA = renderer.alphaBand()

        is_rgb = False
        if isinstance(renderer, QgsMultiBandColorRenderer):
            # rendererName = 'Multi Band Color'
            bandR = renderer.redBand()
            bandG = renderer.greenBand()
            bandB = renderer.blueBand()
            is_rgb = True
        elif isinstance(renderer, (QgsSingleBandGrayRenderer,
                                   QgsPalettedRasterRenderer,
                                   QgsHillshadeRenderer,
                                   QgsRasterContourRenderer,
                                   QgsSingleBandColorDataRenderer,
                                   QgsSingleBandPseudoColorRenderer)
                        ):

            self.mBarR.setPen(color='grey')

            if isinstance(renderer, QgsHillshadeRenderer):
                bandR = renderer.band()
            elif isinstance(renderer, QgsPalettedRasterRenderer):
                bandR = renderer.band()
                # rendererName = 'Paletted Raster Renderer'
            elif isinstance(renderer, QgsRasterContourRenderer):
                bandR = renderer.inputBand()
                # rendererName = 'Raster Contour'
            elif isinstance(renderer, QgsSingleBandColorDataRenderer):
                bandR = None
                # rendererName = 'Single Band Color'
                # todo
            elif isinstance(renderer, QgsSingleBandGrayRenderer):
                bandR = renderer.grayBand()
                # rendererName = 'Single Band Gray'
        emptyPen = QPen()

        self.mItemRenderer.setText(rendererName)

        if len(renderer.usesBands()) >= 3:
            self.mBarR.setName(f'{layerName} red band {bandR}')
            self.mItemBandR.label().setText('Red')
            self.mBarG.setName(f'{layerName} green band {bandG}')
            self.mBarB.setName(f'{layerName} blue band {bandB}')
            self.mBarR.setPen(color='red')
            self.mBarG.setPen(color='green')
            self.mBarB.setPen(color='blue')

        else:
            self.mBarR.setName(f'{layerName} band {bandR}')
            self.mBarR.setPen(color='grey')
            self.mItemBandR.label().setText('Band')

        self.mBarA.setName(f'{layerName} alpha band {bandA}')

        self.mBarR.setVisible(is_checked and self.setBandPosition(bandR, self.mBarR, self.mItemBandR))
        self.mBarG.setVisible(is_checked and self.setBandPosition(bandG, self.mBarG, self.mItemBandG))
        self.mBarB.setVisible(is_checked and self.setBandPosition(bandB, self.mBarB, self.mItemBandB))
        self.mBarA.setVisible(is_checked and self.setBandPosition(bandA, self.mBarA, self.mItemBandA))

        self.appendRow(self.mItemRenderer.propertyRow())
        if bandR:
            self.appendRow(self.mItemBandR.propertyRow())
        if bandG:
            self.appendRow(self.mItemBandG.propertyRow())
        if bandB:
            self.appendRow(self.mItemBandB.propertyRow())
        if bandA:
            self.appendRow(self.mItemBandA.propertyRow())

        # self.updateBarVisiblity()

    def bandPositions(self) -> dict:
        pass

    def bandPlotItems(self) -> typing.List[InfiniteLine]:
        return [self.mBarR, self.mBarG, self.mBarB, self.mBarA]


class ProfileCandidateGroup(SpectralProfilePlotDataItemGroup):
    """
    Controls the style of profile candidates / current profiles
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = 1
        self.setIcon(QIcon(':/qps/ui/icons/select_location.svg'))
        self.setData('Current Profiles', Qt.DisplayRole)
        self.setData('Defines the style of current profile candidates', Qt.ToolTipRole)
        self.mIsVisible: bool = True
        self.mDefaultPlotStyle = PlotStyleItem('DEFAULT')
        self.mDefaultPlotStyle.label().setText('Style')
        self.mDefaultPlotStyle.label().setToolTip('Default plot style of current profiles before they '
                                                  'are added to the spectral library.')
        # self.appendRow(self.mDefaultPlotStyle.propertyRow())
        self.mCandidateStyleItems: typing.Dict[typing.Tuple[int, str], PlotStyleItem] = dict()

        self.initBasicSettings()
        self.setEditable(False)
        self.mMissingValues = False
        # self.setEditable(False)

    def isRemovable(self) -> bool:
        return False

    def generateLabel(self, context: QgsExpressionContext) -> str:
        return f'{context.feature().id()} {context.variable("field_name")}'

    def generateTooltip(self, context: QgsExpressionContext) -> str:
        tooltip = '<html><body><table>'
        label = self.generateLabel(context)
        fid = context.feature().id()
        fname = context.variable('field_name')
        if label:
            tooltip += f'\n<tr><td>Label</td><td>{label}</td></tr>'
        if fid:
            tooltip += f'\n<tr><td>FID</td><td>{fid}</td></tr>'
        if fname not in [None, '']:
            tooltip += f'<tr><td>Field</td><td>{fname}</td></tr>'
        tooltip += '\n</table></body></html>'
        return tooltip

    def generatePlotStyle(self, context: QgsExpressionContext) -> PlotStyle:
        return self.candidateStyle(context.feature().id(), context.variable('field_name'))

    def plotDataItems(self) -> typing.List[PlotDataItem]:
        return [item.plotItem() for item in self.candidateItems()]

    def syncCandidates(self):

        temp_fids = [fid for fid in self.model().speclib().allFeatureIds() if fid < 0]
        to_remove = [k for k in self.mCandidateStyleItems.keys() if k[0] not in temp_fids]
        self.removeCandidates(to_remove)

    def setCandidates(self, candidateStyles: typing.Dict[typing.Tuple[int, str], PlotStyle]):
        self.clearCandidates()
        i = 0
        for (fid, field), style in candidateStyles.items():
            i += 1
            item = ProfileCandidateItem(f'Candidate{i}')
            item.setCellKey(fid, field)

            item.label().setToolTip(f'Feature ID: {fid} field: {field}')
            item.setPlotStyle(style)
            self.mCandidateStyleItems[(fid, field)] = item
            self.appendRow(item.propertyRow())

    def candidateStyle(self, fid: int, field: str) -> PlotStyle:
        item = self.mCandidateStyleItems.get((fid, field), None)
        if isinstance(item, PlotStyleItem):
            return item.plotStyle()
        return None

    def candidateKeys(self) -> typing.List[typing.Tuple[int, str]]:
        return list(self.mCandidateStyleItems.keys())

    def candidateItems(self) -> typing.List[ProfileCandidateItem]:
        return list(self.mCandidateStyleItems.values())

    def candidateFeatureIds(self) -> typing.List[int]:
        return set([i[0] for i in self.candidateKeys()])

    def removeCandidates(self, candidateKeys: typing.List[typing.Tuple[int, str]]):

        to_remove = []
        for k in list(candidateKeys):
            if k in self.mCandidateStyleItems.keys():
                to_remove.append(self.mCandidateStyleItems.pop(k))

        for r in reversed(range(0, self.rowCount())):
            item = self.child(r, 1)
            if item in to_remove:
                self.takeRow(r)

        self.signals().requestPlotUpdate.emit()

    def clearCandidates(self):

        self.removeCandidates(self.mCandidateStyleItems.keys())

    def count(self) -> int:

        return len(self.mCandidateStyleItems)


class ProfileVisualizationGroup(SpectralProfilePlotDataItemGroup):
    """
    Controls the visualization of a set of profiles
    """
    MIME_TYPE = 'application/SpectralProfilePlotVisualization'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = 2
        self.setName('Visualization')
        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = False
        self.mSpeclib: QgsVectorLayer = None

        self.mPlotDataItems: typing.List[PlotDataItem] = []

        self.mPField = QgsPropertyItem('Field')
        self.mPField.setDefinition(QgsPropertyDefinition(
            'Field', 'Name of the field that contains the spectral profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPField.setProperty(QgsProperty.fromField('profiles', True))
        self.mPField.setIsProfileFieldProperty(True)

        self.mPStyle = PlotStyleItem('Style')
        self.mPStyle.setEditColors(False)
        self.mPLabel = QgsPropertyItem('Label')
        self.mPLabel.setDefinition(QgsPropertyDefinition(
            'Label', 'A label to describe the plotted profiles',
            QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPLabel.setProperty(QgsProperty.fromExpression('$id'))

        self.mPFilter = QgsPropertyItem('Filter')
        self.mPFilter.setDefinition(QgsPropertyDefinition(
            'Filter', 'Filter for feature rows', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.mPFilter.setProperty(QgsProperty.fromExpression(''))

        self.mPColor = ProfileColorPropertyItem('Color')
        self.mPColor.setDefinition(QgsPropertyDefinition(
            'Color', 'Color of spectral profile', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mPColor.setProperty(QgsProperty.fromValue(QColor('white')))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLabel, self.mPFilter, self.mPColor, self.mPStyle]:
            self.appendRow(pItem.propertyRow())

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        # connect requestPlotUpdate signal
        for propertyItem in self.propertyItems():
            propertyItem: PropertyItem
            propertyItem.signals().dataChanged.connect(self.signals().dataChanged.emit)
        self.signals().dataChanged.connect(self.update)
        # self.initBasicSettings()

    def initWithPlotModel(self, model):
        self.setSpeclib(model.speclib())

    def propertyRow(self) -> typing.List[QStandardItem]:
        return [self]

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument):
        # appends this visualization to a parent node

        parentNode.setAttribute('name', self.name())
        parentNode.setAttribute('field', self.fieldName())
        parentNode.setAttribute('visible', '1' if self.isVisible() else '0')

        # add speclib node
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            nodeSpeclib = doc.createElement('speclib')
            nodeSpeclib.setAttribute('id', self.speclib().id())
            parentNode.appendChild(nodeSpeclib)

        # add name expression node
        self.mPLabel.writeXml(parentNode, doc)
        self.mPColor.writeXml(parentNode, doc)
        self.mPFilter.writeXml(parentNode, doc)
        self.mPStyle.writeXml(parentNode, doc)

    def createExpressionContextScope(self) -> QgsExpressionContextScope:

        scope = QgsExpressionContextScope('profile_visualization')
        # todo: add scope variables
        scope.setVariable('vis_name', self.name(), isStatic=True)
        return scope

    def readXml(self, parentNode: QDomElement) -> typing.List['ProfileVisualizationGroup']:
        model = self.model()
        self.setText(parentNode.attribute('name'))
        self.setVisible(parentNode.attribute('visible').lower() in ['1', 'true', 'yes'])

        speclibNode = parentNode.firstChildElement('speclib')
        speclib: QgsVectorLayer = None
        if not speclibNode.isNull():
            # try to restore the speclib
            lyrId = speclibNode.attribute('id')
            from ...speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
            if isinstance(model, SpectralProfilePlotModel):
                sl = model.project().mapLayer(lyrId)
                if isinstance(sl, QgsVectorLayer):
                    self.setSpeclib(sl)

            fieldName = parentNode.attribute('field')
            speclib = self.speclib()
            if isinstance(speclib, QgsVectorLayer) and fieldName in speclib.fields().names():
                self.setField(fieldName)
            else:
                self.setField(create_profile_field(fieldName))

            self.mPLabel.readXml(parentNode)
            self.mPFilter.readXml(parentNode)
            self.mPColor.readXml(parentNode)
            self.mPStyle.readXml(parentNode)

    def setColorProperty(self, property: QgsProperty):
        """
        Sets the color property
        :param property:
        :type property:
        :return:
        :rtype:
        """
        assert isinstance(property, QgsProperty)
        self.mPColor.setProperty(property)

    def colorProperty(self) -> QgsProperty:
        """
        Returns the color expression
        :return:
        :rtype:
        """
        return self.mPColor.property()

    def clone(self) -> 'QStandardItem':
        v = ProfileVisualizationGroup()
        return v

    def color(self, context: QgsExpressionContext = QgsExpressionContext()):
        return self.colorProperty().valueAsColor(context, self.generatePlotStyle(context).lineColor())[0]

    def setPlotBackgroundColor(self, color: QColor):
        self.mPStyle.plotStyle().setBackgroundColor(color)
        self.mPStyle.setPlotStyle(self.mPStyle.plotStyle())

    def setColor(self, color: typing.Union[str, QColor]):
        c = QColor(color)
        p = self.mPColor.property()
        p.setStaticValue(c)
        self.mPColor.setProperty(p)

    def name(self) -> str:
        """
        Returns the name of this visualization
        :return:
        """
        return self.text()

    def setName(self, name: str):
        self.setText(name)

    def setSpeclib(self, speclib: QgsVectorLayer):
        assert isinstance(speclib, QgsVectorLayer)
        self.mSpeclib = speclib
        self.update()

    def update(self):
        valuesMissing = False

        if not (isinstance(self.speclib(), QgsVectorLayer)
                and isinstance(self.field(), QgsField)
                and self.field().name() in self.speclib().fields().names()):
            valuesMissing = True
        self.setValuesMissing(valuesMissing)

        self.mPField.label().setIcon(QIcon(WARNING_ICON) if valuesMissing else QIcon())

        to_block = [self.signals()] + [item.signals() for item in self.propertyItems()]
        with SignalBlocker(*to_block) as blocker:
            # modify without signaling
            self.setPlotStyle(self.generatePlotStyle())

        self.signals().requestPlotUpdate.emit()

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def isComplete(self) -> bool:
        speclib = self.speclib()
        field = self.field()
        b = isinstance(speclib, QgsVectorLayer) \
            and is_profile_field(field) \
            and field.name() in speclib.fields().names()
        return b

    def setFilterExpression(self, expression):
        if isinstance(expression, QgsExpression):
            expression = expression.expression()
        assert isinstance(expression, str)
        p = self.mPFilter.property()
        p.setExpressionString(expression)
        self.mPFilter.setProperty(p)

    def filterProperty(self) -> QgsProperty:
        """
        Returns the filter expression that describes included profiles
        :return: str
        """
        return self.mPFilter.property()

    def setLabelExpression(self, expression):
        if isinstance(expression, QgsExpression):
            expression = expression.expression()
        assert isinstance(expression, str)
        p = self.mPLabel.property()
        p.setExpressionString(expression)
        self.mPLabel.setProperty(p)

    def labelProperty(self) -> QgsProperty:
        """
        Returns the expression that returns the name for a single profile
        :return: str
        """
        return self.mPLabel.property()

    def setField(self, field: typing.Union[QgsField, str]):

        if isinstance(field, str):
            speclib = self.speclib()
            assert isinstance(speclib, QgsVectorLayer), 'Speclib undefined'
            field = speclib.fields().field(field)
        assert isinstance(field, QgsField)
        p = self.mPField.property()
        p.setField(field.name())
        self.mPField.setProperty(p)

    def field(self) -> QgsField:
        fields = self.speclib().fields()
        i = fields.lookupField(self.fieldName())
        if i < 0:
            return None
        else:
            return fields.at(i)

    def fieldName(self) -> str:
        return self.mPField.property().field()

    def fieldIdx(self) -> int:
        return self.speclib().fields().lookupField(self.field().name())

    def setPlotStyle(self, style: PlotStyle):
        self.mPStyle.setPlotStyle(style)

    def generateTooltip(self, context: QgsExpressionContext) -> str:
        tooltip = '<html><body><table>'
        label = ''
        fid = context.feature().id()
        fname = context.variable('field_name')
        if label:
            tooltip += f'\n<tr><td>Label</td><td>{label}</td></tr>'
        if fid:
            tooltip += f'\n<tr><td>FID</td><td>{fid}</td></tr>'
        if fname not in [None, '']:
            tooltip += f'<tr><td>Field</td><td>{fname}</td></tr>'
        tooltip += '\n</table></body></html>'
        return tooltip

    def generateLabel(self, context: QgsExpressionContext):
        defaultLabel = ''
        if context.feature().isValid():
            defaultLabel = f'{context.feature().id()}, {self.fieldName()}'
        label, success = self.labelProperty().valueAsString(context, defaultString=defaultLabel)
        if success:
            return label
        else:
            return defaultLabel

    def generatePlotStyle(self, context: QgsExpressionContext = QgsExpressionContext()) -> PlotStyle:
        style = self.mPStyle.plotStyle()
        prop = self.colorProperty()
        featureColor, success = prop.valueAsColor(context, defaultColor=style.linePen.color())

        style = PlotStyle(plotStyle=style)
        if success:
            style.setLineColor(featureColor)
            style.setMarkerColor(featureColor)
            style.setMarkerLinecolor(featureColor)
        return style

    def plotDataItems(self) -> typing.List[PlotDataItem]:
        """
        Returns a list with all pyqtgraph plot data items
        """
        return self.mPlotDataItems[:]


PropertyItemGroup.registerXmlFactory(RasterRendererGroup())
PropertyItemGroup.registerXmlFactory(ProfileVisualizationGroup())
