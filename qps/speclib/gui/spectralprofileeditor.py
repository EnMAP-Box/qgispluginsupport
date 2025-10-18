import json
import logging
import re
import warnings
from copy import copy
from math import isnan
from typing import Any, List, Optional, Tuple

import numpy as np

from qgis.PyQt.QtCore import NULL, pyqtSignal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, \
    Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QComboBox, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QSizePolicy, \
    QSpacerItem, QTableView, QToolButton, QVBoxLayout, QWidget
from qgis.core import Qgis, QgsApplication, QgsFeature, QgsField, QgsFieldFormatter, QgsFieldFormatterRegistry, \
    QgsVectorLayer
from qgis.gui import QgsCodeEditorJson, QgsEditorConfigWidget, QgsEditorWidgetFactory, QgsEditorWidgetWrapper, QgsGui
from .spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitModel
from .spectralprofileplotwidget import SpectralProfilePlotWidget
from .. import EDITOR_WIDGET_REGISTRY_KEY
from ..core import can_store_spectral_profiles
from ..core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict, \
    ProfileEncoding, validateProfileValueDict
from ...utils import SignalBlocker

logger = logging.getLogger(__name__)

SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'

_SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
_SPECTRAL_PROFILE_FIELD_FORMATTER: None


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

        self.mBooleanBBL: bool = True

        self.mIsReadOnly: bool = False

    def setReadOnly(self, read_only: bool):
        self.mIsReadOnly = read_only is True

    def setBooleanBBL(self, b: bool):
        assert isinstance(b, bool)
        self.mBooleanBBL = b

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
        self.mBooleanBBL = False
        for i, y in enumerate(yValues):
            x = xValues[i] if xValues else None
            bbl = None
            if bblValues:
                bbl = bblValues[i]
            # if bbl not in [0, 1]:
            #    self.mBooleanBBL = False
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

        x = np.asarray([v[1] for v in self.mValues])
        y = np.asarray([v[2] for v in self.mValues])
        bbl = [v[3] for v in self.mValues]

        bbl = [1 if v == None or isnan(v) else v for v in bbl]
        if all([v == 1 for v in bbl]):
            bbl = None
        if x.dtype.name == 'object':
            x = None

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
                if self.mBooleanBBL:
                    return True if bbl is None else bool(bbl)
                else:
                    if bbl is None:
                        return 1
                    return bbl

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
                # bbl values, always stored as number
                if self.mBooleanBBL:
                    bbl = int(bool(value))
                else:
                    bbl = int(value)
                item[c] = bbl

        modified = item[c] != itemOld[c]
        if modified:
            self.dataChanged.emit(index, index, [role])
            self.profileChanged.emit()
        return modified

    def flags(self, index):
        if index.isValid():
            c = index.column()
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if c in [1, 2, 3] and not self.mIsReadOnly:
                flags = flags | Qt.ItemIsEditable
            return flags
        return None

    def headerData(self, col: int, orientation: Qt.Orientation, role: int):

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
        self.setProfileDict(d)

    def setProfileDict(self, d: dict):
        jsonData = encodeProfileValueDict(d, ProfileEncoding.Dict)

        if jsonData:
            jsonText = json.dumps(jsonData, ensure_ascii=True, allow_nan=True, indent=2)
        else:
            jsonText = None
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


class CustomEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, dict):
            obj = {k: (self.encode(v) if isinstance(v, list) else v) for k, v in obj.items()}
        if isinstance(obj, list):
            return '[' + ', '.join(map(json.dumps, obj)) + ']'
        return super().encode(obj)


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

        self.mXUnitModel: SpectralProfilePlotXAxisUnitModel = SpectralProfilePlotXAxisUnitModel.instance()
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

    def setReadOnly(self, read_only: bool):
        self.cbXUnit.setEnabled(not read_only)
        self.tbYUnit.setReadOnly(read_only)
        self.tableModel.setReadOnly(read_only)

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
            else:
                # select the empty unit
                self.cbXUnit.setCurrentIndex(0)

    def setYUnit(self, unit: str):
        if self.yUnit() != unit:
            self.tbYUnit.setText(unit)

    def xUnit(self) -> str:
        return self.cbXUnit.currentData(Qt.UserRole)

    def yUnit(self) -> str:
        return self.tbYUnit.text()

    def setProfile(self, d: dict):
        self.setProfileDict(d)

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

        d = prepareProfileValueDict(prototype=d,
                                    xUnit=self.xUnit(),
                                    yUnit=self.yUnit())

        return d


