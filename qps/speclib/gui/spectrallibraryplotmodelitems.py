"""
***************************************************************************
    spectralibraryplotmodelitems.py

    Items to described plot components in a spectral library plot.
    ---------------------
    Beginning            : January 2022
    Copyright            : (C) 2023 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
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
import json
import sys
from typing import Any, List, Union, Optional

import numpy as np

from qgis.PyQt.QtCore import QAbstractItemModel
from qgis.PyQt.QtCore import QMimeData, QModelIndex, QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPen, QPixmap, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QMenu, QSizePolicy, QSpinBox, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import Qgis, QgsExpression, QgsExpressionContext, QgsExpressionContextGenerator, \
    QgsExpressionContextScope, QgsExpressionContextUtils, QgsFeature, QgsFeatureRenderer, QgsField, \
    QgsHillshadeRenderer, QgsMultiBandColorRenderer, QgsPalettedRasterRenderer, QgsProperty, QgsPropertyDefinition, \
    QgsRasterContourRenderer, QgsRasterLayer, QgsRasterRenderer, QgsReadWriteContext, QgsRenderContext, \
    QgsSingleBandColorDataRenderer, QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer, QgsTextFormat, \
    QgsVectorLayer, QgsWkbTypes, QgsXmlUtils
from qgis.core import QgsFeatureRequest
from qgis.core import QgsProject, QgsMapLayer
from qgis.gui import QgsColorButton, QgsDoubleSpinBox, QgsFieldExpressionWidget, QgsPropertyOverrideButton, QgsSpinBox
from qgis.gui import QgsMapLayerComboBox
from ..core import is_spectral_library, is_profile_field
from ...layerfielddialog import LayerFieldWidget
from ...plotstyling.plotstyling import PlotStyle, PlotStyleButton, PlotWidgetStyle
from ...pyqtgraph.pyqtgraph import InfiniteLine, PlotDataItem
from ...pyqtgraph.pyqtgraph.widgets.PlotWidget import PlotWidget
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...unitmodel import BAND_INDEX, BAND_NUMBER, UnitConverterFunctionModel
from ...utils import featureSymbolScope

WARNING_ICON = QIcon(r':/images/themes/default/mIconWarning.svg')


class SpectralProfileColorPropertyWidget(QWidget):
    """
    Widget to specify the SpectralProfile colors.

    """

    class ContextGenerator(QgsExpressionContextGenerator):

        def __init__(self, widget):
            super().__init__()

            self.mWidget: 'SpectralProfileColorPropertyWidget' = widget

        def createExpressionContext(self) -> QgsExpressionContext:
            layer = self.mWidget.mPropertyOverrideButton.vectorLayer()
            if not isinstance(layer, QgsVectorLayer):
                return QgsExpressionContext()

            context: QgsExpressionContext = layer.createExpressionContext()
            feature: Optional[QgsFeature] = None
            for f in layer.getFeatures():
                feature = f
                break

            if isinstance(feature, QgsFeature):
                renderContext = QgsRenderContext()
                context.setFeature(feature)
                renderer = layer.renderer()
                if isinstance(renderer, QgsFeatureRenderer):
                    symbols = renderer.symbols(renderContext)
                    if len(symbols) > 0:
                        symbol = symbols[0]
                        j = context.indexOfScope('Symbol')
                        if j < 0:
                            symbolScope = QgsExpressionContextScope('Symbol')
                            context.appendScope(symbolScope)
                        else:
                            symbolScope: QgsExpressionContextScope = context.scope(j)
                        QgsExpressionContextUtils.updateSymbolScope(symbol, symbolScope)
            return context

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setWindowIcon(QIcon(':/images/themes/default/mIconColorBox.svg'))
        self.mContextGenerator = SpectralProfileColorPropertyWidget.ContextGenerator(self)
        # self.mContext: QgsExpressionContext = QgsExpressionContext()
        # self.mRenderContext: QgsRenderContext = QgsRenderContext()
        # self.mRenderer: QgsFeatureRenderer = None
        self.mDefaultColor = QColor('green')
        self.mColorButton = QgsColorButton()
        self.mColorButton.colorChanged.connect(self.onButtonColorChanged)

        self.mColorButton.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.mPropertyOverrideButton = QgsPropertyOverrideButton()
        self.mPropertyOverrideButton.registerLinkedWidget(self.mColorButton)
        self.mPropertyOverrideButton.registerExpressionContextGenerator(self.mContextGenerator)
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

        self.mPropertyOverrideButton.setVectorLayer(layer)
        self.mPropertyOverrideButton.updateFieldLists()

    def onButtonColorChanged(self, color: QColor):
        self.mPropertyOverrideButton.setActive(False)

    def setDefaultColor(self, color: QColor):
        self.mDefaultColor = QColor(color)

    def setToProperty(self, property: QgsProperty):
        assert isinstance(property, QgsProperty)

        if property.propertyType() == QgsProperty.StaticProperty:
            self.mColorButton.setColor(
                property.valueAsColor(self.mContextGenerator.createExpressionContext(), self.mDefaultColor)[0])
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
        self.mItemName = kwds.get('item_name')

    def __ne__(self, other):
        return not self.__eq__(other)

    def firstColumnSpanned(self) -> bool:
        return len(self.propertyRow()) == 1

    def propertyRow(self) -> List[QStandardItem]:
        return [self]

    def model(self) -> QStandardItemModel:
        return super().model()

    def populateContextMenu(self, menu: QMenu):
        pass

    def previewPixmap(self, size: QSize) -> QPixmap:
        return None

    def hasPixmap(self) -> bool:
        return False

    def data(self, role: int = ...) -> Any:

        if role == Qt.UserRole:
            return self
            # return None
        else:
            return super().data(role)


class PropertyLabel(QStandardItem):
    """
    The label lined to a PropertyItem
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setCheckable(False)
        self.setEditable(False)
        self.setDropEnabled(False)
        self.setDragEnabled(False)
        # self.mSignals = PropertyLabel.Signals()

    def propertyItem(self) -> 'PropertyItem':
        """
        Returns the PropertyItem paired with this PropertyLabel.
        Should be in the column left to it
        """
        item = self.model().index(self.row(), self.column() + 1,
                                  parent=self.parent().index()).data(Qt.UserRole)

        if isinstance(item, PropertyItem) and item.label() == self:
            return item

    def data(self, role: int = ...) -> Any:
        if role == Qt.UserRole:
            return self
        return super().data(role)


