# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/processing.py
    This module contains basic objects to use and process SpectralLibraries
    within the QGIS Processing Framework
    ---------------------
    Date                 : Jan 2021
    Copyright            : (C) 2021 by Benjamin Jakimow
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
import collections
import typing
import importlib
import inspect
import os
import enum
import pathlib
import pickle
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QFontInfo, QContextMenuEvent
from qgis.PyQt.QtXml import QDomElement, QDomDocument, QDomNode, QDomCDATASection
from qgis.PyQt.QtWidgets import QPlainTextEdit, QWidget, QTableView, QTreeView, \
    QLabel, QComboBox, \
    QHBoxLayout, QVBoxLayout, QSpacerItem, QMenu, QAction, QToolButton, QGridLayout
from qgis.core import QgsFeature, QgsProcessingAlgorithm, QgsProcessingContext, \
    QgsRuntimeProfiler, QgsProcessingProvider, QgsProcessingParameterDefinition, QgsProcessingFeedback, \
    QgsProcessingParameterType, QgsProcessingModelChildParameterSource, \
    QgsProcessingModelAlgorithm, QgsApplication, QgsProcessingDestinationParameter, \
    QgsProcessingFeatureSource, QgsProcessingOutputDefinition, QgsProcessingParameterVectorLayer, \
    QgsProcessingModelChildAlgorithm, \
    QgsProcessingRegistry, QgsProcessingModelOutput, QgsProcessingModelParameter

from qgis.gui import QgsCollapsibleGroupBox, QgsCodeEditorPython, QgsProcessingParameterWidgetFactoryInterface, \
    QgsProcessingModelerParameterWidget, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingParameterWidgetContext, QgsProcessingGui, \
    QgsProcessingToolboxModel, QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog, \
    QgsProcessingToolboxTreeView, QgsProcessingGui, QgsGui, QgsAbstractProcessingParameterWidgetWrapper

from processing import ProcessingConfig, Processing
from processing.core.ProcessingConfig import Setting
from processing.gui.wrappers import WidgetWrapperFactory
from processing.gui.wrappers import InvalidParameterValue
from processing.tools.dataobjects import createContext
from processing.gui.wrappers import WidgetWrapper
from processing.modeler.ModelerParametersDialog import \
    ModelerParametersPanelWidget, ModelerParametersWidget, ModelerParametersDialog
import numpy as np
from .core import SpectralLibrary, SpectralProfile, SpectralProfileBlock, speclibUiPath
from ..unitmodel import UnitConverterFunctionModel, BAND_INDEX, XUnitModel
from ..utils import loadUi
from ..models import TreeModel, TreeNode
import sip
import weakref

SpectralMathResult = collections.namedtuple('SpectralMathResult', ['x', 'y', 'x_unit', 'y_unit'])

MIMEFORMAT_SPECTRAL_MATH_FUNCTION = 'qps.speclib.math.spectralmathfunction'

XML_SPECTRALMATHFUNCTION = 'SpectralMathFunction'

REFS = []


def keepRef(o):
    global REFS
    # to_remove = [d for d in REFS if sip.isdeleted(d)]
    # for d in to_remove:
    #    pass
    # REFS.remove(d)
    # REFS[id(o)] = o
    REFS.append(o)


def printCaller(prefix=None, suffix=None):
    """
    prints out the current code location in calling method
    :param prefix: prefix text
    :param suffix: suffix text
    """
    curFrame = inspect.currentframe()
    outerFrames = inspect.getouterframes(curFrame)
    FOI = outerFrames[1]
    stack = inspect.stack()
    stack_class = stack[1][0].f_locals["self"].__class__.__name__
    stack_method = stack[1][0].f_code.co_name
    info = f'{stack_class}.{FOI.function}: {os.path.basename(FOI.filename)}:{FOI.lineno}'

    prefix = f'{prefix}:' if prefix else ''
    suffix = f':{suffix}' if suffix else ''

    print(f'#{prefix}{info}{suffix}')


class SpectralProfileIOFlag(enum.Flag):
    Unknown = enum.auto()
    Inputs = enum.auto()
    Outputs = enum.auto()
    All = Inputs | Outputs


def is_spectral_processing_model(model: QgsProcessingModelAlgorithm, flags=SpectralProfileIOFlag.All) -> bool:
    if not isinstance(model, QgsProcessingModelAlgorithm):
        return False
    return is_spectral_processing_algorithm(model, flags=flags)


