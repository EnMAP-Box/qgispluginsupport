import json
import typing
from copy import copy
from typing import List, Tuple

import numpy as np
from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import QAbstractTableModel, pyqtSignal, QModelIndex, Qt, QVariant
from qgis.PyQt.QtCore import QJsonDocument, QSortFilterProxyModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QGroupBox, QWidget, QLabel
from qgis.PyQt.QtWidgets import QHBoxLayout, QVBoxLayout, QToolButton, QSpacerItem, QSizePolicy, QTableView, \
    QStackedWidget, \
    QFrame, QComboBox, QLineEdit
from qgis.core import Qgis, QgsVectorLayer, QgsField, QgsFieldFormatter, QgsApplication, QgsFeature
from qgis.gui import QgsEditorWidgetWrapper, QgsEditorConfigWidget, QgsGui, QgsJsonEditWidget, \
    QgsEditorWidgetFactory, QgsCodeEditorJson, QgsMessageBar

from .spectrallibraryplotwidget import SpectralProfilePlotXAxisUnitModel
from .. import speclibUiPath, EDITOR_WIDGET_REGISTRY_KEY, EDITOR_WIDGET_REGISTRY_NAME
from ..core import supports_field
from ..core.spectralprofile import SpectralProfile, encodeProfileValueDict, decodeProfileValueDict, \
    prepareProfileValueDict, ProfileEncoding
from ...unitmodel import BAND_INDEX
from ...utils import loadUi

SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'

SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
SPECTRAL_PROFILE_FIELD_FORMATTER: None


class SpectralProfileTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """

    def __init__(self, *args, **kwds):
        super(SpectralProfileTableModel, self).__init__(*args, **kwds)

        self.mColumnNames = {0: '#',
                             1: 'x',
                             2: 'y',
                             3: 'bbl'}
        self.mXUnit = None
        self.mYUnit = None

        self.mValues: List[dict] = list()

        self.mLastProfile: dict = dict()
        self.mCurrentProfile: dict = dict()

    def bands(self) -> int:
        return self.rowCount()

    def setProfile(self, profile: dict):
        """
        :param values:
        :return:
        """
        assert isinstance(profile, dict)

        self.beginResetModel()
        self.mValues.clear()
        self.mLastProfile = profile
        xValues = profile.get('x', None)
        yValues = profile.get('y', [])
        bblValues = profile.get('bbl', None)
        for i, y in enumerate(yValues):
            x = xValues[i] if xValues else None
            bbl = int(bblValues[i]) if bblValues else 1

            item = {0: i + 1,
                    1: x,
                    2: y,
                    3: bbl}
            self.mValues.append(item)

        self.endResetModel()

    def profileDict(self) -> dict:
        x = [v[1] for v in self.mValues]
        y = [v[2] for v in self.mValues]
        bbl = [v[3] for v in self.mValues]
        if np.all(np.asarray(bbl, dtype=bool)):
            bbl = None
        profile = prepareProfileValueDict(
            x=x,
            y=y,
            bbl=bbl
        )
        return profile

    def resetProfile(self):
        self.setProfile(self.mLastProfile)

    def rowCount(self, parent: QModelIndex = None, *args, **kwargs) -> int:

        return len(self.mValues)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.mColumnNames)

    def data(self, index, role=Qt.DisplayRole):
        if role is None or not index.isValid():
            return None
        if index.row() >= len(self.mValues):
            return False

        c = index.column()
        i = index.row()

        item = self.mValues[i]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            if c == 0:
                return i + 1

            if c in [1, 2]:
                return str(item[c])

            elif c == 3:
                bbl = item[c]
                if bbl is None:
                    return True
                else:
                    return bool(bbl)

        return None

    def stringToType(self, value: str):
        """
        Converts a string input into a matching int, float or datetime
        """

        t = str
        for candidate in [float, int]:
            try:
                _ = candidate(value)
                t = candidate
            except ValueError:
                break
        return t(value)

    def setData(self, index, value, role=None):
        if role is None or not index.isValid():
            return None

        c = index.column()
        i = index.row()

        item = self.mValues[i]
        itemOld = copy(item)
        modified = False

        if role == Qt.EditRole:
            if c in [1, 2]:
                # x / y values
                item[c] = self.stringToType(value)

            elif c == 3:
                # bbl values
                bbl = bool(value)
                if bbl:
                    item[c] = 1
                else:
                    item[c] = 0

        modified = item[c] != itemOld[c]
        if modified:
            self.dataChanged.emit(index, index, [role])
        return modified

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if c in [1, 2, 3]:
                flags = flags | Qt.ItemIsEditable
            return flags
        return None

    def headerData(self, col: int, orientation, role):

        if orientation == Qt.Horizontal and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            return self.mColumnNames.get(col, f'{col + 1}')
        if orientation == Qt.Vertical:
            if role == Qt.ToolTipRole:
                return f'Band {col + 1}'
        return None


class SpectralProfileJsonEditor(QgsCodeEditorJson):
    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.setFoldingVisible(True)
        self.setLineNumbersVisible(True)

        self.textChanged.connect(self.profileChanged)

    def setProfile(self, d: dict):
        jsonText = encodeProfileValueDict(d, ProfileEncoding.Json, jsonFormat=QJsonDocument.Indented)
        self.setText(jsonText)

    def profileDict(self) -> dict:
        return json.loads(self.text())


class SpectralProfileTableEditor(QFrame):
    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.tableView = QTableView()
        self.tableModel = SpectralProfileTableModel()
        self.tableModel.dataChanged.connect(self.profileChanged)
        self.proxyModel = QSortFilterProxyModel()
        self.tableFrame = QFrame()

        self.proxyModel.setSourceModel(self.tableModel)
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.cbXUnit = QComboBox()
        self.cbXUnit.currentTextChanged.connect(self.profileChanged)
        self.cbXUnit.setModel(self.mXUnitModel)

        self.tbYUnit = QLineEdit()
        self.tbYUnit.textChanged.connect(self.profileChanged)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('X unit'))
        hbox.addWidget(self.cbXUnit)
        hbox.addWidget(QLabel('Y unit'))
        hbox.addWidget(self.tbYUnit)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tableView)
        self.setLayout(vbox)

    def setXUnit(self, unit: str):
        if self.xUnit() != unit:
            self.cbXUnit.setCurrentText(unit)

    def setYUnit(self, unit: str):
        if self.yUnit() != unit:
            self.tbYUnit.setText(unit)

    def xUnit(self) -> str:
        return self.cbXUnit.currentData(Qt.UserRole)

    def yUnit(self) -> str:
        return self.tbYUnit.text()

    def setProfile(self, d: dict):

        self.tableModel.setProfile(d)

        self.setXUnit(d.get('xUnit', None))
        self.setYUnit(d.get('yUnit', None))

    def profileDict(self) -> dict:
        d = self.tableModel.profileDict()
        xUnit = self.xUnit()
        yUnit = self.yUnit()

        if xUnit:
            d['xUnit'] = xUnit

        if yUnit:
            d['yUnit'] = yUnit

        return d


class SpectralProfileEditorWidget(QGroupBox):
    VIEW_TABLE = 1
    VIEW_JSON_EDITOR = 2

    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget, self).__init__(*args, **kwds)
        self.setWindowIcon(QIcon(':/qps/ui/icons/profile.svg'))
        self.mDefault: dict = False

        self.messageBar = QgsMessageBar()

        self.jsonEditor = SpectralProfileJsonEditor()
        self.jsonEditor.profileChanged.connect(self.onProfileChanged)

        self.tableEditor = SpectralProfileTableEditor()
        self.tableEditor.profileChanged.connect(self.onProfileChanged)

        self.controlBar = QHBoxLayout()
        self.btnReset = QToolButton()
        self.btnReset.setText('Reset')
        self.btnReset.setIcon(QIcon(':/images/themes/default/mActionUndo.svg'))
        self.btnReset.clicked.connect(self.resetProfile)

        self.btnJson = QToolButton()
        self.btnJson.setText('JSON')
        self.btnJson.setToolTip('Edit profile values in JSON editor.')
        self.btnJson.setCheckable(True)
        self.btnJson.setIcon(QIcon(':/images/themes/default/mIconFieldJson.svg'))
        self.btnJson.clicked.connect(lambda: self.setViewMode(self.VIEW_JSON_EDITOR))

        self.btnTable = QToolButton()
        self.btnTable.setCheckable(True)
        self.btnTable.setText('Table')
        self.btnTable.setToolTip('Edit profile values in table editor.')
        self.btnTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        self.btnTable.clicked.connect(lambda: self.setViewMode(self.VIEW_TABLE))

        self.controlBar.addWidget(self.btnJson)
        self.controlBar.addWidget(self.btnTable)
        self.controlBar.addWidget(self.messageBar)
        self.controlBar.addSpacerItem(QSpacerItem(0, 0, hPolicy=QSizePolicy.Expanding))
        self.controlBar.addWidget(self.btnReset)

        self.stackedWidget = QStackedWidget()
        self.stackedWidget.addWidget(self.jsonEditor)
        self.stackedWidget.addWidget(self.tableEditor)

        vbox = QVBoxLayout()
        vbox.addLayout(self.controlBar)
        vbox.addWidget(self.stackedWidget)
        self.setLayout(vbox)

    def setViewMode(self, mode: int):

        if mode == self.VIEW_JSON_EDITOR:
            self.stackedWidget.setCurrentWidget(self.jsonEditor)
        elif mode == self.VIEW_TABLE:
            self.stackedWidget.setCurrentWidget(self.tableEditor)

        self.btnJson.setChecked(self.stackedWidget.currentWidget() == self.jsonEditor)
        self.btnTable.setChecked(self.stackedWidget.currentWidget() == self.tableEditor)

    def viewMode(self) -> int:
        w = self.stackedWidget.currentWidget()
        if w == self.jsonEditor:
            return self.VIEW_JSON_EDITOR
        if w == self.tableView:
            return self.VIEW_TABLE
        raise NotImplementedError()

    def onProfileChanged(self):
        self.messageBar.clearWidgets()
        w = self.stackedWidget.currentWidget()

        if self.sender() != w:
            return

        self.jsonEditor.clearWarnings()
        self.jsonEditor.initializeLexer()
        self.jsonEditor.runPostLexerConfigurationTasks()

        success, error = self.validate()

        if not success:
            self.messageBar.pushMessage('Error', error.splitlines()[0], error, Qgis.Warning)
        else:
            d = self.profile()
            for editor in [self.jsonEditor, self.tableEditor]:
                if editor != w:
                    editor.setProfile(d)
            self.profileChanged.emit()

    def initConfig(self, conf: dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """

        pass

    def setProfile(self, profile: dict):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        assert isinstance(profile, dict)
        self.mDefault = profile
        w = self.stackedWidget.currentWidget()
        self.jsonEditor.setProfile(profile)
        self.tableEditor.setProfile(profile)

    def resetProfile(self):
        if isinstance(self.mDefault, dict):
            self.setProfile(self.mDefault)

    def validate(self) -> Tuple[bool, str]:

        try:
            d = self.profile()

            # enhanced consistency checks
            y = d.get('y', None)
            assert isinstance(y, list), 'Missing y values'
            assert len(y) > 0, 'Missing y values'
            arr = np.asarray(y)
            assert np.issubdtype(arr.dtype, np.number), 'all y values need to be numeric (float/int)'

            x = d.get('x', None)
            if isinstance(x, list):
                assert len(x) == len(y), f'Requires {len(y)} x values instead of {len(x)}'
                if not isinstance(x[0], str):
                    arr = np.asarray(x).dtype
                    assert np.issubdtype(arr, np.number), 'all x values need to be numeric (float/int)'

        except Exception as ex:
            return False, str(ex)
        else:
            return True, ''

    def profile(self) -> dict:
        """
        Return the data as new SpectralProfile
        :return:
        :rtype:
        """
        w = self.stackedWidget.currentWidget()
        if w == self.jsonEditor:
            return w.profileDict()
        elif w == self.tableEditor:
            return w.profileDict()
        else:
            raise NotImplementedError()