class PropertyItem(PropertyItemBase):
    """
    Controls a single property parameter.
    Is paired with a PropertyLabel.
    .propertyRow() -> [PropertyLabel, PropertyItem]
    """

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

    def __eq__(self, other):
        if not isinstance(other, PropertyItem):
            return False
        if self.__class__.__name__ != other.__class__.__name__:
            return False

        return self.key() == other.key() and self.data(Qt.DisplayRole) == other.data(Qt.DisplayRole)

    def __ne__(self, other):
        return not self.__eq__(other)

    def setToolTip(self, tooltip: str):

        self.label().setToolTip(tooltip)
        super().setToolTip(tooltip)

    def itemIsChecked(self) -> bool:

        if self.label().isCheckable():
            return self.label().checkState() == Qt.Checked
        return None

    def setItemCheckable(self, b: bool):
        self.label().setCheckable(b)
        self.label().setEditable(b)

    def setItemChecked(self, b: bool):
        self.label().setCheckState(Qt.Checked if b is True else Qt.Unchecked)

    # def signals(self):
    #    return self.mSignals

    def createEditor(self, parent):

        return None

    def clone(self):
        raise NotImplementedError()

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        pass

    def setModelData(self, w, bridge, index):
        pass

    def key(self) -> str:
        return self.mKey

    def label(self) -> PropertyLabel:
        return self.mLabel

    def propertyRow(self) -> List[QStandardItem]:
        return [self.label(), self]