def is_spectral_processing_algorithm(
        alg: QgsProcessingAlgorithm,
        flags: SpectralProfileIOFlag = SpectralProfileIOFlag.All) -> bool:
    """
    Checks if a QgsProcessingAlgorithm is a SpectralProcessing Algorithms.
    :param flags: conditions
    :param alg: QgsProcessingAlgorithm
    :return: bool
    """
    if not isinstance(alg, QgsProcessingAlgorithm):
        return False

    _flags = SpectralProfileIOFlag.Unknown

    for input in alg.parameterDefinitions():
        if isinstance(input, SpectralProcessingProfiles):
            _flags = SpectralProfileIOFlag.Inputs
            break

    for output in alg.outputDefinitions():
        if isinstance(output, SpectralProcessingProfilesOutput):
            _flags |= SpectralProfileIOFlag.Outputs
            break

    return flags in _flags
    s = ""
    return True


class SpectralProcessingProfiles(QgsProcessingParameterDefinition):
    """
    SpectralAlgorithm Input definition, i.e. defines where the profiles come from
    """
    TYPE = 'spectral_profile'

    def __init__(self, name='Spectral Profile', description='Spectral Profile', optional: bool = False):
        super().__init__(name, description=description, optional=optional)

        metadata = {
            'widget_wrapper': {
                'class': SpectralProcessingProfilesWidgetWrapper}
        }
        self.setMetadata(metadata)

    def isDestination(self):
        return False

    def type(self):
        return self.TYPE

    def clone(self):
        # printCaller()
        return SpectralProcessingProfiles()

    def checkValueIsAcceptable(self, input: typing.Any, context: QgsProcessingContext = None) -> bool:
        """
        Acceptable inputs are: Spectral Libraries or lists of SpectralProfile Blocks
        :param input:
        :param context:
        :return: bool
        """
        if isinstance(input, SpectralLibrary):
            return True
        if isinstance(input, list):
            return all([isinstance(i, SpectralProfileBlock) for i in input])
        return False

    def parameterAsSpectralProfileBlockList(self, parameters: dict, context: QgsProcessingContext) \
            -> typing.List[SpectralProfileBlock]:
        return parameterAsSpectralProfileBlockList(parameters, self.name(), context)

    def description(self):
        return 'the spectral profile'

    def isDynamic(self):
        return True

    def toolTip(self):
        return 'The spectral profile'


class SpectralProfileBlockSink(object):

    def __init__(self):
        self.mSink = []

    def appendProfileBlock(self, profileBlock: SpectralProfileBlock):
        pass


def parameterAsSpectralProfileBlockSink(parameters: dict,
                                        name: str,
                                        context: QgsProcessingContext):
    """
    Evaluates the parameter '
    :param parameters:
    :param name:
    :param context:
    :return:
    """
    return None
    s = ""


def parameterAsSpectralProfileBlockList(parameters: dict,
                                        name: str,
                                        context: QgsProcessingContext) -> typing.List[SpectralProfileBlock]:
    """
    Evaluates the parameter 'name' to a SpectralProcessingProfiles
    :param parameters:
    :param name:
    :param context:
    :return: list of SpectralProfileBlocks
    """
    s = ""
    feedback = context.feedback()
    value = parameters[name]
    blocks = None
    if isinstance(value, SpectralLibrary):
        blocks = list(value.profileBlocks())
    elif isinstance(value, SpectralProfile):
        blocks = [SpectralProfileBlock.fromSpectralProfile(value)]
    elif isinstance(value, typing.Generator):
        blocks = list(value)
        for b in blocks:
            assert isinstance(b, SpectralProfileBlock)
    elif isinstance(value, list):
        blocks = value

    if not isinstance(blocks, list):
        raise Exception(f'Unable to convert {value} to list of SpectralProfileBlocks')

    for block in blocks:
        if not isinstance(block, SpectralProfileBlock):
            raise Exception(f'{block} is not a SpectralProfileBlock')

    return blocks


class SpectralProcessingProfilesOutput(QgsProcessingOutputDefinition):
    TYPE = SpectralProcessingProfiles.TYPE

    def __init__(self, name: str = 'Spectral Profile', description='Spectral Profile'):
        super(SpectralProcessingProfilesOutput, self).__init__(name, description=description)

    def type(self):
        return self.TYPE


