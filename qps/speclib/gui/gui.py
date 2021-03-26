# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/gui.py
    Functionality to plot SpectralLibraries
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import sys
import warnings

import enum
import typing
import numpy as np
from PyQt5.QtWidgets import QToolBar, QHBoxLayout, QVBoxLayout, QToolButton

from qgis.PyQt.QtCore import Qt, pyqtSignal, QModelIndex, QAbstractTableModel, QVariant, NULL
from qgis.PyQt.QtWidgets import QLabel, QPushButton, QFrame, QAction, \
    QWidget, QWidgetAction, QMenu, QGroupBox, QDialog
from qgis.PyQt.QtGui import QDragEnterEvent, QIcon, QContextMenuEvent
from qgis.core import \
    QgsFeature, QgsFieldFormatter, QgsApplication, \
    QgsVectorLayer, QgsField, QgsExpression, QgsFieldProxyModel

from qgis.gui import \
    QgsEditorWidgetWrapper, QgsAttributeTableView, \
    QgsActionMenu, QgsEditorWidgetFactory, QgsStatusBar, \
    QgsDualView, QgsGui, QgsMapCanvas, QgsDockWidget, QgsEditorConfigWidget, \
    QgsAttributeTableFilterModel, QgsFieldExpressionWidget

# from .math import SpectralAlgorithm, SpectralMathResult, XUnitConversion
from .spectrallibraryplotwidget import SpectralLibraryPlotItem, SpectralLibraryPlotStats, SpectralProfilePlotWidget, \
    SpectralLibraryPlotWidget
from ...utils import SpatialPoint, SpatialExtent, loadUi
from .. import EDITOR_WIDGET_REGISTRY_KEY, speclibUiPath
from ...unitmodel import XUnitModel, BAND_INDEX, BAND_NUMBER
from ..core.spectralprofile import SpectralProfile, SpectralProfileKey, encodeProfileValueDict, decodeProfileValueDict
from ..core.spectrallibrary import SpectralLibrary, AbstractSpectralLibraryIO
from ..processing import SpectralProcessingWidget
from ...layerproperties import AttributeTableWidget, showLayerPropertiesDialog
from ...plotstyling.plotstyling import PlotStyleWidget, PlotStyle

SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY: None
SPECTRAL_PROFILE_FIELD_FORMATTER: None
SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE = 'Profile'


# do not show spectral processing widget in production releases
# SHOW_SPECTRAL_PROCESSING_WIDGETS: bool = os.environ.get('DEBUG', 'false').lower() in ['1', 'true']


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
        if np.any(bbl == False) == False:
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
                except:
                    pass
            elif c == 1:
                try:
                    self.mValuesY[i] = float(value)
                    modified = True
                except:
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
        self.mXUnitModel: XUnitModel = XUnitModel()
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
            value = encodeProfileValueDict(p.values())

        return value

    def setEnabled(self, enabled: bool):
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setEnabled(enabled)

    def setValue(self, value):
        self.mLastValue = value
        p = SpectralProfile(values=decodeProfileValueDict(value))
        w = self.widget()
        if isinstance(w, SpectralProfileEditorWidget):
            w.setProfile(p)

        # if isinstance(self.mLabel, QLabel):
        #    self.mLabel.setText(value2str(value))


