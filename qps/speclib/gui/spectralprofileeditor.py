import json
import re
import typing
from copy import copy
from typing import List, Tuple

import numpy as np

from qgis.PyQt.QtCore import QAbstractTableModel, pyqtSignal, QModelIndex, Qt, QVariant, QJsonDocument, \
    QSortFilterProxyModel, NULL
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QHeaderView, QGroupBox, QWidget, QLabel, QHBoxLayout, QVBoxLayout, \
    QToolButton, QSpacerItem, QSizePolicy, QTableView, \
    QStackedWidget, \
    QFrame, QComboBox, QLineEdit
from qgis.core import Qgis, QgsVectorLayer, QgsField, QgsFieldFormatter, QgsApplication, QgsFeature
from qgis.gui import QgsEditorWidgetWrapper, QgsEditorConfigWidget, QgsGui, QgsEditorWidgetFactory, QgsCodeEditorJson, \
    QgsMessageBar
from .spectrallibraryplotwidget import SpectralProfilePlotXAxisUnitModel
from .. import EDITOR_WIDGET_REGISTRY_KEY, EDITOR_WIDGET_REGISTRY_NAME
from ..core import supports_field
from ..core.spectralprofile import encodeProfileValueDict, decodeProfileValueDict, \
    prepareProfileValueDict, ProfileEncoding, validateProfileValueDict
from ...utils import SignalBlocker

SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'

SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
SPECTRAL_PROFILE_FIELD_FORMATTER: None


class SpectralProfileTableModel(QAbstractTableModel):
    """
    A TableModel to show and edit spectral values of a SpectralProfile
    """

    profileChanged = pyqtSignal()

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

        self.dataChanged.connect(lambda: self.profileChanged())

    def clear(self):
        m = copy(self.mValues)
        self.beginResetModel()
        self.mValues.clear()
        self.endResetModel()
        if m != self.mValues:
            self.profileChanged.emit()

    def bands(self) -> int:
        return self.rowCount()

    def setProfileDict(self, profile: dict):
        """
        :param values:
        :return:
        """
        assert isinstance(profile, dict)

        m = copy(self.mValues)

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

        if m != self.mValues:
            self.profileChanged.emit()

    def profileDict(self) -> dict:
        if len(self.mValues) == 0:
            return dict()

        x = [v[1] for v in self.mValues]
        y = [v[2] for v in self.mValues]
        bbl = [v[3] for v in self.mValues]

        if np.asarray(x).dtype.subdtype is None:
            x = None

        bbl = np.asarray(bbl, dtype=bool)
        if np.all(bbl):
            bbl = None

        profile = prepareProfileValueDict(
            x=x,
            y=y,
            bbl=bbl
        )
        return profile

    def resetProfile(self):
        self.setProfileDict(self.mLastProfile)

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

    def setProfileDict(self, d: dict):
        jsonText = encodeProfileValueDict(d, ProfileEncoding.Json, jsonFormat=QJsonDocument.Indented)
        self.setText(jsonText)

    def profileDict(self) -> dict:
        text = self.text().strip()
        if text == '':
            return dict()
        else:
            return json.loads(self.text())

    def addSyntaxWarning(self, line: int, col: int, msg: str):
        self.addWarning(line, msg)
        self.setCursorPosition(line, col - 1)
        self.ensureLineVisible(line)


