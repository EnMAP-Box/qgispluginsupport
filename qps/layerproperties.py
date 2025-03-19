# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    layerproperties.py
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import pathlib
import re
import sys
import warnings
from typing import Any, Dict, List, Optional, Union

from qgis.PyQt.QtCore import QTextStream, QByteArray
from qgis.PyQt.QtCore import pyqtSignal, QMimeData, QModelIndex, QObject, QTimer, QVariant
from qgis.PyQt.QtGui import QCloseEvent, QIcon
from qgis.PyQt.QtWidgets import QAction, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, \
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QSizePolicy, QSpacerItem, \
    QSpinBox, QTableView, QToolButton, QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import Qgis, QgsAction, QgsApplication, QgsCategorizedSymbolRenderer, QgsContrastEnhancement, \
    QgsDataProvider, QgsDistanceArea, QgsEditFormConfig, QgsEditorWidgetSetup, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextGenerator, QgsExpressionContextScope, QgsExpressionContextUtils, QgsFeature, QgsFeatureRenderer, \
    QgsFeatureRequest, QgsField, QgsFieldModel, QgsFieldProxyModel, QgsFields, QgsHillshadeRenderer, QgsLayerTreeGroup, \
    QgsLayerTreeLayer, QgsMapLayer, QgsMapLayerStyle, QgsMultiBandColorRenderer, QgsPalettedRasterRenderer, QgsProject, \
    QgsRasterBandStats, QgsRasterDataProvider, QgsRasterLayer, QgsRasterRenderer, QgsReadWriteContext, QgsRectangle, \
    QgsScopedProxyProgressTask, QgsSettings, QgsSingleBandColorDataRenderer, QgsSingleBandGrayRenderer, \
    QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer, QgsVectorDataProvider, QgsVectorLayer, QgsWkbTypes

from .qgisenums import QGIS_RASTERBANDSTATISTIC
from .speclib import EDITOR_WIDGET_REGISTRY_KEY

try:
    from qgis.gui import QgsFieldCalculator

    FIELD_CALCULATOR = True
except ImportError:
    FIELD_CALCULATOR = False

from qgis.gui import QgisInterface, QgsMapCanvas

from qgis.PyQt.QtCore import Qt
from qgis.gui import \
    QgsActionMenu, \
    QgsAttributeEditorContext, \
    QgsAttributeForm, \
    QgsAttributeTableFilterModel, \
    QgsAttributeTableModel, \
    QgsDockWidget, \
    QgsDualView, \
    QgsExpressionSelectionDialog, \
    QgsMapLayerConfigWidgetFactory, \
    QgsMessageBar, \
    QgsSublayersDialog, \
    QgsFilterLineEdit, \
    QgsExpressionBuilderDialog
# auto-generated file.
from qgis.gui import QgsOrganizeTableColumnsDialog
from qgis.gui import QgsRasterLayerProperties, QgsGui, QgsVectorLayerProperties
from . import DIR_UI_FILES
from .classification.classificationscheme import ClassificationScheme
from .models import OptionListModel, Option
from .speclib.core import can_store_spectral_profiles
from .utils import loadUi, defaultBands, iconForFieldType, qgsFields, copyEditorWidgetSetup
from .vectorlayertools import VectorLayerTools

RENDER_CLASSES = {}
RENDER_CLASSES['rasterrenderer'] = {
    'singlebandpseudocolor': QgsSingleBandPseudoColorRenderer,
    'singlebandgray': QgsSingleBandGrayRenderer,
    'singlebandcolordata': QgsSingleBandColorDataRenderer,
    'paletted': QgsPalettedRasterRenderer,
    'multibandcolor': QgsMultiBandColorRenderer,
    'hillshade': QgsHillshadeRenderer
}
RENDER_CLASSES['renderer-v2'] = {
    'categorizedSymbol': QgsCategorizedSymbolRenderer,
    'singleSymbol': QgsSingleSymbolRenderer
}
DUMMY_RASTERINTERFACE = QgsSingleBandGrayRenderer(None, 0)

MDF_QGIS_LAYER_STYLE = 'application/qgis.style'
MDF_TEXT_PLAIN = 'text/plain'