class PropertyItemGroup(PropertyItemBase):
    """
    Represents a group of properties.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mMissingValues: bool = False
        self.mZValue = 0
        # self.mSignals = PropertyItemGroup.Signals()
        self.mFirstColumnSpanned = True

        self.mProject: QgsProject = QgsProject.instance()

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project

    def project(self) -> QgsProject:
        return self.mProject

    def __eq__(self, other):
        s = ""
        if not (isinstance(other, PropertyItemGroup) and self.__class__.__name__ == other.__class__.__name__):
            return False

        ud1 = self.data(Qt.DisplayRole)
        ud2 = other.data(Qt.DisplayRole)

        b = (self.checkState() == other.checkState()) and (ud1 == ud2)

        if self.rowCount() != other.rowCount():
            return False
        for p1, p2 in zip(self.propertyItems(), other.propertyItems()):
            if p1 != p2:
                return False
        return b

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return super().__repr__() + f' "{self.data(Qt.DisplayRole)}"'

    def disconnectGroup(self):
        """
        Should implement all actions required to remove this property item from the plot
        """
        pass

    def isRemovable(self) -> bool:
        return True

    def zValue(self) -> int:
        return self.mZValue

    def asMap(self) -> dict:
        """
        Returns the settings as dict which can be serialized as JSON string.
        """
        raise NotImplementedError(f'Missing .asMap() in {self.__class__.__name__}')

    def fromMap(self, settings: dict):
        raise NotImplementedError(f'Missing .fromMap() in {self.__class__.__name__}')

    def createPlotStyle(self, feature: QgsFeature, fieldIndex: int) -> Optional[PlotStyle]:

        return None

    def plotDataItems(self) -> List[PlotDataItem]:
        """
        Returns a list with all pyqtgraph plot data items
        """
        return []

    def propertyItems(self) -> List['PropertyItem']:
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

    def data(self, role: int = ...) -> Any:

        if role == Qt.DecorationRole and self.mMissingValues:
            return QIcon(WARNING_ICON)

        return super().data(role)

    def setData(self, value: Any, role: int = ...) -> None:
        value = super().setData(value, role)

        if role == Qt.CheckStateRole:
            # self.mSignals.requestPlotUpdate.emit()
            is_visible = self.isVisible()
            for item in self.plotDataItems():
                item.setVisible(is_visible)
            self.emitDataChanged()
            # if is_visible:
            #    self.mSignals.requestPlotUpdate.emit()
        return value

    def update(self):
        pass

    MIME_TYPE = 'application/SpectralProfilePlot/PropertyItems'

    @staticmethod
    def toMimeData(propertyGroups: List['PropertyItemGroup']):

        for g in propertyGroups:
            assert isinstance(g, PropertyItemGroup)

        md = QMimeData()
        context = QgsReadWriteContext()
        doc = QDomDocument()
        root = doc.createElement('PropertyItemGroups')
        doc.appendChild(root)
        for grp in propertyGroups:
            if isinstance(grp, PropertyItemGroup):
                data = grp.asMap()
                node = doc.createElement('PropertyItemGroup')
                node.setAttribute('type', grp.__class__.__name__)
                tn = doc.createTextNode(json.dumps(data))
                node.appendChild(tn)
                root.appendChild(node)
        md.setData(PropertyItemGroup.MIME_TYPE, doc.toByteArray())
        return md

    @staticmethod
    def fromMimeData(mimeData: QMimeData) -> List['ProfileVisualizationGroup']:

        context = QgsReadWriteContext()

        groups = []
        if mimeData.hasFormat(PropertyItemGroup.MIME_TYPE):
            ba = mimeData.data(PropertyItemGroup.MIME_TYPE)
            doc = QDomDocument()
            doc.setContent(ba)
            root = doc.firstChildElement('PropertyItemGroups')
            if not root.isNull():
                # print(nodeXmlString(root))
                grpNode = root.firstChild().toElement()
                while not grpNode.isNull():
                    if grpNode.nodeName() == 'PropertyItemGroup':
                        grpNode = grpNode.toElement()
                        t = grpNode.attribute('type')
                        grp = None
                        if t == ProfileVisualizationGroup.__name__:
                            grp = ProfileVisualizationGroup()
                            data = grpNode.text()
                            data = json.loads(data)
                            grp.fromMap(data)

                        if grp:
                            groups.append(grp)
                        else:
                            s = ""
                        s = ""

                    grpNode = grpNode.nextSibling()
        return groups


class LegendSettingsGroup(PropertyItemGroup):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = -1
        self.setText('Legend')
        self.setIcon(QIcon())

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Unchecked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

        self.mP_MaxProfiles = QgsPropertyItem('legend_max_profiles')
        self.mP_MaxProfiles.setDefinition(QgsPropertyDefinition(
            'Max. Profiles', 'Maximum number of profiles listed in legend',
            QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositive))
        self.mP_MaxProfiles.setProperty(QgsProperty.fromValue(64))
        # labelTextSize
        self.m_textsize = QgsPropertyItem('legend_text_size')
        self.m_textsize.setDefinition(QgsPropertyDefinition(
            'Text size', 'Legend text size', QgsPropertyDefinition.StandardPropertyTemplate.String))
        self.m_textsize.setProperty(QgsProperty.fromValue('9px'))

        for pItem in [  # self.mPLegend,
            self.mP_MaxProfiles, self.m_textsize
        ]:
            self.appendRow(pItem.propertyRow())

    def asMap(self) -> dict:
        d = {
            'show': self.checkState() == Qt.Checked,
            'text_size': self.m_textsize.value(),
            'max_items': self.mP_MaxProfiles.value(),
        }

        return d


class GeneralSettingsGroup(PropertyItemGroup):
    """
    General Plot Settings
    """

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
                'Sort Bands', 'Sort bands by their x values.',
                QgsPropertyDefinition.StandardPropertyTemplate.Boolean)
        )
        self.mP_SortBands.setValue(QgsProperty.fromValue(True))

        self.mP_BadBands = QgsPropertyItem('BadBands')
        self.mP_BadBands.setDefinition(
            QgsPropertyDefinition(
                'Bad Bands', 'Show or hide values with a bad band value != 1.',
                QgsPropertyDefinition.StandardPropertyTemplate.Boolean)

        )
        self.mP_BadBands.setProperty(QgsProperty.fromValue(True))

        self.mP_MaxProfiles = QgsPropertyItem('MaxProfiles')
        self.mP_MaxProfiles.setDefinition(QgsPropertyDefinition(
            'Max. Profiles', 'Maximum number of profiles that can be plotted.',
            QgsPropertyDefinition.StandardPropertyTemplate.IntegerPositive))

        self.mP_MaxProfiles.setProperty(QgsProperty.fromValue(256))

        self.mP_Antialiasing = QgsPropertyItem('Antialias')
        self.mP_Antialiasing.setDefinition(
            QgsPropertyDefinition(
                'Antialias', 'Enable antialias. Can decrease rendering speed.',
                QgsPropertyDefinition.StandardPropertyTemplate.Boolean)

        )
        self.mP_Antialiasing.setProperty(QgsProperty.fromValue(False))

        self.mP_BG = QgsPropertyItem('BG')
        self.mP_BG.setDefinition(QgsPropertyDefinition(
            'Background', 'Plot background color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_BG.setProperty(QgsProperty.fromValue(QColor('black')))

        self.mP_FG = QgsPropertyItem('FG')
        self.mP_FG.setDefinition(QgsPropertyDefinition(
            'Foreground', 'Plot foreground color', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_FG.setProperty(QgsProperty.fromValue(QColor('white')))

        self.mP_SC = QgsPropertyItem('SC')
        self.mP_SC.setDefinition(QgsPropertyDefinition(
            'Selection', 'Color of selected profiles', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_SC.setProperty(QgsProperty.fromValue(QColor('yellow')))

        self.mP_CH = QgsPropertyItem('CH')
        self.mP_CH.setDefinition(QgsPropertyDefinition(
            'Crosshair', 'Show a crosshair and set its color',
            QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mP_CH.setProperty(QgsProperty.fromValue(QColor('yellow')))
        self.mP_CH.setItemCheckable(True)
        self.mP_CH.setItemChecked(True)

        self.mProfileCandidates = PlotStyleItem('candidate_style', labelName='Candidates')

        tt = 'Highlight profile candidates using a different style<br>' \
             'If activated and unless other defined, use the style defined here.'

        self.mProfileCandidates.setToolTip(tt)

        default_candidate_style = PlotStyle()
        default_candidate_style.setMarkerColor('green')
        default_candidate_style.setLineColor('green')
        default_candidate_style.setLineWidth(2)
        default_candidate_style.setLineStyle(Qt.SolidLine)

        self.mProfileCandidates.setPlotStyle(default_candidate_style)
        self.mProfileCandidates.setItemCheckable(True)
        self.mProfileCandidates.setItemChecked(True)
        self.mProfileCandidates.setEditColors(True)

        self.mLegendGroup = LegendSettingsGroup(self)
        for pItem in [  # self.mPLegend,
            self.mProfileCandidates,
            self.mP_MaxProfiles,
            self.mP_SortBands, self.mP_BadBands, self.mP_Antialiasing,
            self.mP_BG, self.mP_FG, self.mP_SC, self.mP_CH,
            self.mLegendGroup,
        ]:
            self.appendRow(pItem.propertyRow())

        self.mContext: QgsExpressionContext = QgsExpressionContext()

        self.mMissingValues = False

    def fromMap(self, settings: dict):
        TRUE = [True, 1]
        if 'max_profiles' in settings:
            self.setMaximumProfiles(int(settings['max_profiles']))
        if 'show_bad_bands' in settings:
            self.mP_BadBands.setValue(settings['show_bad_bands'] in TRUE)
        if 'sort_bands' in settings:
            self.mP_SortBands.setValue(settings['sort_bands'] in TRUE)
        if 'show_crosshair' in settings:
            self.mP_CH.setValue(settings['show_crosshair'] in TRUE)
        if 'antialiasing' in settings:
            self.mP_Antialiasing.setValue(settings['antialiasing'] in TRUE)
        if 'color_bg' in settings:
            self.mP_BG.setValue(QColor(settings['color_bg']))
        if 'color_fg' in settings:
            self.mP_FG.setValue(QColor(settings['color_fg']))
        if 'color_sc' in settings:
            self.mP_SC.setValue(QColor(settings['color_sc']))
        if 'color_ch' in settings:
            self.mP_CH.setValue(QColor(settings['color_ch']))

        if 'show_candidates' in settings:
            self.mProfileCandidates.setItemChecked(settings['show_candidates'] in TRUE)

        if 'candidate_style' in settings:
            plot_style = PlotStyle.fromMap(settings['candidate_style'])
            self.mProfileCandidates.setPlotStyle(plot_style)

    def asMap(self) -> dict:

        candidate_style = self.profileCandidateStyle().map()
        candidate_show = self.mProfileCandidates.itemIsChecked()

        d = {
            'max_profiles': self.maximumProfiles(),
            'show_bad_bands': self.showBadBands(),
            'sort_bands': self.sortBands(),
            'show_crosshair': self.mP_CH.itemIsChecked(),
            'antialiasing': self.mP_Antialiasing.value(),
            'color_bg': self.backgroundColor().name(),
            'color_fg': self.foregroundColor().name(),
            'color_sc': self.selectionColor().name(),
            'color_ch': self.crosshairColor().name(),
            'candidate_style': candidate_style,
            'show_candidates': candidate_show,
            'legend': self.mLegendGroup.asMap(),
        }
        return d

    def populateContextMenu(self, menu: QMenu):

        m = menu.addMenu('Color Theme')

        for style in PlotWidgetStyle.plotWidgetStyles():
            a = m.addAction(style.name)
            a.setIcon(QIcon(style.icon))
            a.triggered.connect(lambda *args, s=style: self.setPlotWidgetStyle(s))

    def maximumProfiles(self) -> int:
        return self.mP_MaxProfiles.value()

    def setMaximumProfiles(self, n: int):
        assert n >= 0
        self.mP_MaxProfiles.setProperty(QgsProperty.fromValue(n))

    def expressionContext(self) -> QgsExpressionContext:
        return self.mContext

    def profileCandidateStyle(self) -> PlotStyle:
        """
        Returns the plot style to be used as default for profile candidates
        :return: PlotStyle
        """
        style = self.mProfileCandidates.plotStyle()
        style.setAntialias(self.antialias())
        return style

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

        from .spectralprofileplotmodel import SpectralProfilePlotModel
        model: SpectralProfilePlotModel = self.model()
        if isinstance(model, SpectralProfilePlotModel):
            model.mDefaultSymbolRenderer.symbol().setColor(style.foregroundColor)

            b = False
            for vis in model.visualizations():
                vis.setPlotWidgetStyle(style)
        self.emitDataChanged()

    def antialias(self) -> bool:
        return self.mP_Antialiasing.property().valueAsBool(self.expressionContext())[0]

    def backgroundColor(self) -> QColor:
        return self.mP_BG.property().valueAsColor(self.expressionContext())[0]

    def foregroundColor(self) -> QColor:
        return self.mP_FG.property().valueAsColor(self.expressionContext())[0]

    def selectionColor(self) -> QColor:
        return self.mP_SC.property().valueAsColor(self.expressionContext())[0]

    def crosshairColor(self) -> QColor:
        return self.mP_CH.property().valueAsColor(self.expressionContext())[0]

    def showBadBands(self) -> bool:
        return self.mP_BadBands.property().valueAsBool(self.expressionContext(), False)[0]

    def sortBands(self) -> bool:
        return self.mP_SortBands.property().valueAsBool(self.expressionContext(), True)[0]

    def isRemovable(self) -> bool:
        return False

    def isVisible(self) -> bool:
        return True


class PlotStyleItem(PropertyItem):
    """
    A property item to control a PlotStyle
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mPlotStyle = PlotStyle()
        self.setEditable(True)

        self.mEditColors: bool = False

    def clone(self):
        item = PlotStyleItem(self.key())
        item.setPlotStyle(self.plotStyle().clone())
        return item

    def __eq__(self, other):
        return super().__eq__(other) and self.plotStyle() == other.plotStyle()

    def setEditColors(self, b):
        self.mEditColors = b is True

    def setPlotStyle(self, plotStyle: PlotStyle):
        if plotStyle != self.mPlotStyle:
            self.mPlotStyle = plotStyle
            self.emitDataChanged()

    def plotStyle(self) -> PlotStyle:
        return self.mPlotStyle

    def createEditor(self, parent):

        w = PlotStyleButton(parent=parent)
        w.setMinimumSize(5, 5)
        w.setColorWidgetVisibility(self.mEditColors)
        w.setVisibilityCheckboxVisible(False)
        w.setToolTip('Set curve style')
        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        if isinstance(editor, PlotStyleButton):
            grp = self.parent()
            if isinstance(grp, ProfileVisualizationGroup):
                plot_style = grp.plotStyle(add_symbol_scope=True)
            else:
                plot_style = self.plotStyle()

            editor.setPlotStyle(plot_style)

    def setModelData(self, w, bridge, index):
        if isinstance(w, PlotStyleButton):
            self.setPlotStyle(w.plotStyle())

    def writeXml(self, parentNode: QDomElement, context: QgsReadWriteContext, attribute: bool = False):
        doc: QDomDocument = parentNode.ownerDocument()
        xml_tag = self.key()
        node = doc.createElement(xml_tag)
        self.mPlotStyle.writeXml(node, doc)
        parentNode.appendChild(node)

    def readXml(self, parentNode: QDomElement, context: QgsReadWriteContext, attribute: bool = False):
        node = parentNode.firstChildElement(self.key()).toElement()
        if not node.isNull():
            style = PlotStyle.readXml(node)
            if isinstance(style, PlotStyle):
                self.setPlotStyle(style)