class SpectralProfileTableEditor(QFrame):
    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.tableView = QTableView()
        self.tableModel = SpectralProfileTableModel()
        self.tableModel.profileChanged.connect(self.profileChanged)
        self.proxyModel = QSortFilterProxyModel()
        self.tableFrame = QFrame()

        self.proxyModel.setSourceModel(self.tableModel)
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.sortByColumn(0, Qt.AscendingOrder)
        self.tableView.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tableView.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel()
        self.mXUnitModel.setAllowEmptyUnit(True)
        self.cbXUnit = QComboBox()
        self.cbXUnit.setModel(self.mXUnitModel)
        self.cbXUnit.currentTextChanged.connect(self.profileChanged)

        self.tbYUnit = QLineEdit()
        self.tbYUnit.textChanged.connect(self.profileChanged)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('X unit'))
        hbox.addWidget(self.cbXUnit)
        hbox.addWidget(QLabel('Y unit'))
        hbox.addWidget(self.tbYUnit)

        hbox.setStretchFactor(self.cbXUnit, 2)
        hbox.setStretchFactor(self.tbYUnit, 2)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tableView)
        self.setLayout(vbox)

    def clear(self):
        self.tableModel.clear()

    def setXUnit(self, unit: str):
        if self.xUnit() != unit:
            idx = self.mXUnitModel.unitIndex(unit)
            if not idx.isValid():
                # missing unit. add to unit model
                self.mXUnitModel.addUnit(unit, description=str(unit))
                idx = self.mXUnitModel.unitIndex(unit)
            if idx.isValid():
                self.cbXUnit.setCurrentIndex(idx.row())

    def setYUnit(self, unit: str):
        if self.yUnit() != unit:
            self.tbYUnit.setText(unit)

    def xUnit(self) -> str:
        return self.cbXUnit.currentData(Qt.UserRole)

    def yUnit(self) -> str:
        return self.tbYUnit.text()

    def setProfileDict(self, d: dict):
        assert isinstance(d, dict)
        self.tableModel.setProfileDict(d)

        self.setXUnit(d.get('xUnit', None))
        self.setYUnit(d.get('yUnit', None))

    def profileDict(self) -> dict:
        d = self.tableModel.profileDict()

        if len(d) == 0:
            # empty profile dict
            return dict()

        xUnit = self.xUnit()
        yUnit = self.yUnit()

        if 'x' in d.keys() and xUnit:
            d['xUnit'] = xUnit

        if 'y' in d.keys() and yUnit:
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
        self.jsonEditor.profileChanged.connect(self.editorProfileChanged)

        self.tableEditor = SpectralProfileTableEditor()
        self.tableEditor.profileChanged.connect(self.editorProfileChanged)

        self.controlBar = QHBoxLayout()
        self.btnReset = QToolButton()
        self.btnReset.setText('Reset')
        self.btnReset.setToolTip('Resets the profile')
        self.btnReset.setIcon(QIcon(':/images/themes/default/mActionUndo.svg'))
        self.btnReset.clicked.connect(self.resetProfile)

        self.btnJson = QToolButton()
        self.btnJson.setText('JSON')
        self.btnJson.setToolTip('Edit profile values in JSON editor.')
        self.btnJson.setCheckable(True)
        self.btnJson.setIcon(QIcon(':/images/themes/default/mIconFieldJson.svg'))
        self.btnJson.clicked.connect(lambda: self.setViewMode(self.VIEW_JSON_EDITOR))

        self.btnClear = QToolButton()
        self.btnClear.setText('Clear')
        self.btnClear.setToolTip('Removes the profile and replaces it with NULL')
        self.btnClear.setIcon(QIcon(':/images/themes/default/mIconClearItem.svg'))
        self.btnClear.clicked.connect(self.clear)

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
        self.controlBar.addWidget(self.btnClear)
        self.controlBar.addWidget(self.btnReset)

        for btn in [self.btnJson, self.btnTable, self.btnClear, self.btnReset]:
            btn.setAutoRaise(True)

        self.stackedWidget = QStackedWidget()
        self.stackedWidget.addWidget(self.jsonEditor)
        self.stackedWidget.addWidget(self.tableEditor)

        vbox = QVBoxLayout()
        vbox.addLayout(self.controlBar)
        vbox.addWidget(self.stackedWidget)
        self.setLayout(vbox)

        s = ""

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

    RX_JSON_ERROR = re.compile(r'(?P<msg>.*): line.*(?P<line>\d+) column.*(?P<col>\d+).*\(char.*(?P<char>\d+)\)', re.I)

    def editorProfileChanged(self):

        w = self.stackedWidget.currentWidget()

        if self.sender() != w:
            return

        self.messageBar.clearWidgets()
        self.jsonEditor.clearWarnings()
        self.jsonEditor.initializeLexer()
        self.jsonEditor.runPostLexerConfigurationTasks()

        success, error, d = self.validate()

        if not success:
            match = self.RX_JSON_ERROR.match(error)
            if w == self.jsonEditor and match:

                eline = int(match.group('line')) - 1
                ecol = int(match.group('col'))
                emsg = match.group('msg')
                self.jsonEditor.addSyntaxWarning(eline, ecol, emsg)

            else:
                self.messageBar.pushMessage('Error', error.splitlines()[0], error, Qgis.Warning)
        else:
            for editor in [self.jsonEditor, self.tableEditor]:
                if editor != w:
                    editor.setProfileDict(d)
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
        if profile in [None, NULL, QVariant(None)]:
            profile = dict()
        assert isinstance(profile, dict)
        self.mDefault = profile
        w = self.stackedWidget.currentWidget()
        with SignalBlocker(self.jsonEditor, self.tableEditor) as blocker:
            self.jsonEditor.setProfileDict(profile)
            self.tableEditor.setProfileDict(profile)

    def resetProfile(self):
        if isinstance(self.mDefault, dict):
            self.setProfile(self.mDefault)

    def validate(self) -> Tuple[bool, str, dict]:
        """
        Validates the editor widget input.
        :return: tuple (bool, str, dict) with
           bool = is valid,
           str = error message if invalid or '',
           dict = profile dictionary if valid or empty ({})
        """
        try:
            d = self.profileDict()
            if d == dict():
                # allow to return empty profiles -> will be set to NULL in vector layer
                return True, '', d
            else:
                return validateProfileValueDict(self.profileDict())
        except Exception as ex:
            return False, str(ex), dict()

    def clear(self):

        self.jsonEditor.clear()
        self.tableEditor.clear()

    def profile(self) -> dict:
        """
        Returns the spectral profile dictionary collected by profileDict. In case of inconsistencies
        the returned value is None (see `validate`).
        """
        success, err, d = self.validate()
        if success:
            return d
        else:
            return None

    def profileDict(self) -> dict:
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
            if len(p) == 0:
                value = NULL
            else:
                value = encodeProfileValueDict(p, self.field())

        return value

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


class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):
        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        self.label = QLabel('A field to store spectral profiles')
        hbox = QHBoxLayout()
        hbox.addWidget(self.label)
        self.setLayout(hbox)

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