class SpectralProfileEditorWidget(QGroupBox):
    VIEW_TABLE = 1
    VIEW_JSON_EDITOR = 2
    VIEW_PLOT = 3

    CNT = 0

    profileChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralProfileEditorWidget, self).__init__(*args, **kwds)
        self.setWindowIcon(QIcon(':/qps/ui/icons/profile.svg'))

        # self.messageBar = QgsMessageBar()
        # the default profile (from vector layer)
        self.mDefaultProfile: Optional[dict] = None

        # the current widget to show the current profile
        self.mCurrentWidget: Optional[QWidget] = None

        # the potentially modified profile
        self.mCurrentProfile: Optional[dict] = None

        self.mReadOnly: bool = True

        self.controlBar = QHBoxLayout()
        self.controlBar.setSpacing(1)
        self.btnReset = QToolButton()
        self.btnReset.setText('Reset')
        self.btnReset.setToolTip('Resets the profile')
        self.btnReset.setIcon(QIcon(':/images/themes/default/mActionUndo.svg'))
        self.btnReset.clicked.connect(self.resetProfile)
        self.btnReset.setVisible(False)

        self.btnPlot = QToolButton()
        self.btnPlot.setText('Profile')
        self.btnPlot.setToolTip('View profile in plot.')
        self.btnPlot.setCheckable(True)
        self.btnPlot.setIcon(QIcon(':/qps/ui/icons/speclib_plot.svg'))
        self.btnPlot.clicked.connect(lambda: self.setViewMode(self.VIEW_PLOT))

        self.btnJson = QToolButton()
        self.btnJson.setText('JSON')
        self.btnJson.setToolTip('View/edit profile values in JSON editor.')
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

        self.controlBar.addWidget(self.btnPlot)
        self.controlBar.addWidget(self.btnJson)
        self.controlBar.addWidget(self.btnTable)
        # self.controlBar.addWidget(self.messageBar)
        self.controlBar.addSpacerItem(QSpacerItem(0, 0, hPolicy=QSizePolicy.Expanding))
        self.controlBar.addWidget(self.btnClear)
        self.controlBar.addWidget(self.btnReset)

        for btn in [self.btnPlot, self.btnJson, self.btnTable, self.btnClear, self.btnReset]:
            btn.setAutoRaise(True)

        vbox = QVBoxLayout()
        vbox.setSpacing(1)
        vbox.addLayout(self.controlBar)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(5)
        self._vbox = vbox
        self.setLayout(vbox)
        self.setViewMode(self.VIEW_JSON_EDITOR)
        s = ""

    def setReadOnly(self, read_only: bool):
        """
        Enables / disables the widgets to modify values
        :param read_only:
        :return:
        """
        self.mReadOnly = read_only

        if isinstance(self.mCurrentWidget, (SpectralProfileJsonEditor, SpectralProfileTableEditor)):
            self.mCurrentWidget.setReadOnly(read_only)
        self.btnClear.setDisabled(read_only)
        self.btnClear.setVisible(not read_only)

    def updateCurrentWidget(self, mode: int):

        current_profile = self.currentProfile()

        if mode == self.VIEW_JSON_EDITOR and not isinstance(self.mCurrentWidget, SpectralProfileJsonEditor):
            cw_new = SpectralProfileJsonEditor()
            cw_new.setLineNumbersVisible(True)
            cw_new.setFoldingVisible(True)
            if current_profile:
                cw_new.setProfile(current_profile)
            cw_new.profileChanged.connect(self.editorProfileChanged)

        elif mode == self.VIEW_TABLE and not isinstance(self.mCurrentWidget, SpectralProfileTableEditor):
            cw_new = SpectralProfileTableEditor()
            if current_profile:
                cw_new.setProfile(current_profile)
            cw_new.profileChanged.connect(self.editorProfileChanged)

        elif mode == self.VIEW_PLOT and not isinstance(self.mCurrentWidget, SpectralProfilePlotWidget):
            cw_new = SpectralProfilePlotWidget()
            if current_profile:
                cw_new.setProfile(current_profile)
        else:
            # no need to create a new widget
            cw_new = None

        if isinstance(cw_new, QWidget):
            if isinstance(self.mCurrentWidget, QWidget):
                self._vbox.removeWidget(self.mCurrentWidget)
                self.mCurrentWidget.deleteLater()
            self._vbox.addWidget(cw_new)
            self.mCurrentWidget = cw_new
            # remove old CW

    def setViewMode(self, mode: int):

        self.updateCurrentWidget(mode)
        cw = self.mCurrentWidget
        self.btnJson.setChecked(isinstance(cw, SpectralProfileJsonEditor))
        self.btnTable.setChecked(isinstance(cw, SpectralProfileTableEditor))
        self.btnPlot.setChecked(isinstance(cw, SpectralProfilePlotWidget))

    def viewMode(self) -> int:
        cw = self.mCurrentWidget
        if isinstance(cw, SpectralProfileJsonEditor):
            return self.VIEW_JSON_EDITOR
        elif isinstance(cw, SpectralProfileTableEditor):
            return self.VIEW_TABLE
        elif isinstance(cw, SpectralProfilePlotWidget):
            return self.VIEW_PLOT
        else:
            raise NotImplementedError()

    RX_JSON_ERROR = re.compile(r'(?P<msg>.*): line.*(?P<line>\d+) column.*(?P<col>\d+).*\(char.*(?P<char>\d+)\)', re.I)

    def editorProfileChanged(self):

        w = self.mCurrentWidget

        if self.sender() != w:
            return

        success, error, d = self.validate()

        if isinstance(w, SpectralProfileJsonEditor):
            w.clearWarnings()
            w.initializeLexer()
            w.runPostLexerConfigurationTasks()

        if not success:
            match = self.RX_JSON_ERROR.match(error)
            if isinstance(w, SpectralProfileJsonEditor) and match:
                eline = int(match.group('line')) - 1
                ecol = int(match.group('col'))
                emsg = match.group('msg')
                w.addSyntaxWarning(eline, ecol, emsg)

            else:
                QgsApplication.messageLog().logMessage(error, 'SpectralProfileEditorWidget', Qgis.Critical)
                # self.messageBar.pushMessage('Error', error.splitlines()[0], error, Qgis.Warning)
        else:
            self.profileChanged.emit()

    def initConfig(self, conf: dict):
        """
        Initializes widget elements like QComboBoxes etc.
        :param conf: dict
        """
        SpectralProfileEditorWidget.CNT += 1
        logger.debug(f'initConfig #{self.CNT}')

    def setProfile(self, profile: dict):
        """
        Sets the profile values to be shown
        :param values: dict() or SpectralProfile
        :return:
        """
        if profile in [None, NULL, QVariant(None)]:
            profile = dict()
        assert isinstance(profile, dict)
        self.mDefaultProfile = self.mCurrentProfile = profile.copy()

        if isinstance(self.mCurrentWidget,
                      (SpectralProfileJsonEditor, SpectralProfileTableEditor, SpectralProfilePlotWidget)):
            with SignalBlocker(self.mCurrentWidget) as blocker:
                self.mCurrentWidget.setProfile(self.mCurrentProfile)

        # w = self.stackedWidget.currentWidget()
        # with SignalBlocker(self.jsonEditor, self.tableEditor, self.plotView) as blocker:
        #    self.jsonEditor.setProfileDict(profile)
        #    self.tableEditor.setProfileDict(profile)
        #    self.plotView.setProfile(profile)

    def resetProfile(self):
        if isinstance(self.mDefaultProfile, dict):
            self.setProfile(self.mDefaultProfile)

    def validate(self) -> Tuple[bool, str, dict]:
        """
        Validates the editor widget input.
        :return: tuple (bool, str, dict) with
           bool = is valid,
           str = error message if invalid or '',
           dict = profile dictionary if valid or empty ({})
        """
        try:
            return validateProfileValueDict(self.currentProfile(), allowEmpty=True)
        except Exception as ex:
            return False, str(ex), dict()

    def clear(self):

        d = {}
        self.setProfile(d)

    def profile(self) -> Optional[dict]:
        """
        Returns a value spectral profile dictionary collected by profileDict or None, if internal state does not
        return a valid profile dictionary,
        the returned value is None (see `validate`).
        """
        success, err, d = self.validate()
        if d == dict() or not success:
            return None
        else:
            return d

    def currentProfile(self) -> dict:
        """
        Return the data as new SpectralProfile
        :return:
        :rtype:
        """
        cw = self.mCurrentWidget
        cp = self.mCurrentProfile
        if isinstance(cw, SpectralProfileJsonEditor):
            cp = cw.profileDict()
        elif isinstance(cw, SpectralProfileTableEditor):
            cp = cw.profileDict()
        self.mCurrentProfile = cp
        return cp


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
            if p is None:
                value = NULL
            else:
                value = encodeProfileValueDict(p, self.field())

        return value

    def setFeature(self, feature: QgsFeature) -> None:
        super(SpectralProfileEditorWidgetWrapper, self).setFeature(feature)

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setReadOnly(not enabled)

    def setValue(self, value: Any) -> None:
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

    def configKey(self, layer: QgsVectorLayer, fieldIdx: int) -> Tuple[str, int]:
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
        return can_store_spectral_profiles(field)

    def fieldScore(self, vl: QgsVectorLayer, fieldIdx: int) -> int:
        """
        This method allows disabling this editor widget type for a certain profile_field.

        :param vl: QgsVectorLayer
        :param fieldIdx: int
        :return: int
        """
        # log(' fieldScore()')
        field = vl.fields().at(fieldIdx)
        assert isinstance(field, QgsField)
        if can_store_spectral_profiles(field):
            if field.editorWidgetSetup().type() == self.name():
                return 20  # specialized support
            else:
                return 5  # basic support
        else:
            return 0  # no support


_SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = None
_SPECTRAL_PROFILE_FIELD_FORMATTER = None


def spectralProfileEditorWidgetFactory(register: bool = True) -> SpectralProfileEditorWidgetFactory:
    global _SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
    global _SPECTRAL_PROFILE_FIELD_FORMATTER
    if not isinstance(_SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY, SpectralProfileEditorWidgetFactory):
        _SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)

    if not isinstance(_SPECTRAL_PROFILE_FIELD_FORMATTER, SpectralProfileFieldFormatter):
        _SPECTRAL_PROFILE_FIELD_FORMATTER = SpectralProfileFieldFormatter()

        if register:
            fmtReg: QgsFieldFormatterRegistry = QgsApplication.instance().fieldFormatterRegistry()
            fmtReg.addFieldFormatter(_SPECTRAL_PROFILE_FIELD_FORMATTER)

    reg: QgsEditorWidgetFactory = QgsGui.editorWidgetRegistry()

    if register and EDITOR_WIDGET_REGISTRY_KEY not in reg.factories().keys():
        reg.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, _SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)

    return reg.factory(EDITOR_WIDGET_REGISTRY_KEY)


def registerSpectralProfileEditorWidget():
    warnings.warn(DeprecationWarning('Use spectralprofileeditor.spectralProfileEditorWidgetFactory(True)'),
                  stacklevel=2)
    spectralProfileEditorWidgetFactory(True)