class SpectralProcessingProfilesSink(QgsProcessingDestinationParameter):
    """
    Like the QgsProcessingParameterFeatureSink for QgsFeatures,
    this is a sink for SpectralProfiles.
    """

    def __init__(self,
                 name: str,
                 description: str = 'Spectra Profile Output',
                 defaultValue=None, optional: bool = False,
                 createByDefault=True):
        super().__init__(name, description, defaultValue, optional, createByDefault)

        metadata = {
            'widget_wrapper': {
                'class': SpectralProcessingProfilesWidgetWrapper}
        }
        self.setMetadata(metadata)

    def getTemporaryDestination(self) -> str:
        printCaller()
        return 'None'

    def fromVariantMap(self, map: dict) -> bool:
        printCaller()
        super().fromVariantMap(map)
        return bool

    def toVariantMap(self) -> dict:
        map = super().toVariantMap()
        return map

    def isSupportedOutputValue(self, value, context: QgsProcessingContext):
        printCaller()
        error = ''
        result: bool = True

        return result, error

    def defaultFileExtension(self) -> str:
        return 'gpkg'

    def toOutputDefinition(self) -> SpectralProcessingProfilesOutput:
        printCaller()
        return SpectralProcessingProfilesOutput(self.name(), self.description())

    def type(self):
        return SpectralProcessingProfiles.TYPE

    def clone(self):
        return SpectralProcessingProfilesSink(self.name(), self.description())


class SpectralProcessingProfileType(QgsProcessingParameterType):
    """
    Describes a SpectralProcessingProfiles in the Modeler's parameter type list
    """

    def __init__(self):
        super().__init__()
        self.mName = 'PROFILE INPUT'
        self.mRefs = []

    def description(self):
        return 'A single spectral profile or set of similar profiles'

    def name(self):
        return 'Spectral Profiles'

    def className(self) -> str:
        printCaller()
        return 'SpectralProcessingProfileType'

    def create(self, name):
        printCaller()
        p = SpectralProcessingProfiles(name=name)
        # global REFS
        keepRef(p)
        # REFS.append(p)
        # self.mRefs.append(p)
        return p

    def metadata(self):
        printCaller()
        return {'x': [], 'y': []}

    def flags(self):
        return QgsProcessingParameterType.ExposeToModeler

    def id(self):
        printCaller()
        return 'spectral_profile'

    def acceptedPythonTypes(self):
        printCaller()
        return ['SpectralProfile', 'ndarray']

    def acceptedStringValues(self):
        printCaller()
        return ['Profile Input']

    def pythonImportString(self):
        printCaller()
        return 'from .speclib.math import SpectralProcessingProfileType'


class SpectralProcessingAlgorithmInputModelerParameterWidget(QgsProcessingModelerParameterWidget):

    def __init__(self,
                 model: QgsProcessingModelAlgorithm,
                 childId: str,
                 parameter: QgsProcessingParameterDefinition,
                 context: QgsProcessingContext,
                 parent: QWidget = None
                 ):
        super(SpectralProcessingAlgorithmInputModelerParameterWidget, self).__init__(model,
                                                                                     childId,
                                                                                     parameter,
                                                                                     context,
                                                                                     parent)

        # label = QLabel('Profiles')
        # self.layout().addWidget(label)

    def setWidgetValue(self, value: QgsProcessingModelChildParameterSource):
        printCaller()
        s = ""

    def value(self):
        result = dict()
        return result


class SpectralProcessingAlgorithmInputWidget(QgsProcessingAbstractParameterDefinitionWidget):
    """
    Widget to specify SpectralAlgorithm input
    """

    def __init__(self,
                 context: QgsProcessingContext,
                 widgetContext: QgsProcessingParameterWidgetContext,
                 definition: QgsProcessingParameterDefinition = None,
                 algorithm: QgsProcessingAlgorithm = None,
                 parent: QWidget = None):
        printCaller()
        super().__init__(context, widgetContext, definition, algorithm, parent)

        self.mContext = context
        self.mDefinition = definition
        self.mAlgorithm = algorithm
        l = QVBoxLayout()
        self.mL = QLabel('Placeholder Input Widget')
        l.addWidget(self.mL)
        self.mLayout = l
        self.setLayout(l)
        self.mPARAMETERS = dict()

    def createParameter(self, name: str, description: str, flags) -> SpectralProcessingProfiles:
        printCaller()

        param = SpectralProcessingProfiles(name, description=description)
        param.setFlags(flags)
        keepRef(param)

        return param