class SpectralProfileLayerFieldItem(PropertyItem):

    def __init__(self, *args, **kwds):

        self.mFieldName: Optional[str] = None
        self.mLayerID: Optional[str] = None
        self.mProject = QgsProject().instance()

        super().__init__(*args, **kwds)
        self.mEditor = None
        self.setEditable(True)

    def layer(self) -> Optional[QgsVectorLayer]:

        lyr = self.mProject.mapLayer(self.mLayerID)
        if isinstance(lyr, QgsVectorLayer):
            return lyr
        return None

    def setProject(self, project: QgsProject):
        self.mProject = project

    def populateContextMenu(self, menu: QMenu):

        a = menu.addAction('Open attribute table')

        layer = self.layer()

        def onOpenAttributeTableRequest(layer_id: str):
            from .spectralprofileplotmodel import SpectralProfilePlotModel
            model = self.model()
            if isinstance(model, SpectralProfilePlotModel):
                model.sigOpenAttributeTableRequest.emit(layer_id)

        if isinstance(layer, QgsVectorLayer):
            a.setToolTip(f'Open the attribute table of layer "{layer.name()}"')
            a.triggered.connect(lambda *args, lid=self.mLayerID: onOpenAttributeTableRequest(lid))
        else:
            a.setEnabled(False)

    def createEditor(self, parent):
        w = LayerFieldWidget(parent=parent)

        # w = QLabel('TEST', parent=parent)
        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        parentItem = self.parent()

        # if isinstance(parentItem, ProfileVisualizationGroup):
        if isinstance(editor, LayerFieldWidget):
            editor.setProject(self.mProject)
            editor.setLayerFilter(lambda lyr: is_spectral_library(lyr))
            editor.setFieldFilter(lambda field: is_profile_field(field))

            lyr = self.layer()
            if isinstance(lyr, QgsVectorLayer):
                editor.setLayerField(lyr, self.mFieldName)

    def setModelData(self, editor: QWidget, bridge, index: QModelIndex):

        if isinstance(editor, LayerFieldWidget):
            layer, field = editor.layerField()
            self.mLayerID = layer.id()
            self.mFieldName = field
            self.emitDataChanged()

    def setLayerField(self,
                      layer_id: Union[None, str, QgsVectorLayer],
                      field_name: Union[None, str, QgsField]):
        if isinstance(field_name, QgsField):
            field_name = field_name.name()

        if isinstance(layer_id, QgsVectorLayer):
            layer_id = layer_id.id()

        if layer_id != self.mLayerID or field_name != self.mFieldName:
            self.mLayerID = layer_id
            self.mFieldName = field_name

            self.emitDataChanged()

    def field(self) -> Optional[str]:
        return self.mFieldName

    def data(self, role: int = ...) -> Any:

        missing_layer = self.mLayerID in ['', None]
        missing_field = self.mFieldName in ['', None]
        if role == Qt.DisplayRole:

            if missing_layer:
                return '<select layer>'
            elif missing_field:
                return '<select field>'
            else:
                return self.mFieldName

        if role == Qt.ForegroundRole:

            if missing_field or missing_layer:
                return QColor('red')

        return super().data(role)