class CheckableQgsFieldModel(QgsFieldModel):
    """
    A QgsFieldModel that allows to select fields by checkboxes
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mChecked: Dict[int, bool] = dict()
        self.mDisabled: Dict[int, bool] = dict()

    def setDisabledFields(self, disabled: QgsFields):

        if isinstance(disabled, QgsFields):
            disabled = disabled.names()

        for r in range(self.rowCount()):
            field = self.fields().at(r)
            self.mDisabled[r] = field.name() in disabled or r in disabled

    def checkAll(self):
        for r in range(self.rowCount()):
            idx = self.createIndex(r, 0)
            self.setData(idx, Qt.Checked, Qt.CheckStateRole)

    def uncheckAll(self):
        for r in range(self.rowCount()):
            idx = self.createIndex(r, 0)
            self.setData(idx, Qt.Unchecked, Qt.CheckStateRole)

    def checkedFields(self) -> QgsFields:

        fields = QgsFields()
        for r in range(self.rowCount()):
            if self.mChecked.get(r, False) and not self.mDisabled.get(r, False):
                fields.append(self.fields().at(r))
        return fields

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:

        # flags = super().flags(index)
        if self.mDisabled.get(index.row(), False):
            flags = Qt.NoItemFlags
        else:
            flags = Qt.ItemIsUserCheckable | Qt.ItemIsEnabled

        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int) -> Any:

        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section == 0:
                return 'Field Name'
        return super(CheckableQgsFieldModel, self).headerData(section, orientation, role)

    def data(self, index: QModelIndex, role):
        if not index.isValid():
            return None

        row = index.row()
        field: QgsField = self.fields().at(row)

        if role == Qt.CheckStateRole:
            b = self.mChecked.get(row, False)
            return Qt.Checked if b else Qt.Unchecked
        if role == Qt.DecorationRole:
            return iconForFieldType(field)

        return super().data(index, role)

    def setData(self, index: QModelIndex, value: Any, role) -> bool:
        if not index.isValid():
            return False

        row = index.row()

        changed = None

        if role == Qt.CheckStateRole:
            self.mChecked[row] = value == Qt.Checked
            changed = True

        if changed is None:
            return super().setData(index, value, role)
        elif changed:
            self.dataChanged.emit(index, index, [role])
        return changed


class CopyAttributesDialog(QDialog):

    @staticmethod
    def copyLayerFields(layer: QgsVectorLayer,
                        fields: Union[QgsFields, QgsVectorLayer, QgsFeature],
                        parent=None) -> bool:

        d = CopyAttributesDialog(layer, fields)
        if d.exec_() == QDialog.Accepted:
            was_editable = layer.isEditable()
            layer.startEditing()
            layer.beginEditCommand('Add attributes')
            for f in d.selectedFields():
                layer.addAttribute(f)
            copyEditorWidgetSetup(layer, d.selectedFields())
            layer.endEditCommand()
            layer.commitChanges(stopEditing=not was_editable)
            return True
        return False

    def __init__(self,
                 layer: QgsVectorLayer,
                 fields: Union[QgsFields, QgsVectorLayer, QgsFeature],
                 parent=None, **kwds):

        super().__init__(parent, **kwds)
        self.setWindowTitle('Copy attributes')
        self.setWindowIcon(QIcon(r':/images/themes/default/mActionNewAttribute.svg'))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        fields = qgsFields(fields)
        assert isinstance(fields, QgsFields)

        self.mLabel = QLabel('Select attributes to copy')
        self.mTableView = QTableView()

        self.mFieldModel = CheckableQgsFieldModel()
        self.mFieldModel.setFields(fields)
        self.mFieldModel.setDisabledFields(layer.fields())
        self.mFieldModel.dataChanged.connect(self.onFieldSelectionChanged)
        self.mTableView.setModel(self.mFieldModel)
        self.mTableView.horizontalHeader()

        self.btnCheckAll = QToolButton()
        self.btnCheckAll.setToolTip('Check All')
        self.btnCheckAll.setIcon(QIcon(':/images/themes/default/mActionSelectAllTree.svg'))
        self.btnCheckAll.clicked.connect(self.mFieldModel.checkAll)

        self.btnUncheckAll = QToolButton()
        self.btnUncheckAll.setToolTip('Uncheck All')
        self.btnUncheckAll.setIcon(QIcon(':/images/themes/default/mActionDeselectAllTree.svg'))
        self.btnUncheckAll.clicked.connect(self.mFieldModel.uncheckAll)

        layout = QVBoxLayout()
        hl = QHBoxLayout()
        hl.addWidget(self.mLabel)
        hl.addWidget(self.btnCheckAll)
        hl.addWidget(self.btnUncheckAll)
        hl.addSpacerItem(QSpacerItem(0, 0, hPolicy=QSizePolicy.Expanding))
        layout.addLayout(hl)
        layout.addWidget(self.mTableView)

        self.mButtonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.mButtonBox.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.mButtonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        layout.addWidget(self.mButtonBox)

        self.setLayout(layout)

        self.onFieldSelectionChanged()

    def selectedFields(self) -> QgsFields:
        return self.mFieldModel.checkedFields()

    def onFieldSelectionChanged(self):
        fields = self.mFieldModel.checkedFields()
        b = fields.count() > 0
        self.btnUncheckAll.setEnabled(b)
        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(b)


class AddAttributeDialog(QDialog):
    """
    A dialog to set up a new QgsField.
    """

    def __init__(self, layer, parent=None, case_sensitive: bool = False):
        assert isinstance(layer, QgsVectorLayer)
        super(AddAttributeDialog, self).__init__(parent)

        self.setWindowTitle('Add attribute')
        self.setWindowIcon(QIcon(r':/images/themes/default/mActionNewAttribute.svg'))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.mCaseSensitive = case_sensitive
        self.setWindowTitle('Add Field')
        layout = QGridLayout()

        self.tbName = QLineEdit('Name')
        self.tbName.setPlaceholderText('Name')
        self.tbName.textChanged.connect(self.validate)

        layout.addWidget(QLabel('Name'), 0, 0)
        layout.addWidget(self.tbName, 0, 1)

        self.tbComment = QLineEdit()
        self.tbComment.setPlaceholderText('Comment')
        layout.addWidget(QLabel('Comment'), 1, 0)
        layout.addWidget(self.tbComment, 1, 1)

        self.cbType = QComboBox()
        self.typeModel = OptionListModel()

        nativeTypes: List[QgsVectorDataProvider.NativeType] = self.mLayer.dataProvider().nativeTypes()
        for ntype in nativeTypes:
            assert isinstance(ntype, QgsVectorDataProvider.NativeType)

            o = Option(ntype,
                       name=ntype.mTypeName,
                       toolTip=ntype.mTypeDesc,
                       icon=iconForFieldType(ntype))

            self.typeModel.addOption(o)

        self.cbType.setModel(self.typeModel)
        self.cbType.currentIndexChanged.connect(self.onTypeChanged)
        layout.addWidget(QLabel('Type'), 2, 0)
        layout.addWidget(self.cbType, 2, 1)

        self.sbLength = QSpinBox()
        self.sbLength.setRange(0, 99)
        self.sbLength.valueChanged.connect(lambda: self.setPrecisionMinMax())
        self.sbLength.valueChanged.connect(self.onTypeChanged)

        self.lengthLabel = QLabel('Length')
        layout.addWidget(self.lengthLabel, 3, 0)
        layout.addWidget(self.sbLength, 3, 1)

        self.sbPrecision = QSpinBox()
        self.sbPrecision.setRange(0, 99)
        self.precisionLabel = QLabel('Precision')
        layout.addWidget(self.precisionLabel, 4, 0)
        layout.addWidget(self.sbPrecision, 4, 1)

        self.cbSpectralProfile = QCheckBox('Use to store Spectral Profiles')
        self.cbSpectralProfile.setToolTip('Activate to store Spectral Profiles in new field.<br>'
                                          'Requires that the field is either of type String/Text, ByteArray or JSON<br>'
                                          'and has not length limitation (length = 0 or -1)')
        layout.addWidget(self.cbSpectralProfile, 5, 0, 1, 2)

        self.tbValidationInfo = QLabel()
        self.tbValidationInfo.setStyleSheet("QLabel { color : red}")
        layout.addWidget(self.tbValidationInfo, 6, 0, 1, 2)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttons.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        layout.addWidget(self.buttons, 7, 1)
        self.setLayout(layout)
        self.mLayer = layer
        self.onTypeChanged()

        self.validate()

    def setCaseSensitive(self, is_sensitive: bool):
        assert isinstance(is_sensitive, bool)
        self.mCaseSensitive = is_sensitive
        self.validate()

    def setName(self, name: str):
        """
        Sets the field name
        """
        self.tbName.setText(name)

    def name(self) -> str:
        """
        Returns the field name
        :return: str
        """
        return self.tbName.text()

    def accept(self):
        isValid, msg = self.validate()
        if isValid:
            super(AddAttributeDialog, self).accept()
        else:
            QMessageBox.warning(self, "Add Field", msg)

    def privateField(self) -> QgsField:
        ntype = self.currentNativeType()

        fname = self.tbName.text()
        fcomment = self.tbComment.text()
        # ftype = QVariant(ntype.mType).type()

        return QgsField(name=fname,
                        type=ntype.mType,
                        typeName=ntype.mTypeName,
                        len=self.sbLength.value(),
                        prec=self.sbPrecision.value(),
                        comment=fcomment)

    def field(self):
        """
        Returns the new QgsField
        :return:
        """
        field = self.privateField()
        if can_store_spectral_profiles(
                field) and self.cbSpectralProfile.isEnabled() and self.cbSpectralProfile.isChecked():
            # field.setComment('Spectral Profile Field')
            setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
            field.setEditorWidgetSetup(setup)
        return field

    def currentNativeType(self) -> QgsVectorDataProvider.NativeType:
        return self.cbType.currentData().value()

    def onTypeChanged(self, *args):
        ntype = self.currentNativeType()

        vMin, vMax = ntype.mMinLen, ntype.mMaxLen
        assert isinstance(ntype, QgsVectorDataProvider.NativeType)

        isVisible = vMin < vMax
        self.sbLength.setVisible(isVisible)
        self.lengthLabel.setVisible(isVisible)
        self.setSpinBoxMinMax(self.sbLength, vMin, vMax)
        self.setPrecisionMinMax()

        prototype = self.privateField()
        self.cbSpectralProfile.setEnabled(can_store_spectral_profiles(prototype))

    def setPrecisionMinMax(self):
        ntype = self.currentNativeType()
        vMin, vMax = ntype.mMinPrec, ntype.mMaxPrec
        isVisible = vMin < vMax
        self.sbPrecision.setVisible(isVisible)
        self.precisionLabel.setVisible(isVisible)

        vMax = max(ntype.mMinPrec, min(ntype.mMaxPrec, self.sbLength.value()))
        self.setSpinBoxMinMax(self.sbPrecision, vMin, vMax)

    def setSpinBoxMinMax(self, sb, vMin, vMax):
        assert isinstance(sb, QSpinBox)
        value = sb.value()
        sb.setRange(vMin, vMax)

        if value > vMax:
            sb.setValue(vMax)
        elif value < vMin:
            sb.setValue(vMin)

    def validate(self, *args) -> Union[bool, str]:
        """
        Validates the inputs
        :return: (bool, str with error message(s))
        """
        errors = []
        name = self.tbName.text()
        existing_names = self.mLayer.fields().names()
        if self.mCaseSensitive and name in existing_names or \
                not self.mCaseSensitive and name.lower() in [n.lower() for n in existing_names]:
            errors.append('Field name "{}" already exists.'.format(name))
        elif name == '':
            errors.append('Missing field name')
        elif name == 'shape':
            errors.append('Field name "{}" already reserved.'.format(name))
        errors = '\n'.join(errors)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(len(errors) == 0)
        self.tbValidationInfo.setText(errors)

        return len(errors) == 0, errors


class RemoveAttributeDialog(QDialog):

    def __init__(self, layer: QgsVectorLayer, *args, fieldNames=None, **kwds):
        super().__init__(*args, **kwds)
        assert isinstance(layer, QgsVectorLayer)
        self.mLayer = layer
        self.setWindowTitle('Remove Fields')
        self.setWindowIcon(QIcon(r':/images/themes/default/mActionDeleteAttribute.svg'))
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.fieldModel = CheckableQgsFieldModel()
        self.fieldModel.setLayer(self.mLayer)
        self.fieldModel.setAllowEmptyFieldName(False)
        self.fieldModel.setAllowExpression(False)

        self.tvFieldNames = QTableView()
        self.tvFieldNames.setModel(self.fieldModel)

        self.btnBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        self.btnBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.btnBox.button(QDialogButtonBox.Ok).clicked.connect(self.accept)

        self.label = QLabel('Select Fields to remove')

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.tvFieldNames)
        layout.addWidget(self.btnBox)
        self.setLayout(layout)

    def fields(self) -> List[QgsField]:
        """
        Returns the selected QgsFields
        """
        return self.fieldModel.checkedFields()

    def fieldIndices(self) -> List[int]:
        return [self.mLayer.fields().lookupField(f.name()) for f in self.fields()]

    def fieldNames(self) -> List[str]:
        return [f.name() for f in self.fields()]


def openRasterLayerSilent(uri, name, provider) -> QgsRasterLayer:
    """
    Opens a QgsRasterLayer without asking for its CRS in case it is undefined.
    :param uri: path
    :param name: name of layer
    :param provider: provider string
    :return: QgsRasterLayer
    """
    key = '/Projections/defaultBehavior'
    v = QgsSettings().value(key)
    isPrompt = v == 'prompt'

    if isPrompt:
        # do not ask!
        QgsSettings().setValue(key, 'useProject')

    loptions = QgsRasterLayer.LayerOptions(loadDefaultStyle=False)
    lyr = QgsRasterLayer(uri, name, provider, options=loptions)

    if isPrompt:
        QgsSettings().setValue(key, v)
    return lyr


def rendererFromXml(xml):
    """
    Reads a string `text` and returns the first QgsRasterRenderer or QgsFeatureRenderer (if defined).
    :param xml: QMimeData | QDomDocument
    :return:
    """

    if isinstance(xml, QMimeData):
        for format in [MDF_QGIS_LAYER_STYLE, MDF_TEXT_PLAIN]:
            # for format in ['application/qgis.style', 'text/plain']:
            if format in xml.formats():
                dom = QDomDocument()
                dom.setContent(xml.data(format))
                return rendererFromXml(dom)
        return None

    elif isinstance(xml, str):
        dom = QDomDocument()
        dom.setContent(xml)
        return rendererFromXml(dom)

    assert isinstance(xml, QDomDocument)
    root = xml.documentElement()
    for baseClass, renderClasses in RENDER_CLASSES.items():
        elements = root.elementsByTagName(baseClass)
        if elements.count() > 0:
            elem = elements.item(0).toElement()
            typeName = elem.attributes().namedItem('type').nodeValue()
            if typeName in renderClasses.keys():
                rClass = renderClasses[typeName]
                if baseClass == 'rasterrenderer':

                    return rClass.create(elem, DUMMY_RASTERINTERFACE)
                elif baseClass == 'renderer-v2':
                    context = QgsReadWriteContext()
                    return rClass.load(elem, context)
            else:
                # print(typeName)
                s = ""
    return None


def defaultRasterRenderer(layer: QgsRasterLayer,
                          bandIndices: List[int] = None,
                          sampleSize: int = 256,
                          readQml: bool = True) -> Optional[QgsRasterRenderer]:
    """
    Returns a good default Raster Renderer.
    See https://bitbucket.org/hu-geomatics/enmap-box/issues/166/default-raster-visualization

    :param layer:
    :type layer:
    :param bandIndices:
    :type bandIndices:
    :param sampleSize:
    :type sampleSize:
    :param readQml:
    :type readQml:
    :return:
    :rtype:
    """

    assert isinstance(sampleSize, int) and sampleSize > 0
    renderer = None

    if not isinstance(layer, QgsRasterLayer):
        return None

    defaultRenderer = layer.renderer()

    nb = layer.bandCount()

    # band names are defined explicitly
    if isinstance(bandIndices, list):
        bandIndices = [b for b in bandIndices if 0 <= b < nb]
        n = len(bandIndices)
        if n == 0:
            bandIndices = None
        if n >= 3:
            bandIndices = bandIndices[0:3]
        elif n < 3:
            bandIndices = bandIndices[0:1]

    if not isinstance(bandIndices, list):

        # check for *.qml file with default styling information
        if readQml:
            qmlUri = pathlib.Path(layer.styleURI())
            is_file = False
            try:
                is_file = qmlUri.is_file()
            except OSError:
                is_file = False

            if is_file and re.search(r'\.(qml)$', qmlUri.name):
                msg, success = layer.loadDefaultStyle()
                if success:
                    r = layer.renderer().clone()
                    r.setInput(layer.dataProvider())
                    return r
                else:
                    print(msg, file=sys.stderr)

        if nb >= 3:
            if isinstance(defaultRenderer, QgsMultiBandColorRenderer):
                bandIndices = [b - 1 for b in defaultBands(layer)]
            else:
                bandIndices = [2, 1, 0]
        else:
            bandIndices = [0]

    assert isinstance(bandIndices, list)

    # get band stats
    dp: QgsRasterDataProvider = layer.dataProvider()
    assert isinstance(dp, QgsRasterDataProvider)

    stats = QGIS_RASTERBANDSTATISTIC.Min | QGIS_RASTERBANDSTATISTIC.Max

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=DeprecationWarning)
        bandStats = [dp.bandStatistics(b + 1, stats=stats, sampleSize=sampleSize) for b in bandIndices]

    # classification ? -> QgsPalettedRasterRenderer
    classes = ClassificationScheme.fromMapLayer(layer)
    if isinstance(classes, ClassificationScheme):
        r = classes.rasterRenderer(band=bandIndices[0] + 1)
        r.setInput(layer.dataProvider())
        return r

    # single-band / two bands -> QgsSingleBandGrayRenderer
    if len(bandStats) < 3:
        b = bandIndices[0] + 1
        stats = bandStats[0]
        assert isinstance(stats, QgsRasterBandStats)
        dt = dp.dataType(b)
        ce = QgsContrastEnhancement(dt)

        assert isinstance(ce, QgsContrastEnhancement)
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)

        if dt == Qgis.Byte:
            if stats.minimumValue == 0 and stats.maximumValue == 1:
                # handle mask, stretch over larger range
                ce.setMinimumValue(stats.minimumValue)
                ce.setMaximumValue(stats.maximumValue)
            else:
                ce.setMinimumValue(0)
                ce.setMaximumValue(255)
        else:
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            ce.setMinimumValue(vmin)
            ce.setMaximumValue(vmax)

        r = QgsSingleBandGrayRenderer(layer.dataProvider(), b)
        r.setContrastEnhancement(ce)
        return r

    # 3 or more bands -> RGB
    if len(bandStats) >= 3:
        bands = [b + 1 for b in bandIndices[0:3]]
        contrastEnhancements = [QgsContrastEnhancement(dp.dataType(b)) for b in bands]
        ceR, ceG, ceB = contrastEnhancements

        for i, b in enumerate(bands):
            dt = dp.dataType(b)
            ce = contrastEnhancements[i]

            assert isinstance(ce, QgsContrastEnhancement)
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum, True)
            vmin, vmax = layer.dataProvider().cumulativeCut(b, 0.02, 0.98, sampleSize=sampleSize)
            if dt == Qgis.Byte:
                # standard RGB photo?
                if False and layer.bandCount() == 3:
                    ce.setMinimumValue(0)
                    ce.setMaximumValue(255)
                else:
                    ce.setMinimumValue(vmin)
                    ce.setMaximumValue(vmax)
            else:
                ce.setMinimumValue(vmin)
                ce.setMaximumValue(vmax)
        R, G, B = bands
        r = QgsMultiBandColorRenderer(layer.dataProvider(), R, G, B, None, None, None)
        r.setRedContrastEnhancement(ceR)
        r.setGreenContrastEnhancement(ceG)
        r.setBlueContrastEnhancement(ceB)
        r.setRedBand(R)
        r.setGreenBand(G)
        r.setBlueBand(B)
        return r
    if nb >= 3:
        pass

    return defaultRenderer


def rendererToXml(layerOrRenderer, geomType: QgsWkbTypes = None):
    """
    Returns a renderer XML representation
    :param layerOrRenderer: QgsRasterRender | QgsFeatureRenderer
    :return: QDomDocument
    """
    doc = QDomDocument()
    err = ''
    if isinstance(layerOrRenderer, QgsRasterLayer):
        return rendererToXml(layerOrRenderer.renderer())
    elif isinstance(layerOrRenderer, QgsVectorLayer):
        geomType = layerOrRenderer.geometryType()
        return rendererToXml(layerOrRenderer.renderer(), geomType=geomType)
    elif isinstance(layerOrRenderer, QgsRasterRenderer):
        # create a dummy raster layer
        root = doc.createElement('renderer')
        layerOrRenderer.writeXml(doc, root)
        doc.appendChild(root)

    elif isinstance(layerOrRenderer, QgsFeatureRenderer) and geomType is not None:
        # todo: distinguish vector type from requested renderer
        typeName = QgsWkbTypes.geometryDisplayString(geomType)
        lyr = QgsVectorLayer('{}?crs=epsg:4326&field=id:integer'.format(typeName), 'dummy', 'memory')
        lyr.setRenderer(layerOrRenderer.clone())
        err = lyr.exportNamedStyle(doc)
        lyr = None
    else:
        raise NotImplementedError()

    return doc


def pasteStyleToClipboard(layer: QgsMapLayer,
                          categories: QgsMapLayer.StyleCategory = QgsMapLayer.StyleCategory.Symbology | QgsMapLayer.StyleCategory.Rendering):
    doc = QDomDocument()
    err = layer.exportNamedStyle(doc, categories=categories)
    if err == '':
        ba = QByteArray()
        stream = QTextStream(ba)
        stream.setCodec('utf-8')
        doc.documentElement().save(stream, 0)
        md = QMimeData()
        md.setData('application/qgis.style', ba)
        md.setText(str(ba, 'utf-8'))
        QgsApplication.instance().clipboard().setMimeData(md)
    if err != '':
        print(err, file=sys.stderr)


def pasteStyleFromClipboard(layer: QgsMapLayer,
                            categories: QgsMapLayer.StyleCategory = QgsMapLayer.StyleCategory.AllStyleCategories):
    md = QgsApplication.instance().clipboard().mimeData()
    if 'application/qgis.style' in md.formats():
        xml = md.data('application/qgis.style')
        doc = QDomDocument()
        doc.setContent(xml)

        success, err = layer.importNamedStyle(doc, categories=categories)
        if success:
            layer.triggerRepaint()
        else:
            print(err, file=sys.stderr)


def equal_styles(lyr1: QgsMapLayer, lyr2: QgsMapLayer) -> bool:
    if lyr1 == lyr2:
        return True
    if isinstance(lyr1, QgsRasterLayer) and not isinstance(lyr2, QgsRasterLayer):
        return False
    if isinstance(lyr2, QgsVectorLayer) and not isinstance(lyr2, QgsVectorLayer):
        return False

    style1 = QgsMapLayerStyle()
    style2 = QgsMapLayerStyle()
    style1.readFromLayer(lyr1)
    style2.readFromLayer(lyr2)

    return style1.xmlData() == style2.xmlData()


def subLayerDefinitions(mapLayer: QgsMapLayer) -> List[QgsSublayersDialog.LayerDefinition]:
    """

    :param mapLayer:QgsMapLayer
    :return: list of sublayer definitions
    """
    warnings.warn(DeprecationWarning('will be removed'), stacklevel=2)
    definitions = []
    dp: QgsDataProvider = mapLayer.dataProvider()
    subLayers = dp.subLayers()

    if len(subLayers) == 0:
        return []

    for i, sub in enumerate(subLayers):
        ldef = QgsSublayersDialog.LayerDefinition()
        assert isinstance(ldef, QgsSublayersDialog.LayerDefinition)
        elements = sub.split(dp.sublayerSeparator())

        if dp.name() == 'ogr':
            # <layer_index>:<name>:<feature_count>:<geom_type>
            if len(elements) < 4:
                continue

            ldef.layerId = int(elements[0])
            ldef.layerName = elements[1]
            ldef.count = int(elements[2])
            ldef.type = elements[3]

            definitions.append(ldef)

        elif dp.name() == 'gdal':
            ldef.layerId = i

            # remove driver name and file name
            name = elements[0]
            name = name.replace(mapLayer.source(), '')
            name = re.sub('^(netcdf|hdf):', '', name, flags=re.I)
            name = re.sub('^[:"]+', '', name)
            name = re.sub('[:"]+$', '', name)
            ldef.layerName = name

            definitions.append(ldef)

        else:
            s = ""

    return definitions


def subLayers(mapLayer: QgsMapLayer, subLayers: list = None) -> List[QgsMapLayer]:
    """
    Returns a list of QgsMapLayer instances extracted from the input QgsMapLayer.
    Returns the "parent" QgsMapLayer in case no sublayers can be extracted
    :param mapLayer: QgsMapLayer
    :return: [list-of-QgsMapLayers]
    """
    warnings.warn(DeprecationWarning('Use subdatasets.subLayers'), stacklevel=2)
    from .subdatasets import subLayers
    return subLayers(mapLayer)


def showLayerPropertiesDialog(layer: QgsMapLayer,
                              canvas: QgsMapCanvas = None,
                              parent: QObject = None,
                              modal: bool = True,
                              page: str = None,
                              messageBar: QgsMessageBar = None,
                              useQGISDialog: bool = False) -> Union[QDialog.DialogCode, QDialog]:
    """
    Opens a dialog to adjust map layer settings.
    :param layer: QgsMapLayer of type QgsVectorLayer or QgsRasterLayer
    :param canvas: QgsMapCanvas
    :param parent:
    :param modal: bool
    :return: QDialog.DialogCode
    """
    dialog = None
    result = QDialog.Rejected
    from .utils import qgisAppQgisInterface
    iface = qgisAppQgisInterface()
    qgisUsed = False
    if useQGISDialog and isinstance(iface, QgisInterface):
        # try to use the QGIS vector layer properties dialog
        try:
            root = iface.layerTreeView().layerTreeModel().rootGroup()
            assert isinstance(root, QgsLayerTreeGroup)
            temporaryGroup = None
            lastActiveLayer = iface.activeLayer()

            if root.findLayer(layer) is None:
                temporaryGroup = root.addGroup('.')
                assert isinstance(temporaryGroup, QgsLayerTreeGroup)
                temporaryGroup.setItemVisibilityChecked(False)
                lyrNode = temporaryGroup.addLayer(layer)
                assert isinstance(lyrNode, QgsLayerTreeLayer)
            iface.setActiveLayer(layer)
            iface.showLayerProperties(layer)

            if isinstance(temporaryGroup, QgsLayerTreeGroup):
                root.removeChildNode(temporaryGroup)
            iface.setActiveLayer(lastActiveLayer)

            return QDialog.Accepted

        except Exception as ex:
            print(ex, file=sys.stderr)

    else:
        dialog = None
        if not isinstance(canvas, QgsMapCanvas):
            canvas = QgsMapCanvas()
        if not isinstance(messageBar, QgsMessageBar):
            messageBar = QgsMessageBar()

        if isinstance(layer, QgsRasterLayer):
            dialog = QgsRasterLayerProperties(layer, canvas, parent=parent)

        elif isinstance(layer, QgsVectorLayer):
            dialog = QgsVectorLayerProperties(canvas=canvas, messageBar=messageBar, lyr=layer, parent=parent)

        if dialog:
            if hasattr(dialog, 'addPropertiesPageFactory'):
                #  QgsGui::providerGuiRegistry()->mapLayerConfigWidgetFactories( mapLayer )
                from . import MAPLAYER_CONFIGWIDGET_FACTORIES
                added = []
                if Qgis.versionInt() >= 32000:
                    for factory in QgsGui.providerGuiRegistry().mapLayerConfigWidgetFactories(layer):
                        factory: QgsMapLayerConfigWidgetFactory
                        added.append(factory.title())
                        dialog.addPropertiesPageFactory(factory)
                for factory in MAPLAYER_CONFIGWIDGET_FACTORIES:
                    factory: QgsMapLayerConfigWidgetFactory
                    if factory.title() not in added:
                        dialog.addPropertiesPageFactory(factory)

            if page:
                dialog.setCurrentPage(page)
            else:
                dialog.restoreLastPage()

        if dialog:
            if modal:
                dialog.setModal(True)
                return dialog.exec_()
            else:
                dialog.setModal(False)
                dialog.show()
                return dialog

    return None


class AttributeTableMapCanvas(QgsMapCanvas):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        s = ""

    def panToFeatureIds(self, layer, QgsVectorLayer=None, *args, **kwargs):
        s = ""
        s = ""

    def zoomToFeatureIds(self, layer, QgsVectorLayer=None, *args, **kwargs):
        s = ""


class AttributeTableWidget(QMainWindow, QgsExpressionContextGenerator):
    """
    Reimplements QgsAttributeTableDialog which unfortunately is not
    available in PyQGIS (see QGIS code src/app/qgsattributetabledialog.cpp).
    """
    sigWindowIsClosing = pyqtSignal()

    def __init__(self, mLayer: QgsVectorLayer, *args,
                 initialMode: QgsAttributeTableFilterModel.FilterMode = QgsAttributeTableFilterModel.ShowAll,
                 **kwds):
        super().__init__(*args, **kwds)
        loadUi(pathlib.Path(DIR_UI_FILES) / 'attributetablewidget.ui', self)

        self.widgetLeft.setVisible(False)
        self.widgetRight.setVisible(False)

        settings = QgsSettings()
        self.mMainView: QgsDualView
        self.mActionCutSelectedRows.triggered.connect(self.mActionCutSelectedRows_triggered)
        self.mActionCopySelectedRows.triggered.connect(self.mActionCopySelectedRows_triggered)
        self.mActionPasteFeatures.triggered.connect(self.mActionPasteFeatures_triggered)
        self.mActionToggleEditing.toggled.connect(self.mActionToggleEditing_toggled)
        self.mActionSaveEdits.triggered.connect(self.mActionSaveEdits_triggered)
        self.mActionReload.triggered.connect(self.mActionReload_triggered)
        self.mActionInvertSelection.triggered.connect(self.mActionInvertSelection_triggered)
        self.mActionRemoveSelection.triggered.connect(self.mActionRemoveSelection_triggered)
        self.mActionSelectAll.triggered.connect(self.mActionSelectAll_triggered)
        self.mActionZoomMapToSelectedRows.triggered.connect(self.mActionZoomMapToSelectedRows_triggered)
        self.mActionPanMapToSelectedRows.triggered.connect(self.mActionPanMapToSelectedRows_triggered)
        self.mActionSelectedToTop.toggled.connect(self.mMainView.setSelectedOnTop)
        self.mActionAddAttribute.triggered.connect(self.mActionAddAttribute_triggered)
        self.mActionRemoveAttribute.triggered.connect(self.mActionRemoveAttribute_triggered)
        self.mActionOrganizeColumns.triggered.connect(self.mActionOrganizeColumns_triggered)

        self.mActionOpenFieldCalculator.setVisible(FIELD_CALCULATOR)
        self.mActionOpenFieldCalculator.triggered.connect(self.mActionOpenFieldCalculator_triggered)

        self.mActionDeleteSelected.triggered.connect(self.mActionDeleteSelected_triggered)
        self.mMainView.currentChanged.connect(self.mMainView_currentChanged)
        self.mActionAddFeature.triggered.connect(self.mActionAddFeature_triggered)
        self.mActionExpressionSelect.triggered.connect(self.mActionExpressionSelect_triggered)
        self.mMainView.showContextMenuExternally.connect(self.showContextMenu)

        assert isinstance(self.mMainView, QgsDualView)
        pal = self.mMainView.tableView().palette()
        css = r"""QTableView {{
                       selection-background-color: {};
                       selection-color: {};
                        }}""".format(pal.highlight().color().name(),
                                     pal.highlightedText().color().name())
        self.mMainView.setStyleSheet(css)
        self.mDock: QgsDockWidget = None
        self.mEditorContext = QgsAttributeEditorContext()
        self.mLayer: QgsVectorLayer = mLayer
        self.mLayer.nameChanged.connect(self.updateTitle)

        # self.mMapCanvas = QgsMapCanvas()
        self.mMapCanvas = AttributeTableMapCanvas()
        self.mMapCanvas.setLayers([self.mLayer])

        # Initialize the window geometry
        # geom = settings.value("Windows/BetterAttributeTable/geometry")
        # self.restoreGeometry(geom)

        da = QgsDistanceArea()
        da.setSourceCrs(mLayer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())

        self.mEditorContext.setDistanceArea(da)
        self.mVectorLayerTools: VectorLayerTools = None
        self.setVectorLayerTools(VectorLayerTools())

        r = QgsFeatureRequest()
        needsGeom = False
        if mLayer.geometryType() != QgsWkbTypes.NullGeometry and \
                initialMode == QgsAttributeTableFilterModel.ShowVisible:
            mc = self.mMapCanvas
            extent = QgsRectangle(mc.mapSettings().mapToLayerCoordinates(mLayer, mc.extent()))
            r.setFilterRect(extent)
            needsGeom = True
        elif initialMode == QgsAttributeTableFilterModel.ShowSelected:

            r.setFilterFids(mLayer.selectedFeatureIds())

        if not needsGeom:
            r.setFlags(QgsFeatureRequest.NoGeometry)

        # Initialize dual view
        # self.mMainView.init(mLayer, self.mMapCanvas, r, self.mEditorContext, False)

        self.mFeatureRequest = QgsFeatureRequest()
        self.mContext = QgsAttributeEditorContext()
        self.mContext.setMapCanvas(self.mMapCanvas)

        self.mMainView.init(mLayer, self.mMapCanvas, self.mFeatureRequest, self.mContext)

        config = mLayer.attributeTableConfig()
        self.mMainView.setAttributeTableConfig(config)

        # workaround for missing filter widget
        self.mMessageTimeOut = 5
        # self.mFeatureFilterWidget.init(mLayer, self.mEditorContext, self.mMainView, None,
        # QgisApp.instance().messageTimeout())
        self.mApplyFilterButton.setDefaultAction(self.mActionApplyFilter)
        self.mSetFilterButton.setDefaultAction(self.mActionSetFilter)
        self.mActionApplyFilter.triggered.connect(self._filterQueryAccepted)
        self.mActionSetFilter.triggered.connect(self._filterExpressionBuilder)

        self.mActionFeatureActions = QToolButton()
        self.mActionFeatureActions.setAutoRaise(False)
        self.mActionFeatureActions.setPopupMode(QToolButton.InstantPopup)
        self.mActionFeatureActions.setIcon(QgsApplication.getThemeIcon("/mAction.svg"))
        self.mActionFeatureActions.setText(self.tr("Actions"))
        self.mActionFeatureActions.setToolTip(self.tr("Actions"))

        self.mToolbar.addWidget(self.mActionFeatureActions)
        self.mActionSetStyles.triggered.connect(self.openConditionalStyles)

        # info from layer to table
        mLayer.editingStarted.connect(self.editingToggled)
        mLayer.editingStopped.connect(self.editingToggled)
        mLayer.destroyed.connect(self.onLayerDestroyed)
        mLayer.selectionChanged.connect(self.updateTitle)
        mLayer.editCommandEnded.connect(self.scheduleTitleUpdate)
        mLayer.featuresDeleted.connect(self.updateTitle)
        mLayer.editingStopped.connect(self.updateTitle)
        mLayer.readOnlyChanged.connect(self.editingToggled)

        self.mUpdateTrigger: QTimer = QTimer()
        self.mUpdateTrigger.setInterval(2000)
        # self.mUpdateTrigger.timeout.connect(self.updateTitle)

        # connect table info to window
        self.mMainView.filterChanged.connect(self.updateTitle)
        self.mMainView.filterExpressionSet.connect(self.formFilterSet)
        self.mMainView.formModeChanged.connect(self.viewModeChanged)

        # info from table to application
        # self.saveEdits.connect(QgisApp::instance() -> saveEdits() })

        """
        dockTable: bool = bool(settings.value("qgis/dockAttributeTable" , False )
        if dockTable:
            self.mDock = new QgsAttributeTableDock( QString(), QgisApp::instance() );
            mDock->setWidget( this );
            connect( this, &QObject::destroyed, mDock, &QWidget::close );
            QgisApp::instance() -> addDockWidget( Qt::BottomDockWidgetArea, mDock );
        mActionDockUndock->setChecked( dockTable );
        connect( mActionDockUndock, &QAction::toggled, this, &QgsAttributeTableDialog::toggleDockMode );
        installEventFilter( this );
        """

        self.updateTitle()

        # set icons
        self.mActionRemoveSelection.setIcon(QgsApplication.getThemeIcon("/mActionDeselectAll.svg"))
        self.mActionSelectAll.setIcon(QgsApplication.getThemeIcon("/mActionSelectAll.svg"))
        self.mActionSelectedToTop.setIcon(QgsApplication.getThemeIcon("/mActionSelectedToTop.svg"))
        self.mActionCopySelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionEditCopy.svg"))
        self.mActionPasteFeatures.setIcon(QgsApplication.getThemeIcon("/mActionEditPaste.svg"))
        self.mActionZoomMapToSelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionZoomToSelected.svg"))
        self.mActionPanMapToSelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionPanToSelected.svg"))
        self.mActionInvertSelection.setIcon(QgsApplication.getThemeIcon("/mActionInvertSelection.svg"))
        self.mActionToggleEditing.setIcon(QgsApplication.getThemeIcon("/mActionToggleEditing.svg"))
        self.mActionToggleMultiEdit.setIcon(QgsApplication.getThemeIcon("/mActionMultiEdit.svg"))
        self.mActionCutSelectedRows.setIcon(QgsApplication.getThemeIcon("/mActionEditCut.svg"))
        self.mActionSearchForm.setIcon(QgsApplication.getThemeIcon("/mActionFilter2.svg"))
        self.mActionSetStyles.setIcon(QgsApplication.getThemeIcon("/mActionConditionalFormatting.svg"))
        self.mActionReload.setIcon(QgsApplication.getThemeIcon("/mActionRefresh.svg"))
        self.mActionSaveEdits.setIcon(QgsApplication.getThemeIcon("/mActionSaveEdits.svg"))
        self.mActionDeleteSelected.setIcon(QgsApplication.getThemeIcon("/mActionDeleteSelectedFeatures.svg"))
        self.mActionOpenFieldCalculator.setIcon(QgsApplication.getThemeIcon("/mActionCalculateField.svg"))
        self.mActionAddAttribute.setIcon(QgsApplication.getThemeIcon("/mActionNewAttribute.svg"))
        self.mActionRemoveAttribute.setIcon(QgsApplication.getThemeIcon("/mActionDeleteAttribute.svg"))
        self.mTableViewButton.setIcon(QgsApplication.getThemeIcon("/mActionOpenTable.svg"))
        self.mAttributeViewButton.setIcon(QgsApplication.getThemeIcon("/mActionFormView.svg"))
        self.mActionExpressionSelect.setIcon(QgsApplication.getThemeIcon("/mIconExpressionSelect.svg"))
        self.mActionAddFeature.setIcon(QgsApplication.getThemeIcon("/mActionNewTableRow.svg"))
        self.mActionFeatureActions.setIcon(QgsApplication.getThemeIcon("/mAction.svg"))

        # toggle editing
        canChangeAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.ChangeAttributeValues
        canDeleteFeatures = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        canAddAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddAttributes
        canDeleteAttributes = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteAttributes
        canAddFeatures = mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures

        self.mActionToggleEditing.blockSignals(True)
        self.mActionToggleEditing.setCheckable(True)
        self.mActionToggleEditing.setChecked(mLayer.isEditable())
        self.mActionToggleEditing.blockSignals(False)

        self.mActionSaveEdits.setEnabled(self.mActionToggleEditing.isEnabled() and mLayer.isEditable())
        self.mActionReload.setEnabled(not mLayer.isEditable())
        self.mActionAddAttribute.setEnabled((canChangeAttributes or canAddAttributes) and mLayer.isEditable())
        self.mActionRemoveAttribute.setEnabled(canDeleteAttributes and mLayer.isEditable())
        if not canDeleteFeatures:
            self.mToolbar.removeAction(self.mActionDeleteSelected)
            self.mToolbar.removeAction(self.mActionCutSelectedRows)

        self.mActionAddFeature.setEnabled(canAddFeatures and mLayer.isEditable())
        self.mActionPasteFeatures.setEnabled(canAddFeatures and mLayer.isEditable())
        if not canAddFeatures:
            self.mToolbar.removeAction(self.mActionAddFeature)
            self.mToolbar.removeAction(self.mActionPasteFeatures)

        assert isinstance(self.mMainViewButtonGroup, QButtonGroup)
        self.mMainViewButtonGroup.setId(self.mTableViewButton, QgsDualView.AttributeTable)
        self.mMainViewButtonGroup.setId(self.mAttributeViewButton, QgsDualView.AttributeEditor)
        self.mTableViewButton.clicked.connect(lambda: self.setViewMode(QgsDualView.AttributeTable))
        self.mAttributeViewButton.clicked.connect(lambda: self.setViewMode(QgsDualView.AttributeEditor))

        self.setFilterMode(initialMode)

        if isinstance(mLayer, QgsVectorLayer) and mLayer.isValid():

            # self.mUpdateExpressionText.registerExpressionContextGenerator(self)
            self.mFieldCombo.setFilters(QgsFieldProxyModel.AllTypes | QgsFieldProxyModel.HideReadOnly)
            self.mFieldCombo.setLayer(mLayer)

            self.mRunFieldCalc.clicked.connect(self.updateFieldFromExpression)
            self.mRunFieldCalcSelected.clicked.connect(self.updateFieldFromExpressionSelected)
            self.mUpdateExpressionText.fieldChanged.connect(lambda fieldName: self.updateButtonStatus(fieldName, True))
            self.mUpdateExpressionText.setLayer(mLayer)
            self.mUpdateExpressionText.setLeftHandButtonStyle(True)

            initialView = int(settings.value("qgis/attributeTableView", -1))
            if initialView < 0:
                initialView = int(settings.value("qgis/attributeTableLastView", int(QgsDualView.AttributeTable)))
            for m in [QgsDualView.AttributeTable, QgsDualView.AttributeEditor]:
                if initialView == int(m):
                    self.setViewMode(m)

            self.mActionToggleMultiEdit.toggled.connect(self.mMainView.setMultiEditEnabled)
            self.mActionSearchForm.toggled.connect(self.mMainView.toggleSearchMode)
            self.updateMultiEditButtonState()

            if mLayer.editFormConfig().layout() == QgsEditFormConfig.UiFileLayout:
                # not supported with custom UI
                self.mActionToggleMultiEdit.setEnabled(False)
                self.mActionToggleMultiEdit.setToolTip(
                    self.tr("Multi-edit is not supported when using custom UI forms"))
                self.mActionSearchForm.setEnabled(False)
                self.mActionSearchForm.setToolTip(self.tr("Search is not supported when using custom UI forms"))

            self.editingToggled()

            self.mMainView.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)

        self._hide_unconnected_widgets()

    def onWillShowContextMenuAttributeTable(self, menu: QMenu, atIndex: QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """

        fid = atIndex.data(QgsAttributeTableModel.FeatureIdRole)

        def findAction(name: str) -> QAction:
            name = self.tr(name)

            for a in menu.actions():
                if a.text() == name:
                    return a
            return None

        layer = self.mLayer
        vlTool = self.vectorLayerTools()

        if isinstance(vlTool, VectorLayerTools) and isinstance(layer, QgsVectorLayer):
            actionZoomToFeature = findAction('Zoom to Feature')
            actionPanToFeature = findAction('Pan to Feature')
            actionFlashFeature = findAction('Flash Feature')

            if isinstance(actionZoomToFeature, QAction):
                actionZoomToFeature.triggered.connect(
                    lambda *args, lyr=layer, fids=[fid]: vlTool.zoomToFeatures(lyr, fids))
            if isinstance(actionPanToFeature, QAction):
                actionPanToFeature.triggered.connect(
                    lambda *args, lyr=layer, fids=[fid]: vlTool.panToFeatures(lyr, fids))
            if isinstance(actionFlashFeature, QAction):
                actionFlashFeature.triggered.connect(
                    lambda *args, lyr=layer, fids=[fid]: vlTool.flashFeatures(lyr, fids))

    def closeEvent(self, event: QCloseEvent):
        super().closeEvent(event)
        if event.isAccepted():
            self.sigWindowIsClosing.emit()

    def setVectorLayerTools(self, tools: VectorLayerTools):
        assert isinstance(tools, VectorLayerTools)
        self.mVectorLayerTools = tools

        self.mEditorContext.setVectorLayerTools(tools)

    def vectorLayerTools(self) -> VectorLayerTools:
        return self.mVectorLayerTools
        # return self.mEditorContext.vectorLayerTools()

    def setMapCanvas(self, canvas: QgsMapCanvas):
        self.mEditorContext.setMapCanvas(canvas)

    def createExpressionContext(self) -> QgsExpressionContext:
        return QgsExpressionContext()

    def updateButtonStatus(self, fieldName: str, isValid: bool):
        self.mRunFieldCalc.setEnabled(isValid)

    def updateMultiEditButtonState(self):
        if not isinstance(self.mLayer, QgsVectorLayer) or \
                (self.mLayer.editFormConfig().layout() == QgsEditFormConfig.UiFileLayout):
            return

        self.mActionToggleMultiEdit.setEnabled(self.mLayer.isEditable())

        if not self.mLayer.isEditable() or \
                (self.mLayer.isEditable() and self.mMainView.view() != QgsDualView.AttributeEditor):
            self.mActionToggleMultiEdit.setChecked(False)

    def openConditionalStyles(self):
        self.mMainView.openConditionalStyles()

    def mActionCutSelectedRows_triggered(self):
        self.vectorLayerTools().cutSelectionToClipboard(self.mLayer)

    def mActionCopySelectedRows_triggered(self):
        self.vectorLayerTools().copySelectionToClipboard(self.mLayer)

    def setMainMessageBar(self, messageBar: QgsMessageBar):
        self.mEditorContext.setMainMessageBar(messageBar)

    def mainMessageBar(self) -> QgsMessageBar:
        return self.mEditorContext.mainMessageBar()

    def updateFieldFromExpression(self):

        filtered = self.mMainView.filterMode() != QgsAttributeTableFilterModel.ShowAll
        filteredIds = self.mMainView.filteredFeatures() if filtered else []
        self.runFieldCalculation(self.mLayer, self.mFieldCombo.currentField(),
                                 self.mUpdateExpressionText.asExpression(), filteredIds)

    def updateFieldFromExpressionSelected(self):

        filteredIds = self.mLayer.selectedFeatureIds()
        self.runFieldCalculation(self.mLayer, self.mFieldCombo.currentField(),
                                 self.mUpdateExpressionText.asExpression(), filteredIds)

    def _filterExpressionBuilder(self):
        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.mLayer))

        # taken from qgsfeaturefilterwidget.cpp : void QgsFeatureFilterWidget::filterExpressionBuilder()
        dlg = QgsExpressionBuilderDialog(self.mLayer, self.mFilterQuery.text(),
                                         self,
                                         'generic', context)
        dlg.setWindowTitle('Expression Based Filter')
        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        dlg.setGeomCalculator(myDa)

        if dlg.exec() == QDialog.Accepted:
            self.setFilterExpression(dlg.expressionText(), QgsAttributeForm.ReplaceFilter, True)

    def _filterQueryAccepted(self):
        if self.mFilterQuery.text().strip() == '':
            self._filterShowAll()
        else:
            self._filterQueryChanged(self.mFilterQuery.text())

    def _filterShowAll(self):
        self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowAll)

    def _filterQueryChanged(self, query):
        self.setFilterExpression(query)

    def runFieldCalculation(self, layer: QgsVectorLayer,
                            fieldName: str,
                            expression: str,
                            filteredIds: list):
        fieldindex = layer.fields().indexFromName(fieldName)
        if fieldindex < 0:
            # // this shouldn't happen... but it did. There's probably some deeper underlying issue
            # // but we may as well play it safe here.
            QMessageBox.critical(None, self.tr("Update Attributes"),
                                 "An error occurred while trying to update the field {}".format(fieldName))
            return

        # cursorOverride = QgsTemporaryCursorOverride(Qt.WaitCursor)
        self.mLayer.beginEditCommand("Field calculator")

        calculationSuccess = True
        error = None

        exp = QgsExpression(expression)
        da = QgsDistanceArea()
        da.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        exp.setGeomCalculator(da)
        exp.setDistanceUnits(QgsProject.instance().distanceUnits())
        exp.setAreaUnits(QgsProject.instance().areaUnits())
        useGeometry: bool = exp.needsGeometry()

        request = QgsFeatureRequest(self.mMainView.masterModel().request())
        useGeometry = useGeometry or not request.filterRect().isNull()
        request.setFlags(QgsFeatureRequest.NoFlags if useGeometry else QgsFeatureRequest.NoGeometry)

        rownum = 1

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        exp.prepare(context)

        fld: QgsField = layer.fields().at(fieldindex)

        referencedColumns = exp.referencedColumns()
        referencedColumns.add(
            fld.name())  # need existing column value to store old attribute when changing field values
        request.setSubsetOfAttributes(referencedColumns, layer.fields())

        task = QgsScopedProxyProgressTask(self.tr("Calculating field"))

        count = len(filteredIds) if len(filteredIds) > 0 else layer.featureCount()
        i = 0

        for feature in layer.getFeatures(request):

            if len(filteredIds) > 0 and feature.id() not in filteredIds:
                continue

            i += 1
            task.setProgress(i / count * 100)
            context.setFeature(feature)
            context.lastScope().addVariable(QgsExpressionContextScope.StaticVariable("row_number", rownum, True))

            value = exp.evaluate(context)
            convertError = None
            try:
                value = fld.convertCompatible(value)
            except (SystemError, ValueError) as ex:
                error = 'Unable to convert "{}" to type {}'.format(value, fld.typeName())
            # Bail if we have a update error
            if exp.hasEvalError():
                calculationSuccess = False
                error = exp.evalErrorString()
                break
            elif isinstance(error, str):
                calculationSuccess = False
                break
            else:
                oldvalue = feature.attributes()[fieldindex]
                self.mLayer.changeAttributeValue(feature.id(), fieldindex, value, oldvalue)
            rownum += 1

        # cursorOverride.release()
        # task.reset()

        if not calculationSuccess:
            QMessageBox.critical(None,
                                 self.tr("Update Attributes"),
                                 "An error occurred while evaluating the calculation string:\n{}".format(error))
            self.mLayer.destroyEditCommand()

        else:
            self.mLayer.endEditCommand()

            # refresh table with updated values
            # fixes https:#github.com/qgis/QGIS/issues/25210
            masterModel: QgsAttributeTableModel = self.mMainView.masterModel()
            modelColumn: int = masterModel.fieldCol(fieldindex)
            masterModel.reload(masterModel.index(0, modelColumn),
                               masterModel.index(masterModel.rowCount() - 1, modelColumn))

    def layerActionTriggered(self):
        action = self.sender()
        if isinstance(action, QAction):
            action: QgsAction = action.data()

            context: QgsExpressionContext = self.mLayer.createExpressionContext()
            scope = QgsExpressionContextScope()
            scope.addVariable(QgsExpressionContextScope.StaticVariable("action_scope", "AttributeTable"))
            context.appendScope(scope)
            action.run(context)

    def formFilterSet(self, filterText: str, filterType: QgsAttributeForm.FilterType):
        self.setFilterExpression(filterText, filterType, True)

    def setFilterExpression(self,
                            filterString: str,
                            filterType: QgsAttributeForm.FilterType = QgsAttributeForm.ReplaceFilter,
                            alwaysShowFilter: bool = False):

        # as long we have no filter widget implementation
        if filterString is None:
            filterString = ''

        messageBar: QgsMessageBar = self.mainMessageBar()

        assert isinstance(self.mFilterQuery, QgsFilterLineEdit)
        filter = self.mFilterQuery.text()
        if filter != '' and filterString != '':
            if filterType == QgsAttributeForm.ReplaceFilter:
                filter = filterString
            elif filterType == QgsAttributeForm.FilterAnd:
                filter = f'({filter}) AND ({filterString})'
            elif filterType == QgsAttributeForm.FilterOr:
                filter = f'({filter}) OR ({filterString})'
        elif len(filterString) > 0:
            filter = filterString
        else:
            self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowAll)
            return
        self.mFilterQuery.setText(filter)

        filterExpression: QgsExpression = QgsExpression(filter)
        context: QgsExpressionContext = QgsExpressionContext(
            QgsExpressionContextUtils.globalProjectLayerScopes(self.mLayer))
        fetchGeom: bool = filterExpression.needsGeometry()

        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        filterExpression.setGeomCalculator(myDa)
        filterExpression.setDistanceUnits(QgsProject.instance().distanceUnits())
        filterExpression.setAreaUnits(QgsProject.instance().areaUnits())

        if filterExpression.hasParserError():
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Parsing error', filterExpression.parserErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Parsing errors: {filterExpression.parserErrorString()}', file=sys.stderr)

        if not filterExpression.prepare(context):
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Evaluation error', filterExpression.evalErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Evaluation error {filterExpression.evalErrorString()}', file=sys.stderr)
            return

        filteredFeatures = []

        request = self.mMainView.masterModel().request()
        request.setSubsetOfAttributes(filterExpression.referencedColumns(), self.mLayer.fields())
        if not fetchGeom:
            request.setFlags(QgsFeatureRequest.NoGeometry)
        else:
            request.setFlags(request.flags() & QgsFeatureRequest.NoGeometry)

        for f in self.mLayer.getFeatures(request):
            context.setFeature(f)
            if filterExpression.evaluate(context) != 0:
                filteredFeatures.append(f.id())
            if filterExpression.hasEvalError():
                break

        self.mMainView.setFilteredFeatures(filteredFeatures)

        if filterExpression.hasEvalError():
            if isinstance(messageBar, QgsMessageBar):
                messageBar.pushMessage('Error filtering', filterExpression.evalErrorString(),
                                       Qgis.Warning, self.mMessageTimeOut)
            else:
                print(f'Error filtering: {filterExpression.evalErrorString()}', file=sys.stderr)
            return
        self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowFilteredList)

    def viewModeChanged(self, mode: QgsAttributeEditorContext.Mode):
        if mode != QgsAttributeEditorContext.SearchMode:
            self.mActionSearchForm.setChecked(False)

    def scheduleTitleUpdate(self):
        self.mUpdateTrigger.start(2000)

    def updateTitle(self):
        self.mUpdateTrigger.stop()
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        w = self.mDock if isinstance(self.mDock, QWidget) else self
        w.setWindowTitle(" {0} :: Features Total: {1} Filtered: {2}, Selected: {3}".format(
            self.mLayer.name(),
            max(self.mMainView.featureCount(), self.mLayer.featureCount()),
            self.mMainView.filteredFeatureCount(),
            self.mLayer.selectedFeatureCount())
        )

        if self.mMainView.filterMode() == QgsAttributeTableFilterModel.ShowAll:
            self.mRunFieldCalc.setText(self.tr("Update All"))
        else:
            self.mRunFieldCalc.setText(self.tr("Update Filtered"))

        canDeleteFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        enabled = self.mLayer.selectedFeatureCount() > 0
        self.mRunFieldCalcSelected.setEnabled(enabled)
        self.mActionDeleteSelected.setEnabled(canDeleteFeatures and self.mLayer.isEditable() and enabled)
        self.mActionCutSelectedRows.setEnabled(canDeleteFeatures and self.mLayer.isEditable() and enabled)
        self.mActionCopySelectedRows.setEnabled(enabled)

    def editingToggled(self):
        self.mActionToggleEditing.blockSignals(True)
        self.mActionToggleEditing.setChecked(self.mLayer.isEditable())
        self.mActionSaveEdits.setEnabled(self.mLayer.isEditable())
        self.mActionReload.setEnabled(not self.mLayer.isEditable())
        self.updateMultiEditButtonState()
        if self.mLayer.isEditable():
            self.mActionSearchForm.setChecked(False)

        self.mActionToggleEditing.blockSignals(False)

        canChangeAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.ChangeAttributeValues
        canDeleteFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteFeatures
        canAddAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddAttributes
        canDeleteAttributes = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.DeleteAttributes
        canAddFeatures = self.mLayer.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures
        self.mActionAddAttribute.setEnabled((canChangeAttributes or canAddAttributes) and self.mLayer.isEditable())
        self.mActionRemoveAttribute.setEnabled(canDeleteAttributes and self.mLayer.isEditable())
        self.mActionDeleteSelected.setEnabled(
            canDeleteFeatures and self.mLayer.isEditable() and self.mLayer.selectedFeatureCount() > 0)
        self.mActionCutSelectedRows.setEnabled(
            canDeleteFeatures and self.mLayer.isEditable() and self.mLayer.selectedFeatureCount() > 0)
        self.mActionAddFeature.setEnabled(canAddFeatures and self.mLayer.isEditable())
        self.mActionPasteFeatures.setEnabled(canAddFeatures and self.mLayer.isEditable())
        self.mActionToggleEditing.setEnabled((canChangeAttributes
                                              or canDeleteFeatures
                                              or canAddAttributes
                                              or canDeleteAttributes
                                              or canAddFeatures) and not self.mLayer.readOnly())

        self.mUpdateExpressionBox.setVisible(self.mLayer.isEditable())
        if self.mLayer.isEditable() and self.mFieldCombo.currentIndex() == -1:
            self.mFieldCombo.setCurrentIndex(0)

        # not necessary to set table read only if layer is not editable
        # because model always reflects actual state when returning item flags
        actions = self.mLayer.actions().actions("Layer")

        if len(actions) == 0:
            self.mActionFeatureActions.setVisible(True)
        else:
            actionMenu = QMenu()
            constActions = actions
            for action in constActions:

                if not self.mLayer.isEditable() and action.isEnabledOnlyWhenEditable():
                    continue

                    qAction: QAction = actionMenu.addAction(action.icon(), action.shortTitle())
                    qAction.setToolTip(action.name())
                    qAction.setData(QVariant.fromValue < QgsAction > (action))
                    qAction.triggered.connect(self.layerActionTriggered)

            self.mActionFeatureActions.setMenu(actionMenu)

    def setCadDockWidget(self, cadDockWidget):
        self.mEditorContext.setCadDockWidget(cadDockWidget)

    def mActionPasteFeatures_triggered(self):
        self.vectorLayerTools().pasteFromClipboard(self.mLayer)

    def mActionReload_triggered(self):
        self.mMainView.masterModel().layer().dataProvider().reloadData()

    def mActionInvertSelection_triggered(self):
        self.vectorLayerTools().invertSelection(self.mLayer)

    def mActionRemoveSelection_triggered(self):
        self.vectorLayerTools().removeSelection(self.mLayer)

    def mActionSelectAll_triggered(self):
        self.vectorLayerTools().selectAll(self.mLayer)

    def mActionZoomMapToSelectedRows_triggered(self):
        self.vectorLayerTools().zoomToSelected(self.mLayer)

    def mActionPanMapToSelectedRows_triggered(self):
        self.vectorLayerTools().panToSelected(self.mLayer)

    def mActionDeleteSelected_triggered(self):
        self.vectorLayerTools().deleteSelection(self.mLayer)

    def onLayerDestroyed(self):
        self.mMainView.cancelProgress()
        self.mLayer = None

    def reloadModel(self):
        """
        Reloads the table model
        """
        masterModel = self.mMainView.masterModel()
        # // update model - a field has been added or updated
        masterModel.reload(masterModel.index(0, 0),
                           masterModel.index(masterModel.rowCount() - 1,
                                             masterModel.columnCount() - 1))

    def mActionAddAttribute_triggered(self):
        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable():
            d = AddAttributeDialog(self.mLayer)
            d.exec_()
            if d.result() == QDialog.Accepted:
                field = d.field()
                self.mLayer.addAttribute(field)
                self.reloadModel()

    def mActionOpenFieldCalculator_triggered(self):
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        masterModel: QgsAttributeTableModel = self.mMainView.masterModel()
        if FIELD_CALCULATOR:
            calc: QgsFieldCalculator = QgsFieldCalculator(self.mLayer, self)
            if calc.exec_() == QDialog.Accepted:
                col = masterModel.fieldCol(calc.changedAttributeId())
                if col >= 0:
                    masterModel.reload(masterModel.index(0, col), masterModel.index(masterModel.rowCount() - 1, col))

    def mActionOrganizeColumns_triggered(self):
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        dlg = QgsOrganizeTableColumnsDialog(self.mLayer, self.mLayer.attributeTableConfig(), self)
        if dlg.exec_() == QDialog.Accepted:
            config = dlg.config()
            self.mMainView.setAttributeTableConfig(config)

    def mActionRemoveAttribute_triggered(self):
        if not (isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable()):
            return

        d = RemoveAttributeDialog(self.mLayer)

        if d.exec_() == QDialog.Accepted:
            fieldIndices = d.fieldIndices()
            self.mLayer.beginEditCommand('Delete attributes')
            if self.mLayer.deleteAttributes(fieldIndices):
                self.mLayer.endEditCommand()
            else:
                self.mainMessageBar().pushMessage(self.tr("Attribute error"),
                                                  self.tr("The attribute(s) could not be deleted"),
                                                  Qgis.Warning)
            self.reloadModel()

    def mMainView_currentChanged(self, viewMode: QgsDualView.ViewMode):
        if isinstance(viewMode, int):
            for m in [QgsDualView.AttributeTable, QgsDualView.AttributeEditor]:
                if int(m) == viewMode:
                    viewMode = m
                    break

        assert isinstance(viewMode, QgsDualView.ViewMode)
        self.mMainViewButtonGroup.button(viewMode).click()
        self.updateMultiEditButtonState()

        if viewMode == QgsDualView.AttributeTable:
            self.mActionSearchForm.setChecked(False)

        s = QgsSettings()
        s.setValue("/qgis/attributeTableLastView", int(viewMode))

    def showContextMenu(self, menu: QgsActionMenu, fid: int):
        if self.mLayer.isEditable():
            qAction = menu.addAction(QgsApplication.getThemeIcon("/mActionDeleteSelectedFeatures.svg"),
                                     self.tr("Delete Feature"))
            qAction.triggered.connect(lambda *args, f=fid: self.deleteFeature(fid))

    def deleteFeature(self, fid: int):
        self.mLayer.deleteFeature(fid)

    def mActionAddFeature_triggered(self):

        if not self.mLayer.isEditable():
            return

        masterModel = self.mMainView.masterModel()
        f = QgsFeature(self.mLayer.fields())
        if self.vectorLayerTools().addFeature(
                self.mLayer,
                f=f
        ):
            masterModel.reload(masterModel.index(0, 0), masterModel.index(
                masterModel.rowCount() - 1, masterModel.columnCount() - 1))

    def mActionExpressionSelect_triggered(self):
        dlg = QgsExpressionSelectionDialog(self.mLayer)
        dlg.setMessageBar(self.mainMessageBar())
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.exec_()

    def mActionToggleEditing_toggled(self, b: bool):
        if not isinstance(self.mLayer, QgsVectorLayer):
            return

        # this has to be done, because in case only one cell has been changed and is still enabled, the change
        # would not be added to the mEditBuffer. By disabling, it looses focus and the change will be stored.
        s = ""
        if self.mLayer.isEditable() and \
                self.mMainView.tableView().indexWidget(self.mMainView.tableView().currentIndex()) is not None:
            self.mMainView.tableView().indexWidget(self.mMainView.tableView().currentIndex()).setEnabled(False)

        self.vectorLayerTools().toggleEditing(self.mLayer)
        self.editingToggled()

    def mActionSaveEdits_triggered(self):
        self.vectorLayerTools().saveEdits(self.mLayer, leave_editable=True, trigger_repaint=True)

    def setViewMode(self, mode: QgsDualView.ViewMode):
        assert isinstance(mode, QgsDualView.ViewMode)
        self.mMainView.setView(mode)
        for m in [QgsDualView.AttributeEditor, QgsDualView.AttributeTable]:
            self.mMainViewButtonGroup.button(m).setChecked(m == mode)

    def setFilterMode(self, mode: QgsAttributeTableFilterModel.FilterMode):
        self.mMainView.setFilterMode(mode)
        return
        # todo: re-implement QgsFeatureFilterWidget

        if mode == QgsAttributeTableFilterModel.ShowVisible:
            self.mFeatureFilterWidget.filterVisible()
        elif mode == QgsAttributeTableFilterModel.ShowSelected:
            self.mFeatureFilterWidget.filterSelected()
        else:
            self.mFeatureFilterWidget.filterShowAll()

    def _hide_unconnected_widgets(self):
        # self.mActionOpenFieldCalculator.setVisible(False)
        self.mActionDockUndock.setVisible(False)