class SpectralProcessingModelTableModelAlgorithmWrapper(QObject):

    def __init__(self, alg: QgsProcessingAlgorithm):
        super().__init__()
        self.alg: QgsProcessingAlgorithm = alg
        self.name: str = alg.displayName()
        self.parameters: typing.Dict = dict()
        self.is_active: bool = True

    def allParametersDefined(self) -> bool:
        """
        Returns True if all required parameters are set
        :return:
        """
        for p in self.alg.parameterDefinitions():
            if isinstance(p, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                # will be connected automatically
                continue
            if p.name() not in self.parameters.keys() and \
                    (bool(
                        p.flags() & QgsProcessingParameterDefinition.FlagOptional) == False and p.defaultValue() is None):
                return False

        return True

    def __hash__(self):
        return hash((self.alg.name(), id(self)))


class SpectralProcessingModelTableModel(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super(SpectralProcessingModelTableModel, self).__init__(*args, **kwds)
        self.mAlgorithmWrappers: typing.List[SpectralProcessingModelTableModelAlgorithmWrapper] = []
        self.mWrapperParameters: typing.Dict[SpectralProcessingModelTableModelAlgorithmWrapper, dict] = dict()
        self.mParameterWrappers: typing.Dict[SpectralProcessingModelTableModelAlgorithmWrapper,
                                             QgsAbstractProcessingParameterWidgetWrapper] = dict()
        self.mColumnNames = {0: 'Algorithm',
                             1: 'Parameters'}

        self.mModelName: str = 'SpectralProcessingModel'
        self.mModelGroup: str = ''
        self.mProcessingContext: QgsProcessingContext = QgsProcessingContext()

    def setModelName(self, name: str):
        assert isinstance(name, str)
        self.mModelName = name

    def parameterWrappers(self, wrapper) -> \
            typing.Dict[QgsProcessingParameterDefinition,  QgsAbstractProcessingParameterWidgetWrapper]:
        return self.mParameterWrappers.get(wrapper, None)

    def setModelGroup(self, group: str):
        assert isinstance(group, str)
        self.mModelGroup = group

    def __len__(self):
        return len(self.mAlgorithmWrappers)

    def __iter__(self):
        return iter(self.mAlgorithmWrappers)

    INPUT_PROFILE_PREFIX = 'input_profiles'
    OUTPUT_PROFILE_PREFIX = 'output_profiles'

    def createModel(self) -> QgsProcessingModelAlgorithm:

        model = QgsProcessingModelAlgorithm()
        model.setName(self.mModelName)
        model.setGroup(self.mModelGroup)

        # create child algorithms
        child_ids: typing.List[str] = []
        previous_cid: str = None
        previous_calg: QgsProcessingModelChildAlgorithm = None

        if len(self) == 0:
            return None

        for w in self:
            w: SpectralProcessingModelTableModelAlgorithmWrapper
            if not w.is_active:
                continue
            # create new child algorithm
            calg: QgsProcessingModelChildAlgorithm = QgsProcessingModelChildAlgorithm(w.alg.id())
            calg.generateChildId(model)
            calg.setDescription(w.name)

            cid = model.addChildAlgorithm(calg)
            child_ids.append(cid)
            # get model internal child Algorithm instance
            calg: QgsProcessingModelChildAlgorithm = model.childAlgorithm(cid)

            sources: typing.List[SpectralProcessingProfiles] = [p for p in calg.algorithm().parameterDefinitions()
                                                                if isinstance(p, SpectralProcessingProfiles)]

            # connect output of previous with input of this one
            if previous_cid is None:
                # set 1st Alg inputs as model inputs
                for i, source in enumerate(sources):
                    par_name = f'{self.INPUT_PROFILE_PREFIX}_{i + 1}'
                    par_descr = f'Profile Source {i + 1}'
                    model.addModelParameter(
                        SpectralProcessingProfiles(par_name, description=par_descr),
                        QgsProcessingModelParameter(par_name))
                    calg.addParameterSources(
                        source.name(),
                        [QgsProcessingModelChildParameterSource.fromModelParameter(par_name)]
                    )
            elif isinstance(previous_cid, str):
                # connect child inputs with previous outputs
                sinks = [p for p in previous_calg.algorithm().parameterDefinitions()
                         if isinstance(p, SpectralProcessingProfilesSink)]
                for sink, source in zip(sinks, sources):
                    calg.addParameterSources(source.name(),
                                             [QgsProcessingModelChildParameterSource.fromChildOutput(previous_cid,
                                                                                                     sink.name())])

            # todo: add none-profile parameter sources (which are not set / connected automatically)

            if len(calg.parameterSources()) == 0:
                raise Exception('Unable to retrieve sources for {}')
            previous_cid = cid
            previous_calg = calg

        # finally, use sinks of last algorithm as model outputs
        model_outputs = {}

        for i, sink in enumerate([p for p in calg.algorithm().parameterDefinitions()
                                  if isinstance(p, SpectralProcessingProfilesSink)]):
            outname = f'{self.OUTPUT_PROFILE_PREFIX}_{i + 1}'

            childOutput = QgsProcessingModelOutput(outname)
            childOutput.setChildOutputName(sink.name())
            calg.setModelOutputs({outname: childOutput})
            model.addOutput(SpectralProcessingProfilesOutput(outname))

        return model

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self.mAlgorithmWrappers)

    def columnCount(self, parent: QModelIndex = None) -> int:
        return len(self.mColumnNames)

    """
    def index(self, row: int, column: int = ..., parent: QModelIndex = ...) -> QModelIndex:

        wrapper = self.mAlgorithmWrappers[row]

        return self.createIndex(row, column, wrapper)
    """

    def _algWrapper(self, index) -> SpectralProcessingModelTableModelAlgorithmWrapper:

        if isinstance(index, QModelIndex):
            index = index.row()
        return self.mAlgorithmWrappers[index]

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsSelectable

        return flags

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if not index.isValid():
            return None
        col = index.column()
        wrapper = self._algWrapper(index)

        if role == Qt.DisplayRole:
            if col == 0:
                return wrapper.name
            if col == 1:
                return str(wrapper.parameters)
        if role == Qt.DecorationRole:
            if col == 0:
                if wrapper.allParametersDefined():
                    return QColor('green')
                else:
                    return QColor('red')

        if role == Qt.UserRole:
            return wrapper

        if role == Qt.EditRole:
            if col == 0:
                return wrapper.name

        if role == Qt.ToolTipRole:
            if col == 0:
                return wrapper.alg.description()
            if col == 1:
                return '\n'.join(f'{k}:{v}' for k, v in wrapper.parameters.items())

        if role == Qt.CheckStateRole:
            if col == 0:
                return Qt.Checked if wrapper.is_active else Qt.Unchecked

        if role == Qt.FontRole:
            if not wrapper.is_active:
                font = QFont()
                font.setItalic(True)
                return font
        if role == Qt.ForegroundRole:
            if not wrapper.is_active:
                return QColor('grey')
        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return False

        wrapper = self._algWrapper(index)

        changed = False
        if index.column() == 0:
            if role == Qt.CheckStateRole:
                new_value = value == Qt.Checked
                if wrapper.is_active != new_value:
                    wrapper.is_active = new_value
                    changed = True
            elif role == Qt.EditRole:
                new_value = str(value)
                if wrapper.name != new_value:
                    wrapper.name = new_value
                    changed = True

        if changed:
            self.dataChanged.emit(index, index, [role])
        return changed

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[section]
        return None

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        if row < 0 or row >= len(self.mAlgorithmWrappers):
            return QModelIndex()
        alg = self.mAlgorithmWrappers[row]
        return self.createIndex(row, column, alg)

    def insertAlgorithm(self,
                        alg: typing.Union[
                            str,
                            QgsProcessingAlgorithm,
                            SpectralProcessingModelTableModelAlgorithmWrapper],
                        index: int,
                        name: str = None):

        if isinstance(alg, str):
            procReg = QgsApplication.instance().processingRegistry()
            assert isinstance(procReg, QgsProcessingRegistry)
            a = procReg.algorithmById(alg)
            assert isinstance(a, QgsProcessingAlgorithm), f'Unable to find QgsProcessingAlgorithm {alg}'
            wrapper = SpectralProcessingModelTableModelAlgorithmWrapper(a)
        elif isinstance(alg, QgsProcessingAlgorithm):
            wrapper = SpectralProcessingModelTableModelAlgorithmWrapper(alg)
        else:
            assert isinstance(alg, SpectralProcessingModelTableModelAlgorithmWrapper)
            wrapper = alg

        if index < 0:
            index = self.rowCount()

        names = [w.name for w in self]

        self.beginInsertRows(QModelIndex(), index, index)
        if name:
            wrapper.name = name
        else:
            name2 = wrapper.name
            i = 1
            while name2 in names:
                i += 1
                name2 = f'{wrapper.name}({i})'

            wrapper.name = name2
        self.mAlgorithmWrappers.insert(index, wrapper)

        parameterWidgetWrappers = dict()
        for param in wrapper.alg.parameterDefinitions():
            if isinstance(param, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                continue
            pWrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(param, QgsProcessingGui.Standard)
            pWrapper.createWrappedLabel()
            pWrapper.createWrappedWidget(self.mProcessingContext)
            parameterWidgetWrappers[param.name()] = pWrapper
        self.mParameterWrappers[wrapper] = parameterWidgetWrappers
        self.endInsertRows()

    def addAlgorithm(self, alg, name: str = None):
        self.insertAlgorithm(alg, -1, name=name)

    def removeAlgorithm(self, alg: SpectralProcessingModelTableModelAlgorithmWrapper):
        assert isinstance(alg, SpectralProcessingModelTableModelAlgorithmWrapper)
        assert alg in self.mAlgorithmWrappers

        i = self.mAlgorithmWrappers.index(alg)
        self.beginRemoveRows(QModelIndex(), i, i)
        self.mAlgorithmWrappers.remove(alg)
        self.endRemoveRows()


class SpectralProcessingModelTableView(QTableView):
    """
    A QTableView used in the SpectralProcessingWidget
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.horizontalHeader().setStretchLastSection(True)

    def selectedAlgorithmWrappers(
            self) -> SpectralProcessingModelTableModelAlgorithmWrapper:
        w = self.currentIndex().data(Qt.UserRole)
        if isinstance(w, SpectralProcessingModelTableModelAlgorithmWrapper):
            return w
        else:
            return None

    def spectralProcessingModelTableModel(self) -> SpectralProcessingModelTableModel:

        return self.model()

    def onRemoveSelected(self, indices: typing.List[QModelIndex]):
        """
        Removes selected rows
        :param indices:
        :return:
        """
        if indices is None:
            indices = self.selectedIndexes()

        m = self.spectralProcessingModelTableModel()
        wrappers = set()
        for i in indices:
            wrappers.add(i.data(Qt.UserRole))

        for w in wrappers:
            if isinstance(w, SpectralProcessingModelTableModelAlgorithmWrapper):
                m.removeAlgorithm(w)

    def onSetChecked(self, indices: typing.List[QModelIndex], check: bool):

        for i in indices:
            self.model().setData(i, Qt.Checked if check else Qt.Unchecked, role=Qt.CheckStateRole)

    def createContextMenu(self, index: QModelIndex) -> QMenu:
        wrapper: SpectralProcessingModelTableModelAlgorithmWrapper = index.data(Qt.UserRole)

        indices = self.selectedIndexes()
        m = QMenu()
        a = m.addAction('Rename')
        a.triggered.connect(lambda: self.edit(self.currentIndex()))

        a = m.addAction('Remove selected')
        a.triggered.connect(lambda *args, idx=indices: self.onRemoveSelected(idx))

        a = m.addAction('Check selected')
        a.triggered.connect(lambda *args, idx=indices: self.onSetChecked(idx, True))

        a = m.addAction('Uncheck selected')
        a.triggered.connect(lambda *args, idx=indices: self.onSetChecked(idx, False))

        return m

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:

        index = self.indexAt(event.pos())
        if index.isValid():
            m = self.createContextMenu(index)
            m.exec_(event.globalPos())


class SpectralProcessingAlgorithmTreeView(QgsProcessingToolboxTreeView):
    """
    The QTreeView used to show SpectraProcessingAlgorithms in the SpectralProcessingWidget
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setHeaderHidden(True)


class SpectralProcessingAlgorithmModel(QgsProcessingToolboxProxyModel):
    """
    This proxy model filters out all QgsProcessingAlgorithms that do not use
    SpectralProcessingProfiles
    """

    def __init__(self,
                 parent: QObject,
                 registry: QgsProcessingRegistry = None,
                 recentLog: QgsProcessingRecentAlgorithmLog = None):
        super().__init__(parent, registry, recentLog)
        self.setRecursiveFilteringEnabled(True)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex):
        procReg = QgsApplication.instance().processingRegistry()
        b = super().filterAcceptsRow(sourceRow, sourceParent)
        if b:
            sourceIdx = self.toolboxModel().index(sourceRow, 0, sourceParent)
            if self.toolboxModel().isAlgorithm(sourceIdx):
                algId = self.sourceModel().data(sourceIdx, QgsProcessingToolboxModel.RoleAlgorithmId)
                alg = procReg.algorithmById(algId)
                return is_spectral_processing_algorithm(alg,
                                                        SpectralProfileIOFlag.Outputs | SpectralProfileIOFlag.Inputs)
            else:
                return False
        return b


class SpectralProcessingWidget(QWidget):
    sigSpectralMathChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralprocessingwidget.ui'), self)

        self.mAlgorithmModel = SpectralProcessingAlgorithmModel(self)
        # self.mProcessingModel = SimpleProcessingModelAlgorithm()
        self.mProcessingModelTableModel = SpectralProcessingModelTableModel()

        self.tbModelGroup.textChanged.connect(self.mProcessingModelTableModel.setModelGroup)
        self.tbModelName.textChanged.connect(self.mProcessingModelTableModel.setModelName)

        self.mTableView: SpectralProcessingModelTableView
        assert isinstance(self.mTableView, SpectralProcessingModelTableView)
        self.mTableView.setModel(self.mProcessingModelTableModel)
        self.mTableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mTableView.selectionModel().currentChanged.connect(self.onCurrentAlgorithmChanged)
        self.mTreeView: SpectralProcessingAlgorithmTreeView
        self.mTreeView.header().setVisible(False)
        self.mTreeView.setDragDropMode(QTreeView.DragOnly)
        self.mTreeView.setDropIndicatorShown(True)
        self.mTreeView.doubleClicked.connect(self.onTreeViewDoubleClicked)
        self.mTreeView.setToolboxProxyModel(self.mAlgorithmModel)

        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: QgsProcessingAlgorithm = None

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)

    def onCurrentAlgorithmChanged(self, current, previous):

        wrapper = current.data(Qt.UserRole)
        if isinstance(wrapper, SpectralProcessingModelTableModelAlgorithmWrapper):
            pWrappers: QgsAbstractProcessingParameterWidgetWrapper = \
                self.mProcessingModelTableModel.parameterWrappers(wrapper)

            l = QGridLayout()
            alg: QgsProcessingAlgorithm = wrapper.alg
            for param in alg.parameterDefinitions():
                if isinstance(param, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                    continue
                pWrapper = pWrappers.get(param.name(), None)
                if isinstance(pWrapper, QgsAbstractProcessingParameterWidgetWrapper):
                    l.addWidget(pWrapper.wrappedLabel())

    def onTreeViewDoubleClicked(self, *args):

        alg = self.mTreeView.selectedAlgorithm()
        if is_spectral_processing_algorithm(alg, SpectralProfileIOFlag.Outputs | SpectralProfileIOFlag.Inputs):
            self.mProcessingModelTableModel.addAlgorithm(alg)

    def functionModel(self):
        return self.mProcessingModel

    def onSelectionChanged(self, selected, deselected):

        self.actionRemoveFunction.setEnabled(selected.count() > 0)
        current: QModelIndex = self.mTableView.currentIndex()
        f = None
        if current.isValid():
            f = current.data(Qt.UserRole)

        if f != self.mCurrentFunction:
            wOld = self.scrollArea.takeWidget()
            self.mCurrentFunction = f

    def tableView(self) -> SpectralProcessingAlgorithmTreeView:
        return self.mTableView

    def setTextProfile(self, f: QgsFeature):
        self.mTestProfile = f
        self.validate()

    def validate(self) -> bool:
        is_valid = False
        # todo: validate mode with example input

        return is_valid

    def is_valid(self) -> bool:
        return self.validate()

    def expression(self) -> str:
        return self.tbExpression.toPlainText()


def spectral_algorithms() -> typing.List[QgsProcessingAlgorithm]:
    """
    Returns all QgsProcessingAlgorithms that can output a SpectralProfile
    :return:
    """
    spectral_algos = []
    for alg in QgsApplication.instance().processingRegistry().algorithms():
        for output in alg.outputDefinitions():
            if isinstance(output, SpectralProcessingProfilesOutput):
                spectral_algos.append(alg)
                break
    return spectral_algos


class SpectralProcessingProfilesWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    # def __init__(self, parameter: QgsProcessingParameterDefinition, wtype: QgsProcessingGui.WidgetType, parent=None):
    def __init__(self, parameter, dialog, row=0, col=0, **kwargs):
        self.mDialogType = QgsProcessingGui.Standard
        printCaller()
        super().__init__(parameter, self.mDialogType)
        self.widget = self.createWidget(**kwargs)
        self.label = self.createLabel(**kwargs)
        # super(SpectralProcessingProfilesWidgetWrapper, self).__init__(parameter, wtype, parent)

    def createWidget(self, *args, **kwargs):
        printCaller()
        # w = SpectralProcessingAlgorithmInputModelerParameterWidget()
        w = QWidget()
        w.setWindowTitle('Dummy widget')
        w.setLayout(QHBoxLayout())
        w.layout().addWidget(QLabel('Dummy label '))
        return w

    def setWidgetValue(self, value, context: QgsProcessingContext):
        printCaller()
        pass

    def setWidgetValue(self, value, context):
        printCaller()
        pass

    def widgetValue(self):
        printCaller()
        v = dict()
        return v

    def createLabel(self, *args, **kwargs) -> QLabel:
        pdef = self.parameterDefinition()
        return QLabel(pdef.name())

    def createWrappedLabel(self):
        printCaller()
        return QLabel('TestLabel')

    def createWrappedWidget(self):
        printCaller()
        w = QWidget()
        return w

    def setValue(self, value):

        if value is None:
            value = ''

        if self.mDialogType == QgsProcessingGui.Modeler:
            self.widget
        elif self.mDialogType == QgsProcessingGui.Batch:
            self.widget
        else:
            self.widget

    def value(self):
        if self.mDialogType == QgsProcessingGui.Modeler:
            return self.widget.windowTitle() + '+Modeler'
        elif self.mDialogType == QgsProcessingGui.Batch:
            return self.widget.windowTitle() + '+Batch'
        else:
            return self.widget.windowTitle() + '+Std'


class SpectralProcessingAlgorithmInputWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralProcessingAlgorithmInputWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model: QgsProcessingModelAlgorithm,
                                   childId: str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()

        widget = SpectralProcessingAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )

        compatible_parameter_types = [SpectralProcessingProfiles.TYPE]
        compatible_output_types = [SpectralProcessingProfiles.TYPE]
        compatible_data_types = []
        widget.populateSources(compatible_parameter_types, compatible_output_types, compatible_data_types)

        self.mRef = widget

        return widget

    def createParameterDefinitionWidget(self,
                                        context: QgsProcessingContext,
                                        widgetContext: QgsProcessingParameterWidgetContext,
                                        definition: QgsProcessingParameterDefinition = None,
                                        algorithm: QgsProcessingAlgorithm = None
                                        ) -> QgsProcessingAbstractParameterDefinitionWidget:
        printCaller(f'#{id(self)}')
        w = SpectralProcessingAlgorithmInputWidget(context, widgetContext, definition, algorithm, None)
        keepRef(w)
        # self.mWrappers.append(w)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype: QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper:
        printCaller()
        wrapper = SpectralProcessingProfilesWidgetWrapper(parameter, wtype)
        # wrapper.destroyed.connect(self._onWrapperDestroyed)
        # self.mWrappers.append(wrapper)
        keepRef(wrapper)
        return wrapper

    def parameterType(self):
        return SpectralProcessingProfiles.TYPE  # 'spectral_profile' #SpectralProcessingProfileType.__class__.__name__

    def compatibleDataTypes(self):
        #    printCaller()
        return []

    def compatibleOutputTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]

    def compatibleParameterTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]


class SpectralProcessingProfilesOutputWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralProcessingProfilesOutputWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model: QgsProcessingModelAlgorithm,
                                   childId: str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()

        widget = SpectralProcessingAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )

        compatible_parameter_types = [SpectralProcessingProfiles.TYPE]
        compatible_ouptut_types = [SpectralProcessingProfiles.TYPE]
        compatible_data_types = []
        widget.populateSources(compatible_parameter_types, compatible_ouptut_types, compatible_data_types)

        self.mRef = widget

        return widget

    def createParameterDefinitionWidget(self,
                                        context: QgsProcessingContext,
                                        widgetContext: QgsProcessingParameterWidgetContext,
                                        definition: QgsProcessingParameterDefinition = None,
                                        algorithm: QgsProcessingAlgorithm = None
                                        ) -> QgsProcessingAbstractParameterDefinitionWidget:
        printCaller(f'#{id(self)}')
        w = SpectralProcessingAlgorithmInputWidget(context, widgetContext, definition, algorithm, None)
        keepRef(w)
        # self.mWrappers.append(w)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype: QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper:
        printCaller()
        wrapper = SpectralProcessingProfilesWidgetWrapper(parameter, wtype)
        return wrapper

    def parameterType(self):
        printCaller()
        return SpectralProcessingProfilesOutput.TYPE  # 'spectral_profile' #SpectralProcessingProfileType.__class__.__name__

    def compatibleDataTypes(self, parameter):
        #    printCaller()
        return [SpectralProcessingProfiles.TYPE, SpectralProcessingProfilesOutput.TYPE]

    def compatibleOutputTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]

    def compatibleParameterTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]