class QgsTextFormatItem(PropertyItem):

    def __init__(self, *args, **kwds):
        super(self).__init__(*args, **kwds)
        self.mTextFormat = QgsTextFormat()
        self.setEditable(True)


class QgsPropertyItem(PropertyItem):

    def __init__(self, *args, **kwds):
        self.mProperty: Optional[QgsProperty] = None
        self.mDefinition: Optional[QgsPropertyDefinition] = None
        super().__init__(*args, **kwds)
        self.setEditable(True)

    def update(self):
        self.setText(self.mProperty.valueAsString(QgsExpressionContext()))

    def writeXml(self, parentNode: QDomElement, context: QgsReadWriteContext, attribute: bool = False):
        doc: QDomDocument = parentNode.ownerDocument()
        xml_tag = self.key()
        node = QgsXmlUtils.writeVariant(self.property(), doc)
        node.setTagName(xml_tag)
        parentNode.appendChild(node)

    def readXml(self, parentNode: QDomElement, context: QgsReadWriteContext, attribute: bool = False) -> bool:

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

    def data(self, role: int = ...) -> Any:

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

    def isColorProperty(self) -> bool:
        return self.definition().standardTemplate() in [QgsPropertyDefinition.ColorWithAlpha,
                                                        QgsPropertyDefinition.ColorNoAlpha]

    def createEditor(self, parent):
        # speclib: Optional[QgsVectorLayer] = self.speclib()
        template = self.definition().standardTemplate()

        if self.isColorProperty():
            w = SpectralProfileColorPropertyWidget(parent=parent)

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

        return w

    def setEditorData(self, editor: QWidget, index: QModelIndex):

        grp = self.parent()
        if isinstance(grp, ProfileVisualizationGroup):
            lyr = grp.layer()
        else:
            lyr = None

        if isinstance(editor, QgsFieldExpressionWidget):
            editor.setProperty('lastexpr', self.property().expressionString())
            if isinstance(grp, ProfileVisualizationGroup):
                editor.registerExpressionContextGenerator(grp.expressionContextGenerator())
            if isinstance(lyr, QgsVectorLayer):
                editor.setLayer(lyr)

        elif isinstance(editor, SpectralProfileColorPropertyWidget):
            editor.setToProperty(self.property())
            if isinstance(lyr, QgsVectorLayer):
                editor.setLayer(lyr)

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

        elif isinstance(w, QComboBox):
            property = QgsProperty.fromValue(w.currentData(Qt.UserRole))

        elif isinstance(w, (QgsSpinBox, QgsDoubleSpinBox)):
            property = QgsProperty.fromValue(w.value())

        if isinstance(property, QgsProperty):
            self.setProperty(property)


