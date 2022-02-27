import typing

import numpy as np

from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import QAbstractTableModel, pyqtSignal, QModelIndex, Qt, QVariant
from qgis.PyQt.QtWidgets import QGroupBox, QWidget, QLabel
from qgis.core import QgsVectorLayer, QgsField, QgsFieldFormatter, QgsApplication
from qgis.gui import QgsEditorWidgetWrapper, QgsEditorConfigWidget, QgsGui, \
    QgsEditorWidgetFactory
from .spectrallibraryplotwidget import SpectralProfilePlotXAxisUnitModel
from .. import speclibUiPath, EDITOR_WIDGET_REGISTRY_KEY, EDITOR_WIDGET_REGISTRY_NAME
from ..core import supports_field
from ..core.spectralprofile import SpectralProfile, encodeProfileValueDict, decodeProfileValueDict
from ...unitmodel import BAND_INDEX
from ...utils import loadUi

SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'

SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
SPECTRAL_PROFILE_FIELD_FORMATTER: None


class SpectralProfileTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """

    sigXUnitChanged = pyqtSignal(str)
    sigYUnitChanged = pyqtSignal(str)

    def __init__(self, *args, **kwds):
        super(SpectralProfileTableModel, self).__init__(*args, **kwds)

        self.mColumnNames = {0: 'x',
                             1: 'y'}
        self.mColumnUnits = {0: None,
                             1: None}

        self.mValuesX: typing.Dict[int, typing.Any] = {}
        self.mValuesY: typing.Dict[int, typing.Any] = {}
        self.mValuesBBL: typing.Dict[int, typing.Any] = {}

        self.mLastProfile: SpectralProfile = SpectralProfile()

        self.mRows: int = 0

    def setBands(self, bands: int):
        bands = int(bands)

        assert bands >= 0

        if bands > self.bands():
            self.beginInsertRows(QModelIndex(), self.bands(), bands - 1)
            self.mRows = bands
            self.endInsertRows()

        elif bands < self.bands():
            self.beginRemoveRows(QModelIndex(), bands, self.bands() - 1)
            self.mRows = bands
            self.endRemoveRows()

    def bands(self) -> int:
        return self.rowCount()

    def setProfile(self, profile: SpectralProfile):
        """
        :param values:
        :return:
        """
        assert isinstance(profile, SpectralProfile)

        self.beginResetModel()
        self.mValuesX.clear()
        self.mValuesY.clear()
        self.mValuesBBL.clear()
        self.mLastProfile = profile
        self.mValuesX.update({i: v for i, v in enumerate(profile.xValues())})
        self.mValuesY.update({i: v for i, v in enumerate(profile.yValues())})
        self.mValuesBBL.update({i: v for i, v in enumerate(profile.bbl())})

        self.setBands(len(self.mValuesY))

        self.endResetModel()
        self.setXUnit(profile.xUnit())
        self.setYUnit(profile.yUnit())

    def setXUnit(self, unit: str):
        if self.xUnit() != unit:
            self.mColumnUnits[0] = unit
            idx0 = self.index(0, 0)
            idx1 = self.index(self.rowCount(QModelIndex()) - 1, 0)
            self.dataChanged.emit(idx0, idx1)
            # self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount(QModelIndex())-1)
            self.sigXUnitChanged.emit(unit)

    def setYUnit(self, unit: str):
        if self.yUnit() != unit:
            self.mColumnUnits[1] = unit
            # self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount(QModelIndex())-1)
            self.sigYUnitChanged.emit(unit)

    def xUnit(self) -> str:
        return self.mColumnUnits[0]

    def yUnit(self) -> str:
        return self.mColumnUnits[1]

    def profile(self) -> SpectralProfile:
        """
        Return the data as new SpectralProfile
        :return:
        :rtype:
        """
        p = SpectralProfile(fields=self.mLastProfile.fields())
        nb = self.bands()

        y = [self.mValuesY.get(b, None) for b in range(nb)]
        if self.xUnit() == BAND_INDEX:
            x = None
        else:
            x = [self.mValuesX.get(b, None) for b in range(nb)]

        bbl = [self.mValuesBBL.get(b, None) for b in range(nb)]
        bbl = np.asarray(bbl, dtype=bool)
        if not np.any(np.equal(bbl, False)):
            bbl = None
        p.setValues(x, y, xUnit=self.xUnit(), yUnit=self.yUnit(), bbl=bbl)

        return p

    def resetProfile(self):
        self.setProfile(self.mLastProfile)

    def rowCount(self, parent: QModelIndex = None, *args, **kwargs) -> int:

        return self.mRows

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.mColumnNames)

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        if role in [Qt.DisplayRole, Qt.EditRole]:
            value = None
            if c == 0:
                if self.xUnit() != BAND_INDEX:
                    value = self.mValuesX.get(i, None)
                    if value:
                        return str(value)
                    else:
                        return None
                else:
                    return i + 1

            elif c == 1:
                value = self.mValuesY.get(i, None)
                if value:
                    return str(value)
                else:
                    return None

        elif role == Qt.CheckStateRole:
            if c == 0:
                if bool(self.mValuesBBL.get(i, True)):
                    return Qt.Checked
                else:
                    return Qt.Unchecked
        return None

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        modified = False
        if role == Qt.CheckStateRole:
            if c == 0:
                self.mValuesBBL[i] = value == Qt.Checked
                modified = True

        if role == Qt.EditRole:
            if c == 0:
                try:
                    self.mValuesX[i] = float(value)
                    modified = True
                except (TypeError, ValueError):
                    pass
            elif c == 1:
                try:
                    self.mValuesY[i] = float(value)
                    modified = True
                except (TypeError, ValueError):
                    pass

        if modified:
            self.dataChanged.emit(index, index, [role])
        return modified

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

            if c == 0:
                flags = flags | Qt.ItemIsUserCheckable
                if self.xUnit() != BAND_INDEX:
                    flags = flags | Qt.ItemIsEditable
            elif c == 1:
                flags = flags | Qt.ItemIsEditable
            return flags
        return None

    def headerData(self, col: int, orientation, role):

        if orientation == Qt.Horizontal and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            return self.mColumnNames.get(col, f'{col + 1}')
        return None


class SpectralProfileEditorWidget(QGroupBox):
    sigProfileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget, self).__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralprofileeditorwidget.ui'), self)
        self.mDefault: SpectralProfile = None
        self.mModel: SpectralProfileTableModel = SpectralProfileTableModel()
        self.mModel.rowsInserted.connect(self.onBandsChanged)
        self.mModel.rowsRemoved.connect(self.onBandsChanged)
        self.mModel.dataChanged.connect(lambda *args: self.onProfileChanged())
        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.cbXUnit.setModel(self.mXUnitModel)
        self.cbXUnit.currentIndexChanged.connect(
            lambda *args: self.mModel.setXUnit(self.cbXUnit.currentData(Qt.UserRole)))
        self.mModel.sigXUnitChanged.connect(self.onXUnitChanged)

        self.tbYUnit.textChanged.connect(self.mModel.setYUnit)
        self.mModel.sigYUnitChanged.connect(self.tbYUnit.setText)
        self.mModel.sigYUnitChanged.connect(self.onProfileChanged)
        self.mModel.sigXUnitChanged.connect(self.onProfileChanged)
        # self.mModel.sigColumnValueUnitChanged.connect(self.onValueUnitChanged)
        # self.mModel.sigColumnDataTypeChanged.connect(self.onDataTypeChanged)
        self.tableView.setModel(self.mModel)

        self.actionReset.triggered.connect(self.resetProfile)
        self.btnReset.setDefaultAction(self.actionReset)

        self.sbBands.valueChanged.connect(self.mModel.setBands)
        # self.onDataTypeChanged(0, float)
        # self.onDataTypeChanged(1, float)

        self.setProfile(SpectralProfile())

    def onProfileChanged(self):
        if self.profile() != self.mDefault:
            self.sigProfileChanged.emit()

    def onXUnitChanged(self, unit: str):
        unit = self.mXUnitModel.findUnit(unit)
        if unit is None:
            unit = BAND_INDEX
        self.cbXUnit.setCurrentIndex(self.mXUnitModel.unitIndex(unit).row())

    def onBandsChanged(self, *args):
        self.sbBands.setValue(self.mModel.bands())
        self.onProfileChanged()

    def initConfig(self, conf: dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        pass

    def setProfile(self, profile: SpectralProfile):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        assert isinstance(profile, SpectralProfile)
        self.mDefault = profile

        self.mModel.setProfile(profile)

    def resetProfile(self):
        self.mModel.setProfile(self.mDefault)

    def profile(self) -> SpectralProfile:
        """
        Returns modified SpectralProfile
        :return: dict
        """

        return self.mModel.profile()


class SpectralProfileEditorWidgetWrapper(QgsEditorWidgetWrapper):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, editor: QWidget, parent: QWidget):
        super(SpectralProfileEditorWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.mWidget: QWidget = None

        self.mLastValue = QVariant()

    def createWidget(self, parent: QWidget):
        # log('createWidget')

        if not self.isInTable(parent):
            self.mWidget = SpectralProfileEditorWidget(parent=parent)
        else:
            self.mWidget = QLabel(' Profile', parent=parent)
        return self.mWidget

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        conf = self.config()

        if isinstance(editor, SpectralProfileEditorWidget):

            editor.sigProfileChanged.connect(self.onValueChanged)
            editor.initConfig(conf)

        elif isinstance(editor, QLabel):
            editor.setText(SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE)
            editor.setToolTip('Use Form View to edit values')

    def onValueChanged(self, *args):
        self.valuesChanged.emit(self.value())
        s = ""

    def valid(self, *args, **kwargs) -> bool:
        return isinstance(self.mWidget, (SpectralProfileEditorWidget, QLabel))

    def value(self, *args, **kwargs):
        value = self.mLastValue
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            p = w.profile()
            value = encodeProfileValueDict(p.values(), self.field())

        return value

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setEnabled(enabled)

    def setValue(self, value):
        self.mLastValue = value
        p = SpectralProfile(fields=self.layer().fields(), profile_field=self.field())
        p.setValues(profile_value_dict=decodeProfileValueDict(value))
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setProfile(p)

        # if isinstance(self.mLabel, QLabel):
        #    self.mLabel.setText(value2str(value))


class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):
        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        loadUi(speclibUiPath('spectralprofileeditorconfigwidget.ui'), self)

    def config(self, *args, **kwargs) -> dict:
        config = {}

        return config

    def setConfig(self, config: dict):
        pass


class SpectralProfileFieldFormatter(QgsFieldFormatter):

    def __init__(self, *args, **kwds):
        super(SpectralProfileFieldFormatter, self).__init__(*args, **kwds)

    def id(self) -> str:
        return EDITOR_WIDGET_REGISTRY_KEY

    def representValue(self, layer: QgsVectorLayer, fieldIndex: int, config: dict, cache, value):

        if value not in [None, NULL]:
            return SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE
        else:
            return 'NULL'
        s = ""


class SpectralProfileEditorWidgetFactory(QgsEditorWidgetFactory):

    def __init__(self, name: str):

        super(SpectralProfileEditorWidgetFactory, self).__init__(name)

        self.mConfigurations = {}

    def configWidget(self, layer: QgsVectorLayer, fieldIdx: int, parent=QWidget) -> SpectralProfileEditorConfigWidget:
        """
        Returns a SpectralProfileEditorConfigWidget
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param parent: QWidget
        :return: SpectralProfileEditorConfigWidget
        """

        w = SpectralProfileEditorConfigWidget(layer, fieldIdx, parent)
        key = self.configKey(layer, fieldIdx)
        w.setConfig(self.readConfig(key))
        w.changed.connect(lambda *args, ww=w, k=key: self.writeConfig(key, ww.config()))
        return w

    def configKey(self, layer: QgsVectorLayer, fieldIdx: int) -> typing.Tuple[str, int]:
        """
        Returns a tuple to be used as dictionary key to identify a layer profile_field configuration.
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :return: (str, int)
        """
        return layer.id(), fieldIdx

    def create(self, layer: QgsVectorLayer, fieldIdx: int, editor: QWidget,
               parent: QWidget) -> SpectralProfileEditorWidgetWrapper:
        """
        Create a SpectralProfileEditorWidgetWrapper
        :param layer: QgsVectorLayer
        :param fieldIdx: int
        :param editor: QWidget
        :param parent: QWidget
        :return: SpectralProfileEditorWidgetWrapper
        """

        w = SpectralProfileEditorWidgetWrapper(layer, fieldIdx, editor, parent)
        # self.editWrapper = w
        return w

    def writeConfig(self, key: tuple, config: dict):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :param config: dict with config values
        """
        self.mConfigurations[key] = config
        # print('Save config')
        # print(config)

    def readConfig(self, key: tuple):
        """
        :param key: tuple (str, int), as created with .configKey(layer, fieldIdx)
        :return: {}
        """
        return self.mConfigurations.get(key, {})

    def supportsField(self, vl: QgsVectorLayer, fieldIdx: int) -> bool:
        """
        :param vl:
        :param fieldIdx:
        :return:
        """
        field: QgsField = vl.fields().at(fieldIdx)
        return supports_field(field)

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain profile_field.
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
        if supports_field(field):
            if field.type() in [QVariant.ByteArray, 8]:
                return 20
            else:
                return 1
        else:
            return 0


def registerSpectralProfileEditorWidget():
    widgetRegistry = QgsGui.editorWidgetRegistry()
    fieldFormatterRegistry = QgsApplication.instance().fieldFormatterRegistry()

    if EDITOR_WIDGET_REGISTRY_KEY not in widgetRegistry.factories().keys():
        global SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
        global SPECTRAL_PROFILE_FIELD_FORMATTER
        SPECTRAL_PROFILE_FIELD_FORMATTER = SpectralProfileFieldFormatter()

        if True:
            # workaround as long human-readible name needs to be in QML
            SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
            widgetRegistry.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)
        else:
            # as it should be
            SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_NAME)
            widgetRegistry.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)

        # uncomment when https://github.com/qgis/QGIS/issues/45478 is fixed
        fieldFormatterRegistry.addFieldFormatter(SPECTRAL_PROFILE_FIELD_FORMATTER)