class SpectralProfileEditorWidget_OLD(QGroupBox):
    sigProfileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget_OLD, self).__init__(*args, **kwds)
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

    def setProfile(self, profile: dict):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        assert isinstance(profile, dict)
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

        self.mLastValue: QVariant = QVariant()
        s = ""

    def createWidget(self, parent: QWidget):
        # log('createWidget')

        if not self.isInTable(parent):
            self.mWidget = SpectralProfileEditorWidget(parent=parent)
        else:
            self.mWidget = QLabel('Profile', parent=parent)
        return self.mWidget

    def initWidget(self, editor: QWidget):
        # log(' initWidget')
        conf = self.config()

        if isinstance(editor, SpectralProfileEditorWidget):

            editor.profileChanged.connect(self.onValueChanged)
            editor.initConfig(conf)

        elif isinstance(editor, QLabel):
            editor.setText(f'{SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE} ({self.field().typeName()})')
            editor.setToolTip('Use Form View to edit values')

    def onValueChanged(self, *args):
        self.valuesChanged.emit(self.value())

    def valid(self, *args, **kwargs) -> bool:
        return isinstance(self.mWidget, (SpectralProfileEditorWidget, QLabel))

    def value(self, *args, **kwargs):
        value = self.mLastValue
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            p = w.profile()
            if isinstance(p, dict) and len(p.get('x', [])) > 0:
                value = encodeProfileValueDict(p.values(), self.field())

        return QVariant(value)

    def setFeature(self, feature: QgsFeature) -> None:
        super(SpectralProfileEditorWidgetWrapper, self).setFeature(feature)

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setEnabled(enabled)

    def setValue(self, value: typing.Any) -> None:
        self.mLastValue = value
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setProfile(decodeProfileValueDict(value))
        if isinstance(w, QgsJsonEditWidget):
            pass


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
            # return f'{SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE} ({layer.fields().at(fieldIndex).typeName()})'
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