class SpectralProfileEditorConfigWidget(QgsEditorConfigWidget):

    def __init__(self, vl: QgsVectorLayer, fieldIdx: int, parent: QWidget):

        super(SpectralProfileEditorConfigWidget, self).__init__(vl, fieldIdx, parent)
        loadUi(speclibUiPath('spectralprofileeditorconfigwidget.ui'), self)

        self.mLastConfig: dict = {}
        self.MYCACHE = dict()
        self.mFieldExpressionName: QgsFieldExpressionWidget
        self.mFieldExpressionSource: QgsFieldExpressionWidget

        self.mFieldExpressionName.setLayer(vl)
        self.mFieldExpressionSource.setLayer(vl)

        self.mFieldExpressionName.setFilters(QgsFieldProxyModel.String)
        self.mFieldExpressionSource.setFilters(QgsFieldProxyModel.String)

        self.mFieldExpressionName.fieldChanged[str, bool].connect(self.onFieldChanged)
        self.mFieldExpressionSource.fieldChanged[str, bool].connect(self.onFieldChanged)

    def onFieldChanged(self, expr: str, valid: bool):
        if valid:
            self.changed.emit()

    def expressionName(self) -> QgsExpression:
        exp = QgsExpression(self.mFieldExpressionName.expression())
        return exp

    def expressionSource(self) -> QgsExpression:
        exp = QgsExpression(self.mFieldExpressionSource.expression())
        return exp

    def config(self, *args, **kwargs) -> dict:
        config = {'expressionName': self.mFieldExpressionName.expression(),
                  'expressionSource': self.mFieldExpressionSource.expression(),
                  'mycache': self.MYCACHE}

        return config

    def setConfig(self, config: dict):
        self.mLastConfig = config
        field: QgsField = self.layer().fields().at(self.field())
        defaultExprName = "format('Profile %1 {}',$id)".format(field.name())
        defaultExprSource = ""
        # set some defaults
        if True:
            for field in self.layer().fields():
                assert isinstance(field, QgsField)
                if field.name() == 'name':
                    defaultExprName = f'"{field.name()}"'
                if field.name() == 'source':
                    defaultExprSource = f'"{field.name()}"'

        self.mFieldExpressionName.setExpression(config.get('expressionName', defaultExprName))
        self.mFieldExpressionSource.setExpression(config.get('expressionSource', defaultExprSource))
        # print('setConfig')


class SpectralProfileFieldFormatter(QgsFieldFormatter):

    def __init__(self, *args, **kwds):
        super(SpectralProfileFieldFormatter, self).__init__(*args, **kwds)

    def id(self) -> str:
        return EDITOR_WIDGET_REGISTRY_KEY

    def representValue(self, layer: QgsVectorLayer, fieldIndex: int, config: dict, cache, value):

        if value not in [None, NULL]:
            return SPECTRAL_PROFILE_FIELD_REPRESENT_VALUE
        else:
            return 'Empty'
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
        Returns a tuple to be used as dictionary key to identify a layer field configuration.
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
        return field.type() == QVariant.ByteArray

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
        if field.type() == QVariant.ByteArray:
            return 20
        else:
            return 0


def registerSpectralProfileEditorWidget():
    widgetRegistry = QgsGui.editorWidgetRegistry()
    fieldFormaterRegistry = QgsApplication.instance().fieldFormatterRegistry()

    if not EDITOR_WIDGET_REGISTRY_KEY in widgetRegistry.factories().keys():
        global SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY
        global SPECTRAL_PROFILE_FIELD_FORMATTER
        SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY = SpectralProfileEditorWidgetFactory(EDITOR_WIDGET_REGISTRY_KEY)
        SPECTRAL_PROFILE_FIELD_FORMATTER = SpectralProfileFieldFormatter()
        widgetRegistry.registerWidget(EDITOR_WIDGET_REGISTRY_KEY, SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY)
        fieldFormaterRegistry.addFieldFormatter(SPECTRAL_PROFILE_FIELD_FORMATTER)
        s = ""