class ProfileColorPropertyItem(QgsPropertyItem):
    """
    A property item to collect a color or color expression.
    """

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

    def setColor(self, color: Union[str, QColor]):
        """Sets the color as fixed color value"""
        c = QColor(color)
        p = self.property()
        p.setStaticValue(c)
        self.emitDataChanged()

    def setColorExpression(self, expression: str):
        assert isinstance(expression, str)
        p = self.property()
        p.setExpressionString(expression)
        self.emitDataChanged()

    def colorExpression(self) -> str:
        """
        Returns the current color as expression string
        :return:
        """
        p = self.property()
        if p.propertyType() == Qgis.PropertyType.Expression:
            color_expression = p.expressionString()
        elif p.propertyType() == Qgis.PropertyType.Static:
            color_expression = p.staticValue()
            if isinstance(color_expression, QColor):
                color_expression = f"'{color_expression.name()}'"
        else:
            color_expression = "'white'"
        return color_expression

    def populateContextMenu(self, menu: QMenu):

        if self.isColorProperty():
            a = menu.addAction('Use vector symbol color')
            a.setToolTip('Use map vector symbol colors as profile color.')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
            a.triggered.connect(self.setToSymbolColor)

    def setToSymbolColor(self, *args):
        if self.isColorProperty():
            self.setProperty(QgsProperty.fromExpression('@symbol_color'))


class RasterRendererGroup(PropertyItemGroup):
    """
    Visualizes the bands of a QgsRasterLayer
    """

    def __init__(self, *args, layer: QgsRasterLayer = None, **kwds):
        super().__init__(*args, **kwds)
        self.mZValue = 0
        self.setIcon(QIcon(':/images/themes/default/rendererCategorizedSymbol.svg'))
        self.setData('Renderer', Qt.DisplayRole)
        self.setData('Raster Layer Renderer', Qt.ToolTipRole)

        # self.mPropertyNames[LayerRendererVisualization.PIX_TYPE] = 'Renderer'
        # self.mPropertyTooltips[LayerRendererVisualization.PIX_TYPE] = 'raster layer renderer type'

        self.mLayerID = None
        self.mSpectralProperties: Optional[QgsRasterLayerSpectralProperties] = None

        self.mUnitConverter: UnitConverterFunctionModel = UnitConverterFunctionModel.instance()
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

    def createEditor(self, parent):
        # speclib: Optional[QgsVectorLayer] = self.speclib()

        return QgsMapLayerComboBox(parent=parent)

    def setEditorData(self, editor: QWidget, index: QModelIndex):

        if isinstance(editor, QgsMapLayerComboBox):
            editor.setFilters(Qgis.LayerFilter.RasterLayer)

            layer = self.layer()
            p = self.project()
            if isinstance(layer, QgsRasterLayer):
                if layer.id() not in p.mapLayers():
                    p2 = layer.project()
                    if isinstance(p2, QgsProject) and layer.id() in p2.mapLayers():
                        p = p2
            if isinstance(p, QgsProject):
                editor.setProject(p)

            if isinstance(layer, QgsRasterLayer):
                editor.setLayer(layer)
                for i in range(editor.count()):
                    s = ""
        s = ""

    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex):

        if isinstance(editor, QgsMapLayerComboBox):
            new_layer = editor.currentLayer()
            if isinstance(new_layer, QgsMapLayer) and new_layer.id() != self.mLayerID:
                self.setLayer(new_layer)

    def updateBarVisiblity(self):
        model = self.model()
        from .spectralprofileplotmodel import SpectralProfilePlotModel
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
        from .spectralprofileplotmodel import SpectralProfilePlotModel
        assert isinstance(model, SpectralProfilePlotModel)
        self.setXUnit(model.xUnit().unit)
        # self.updateBarVisiblity()
        for bar in self.bandPlotItems():
            model.mPlotWidget.plotItem.addItem(bar)

    def clone(self) -> QStandardItem:
        item = RasterRendererGroup()
        item.setLayer(self.layer())
        item.setVisible(self.isVisible())
        return item

    def setXUnit(self, xUnit: str):
        assert xUnit is None or isinstance(xUnit, str)
        if xUnit is None:
            xUnit = BAND_NUMBER
        self.mXUnit = xUnit
        self.updateFromRenderer()

    def layerId(self) -> str:
        return self.mLayerID

    def layer(self) -> Optional[QgsRasterLayer]:
        """
        Returns the layer instance relating to the stored layer id.
        :return: QgsRasterLayer or None
        """

        lyr = self.project().mapLayer(self.mLayerID)

        if not isinstance(lyr, QgsRasterLayer):
            lyr = QgsProject.instance().mapLayer(self.mLayerID)

        return lyr

    def setLayer(self, layer: QgsRasterLayer):
        assert isinstance(layer, QgsRasterLayer) and layer.isValid()

        lid = layer.id()
        if lid == self.mLayerID:
            # layer already linked
            return
        self.onLayerRemoved()
        self.mSpectralProperties = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)
        self.mLayerID = layer.id()

        layer.rendererChanged.connect(self.updateFromRenderer)
        layer.willBeDeleted.connect(self.onLayerRemoved)
        layer.nameChanged.connect(self.updateLayerName)

        self.updateFromRenderer()
        self.updateLayerName()

    def onLayerRemoved(self):
        self.disconnectGroup()

    def plotWidget(self) -> Optional[PlotWidget]:
        model = self.model()
        if model:
            return model.plotWidget()
        return None

    def connectGroup(self):

        pw: PlotWidget = self.plotWidget()
        if pw:
            for bar in self.bandPlotItems():
                if bar not in pw.items():
                    pw.addItem(bar)
                    s = ""

    def disconnectGroup(self):
        pw = self.plotWidget()
        if pw:
            for bar in self.bandPlotItems():
                if bar in pw.items():
                    pw.removeItem(bar)

    def updateToRenderer(self):

        layer = self.layer()
        if not isinstance(layer, QgsRasterLayer):
            return

        renderer: QgsRasterRenderer = layer.renderer().clone()

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

        layer.setRenderer(renderer)
        layer.triggerRepaint()
        # convert to band unit

    def xValueToBand(self, pos: float) -> int:

        band = None
        if self.mXUnit == BAND_NUMBER:
            band = int(round(pos))
        elif self.mXUnit == BAND_INDEX:
            band = int(round(pos)) + 1
        else:
            wl = self.mSpectralProperties.wavelengths()
            wlu = self.mSpectralProperties.wavelengthUnits()

            if wlu:
                func = self.mUnitConverter.convertFunction(self.mXUnit, wlu[0])
                new_wlu = func(pos)
                if new_wlu is not None:
                    band = np.argmin(np.abs(np.asarray(wl) - new_wlu)) + 1
        if isinstance(band, int):
            band = max(band, 0)
            band = min(band, self.mSpectralProperties.bandCount())
        return band

    def bandToXValue(self, band: int) -> Optional[float]:

        if not isinstance(self.mSpectralProperties, QgsRasterLayerSpectralProperties):
            return None

        if self.mXUnit == BAND_NUMBER:
            return band
        elif self.mXUnit == BAND_INDEX:
            return band - 1
        else:
            wl = self.mSpectralProperties.wavelengths()
            wlu = self.mSpectralProperties.wavelengthUnits()
            if len(wlu) >= band:
                wlu = wlu[band - 1]
            else:
                wlu = wlu[0]
            if wlu:
                func = self.mUnitConverter.convertFunction(wlu, self.mXUnit)
                return func(wl[band - 1])

        return None

    def setData(self, value: Any, role: int = ...) -> None:
        super(RasterRendererGroup, self).setData(value, role)

    def plotDataItems(self) -> List[PlotDataItem]:
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
        layer = self.layer()
        if not (isinstance(layer, QgsRasterLayer)
                and layer.isValid()
                and isinstance(layer.renderer(), QgsRasterRenderer)):
            for b in self.bandPlotItems():
                b.setVisible(False)
            self.setValuesMissing(True)
            return
        else:
            self.setValuesMissing(False)

        layerName = layer.name()
        renderer = layer.renderer()
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
            elif isinstance(renderer, QgsSingleBandPseudoColorRenderer):
                bandR = renderer.band()
            elif isinstance(renderer, QgsSingleBandGrayRenderer):
                if Qgis.versionInt() >= 33800:
                    bandR = renderer.inputBand()
                else:
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

        # note the order!
        # in any case we want to evaluate setBandPosition first, although items may be hidden
        self.mBarR.setVisible(self.setBandPosition(bandR, self.mBarR, self.mItemBandR) and is_checked)
        self.mBarG.setVisible(self.setBandPosition(bandG, self.mBarG, self.mItemBandG) and is_checked)
        self.mBarB.setVisible(self.setBandPosition(bandB, self.mBarB, self.mItemBandB) and is_checked)
        self.mBarA.setVisible(self.setBandPosition(bandA, self.mBarA, self.mItemBandA) and is_checked)

        self.appendRow(self.mItemRenderer.propertyRow())
        if bandR:
            self.appendRow(self.mItemBandR.propertyRow())
        if bandG:
            self.appendRow(self.mItemBandG.propertyRow())
        if bandB:
            self.appendRow(self.mItemBandB.propertyRow())
        if bandA:
            self.appendRow(self.mItemBandA.propertyRow())

    def bandPlotItems(self) -> List[InfiniteLine]:
        return [self.mBarR, self.mBarG, self.mBarB, self.mBarA]


class ProfileVisualizationGroup(PropertyItemGroup):
    """
    Controls the visualization for a set of profiles
    """
    MIME_TYPE = 'application/SpectralProfilePlotVisualization'

    class ExpressionContextGenerator(QgsExpressionContextGenerator):

        def __init__(self, grp, *args, **kwds):
            super().__init__(*args, **kwds)
            self.grp: ProfileVisualizationGroup = grp

        def createExpressionContext(self):
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.globalScope())
            lyr = self.grp.layer()
            context.appendScope(QgsExpressionContextUtils.projectScope(self.grp.project()))

            if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
                context.appendScope(QgsExpressionContextUtils.layerScope(lyr))

            # myscope = QgsExpressionContextScope('myscope')
            # myscope.setVariable('MYVAR', 42)
            # context.appendScope(myscope)
            return context

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mExpressionContextGenerator = self.ExpressionContextGenerator(self)

        # foreground and background colors that are used for preview icons
        self.mPlotWidgetStyle: PlotWidgetStyle = PlotWidgetStyle.default()

        self.mZValue = 2
        self.setName('Visualization')
        self.setIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mFirstColumnSpanned = False

        self.mProject: QgsProject = QgsProject.instance()

        self.mPlotDataItems: List[PlotDataItem] = []

        self.mPField = SpectralProfileLayerFieldItem('Field')

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

        self.mPColor: ProfileColorPropertyItem = ProfileColorPropertyItem('Color')
        self.mPColor.setDefinition(QgsPropertyDefinition(
            'Color', 'Color of spectral profile', QgsPropertyDefinition.StandardPropertyTemplate.ColorWithAlpha))
        self.mPColor.setProperty(QgsProperty.fromValue('@symbol_color'))

        # self.mPColor.signals().dataChanged.connect(lambda : self.setPlotStyle(self.generatePlotStyle()))
        for pItem in [self.mPField, self.mPLabel, self.mPFilter, self.mPColor, self.mPStyle]:
            self.appendRow(pItem.propertyRow())

        self.setUserTristate(False)
        self.setCheckable(True)
        self.setCheckState(Qt.Checked)
        self.setDropEnabled(False)
        self.setDragEnabled(False)

    def fromMap(self, data: dict):
        self.setName(data.get('name', 'Visualization'))
        self.setLayerField(data.get('field', None))
        s = ""

    def asMap(self) -> dict:

        layer_id = self.layerId()
        layer_src = layer_name = layer_provider = None
        if layer_id:
            lyr = self.project().mapLayer(layer_id)
            if isinstance(lyr, QgsVectorLayer):
                layer_src = lyr.source()
                layer_name = lyr.name()
                layer_provider = lyr.providerType()

        color_expression = self.colorExpression()
        plot_style = self.plotStyle()
        settings = {
            'name': self.name(),
            'field_name': self.fieldName(),
            'layer_id': layer_id,
            'layer_source': layer_src,
            'layer_name': layer_name,
            'layer_provider': layer_provider,
            'label_expression': self.labelExpression(),
            'filter_expression': self.filterExpression(),
            'color_expression': color_expression,
            'tooltip_expression': self.labelExpression(),
            'plot_style': plot_style.map()
        }
        return settings

    def setColorExpression(self, expression: str):

        self.mPColor.setColorExpression(expression)

    def colorExpression(self) -> str:
        """
        Returns the color as QGIS expression string
        :return: str
        """
        return self.mPColor.colorExpression()

    def initWithPlotModel(self, model):
        self.setSpeclib(model.speclib())

    def propertyRow(self) -> List[QStandardItem]:
        return [self]

    def expressionContextGenerator(self) -> QgsExpressionContextGenerator:
        return self.mExpressionContextGenerator

    def createExpressionContextScope(self) -> QgsExpressionContextScope:

        scope = QgsExpressionContextScope('profile_visualization')
        # todo: add scope variables
        scope.setVariable('vis_name', self.name(), isStatic=True)
        return scope

    def clone(self) -> 'ProfileVisualizationGroup':
        v = ProfileVisualizationGroup()
        v.fromMap(self.asMap())
        v.setEditable(self.isEditable())
        v.setVisible(self.isVisible())
        v.setCheckable(self.isCheckable())

        return v

    def setPlotWidgetStyle(self, style: PlotWidgetStyle):
        """

        :param style:
        :return:
        """
        assert isinstance(style, PlotWidgetStyle)
        if style != self.mPlotWidgetStyle:
            self.mPlotWidgetStyle = style
            self.setColor(style.foregroundColor)
            self.emitDataChanged()

    def setColor(self, color: Union[str, QColor]):
        self.mPColor.setColor(color)

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
        if speclib.geometryType() in [QgsWkbTypes.GeometryType.PointGeometry,
                                      QgsWkbTypes.GeometryType.LineGeometry,
                                      QgsWkbTypes.GeometryType.PolygonGeometry]:
            self.mPColor.setToSymbolColor()
        self.mSpeclib = speclib
        self.update()

    def update(self):
        is_complete = self.isComplete()
        self.setValuesMissing(not is_complete)
        self.mPField.label().setIcon(QIcon() if is_complete else QIcon(WARNING_ICON))

    def isComplete(self) -> bool:

        has_layer = isinstance(self.layerId(), str)
        has_field = isinstance(self.fieldName(), str)

        return has_layer and has_field

    def setFilterExpression(self, expression):
        if isinstance(expression, QgsExpression):
            expression = expression.expression()
        assert isinstance(expression, str)
        p = self.mPFilter.property()
        p.setExpressionString(expression)
        self.mPFilter.setProperty(p)

    def filterExpression(self) -> str:
        return self.filterProperty().expressionString()

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

    def labelExpression(self) -> str:
        return self.mPLabel.property().expressionString()

    def labelProperty(self) -> QgsProperty:
        """
        Returns the expression that returns the name for a single profile
        :return: str
        """
        return self.mPLabel.property()

    def setLayerField(self, layer: Union[QgsVectorLayer, str], field: Union[QgsField, str]):
        self.mPField.setLayerField(layer, field)

    def fieldName(self) -> str:
        return self.mPField.mFieldName

    def layerId(self) -> str:
        return self.mPField.mLayerID

    def layer(self) -> QgsMapLayer:
        """Returns the layer instance realting to the layerId.
        Requires that the layer is stored in the provide QgsProject instance.
        """
        return self.project().mapLayer(self.layerId())

    def setPlotStyle(self, style: PlotStyle):
        # update style
        self.mPStyle.setPlotStyle(style)
        # trigger update of group icon
        self.emitDataChanged()

    def populateContextMenu(self, menu: QMenu):

        for item in [self.mPField, self.mPColor]:
            item.populateContextMenu(menu)

    def plotStyle(self, add_symbol_scope: bool = False) -> PlotStyle:
        """
        Creates a PlotStyle that uses the color
        as line and marker color. In case of a color expression, the plot foreground color will be used.
        Antialias flag is taken from general settings.
        :return: PlotStyle
        """
        style = self.mPStyle.plotStyle().clone()

        expr = QgsExpression(self.colorExpression())
        context = self.expressionContextGenerator().createExpressionContext()

        lyr = self.layer()

        if add_symbol_scope and isinstance(lyr, QgsVectorLayer) and isinstance(lyr.renderer(), QgsFeatureRenderer):

            request = QgsFeatureRequest()
            filter = self.filterExpression()
            if filter != '':
                request.setFilterExpression(filter)

            # get color from 1st feature
            for feature in lyr.getFeatures(request):
                context.setFeature(feature)
                context.appendScope(featureSymbolScope(feature, renderer=lyr.renderer(), context=context))
                break

        from .spectralprofileplotmodel import SpectralProfilePlotModel
        model = self.model()
        if isinstance(model, SpectralProfilePlotModel):
            gsettings: GeneralSettingsGroup = model.generalSettings()
            bc = gsettings.backgroundColor()
            fc = gsettings.foregroundColor()
            al = gsettings.antialias()
        else:
            bc = QColor(self.mPlotWidgetStyle.backgroundColor)
            fc = QColor(self.mPlotWidgetStyle.foregroundColor)
            al = False

        color = QColor(expr.evaluate(context))
        if not color.isValid():
            color = fc
        style.setBackgroundColor(bc)
        style.setLineColor(color)
        style.setMarkerColor(color)
        style.setAntialias(al)

        return style

    def generateTooltip(self, context: QgsExpressionContext, label: str = None) -> str:
        tooltip = '<html><body><table>'
        if label is None:
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

    def generateLabel(self, context: QgsExpressionContext):
        defaultLabel = ''
        if context.feature().isValid():
            defaultLabel = f'{context.feature().id()}, {self.fieldName()}'
        label, success = self.labelProperty().valueAsString(context, defaultString=defaultLabel)
        if success:
            return label
        else:
            return defaultLabel

    def plotDataItems(self) -> List[PlotDataItem]:
        """
        Returns a list with all pyqtgraph plot data items
        """
        return self.mPlotDataItems[:]