class SpectralLibraryWidget(AttributeTableWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)
    sigCurrentProfilesChanged = pyqtSignal(list)

    class ViewType(enum.Enum):
        AttributeTable = enum.auto()
        FormView = enum.auto()
        ProcessingView = enum.auto()

    def __init__(self, *args, speclib: SpectralLibrary = None, mapCanvas: QgsMapCanvas = None, **kwds):

        if not isinstance(speclib, SpectralLibrary):
            speclib = SpectralLibrary()

        super().__init__(speclib)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib.svg'))
        self.mQgsStatusBar = QgsStatusBar(self.statusBar())
        self.mQgsStatusBar.setParentStatusBar(self.statusBar())
        self.mStatusLabel: SpectralLibraryInfoLabel = SpectralLibraryInfoLabel()
        self.mStatusLabel.setTextFormat(Qt.RichText)
        self.mQgsStatusBar.addPermanentWidget(self.mStatusLabel, 1, QgsStatusBar.AnchorLeft)

        self.mIODialogs: typing.List[QWidget] = list()

        from ..io.envi import EnviSpectralLibraryIO
        from ..io.csvdata import CSVSpectralLibraryIO
        from ..io.asd import ASDSpectralLibraryIO
        from ..io.ecosis import EcoSISSpectralLibraryIO
        from ..io.specchio import SPECCHIOSpectralLibraryIO
        from ..io.artmo import ARTMOSpectralLibraryIO
        from ..io.vectorsources import VectorSourceSpectralLibraryIO
        from ..io.rastersources import RasterSourceSpectralLibraryIO
        self.mSpeclibIOInterfaces = [
            EnviSpectralLibraryIO(),
            CSVSpectralLibraryIO(),
            ARTMOSpectralLibraryIO(),
            ASDSpectralLibraryIO(),
            EcoSISSpectralLibraryIO(),
            SPECCHIOSpectralLibraryIO(),
            VectorSourceSpectralLibraryIO(),
            RasterSourceSpectralLibraryIO(),
        ]

        self.mSpeclibIOInterfaces = sorted(self.mSpeclibIOInterfaces, key=lambda c: c.__class__.__name__)

        self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        self.mSpeclibPlotWidget: SpectralProfilePlotWidget = SpectralLibraryPlotWidget()
        assert isinstance(self.mSpeclibPlotWidget, SpectralLibraryPlotWidget)
        self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mStatusLabel.setPlotWidget(self.mSpeclibPlotWidget)
        self.mSpeclibPlotWidget.plotWidget.mUpdateTimer.timeout.connect(self.mStatusLabel.update)

        self.pageProcessingWidget: SpectralProcessingWidget = SpectralProcessingWidget()
        self.pageProcessingWidget.sigSpectralProcessingModelChanged.connect(
            lambda *args: self.mSpeclibPlotWidget.addSpectralModel(self.pageProcessingWidget.model()))

        l = QVBoxLayout()
        l.addWidget(self.mSpeclibPlotWidget)
        # l.addWidget(self.pageProcessingWidget)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        self.widgetRight.setLayout(l)
        self.widgetRight.setVisible(True)

        self.widgetCenter.addWidget(self.pageProcessingWidget)
        self.widgetCenter.currentChanged.connect(self.onCenterWidgetChanged)
        self.mMainView.formModeChanged.connect(self.onCenterWidgetChanged)

        # define Actions and Options

        self.actionSelectProfilesFromMap = QAction(r'Select Profiles from Map')
        self.actionSelectProfilesFromMap.setToolTip(r'Select new profile from map')
        self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddProfiles = QAction('Add Profile(s)')
        self.actionAddProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.actionAddCurrentProfiles = QAction('Add Profiles(s)')
        self.actionAddCurrentProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.optionAddCurrentProfilesAutomatically = QAction('Add profiles automatically')
        self.optionAddCurrentProfilesAutomatically.setToolTip('Activate to add profiles automatically '
                                                              'into the spectral library')
        self.optionAddCurrentProfilesAutomatically.setIcon(QIcon(':/qps/ui/icons/profile_add_auto.svg'))
        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)

        self.actionImportVectorRasterSource = QAction('Import profiles from raster + vector source')
        self.actionImportVectorRasterSource.setToolTip('Import spectral profiles from a raster image '
                                                       'based on vector geometries (Points).')
        self.actionImportVectorRasterSource.setIcon(QIcon(':/images/themes/default/mActionAddOgrLayer.svg'))
        self.actionImportVectorRasterSource.triggered.connect(self.onImportFromRasterSource)

        m = QMenu()
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        self.actionAddProfiles.setMenu(m)

        self.actionImportSpeclib = QAction('Import Spectral Profiles')
        self.actionImportSpeclib.setToolTip('Import spectral profiles from other data sources')
        self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        m = QMenu()
        m.addAction(self.actionImportVectorRasterSource)
        m.addSeparator()
        self.createSpeclibImportMenu(m)
        self.actionImportSpeclib.setMenu(m)
        self.actionImportSpeclib.triggered.connect(self.onImportSpeclib)

        self.actionExportSpeclib = QAction('Export Spectral Profiles')
        self.actionExportSpeclib.setToolTip('Export spectral profiles to other data formats')
        self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))

        m = QMenu()
        self.createSpeclibExportMenu(m)
        self.actionExportSpeclib.setMenu(m)
        self.actionExportSpeclib.triggered.connect(self.onExportSpectra)

        self.tbSpeclibAction = QToolBar('Spectral Profiles')
        self.tbSpeclibAction.setObjectName('SpectralLibraryToolbar')
        self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        self.tbSpeclibAction.addAction(self.actionAddProfiles)
        self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        self.tbSpeclibAction.addAction(self.actionExportSpeclib)

        self.tbSpeclibAction.addSeparator()
        self.cbXAxisUnit = self.plotWidget().actionXAxis().createUnitComboBox()
        self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        self.tbSpeclibAction.addAction(self.plotWidget().optionUseVectorSymbology())

        self.actionShowFormView = QAction('Show Form View')
        self.actionShowFormView.setCheckable(True)
        self.actionShowFormView.setIcon(QIcon(':/images/themes/default/mActionFormView.svg'))
        self.actionShowFormView.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.FormView))

        self.actionShowAttributeTable = QAction('Show Attribute Table')
        self.actionShowAttributeTable.setCheckable(True)
        self.actionShowAttributeTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        self.actionShowAttributeTable.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.AttributeTable))

        self.actionShowProcessingWidget = QAction('Show Spectral Processing Options')
        self.actionShowProcessingWidget.setCheckable(True)
        self.actionShowProcessingWidget.setIcon(QIcon(':/qps/ui/icons/profile_processing.svg'))
        self.actionShowProcessingWidget.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.ProcessingView))
        self.mMainViewButtonGroup.buttonClicked.connect(self.onCenterWidgetChanged)

        self.tbSpectralProcessing = QToolBar('Spectral Processing')

        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionApplyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionVerifyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionSaveModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionLoadModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionRemoveFunction)

        self.addToolBar(self.tbSpectralProcessing)

        r = self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowFormView)
        self.tbSpeclibAction.addAction(self.actionShowAttributeTable)
        self.tbSpeclibAction.addAction(self.actionShowProcessingWidget)

        # update toolbar visibilities
        self.onCenterWidgetChanged()

        self.insertToolBar(self.mToolbar, self.tbSpeclibAction)

        self.actionShowProperties = QAction('Show Spectral Library Properties')
        self.actionShowProperties.setToolTip('Show Spectral Library Properties')
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.btnShowProperties = QToolButton()
        self.btnShowProperties.setAutoRaise(True)
        self.btnShowProperties.setDefaultAction(self.actionShowProperties)

        self.tbSpeclibAction.addAction(self.actionShowProperties)
        self.centerBottomLayout.insertWidget(self.centerBottomLayout.indexOf(self.mAttributeViewButton),
                                             self.btnShowProperties)

        self.setAcceptDrops(True)

    def depr_setViewMode(self, mode: QgsDualView.ViewMode):
        assert isinstance(mode, QgsDualView.ViewMode)
        self.mMainView.setView(mode)
        for m in [QgsDualView.AttributeEditor, QgsDualView.AttributeTable]:
            self.mMainViewButtonGroup.button(m).setChecked(m == mode)

    def setCenterView(self, view: typing.Union[QgsDualView.ViewMode,
                                               typing.Optional['SpectralLibraryWidget.ViewType']]):
        if isinstance(view, QgsDualView.ViewMode):
            if view == QgsDualView.AttributeTable:
                view = SpectralLibraryWidget.ViewType.AttributeTable
            elif view == QgsDualView.AttributeEditor:
                view = SpectralLibraryWidget.ViewType.FormView

        assert isinstance(view, SpectralLibraryWidget.ViewType)

        if view == SpectralLibraryWidget.ViewType.AttributeTable:
            self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
            self.mMainView.setView(QgsDualView.AttributeTable)

        elif view == SpectralLibraryWidget.ViewType.FormView:
            self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
            self.mMainView.setView(QgsDualView.AttributeEditor)

        elif view == SpectralLibraryWidget.ViewType.ProcessingView:
            self.widgetCenter.setCurrentWidget(self.pageProcessingWidget)

        # legacy code
        self.mMainViewButtonGroup.button(QgsDualView.AttributeTable) \
            .setChecked(self.actionShowAttributeTable.isChecked())
        self.mMainViewButtonGroup.button(QgsDualView.AttributeEditor) \
            .setChecked(self.actionShowFormView.isChecked())

    def onCenterWidgetChanged(self, *args):
        w = self.widgetCenter.currentWidget()

        self.mToolbar.setVisible(w == self.pageAttributeTable)
        self.tbSpectralProcessing.setVisible(w == self.pageProcessingWidget)
        self.actionShowProcessingWidget.setChecked(w == self.pageProcessingWidget)

        if w == self.pageAttributeTable:
            viewMode: QgsDualView.ViewMode = self.mMainView.view()
            self.actionShowAttributeTable.setChecked(viewMode == QgsDualView.AttributeTable)
            self.actionShowFormView.setChecked(viewMode == QgsDualView.AttributeEditor)
        else:
            self.actionShowAttributeTable.setChecked(False)
            self.actionShowFormView.setChecked(False)

    def tableView(self) -> QgsAttributeTableView:
        return self.mMainView.tableView()

    def onShowContextMenuAttributeEditor(self, menu: QgsActionMenu, fid):
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def onWillShowContextMenuAttributeTable(self, menu: QMenu, atIndex: QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def addProfileStyleMenu(self, menu: QMenu):
        selectedFIDs = self.tableView().selectedFeaturesIds()
        n = len(selectedFIDs)
        menuProfileStyle = menu.addMenu('Profile Style')
        wa = QWidgetAction(menuProfileStyle)

        btnResetProfileStyles = QPushButton('Reset')
        btnApplyProfileStyle = QPushButton('Apply')

        plotStyle = self.plotWidget().profileRenderer().profileStyle
        if n == 0:
            btnResetProfileStyles.setText('Reset All')
            btnResetProfileStyles.clicked.connect(self.plotWidget().resetProfileStyles)
            btnResetProfileStyles.setToolTip('Resets all profile styles')
        else:
            for fid in selectedFIDs:
                ps = self.plotWidget().profileRenderer().profilePlotStyle(fid, ignore_selection=True)
                if isinstance(ps, PlotStyle):
                    plotStyle = ps.clone()
                break

            btnResetProfileStyles.setText('Reset Selected')
            btnResetProfileStyles.clicked.connect(
                lambda *args, fids=selectedFIDs: self.plotWidget().setProfileStyles(None, fids))

        psw = PlotStyleWidget(plotStyle=plotStyle)
        psw.setPreviewVisible(False)
        psw.cbIsVisible.setVisible(False)
        btnApplyProfileStyle.clicked.connect(lambda *args, fids=selectedFIDs, w=psw:
                                             self.plotWidget().setProfileStyles(psw.plotStyle(), fids))

        hb = QHBoxLayout()
        hb.addWidget(btnResetProfileStyles)
        hb.addWidget(btnApplyProfileStyle)
        l = QVBoxLayout()
        l.addWidget(psw)
        l.addLayout(hb)

        frame = QFrame()
        frame.setLayout(l)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

    def showProperties(self, *args):



        showLayerPropertiesDialog(self.speclib(), None, parent=self, useQGISDialog=True)

        s = ""

    def createSpeclibImportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to import SpectralProfiles
        """
        separated = []
        from ..io.rastersources import RasterSourceSpectralLibraryIO

        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO), iface
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addImportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addImportActions(self.speclib(), menu)

    def createSpeclibExportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to export the SpectralLibrary
        """
        separated = []
        from ..io.rastersources import RasterSourceSpectralLibraryIO
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO)
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addExportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addExportActions(self.speclib(), menu)

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget

    def plotItem(self) -> SpectralLibraryPlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.plotWidget().getPlotItem()

    def updatePlot(self):
        self.plotWidget().updatePlot()

    def speclib(self) -> SpectralLibrary:
        return self.mLayer

    def spectralLibrary(self) -> SpectralLibrary:
        return self.speclib()

    def addSpeclib(self, speclib: SpectralLibrary):
        assert isinstance(speclib, SpectralLibrary)
        sl = self.speclib()
        wasEditable = sl.isEditable()
        try:
            sl.startEditing()
            info = 'Add {} profiles from {} ...'.format(len(speclib), speclib.name())
            sl.beginEditCommand(info)
            sl.addSpeclib(speclib)
            sl.endEditCommand()
            if not wasEditable:
                sl.commitChanges()
        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

    def addCurrentSpectraToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """

        keys = list(self.plotWidget().mTEMPORARY_PROFILES)
        self.plotWidget().mTEMPORARY_PROFILES.clear()

        self.plotWidget().updatePlotDataItemStyles(keys)

    def setCurrentProfiles(self,
                           currentProfiles: typing.List[SpectralProfile],
                           profileStyles: typing.Dict[SpectralProfile, PlotStyle] = None):
        """
        Sets temporary profiles for the spectral library.
        If not made permanent, they will be removes when adding the next set of temporary profiles
        :param currentProfiles:
        :param profileStyles:
        :return:
        """
        assert isinstance(currentProfiles, list)

        if not isinstance(profileStyles, dict):
            profileStyles = dict()

        speclib: SpectralLibrary = self.speclib()
        plotWidget: SpectralProfilePlotWidget = self.plotWidget()

        #  stop plot updates
        plotWidget.mUpdateTimer.stop()
        restart_editing: bool = not speclib.startEditing()
        oldCurrentKeys = self.plotWidget().temporaryProfileKeys()
        oldCurrentIDs = self.plotWidget().temporaryProfileIds()
        addAuto: bool = self.optionAddCurrentProfilesAutomatically.isChecked()

        if not addAuto:
            # delete previous current profiles from speclib
            speclib.beginEditCommand('Remove temporary')
            speclib.deleteFeatures(oldCurrentIDs)
            speclib.endEditCommand()
            plotWidget.removeSPDIs(oldCurrentKeys, updateScene=False)
            # now there shouldn't be any PDI or style ref related to an old ID
        else:
            self.addCurrentSpectraToSpeclib()

        self.plotWidget().mTEMPORARY_PROFILES.clear()
        # if necessary, convert QgsFeatures to SpectralProfiles
        for i in range(len(currentProfiles)):
            p = currentProfiles[i]
            assert isinstance(p, QgsFeature)
            if not isinstance(p, SpectralProfile):
                p = SpectralProfile.fromQgsFeature(p)
                currentProfiles[i] = p

        # add current profiles to speclib
        oldIDs = set(speclib.allFeatureIds())
        res = speclib.addProfiles(currentProfiles)

        self.speclib().commitChanges()
        if restart_editing:
            speclib.startEditing()

        addedIDs = sorted(set(speclib.allFeatureIds()).difference(oldIDs))
        addedKeys: typing.List[SpectralProfileKey] = []
        value_fields = [f.name() for f in self.speclib().spectralValueFields()]

        for id in addedIDs:
            for n in value_fields:
                addedKeys.append(SpectralProfileKey(id, n))
        # set profile style
        PROFILE2FID = dict()
        for p, fid in zip(currentProfiles, addedIDs):
            PROFILE2FID[p] = fid

        renderer = self.speclib().profileRenderer()

        customStyles = set(profileStyles.values())
        if len(customStyles) > 0:
            profileRenderer = plotWidget.profileRenderer()
            for customStyle in customStyles:
                fids = [PROFILE2FID[p] for p, s in profileStyles.items() if s == customStyle]
                profileRenderer.setProfilePlotStyle(customStyle, fids)
            plotWidget.setProfileRenderer(profileRenderer)

        # set current profiles highlighted

        if not addAuto:
            # give current spectra the current spectral style
            self.plotWidget().mTEMPORARY_PROFILES.update(addedKeys)

        plotWidget.mUpdateTimer.start()

    def currentProfiles(self) -> typing.List[SpectralProfile]:
        return self.mSpeclibPlotWidget.plotWidget.currentProfiles()

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mMapCanvas

    def setAddCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def dropEvent(self, event):
        self.plotWidget().dropEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.plotWidget().dragEnterEvent(event)

    def onImportSpeclib(self):
        """
        Imports a SpectralLibrary
        :param path: str
        """

        slib = SpectralLibrary.readFromSourceDialog(self)

        if isinstance(slib, SpectralLibrary) and len(slib) > 0:
            self.addSpeclib(slib)

    def onImportFromRasterSource(self):
        from ..io.rastersources import SpectralProfileImportPointsDialog
        d = SpectralProfileImportPointsDialog(parent=self)
        d.finished.connect(lambda *args, d=d: self.onIODialogFinished(d))
        d.show()
        self.mIODialogs.append(d)

    def onIODialogFinished(self, w: QWidget):
        from ..io.rastersources import SpectralProfileImportPointsDialog
        if isinstance(w, SpectralProfileImportPointsDialog):
            if w.result() == QDialog.Accepted:
                profiles = w.profiles()
                info = w.rasterSource().name()
                self.addProfiles(profiles, add_missing_fields=w.allAttributes())
            else:
                s = ""

        if w in self.mIODialogs:
            self.mIODialogs.remove(w)
        w.close()

    def addProfiles(self, profiles, add_missing_fields: bool = False):
        b = self.speclib().isEditable()
        self.speclib().startEditing()
        self.speclib().beginEditCommand('Add {} profiles'.format(len(profiles)))
        self.speclib().addProfiles(profiles, addMissingFields=add_missing_fields)
        self.speclib().endEditCommand()
        self.speclib().commitChanges()
        if b:
            self.speclib().startEditing()

    def onExportSpectra(self, *args):
        files = self.speclib().write(None)
        if len(files) > 0:
            self.sigFilesCreated.emit(files)

    def clearSpectralLibrary(self):
        """
        Removes all SpectralProfiles and additional fields
        """
        warnings.warn('Deprectated and desimplemented', DeprecationWarning)


class SpectralLibraryInfoLabel(QLabel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mPW: SpectralProfilePlotWidget = None

        self.mLastStats: SpectralLibraryPlotStats = None
        self.setStyleSheet('QToolTip{width:300px}')

    def setPlotWidget(self, pw: SpectralLibraryPlotWidget):
        assert isinstance(pw, SpectralLibraryPlotWidget)
        self.mPW = pw

    def plotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mPW

    def update(self):
        if not isinstance(self.plotWidget(), SpectralProfilePlotWidget):
            self.setText('')
            self.setToolTip('')
            return

        stats = self.plotWidget().profileStats()
        if self.mLastStats == stats:
            return

        msg = f'<html><head/><body>'
        ttp = f'<html><head/><body><p>'

        # total + filtering
        if stats.filter_mode == QgsAttributeTableFilterModel.ShowFilteredList:
            msg += f'{stats.profiles_filtered}f'
            ttp += f'{stats.profiles_filtered} profiles filtered out of {stats.profiles_total}<br/>'
        else:
            # show all
            msg += f'{stats.profiles_total}'
            ttp += f'{stats.profiles_total} profiles in total<br/>'

        # show selected
        msg += f'/{stats.profiles_selected}'
        ttp += f'{stats.profiles_selected} selected in plot<br/>'

        if stats.profiles_empty > 0:
            msg += f'/<span style="color:red">{stats.profiles_empty}N</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_empty} profile fields empty (NULL)<br/>'

        if stats.profiles_error > 0:
            msg += f'/<span style="color:red">{stats.profiles_error}E</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_error} profiles ' \
                   f'can not be converted to X axis unit "{self.plotWidget().xUnit()}" (ERROR)</span><br/>'

        if stats.profiles_plotted >= stats.profiles_plotted_max and stats.profiles_total > stats.profiles_plotted_max:
            msg += f'/<span style="color:red">{stats.profiles_plotted}</span>'
            ttp += f'<span style="color:red">{stats.profiles_plotted} profiles plotted. Increase plot ' \
                   f'limit ({stats.profiles_plotted_max}) to show more at same time.</span><br/>'
        else:
            msg += f'/{stats.profiles_plotted}'
            ttp += f'{stats.profiles_plotted} profiles plotted<br/>'

        msg += '</body></html>'
        ttp += '</p></body></html>'

        self.setText(msg)
        self.setToolTip(ttp)
        self.setMinimumWidth(self.sizeHint().width())

        self.mLastStats = stats

    def contextMenuEvent(self, event: QContextMenuEvent):
        m = QMenu()

        stats = self.plotWidget().profileStats()

        a = m.addAction('Select axis-unit incompatible profiles')
        a.setToolTip(f'Selects all profiles that cannot be displayed in {self.plotWidget().xUnit()}')
        a.triggered.connect(self.onSelectAxisUnitIncompatibleProfiles)

        a = m.addAction('Reset to band number')
        a.setToolTip('Resets the x-axis to show the band number.')
        a.triggered.connect(lambda *args: self.plotWidget().setXUnit(BAND_NUMBER))

        m.exec_(event.globalPos())

    def onSelectAxisUnitIncompatibleProfiles(self):
        incompatible = []
        pw: SpectralProfilePlotWidget = self.plotWidget()
        if not isinstance(pw, SpectralProfilePlotWidget) or not isinstance(pw.speclib(), SpectralLibrary):
            return

        targetUnit = pw.xUnit()
        for p in pw.speclib():
            if isinstance(p, SpectralProfile):
                f = pw.unitConversionFunction(p.xUnit(), targetUnit)
                if f == pw.mUnitConverter.func_return_none:
                    incompatible.append(p.id())

        pw.speclib().selectByIds(incompatible)


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib: SpectralLibrary = None, **kwds):
        super(SpectralLibraryPanel, self).__init__(*args, **kwds)
        self.setObjectName('spectralLibraryPanel')

        self.SLW = SpectralLibraryWidget(speclib=speclib)
        self.setWindowTitle(self.speclib().name())
        self.speclib().nameChanged.connect(lambda *args: self.setWindowTitle(self.speclib().name()))
        self.setWidget(self.SLW)

    def spectralLibraryWidget(self) -> SpectralLibraryWidget:
        """
        Returns the SpectralLibraryWidget
        :return: SpectralLibraryWidget
        """
        return self.SLW

    def speclib(self) -> SpectralLibrary:
        """
        Returns the SpectralLibrary
        :return: SpectralLibrary
        """
        return self.SLW.speclib()

    def setCurrentSpectra(self, listOfSpectra):
        """
        Adds a list of SpectralProfiles as current spectra
        :param listOfSpectra: [list-of-SpectralProfiles]
        :return:
        """
        self.SLW.setCurrentProfiles(listOfSpectra)


