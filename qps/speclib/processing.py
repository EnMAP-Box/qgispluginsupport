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
import inspect
import os
import re
import sys
import enum
import pathlib
import pickle

from PyQt5.QtWidgets import QInputDialog
from qgis.core import QgsProcessingProvider

from qgis.PyQt.QtCore import QMimeData, Qt, pyqtSignal, QModelIndex, QAbstractListModel, QObject, QPointF, QByteArray
from qgis.PyQt.QtGui import QColor, QFont, QContextMenuEvent
from qgis.PyQt.QtWidgets import QWidget, QTableView, QTreeView, \
    QLabel, QGroupBox, QFileDialog, QMessageBox, \
    QHBoxLayout, QVBoxLayout, QMenu, QAction, QToolButton, QGridLayout
from qgis.core import QgsFeature, QgsProcessingAlgorithm, QgsProcessingContext, \
    QgsProcessingParameterDefinition, QgsProcessingFeedback, \
    QgsProcessingParameterType, QgsProcessingModelChildParameterSource, \
    QgsProcessingModelAlgorithm, QgsApplication, QgsProcessingDestinationParameter, \
    QgsProcessingOutputDefinition, QgsProcessingModelChildAlgorithm, \
    QgsProcessingRegistry, QgsProcessingModelOutput, QgsProcessingModelParameter, QgsProject, QgsProcessingException, \
    Qgis

from qgis.gui import QgsProcessingParameterWidgetFactoryInterface, \
    QgsProcessingModelerParameterWidget, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsProcessingParameterWidgetContext, QgsProcessingToolboxModel, QgsProcessingToolboxProxyModel, \
    QgsProcessingRecentAlgorithmLog, \
    QgsProcessingToolboxTreeView, QgsProcessingGui, QgsGui, QgsAbstractProcessingParameterWidgetWrapper, \
    QgsProcessingContextGenerator, QgsProcessingParametersWidget
from processing.modeler.ProjectProvider import ProjectProvider
from processing.modeler.ModelerAlgorithmProvider import ModelerAlgorithmProvider
from .core.spectrallibrary import SpectralLibrary, SpectralProfile, SpectralProfileBlock
from . import speclibUiPath
from ..utils import loadUi

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
        if isinstance(input, (SpectralLibrary, SpectralProfileBlock)):
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


def structureModelGraphicItems(model: QgsProcessingModelAlgorithm):
    # set the positions for parameters and algorithms in the model canvas:
    x = 150
    y = 50
    dx = 100
    dy = 75
    components = model.parameterComponents()
    for n, p in components.items():
        p: QgsProcessingModelParameter
        p.setPosition(QPointF(x, y))
        x += dx
    model.setParameterComponents(components)

    y = 150
    x = 250
    childAlgs = [model.childAlgorithm(childId) for childId in model.childAlgorithms()]

    for calg in childAlgs:
        calg: QgsProcessingModelChildAlgorithm
        calg.setPosition(QPointF(x, y))
        y += dy
    for outDef in model.outputDefinitions():
        s = ""
    s = ""


def outputParameterResult(results: dict,
                          output_parameter: typing.Union[str, QgsProcessingOutputDefinition]):
    """

    :param results: dict, QgsProcessingModelAlgorithm or QgsProcessingAlgorithm result
    :param output_parameter: name or QgsProcessingOutputDefinition
    :return: the parameter result or None
    """
    if isinstance(output_parameter, QgsProcessingOutputDefinition):
        output_parameter = output_parameter.name()

    for k, v in results.items():
        if k.endswith(output_parameter):
            return v
    return None


def outputParameterResults(results: dict, model: QgsProcessingModelAlgorithm) -> typing.Dict[str, typing.Any]:
    R: typing.Dict[str, typing.Any] = dict()
    for p in model.outputDefinitions():
        R[p.name()] = outputParameterResult(results, p)
    return R


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
    elif isinstance(value, SpectralProfileBlock):
        blocks = [value]
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
        # printCaller()
        error = ''
        result: bool = True

        return result, error

    def defaultFileExtension(self) -> str:
        return 'gpkg'

    def toOutputDefinition(self) -> SpectralProcessingProfilesOutput:
        # printCaller()
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


class NULL_MODEL(QgsProcessingModelAlgorithm):
    """
    A proxy to represent None | NULL proxy values in a SpectralProcessingModelList
    """

    def __init__(self, *args, **kwds):
        super(NULL_MODEL, self).__init__(*args, *kwds)

    def id(self):
        return ''

    def displayName(self):
        return ''


class SpectralProcessingModelList(QAbstractListModel):
    """
    Contains a list of SpectralProcessingModels(QgsModelAlgorithms)
    """

    def __init__(self, *args,
                 allow_empty: bool = False,
                 init_models: bool = True,
                 **kwds):
        """
        A list model that shows existing spectral processing models
        :param args:
        :param allow_empty: shows an "empty" model, e.g. to select None (NULL_MODEL())
        :param init_models: True, if True, searches existing processing providers for spectral models
        :param kwds:
        """
        super(SpectralProcessingModelList, self).__init__(*args, **kwds)

        self.mModelIds: typing.List[str] = list()
        self.mNullModel = NULL_MODEL()
        if allow_empty:
            self.mModelIds.append('')

        if init_models:
            procReg = QgsApplication.instance().processingRegistry()
            for p in procReg.providers():
                p: QgsProcessingProvider
                self.refreshProvider(p)
                p.algorithmsLoaded.connect(lambda *args, p=p.id(): self.refreshProvider(p))

    def refreshProvider(self, provider):

        if isinstance(provider, str):
            provider = QgsApplication.instance().processingRegistry().providerById(provider)
        if isinstance(provider, QgsProcessingProvider):
            old_models = [a for a in self.mModelIds if a.startswith(provider.id())]
            all_models = [a.id() for a in provider.algorithms() if is_spectral_processing_model(a)]
            to_remove = [a for a in old_models if a not in all_models]
            to_add = [a for a in all_models if a not in old_models]
            for m in to_remove:
                self.removeModel(m)
            for m in to_add:
                self.addModel(m)

    def __iter__(self):
        return iter(self.mModelIds)

    def __getitem__(self, slice):
        return self.mModelIds[slice]

    def __contains__(self, item):
        if isinstance(item, QgsProcessingAlgorithm):
            item = item.id()
        return item in self.mModelIds

    def __len__(self):
        return len(self.mModelIds)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mModelIds)

    def columnCount(self, *args, **kwargs):
        return 1

    def addModel(self, model: QgsProcessingModelAlgorithm):
        self.insertModel(-1, model)

    def findModelId(self, model: typing.Union[str, QgsProcessingModelAlgorithm]) -> \
            typing.Tuple[int, str]:
        if isinstance(model, QgsProcessingModelAlgorithm):
            model_id = model.id()
        else:
            model_id = model
        if model_id in self.mModelIds:
            return self.mModelIds.index(model_id), model_id
        return None, None

    def modelId2model(self, modelId: str) -> QgsProcessingModelAlgorithm:
        if modelId == self.mNullModel.id():
            return self.mNullModel
        else:
            reg = QgsApplication.instance().processingRegistry()
            model: QgsProcessingModelAlgorithm = reg.algorithmById(modelId)
            assert is_spectral_processing_model(model)
            return model

    def insertModel(self, row, modelId: typing.Union[str, QgsProcessingModelAlgorithm]):
        if isinstance(modelId, QgsProcessingModelAlgorithm):
            assert is_spectral_processing_model(modelId)
            modelId = modelId.id()

        assert isinstance(modelId, str)

        if not isinstance(QgsApplication.processingRegistry().algorithmById(modelId), QgsProcessingModelAlgorithm):
            raise Exception(f'Model {modelId} needs to be registered to a QgsProcessingProvider first')

        if isinstance(row, QModelIndex):
            row = row.row()

        if modelId in self.mModelIds:
            i = self.mModelIds.index(modelId)
            # update existing model
            idx = self.index(i, 0)
            self.dataChanged.emit(idx, idx)
        else:
            if row < 0:
                row = self.rowCount()

            self.beginInsertRows(QModelIndex(), row, row)
            self.mModelIds.insert(row, modelId)
            self.endInsertRows()

    def removeModel(self, modelId: str):
        if isinstance(modelId, QgsProcessingModelAlgorithm):
            modelId = modelId.id()

        assert isinstance(modelId, str)
        if modelId in self.mModelIds:
            row = self.mModelIds.index(modelId)
            self.beginRemoveRows(QModelIndex(), row, row)
            self.mModelIds.remove(modelId)
            self.endRemoveRows()

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        if row < 0 or row >= len(self.mModelIds):
            return QModelIndex()
        model = self.mModelIds[row]
        return self.createIndex(row, column, model)

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        modelId = self.mModelIds[index.row()]
        model = self.modelId2model(modelId)

        provider = model.provider()
        if isinstance(provider, QgsProcessingProvider):
            providerName = provider.name() + ':'
        else:
            providerName = ''

        if role == Qt.DisplayRole:
            return f'{model.displayName()}'

        if role == Qt.ToolTipRole:
            return f'{model.id()}'

        if role == Qt.UserRole:
            return model
        return None


class SpectralProcessingModelCreatorAlgorithmWrapper(QgsProcessingParametersWidget):
    """
    A wrapper to keep a references on QgsProcessingAlgorithm
    and related parameter values and widgets
    """
    sigParameterValueChanged = pyqtSignal(str)
    sigVerificationChanged = pyqtSignal(bool)

    def __init__(self, alg: QgsProcessingAlgorithm,
                 test_blocks: typing.List[SpectralProfileBlock],
                 context: QgsProcessingContext = None):
        super().__init__(alg, None)
        # self.alg: QgsProcessingAlgorithm = alg.create({})
        self.name: str = self.algorithm().displayName()
        # self.parameterValuesDefault: typing.Dict[str, typing.Any] = dict()
        self.parameterValues: typing.Dict[str, typing.Any] = dict()
        self.mErrors: typing.List[str] = []
        self.wrappers = {}
        self.mTestBlocks: typing.List[SpectralProfileBlock] = test_blocks
        self.extra_parameters = {}
        if context is None:
            context = QgsProcessingContext()
        self.processing_context: QgsProcessingContext = context

        class ContextGenerator(QgsProcessingContextGenerator):

            def __init__(self, context):
                super().__init__()
                self.processing_context = context

            def processingContext(self):
                return self.processing_context

        self.context_generator = ContextGenerator(self.processing_context)

        self.initWidgets()
        self.tooltip: str = ''

        self._mWidgets = []
        self.is_active: bool = True

        self.verify(self.mTestBlocks)

    def initWidgets(self):
        super().initWidgets()
        # Create widgets and put them in layouts
        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(QgsProject.instance())

        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue
            if isinstance(param, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                continue
            if param.isDestination():
                continue

            wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(param, QgsProcessingGui.Standard)
            wrapper.setWidgetContext(widget_context)
            wrapper.registerProcessingContextGenerator(self.context_generator)
            wrapper.registerProcessingParametersGenerator(self)
            wrapper.widgetValueHasChanged.connect(self.parameterWidgetValueChanged)
            self.wrappers[param.name()] = wrapper

            label = wrapper.createWrappedLabel()
            self.addParameterLabel(param, label)

            widget = wrapper.createWrappedWidget(self.processing_context)
            stretch = wrapper.stretch()
            self.addParameterWidget(param, widget, stretch)

        for wrapper in list(self.wrappers.values()):
            wrapper.postInitialize(list(self.wrappers.values()))

    def parameterWidgetValueChanged(self, wrapper: QgsAbstractProcessingParameterWidgetWrapper):

        print(f'new value: {self.name}:{wrapper}= {wrapper.parameterValue()} = {wrapper.widgetValue()}')
        self.verify(self.mTestBlocks)
        self.parameterValues[wrapper.parameterDefinition().name()] = wrapper.widgetValue()
        self.sigParameterValueChanged.emit(wrapper.parameterDefinition().name())

    def verify(self, test_blocks: typing.List[SpectralProfileBlock]) -> bool:
        context = self.context_generator.processingContext()
        feedback = QgsProcessingFeedback()
        alg = self.algorithm()
        self.mErrors.clear()
        try:
            undefined = self.undefinedParameters()
            assert len(undefined) == 0, f'Undefined parameters: {",".join([p.name() for p in undefined])}'

            parameters = {}
            for p in alg.parameterDefinitions():
                if isinstance(p, SpectralProcessingProfiles):
                    parameters[p.name()] = test_blocks
                else:
                    if p.name() in self.wrappers.keys():
                        parameters[p.name()] = self.wrappers[p.name()].parameterValue()

            success = alg.prepareAlgorithm(parameters, context, feedback)
            assert success, feedback.textLog()
            results = alg.processAlgorithm(parameters, context, feedback)

            for p in alg.outputDefinitions():
                if isinstance(p, SpectralProcessingProfilesOutput):
                    assert p.name() in results.keys(), feedback.textLog()
            s = ""

        except QgsProcessingException as ex1:
            self.mErrors.append(feedback.textLog())
        except AssertionError as ex2:
            self.mErrors.append(str(ex2))

        success = len(self.mErrors) == 0

        # enable css highlighting?
        if False and isinstance(self.parent(), QGroupBox):
            if success:
                self.setStyleSheet('')
            else:
                self.setStyleSheet("""background-color: red;""")

        return success, ','.join(self.mErrors)

    def undefinedParameters(self) -> typing.List[QgsProcessingParameterDefinition]:
        """
        Return the paramters with missing values
        :return:
        :rtype:
        """
        missing = []
        for p in self.algorithm().parameterDefinitions():
            if isinstance(p, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                # will be connected automatically
                continue
            if not bool(p.flags() & QgsProcessingParameterDefinition.FlagOptional) and p.defaultValue() is None:
                value = self.parameterValues.get(p.name(), None)
                if value is None:
                    missing.append(p)
        return missing

    def isVerified(self) -> bool:
        return len(self.mErrors) == 0

    def allParametersDefined(self) -> bool:
        """
        Returns True if all required parameters are set
        :return:
        """
        return len(self.undefinedParameters()) == 0

    def __hash__(self):
        return hash((self.algorithm().name(), id(self)))


class SpectralProcessingModelCreatorTableModel(QAbstractListModel):
    sigModelVerified = pyqtSignal(bool, str)

    def __init__(self, *args, **kwds):
        super(SpectralProcessingModelCreatorTableModel, self).__init__(*args, **kwds)
        self.mAlgorithmWrappers: typing.List[SpectralProcessingModelCreatorAlgorithmWrapper] = []

        self.mColumnNames = {0: 'Algorithm',
                             1: 'Parameters'}

        self.mModelName: str = 'New Model'
        self.mModelGroup: str = ''
        self.mProcessingContext: QgsProcessingContext = QgsProcessingContext()
        self.mModelChildIds: typing.Dict[str, SpectralProcessingModelCreatorAlgorithmWrapper] = dict()
        self.mTestBlocks: typing.List[SpectralProfileBlock] = [
            SpectralProfileBlock.dummy(5)]

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.MoveAction | Qt.CopyAction

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.MoveAction

    def setProcessingContext(self, context: QgsProcessingContext):
        assert isinstance(context, QgsProcessingContext)
        self.mProcessingContext = context

    def processingContext(self) -> QgsProcessingContext:
        return self.mProcessingContext

    MIMEDATAKEY = 'application/wrapperindices'

    def mimeTypes(self) -> typing.List[str]:
        return [self.MIMEDATAKEY]

    def mimeData(self, indexes: typing.Iterable[QModelIndex]) -> QMimeData:
        mimeData = QMimeData()

        wrappers = []
        wrapper_idx = []
        wrapper_rows = []
        for idx in indexes:
            if idx.isValid():
                w = idx.data(Qt.UserRole)
                if isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper):
                    wrappers.append(w)
                    wrapper_rows.append(self.mAlgorithmWrappers.index(w))
                    wrapper_idx.append(idx)

        mimeData.setData(self.MIMEDATAKEY, QByteArray(pickle.dumps(wrapper_rows)))
        return mimeData

    def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int,
                        parent: QModelIndex) -> bool:

        if self.MIMEDATAKEY in data.formats():
            return True

        return False

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:

        if self.MIMEDATAKEY in data.formats() and action == Qt.MoveAction:
            ba = bytes(data.data(self.MIMEDATAKEY))
            src_rows = pickle.loads(ba)
            self.beginMoveRows(QModelIndex(), src_rows[0], src_rows[-1], QModelIndex(), row)
            for src_row in sorted(src_rows, reverse=True):
                self.mAlgorithmWrappers.insert(max(0, row), self.mAlgorithmWrappers.pop(src_row))
            self.endMoveRows()
        else:
            s = ""

        return False

    def setModelName(self, name: str):
        assert isinstance(name, str)
        self.mModelName = name

    def modelName(self) -> str:
        return self.mModelName

    def setModelGroup(self, group: str):
        assert isinstance(group, str)
        self.mModelGroup = group

    def modelGroup(self) -> str:
        return self.mModelGroup

    def __getitem__(self, slice):
        return self.mAlgorithmWrappers[slice]

    def __delitem__(self, slice):
        w = self[slice]
        self.removeAlgorithms(w)

    def __len__(self):
        return len(self.mAlgorithmWrappers)

    def __iter__(self):
        return iter(self.mAlgorithmWrappers)

    INPUT_PROFILE_PREFIX = 'model_profile_input'
    OUTPUT_PROFILE_PREFIX = 'model_profile_output'

    def createModel(self) -> QgsProcessingModelAlgorithm:

        model = QgsProcessingModelAlgorithm()
        model.setName(self.mModelName)
        model.setGroup(self.mModelGroup)

        # create child algorithms
        self.mModelChildIds.clear()

        previous_cid: str = None
        previous_calg: QgsProcessingModelChildAlgorithm = None

        active_wrappers = [w for w in self if w.is_active]
        if len(active_wrappers) == 0:
            return None

        for w in active_wrappers:
            w: SpectralProcessingModelCreatorAlgorithmWrapper
            if not w.is_active:
                continue
            # create new child algorithm
            calg: QgsProcessingModelChildAlgorithm = QgsProcessingModelChildAlgorithm(w.algorithm().id())
            calg.generateChildId(model)
            calg.setDescription(w.name)

            cid = model.addChildAlgorithm(calg)
            self.mModelChildIds[cid] = w
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

            # add none-profile parameter sources (which are not set / connected automatically)
            for parameter in w.algorithm().parameterDefinitions():
                if isinstance(parameter, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
                    continue
                value = w.wrappers[parameter.name()].parameterValue()
                # todo: handle expressions
                calg.addParameterSources(parameter.name(),
                                         [QgsProcessingModelChildParameterSource.fromStaticValue(value)])

            if len(calg.parameterSources()) == 0:
                raise Exception('Unable to retrieve sources for {}')
            previous_cid = cid
            previous_calg = calg

        # use sinks of last algorithm as model outputs
        for i, sink in enumerate([p for p in calg.algorithm().parameterDefinitions()
                                  if isinstance(p, SpectralProcessingProfilesSink)]):
            outname = f'{self.OUTPUT_PROFILE_PREFIX}_{i + 1}'

            childOutput = QgsProcessingModelOutput(outname)
            childOutput.setChildOutputName(sink.name())
            calg.setModelOutputs({outname: childOutput})
            model.addOutput(SpectralProcessingProfilesOutput(outname))

        # set the positions for input parameters and algorithms in the model canvas:
        x = 150
        y = 50
        dx = 100
        dy = 75
        components = model.parameterComponents()
        for n, p in components.items():
            p.setPosition(QPointF(x, y))
            x += dx
        model.setParameterComponents(components)

        y = 150
        x = 250
        for cid in self.mModelChildIds:
            calg = model.childAlgorithms()[cid]
            calg.setPosition(QPointF(x, y))
            y += dy

        return model

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self.mAlgorithmWrappers)

    def columnCount(self, parent: QModelIndex = None) -> int:
        return len(self.mColumnNames)

    def clearModel(self):
        self.beginResetModel()
        self.removeAlgorithms(self[:])
        self.endResetModel()

    """
    def index(self, row: int, column: int = ..., parent: QModelIndex = ...) -> QModelIndex:

        wrapper = self.mAlgorithmWrappers[row]

        return self.createIndex(row, column, wrapper)
    """

    def verifyModel(self, test_blocks: typing.List[SpectralProfileBlock],
                    context: QgsProcessingContext,
                    feedback: QgsProcessingFeedback) -> \
            typing.Tuple[bool, str]:
        messages = []

        try:
            algs = [w for w in self if w.is_active]
            assert len(algs) > 0, 'Please add / activate spectral processing algorithms'
            # 1. create model
            model = self.createModel()

            assert isinstance(model, QgsProcessingModelAlgorithm), 'Unable to create QgsProcessingModelAlgorithm'
            assert is_spectral_processing_model(model), 'Create model is not a spectral processing mode'

            parameters = {}
            for p in model.parameterDefinitions():
                if isinstance(p, SpectralProcessingProfiles):
                    parameters[p.name()] = test_blocks

            model.initAlgorithm()
            success, msg = model.canExecute()
            assert success, msg

            # 2. prepare model
            assert model.prepareAlgorithm(parameters, context, feedback), \
                'Failed to prepare model with test data'

            # 3. execute model
            results: dict = model.processAlgorithm(parameters, context, feedback)

            # 4. check outputs
            for p in model.outputDefinitions():
                if isinstance(p, SpectralProcessingProfilesOutput):
                    for k, block_list in results.items():
                        if isinstance(k, str) and k.endswith(f':{p.name()}'):
                            assert isinstance(block_list, list), \
                                f'Output for {p.name()} is not List[SpectralProfileBlock], but {block_list}'
                            for block in block_list:
                                assert isinstance(block, SpectralProfileBlock), \
                                    f'Output for {p.name()} (List[SpectralProfileBlock]) contains {block}'

        except Exception as ex:
            messages.append(str(ex))
        success = len(messages) == 0
        msg = '\n'.join(messages)
        self.sigModelVerified.emit(success, msg)

        return success, msg

    def wrapper2idx(self, wrapper: SpectralProcessingModelCreatorAlgorithmWrapper) -> QModelIndex:
        assert isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper)
        row = self.mAlgorithmWrappers.index(wrapper)
        return self.index(row, 0)

    def idx2wrapper(self, index) -> SpectralProcessingModelCreatorAlgorithmWrapper:

        if isinstance(index, QModelIndex):
            index = index.row()
        return self.mAlgorithmWrappers[index]

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsSelectable | \
                Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled

        return flags

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if not index.isValid():
            return None
        col = index.column()
        wrapper = self.idx2wrapper(index)
        alg: QgsProcessingAlgorithm = wrapper.algorithm()

        if role == Qt.DisplayRole:
            if col == 0:
                return wrapper.name
            if col == 1:
                return str(wrapper.parameterValues())
        if role == Qt.DecorationRole:
            if col == 0:
                if wrapper.allParametersDefined() and wrapper.isVerified():
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
                tt = f'{alg.displayName()}\n{alg.shortDescription()}'
                if not wrapper.isVerified():
                    # tt += '\n<span style="color:red">'+'<br/>'.join(wrapper.mErrors) + '</span>'
                    tt += '\n' + '\n'.join(wrapper.mErrors)
                return tt

            if col == 1:
                return '\n'.join(f'{k}:{v}' for k, v in wrapper.parameterValues().items())

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

        wrapper = self.idx2wrapper(index)

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
                            SpectralProcessingModelCreatorAlgorithmWrapper],
                        index: int,
                        name: str = None) -> SpectralProcessingModelCreatorAlgorithmWrapper:
        procReg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)
        alg_ids = [a.id() for a in procReg.algorithms()]

        if isinstance(alg, str):
            # alg needs to be a registered algorithms id
            if alg not in alg_ids:
                for a in alg_ids:
                    if a.endswith(alg):
                        alg = a

            a = procReg.algorithmById(alg)

            assert isinstance(a, QgsProcessingAlgorithm), f'Unable to find QgsProcessingAlgorithm {alg}'
            wrapper = SpectralProcessingModelCreatorAlgorithmWrapper(a,
                                                                     self.mTestBlocks,
                                                                     context=self.mProcessingContext)
        elif isinstance(alg, QgsProcessingAlgorithm):
            return self.insertAlgorithm(alg.id(), index, name=name)
        else:
            assert isinstance(alg, SpectralProcessingModelCreatorAlgorithmWrapper)
            wrapper = alg
            wrapper.processing_context = self.processingContext()

        if index < 0:
            index = self.rowCount()

        names = [w.name for w in self]
        wrapper.sigParameterValueChanged.connect(self.onParameterChanged)
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
        self.endInsertRows()
        return wrapper

    def onParameterChanged(self, parameter_name: str):
        w = self.sender()
        if isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper) and w in self.mAlgorithmWrappers:
            row = self.mAlgorithmWrappers.index(w)
            self.dataChanged.emit(self.index(row, 0),
                                  self.index(row, self.columnCount()),
                                  [Qt.DisplayRole, Qt.DecorationRole])

    def addAlgorithm(self, alg, name: str = None) -> SpectralProcessingModelCreatorAlgorithmWrapper:
        return self.insertAlgorithm(alg, -1, name=name)

    def removeAlgorithms(self, algorithms: typing.Union[typing.List[SpectralProcessingModelCreatorAlgorithmWrapper],
                                                        SpectralProcessingModelCreatorAlgorithmWrapper]
                         ):

        if isinstance(algorithms, SpectralProcessingModelCreatorAlgorithmWrapper):
            algorithms = [algorithms]
        for alg in algorithms:
            assert alg in self.mAlgorithmWrappers
            i = self.mAlgorithmWrappers.index(alg)
            self.beginRemoveRows(QModelIndex(), i, i)
            self.mAlgorithmWrappers.remove(alg)
            self.endRemoveRows()


class SpectralProcessingModelCreatorTableView(QTableView):
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
            self) -> typing.List[SpectralProcessingModelCreatorAlgorithmWrapper]:
        wrappers = set()
        for idx in self.selectedIndexes():
            w = idx.data(Qt.UserRole)
            if isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper):
                wrappers.add(w)
        return list(wrappers)

    def currentAlgorithmWrapper(self) -> SpectralProcessingModelCreatorAlgorithmWrapper:
        w = self.currentIndex().data(Qt.UserRole)
        if isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper):
            return w
        else:
            return None

    def setCurrentAlgorithmWrapper(self, w: SpectralProcessingModelCreatorAlgorithmWrapper):
        for r in range(self.model().rowCount()):
            idx = self.model().index(r, 0)
            if idx.data(Qt.UserRole) == w:
                self.setCurrentIndex(idx)
                break

    def spectralProcessingModelTableModel(self) -> SpectralProcessingModelCreatorTableModel:

        return self.model()

    def onRemoveSelected(self, indices: typing.List[QModelIndex]):
        """
        Removes selected rows
        :param indices:
        :return:
        """

        if isinstance(indices, bool):
            indices = self.selectedIndexes()

        m = self.spectralProcessingModelTableModel()
        wrappers = set()
        for i in indices:
            wrappers.add(i.data(Qt.UserRole))
        for w in wrappers:
            if isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper):
                m.removeAlgorithms(w)

    def onSetChecked(self, indices: typing.List[QModelIndex], check: bool):

        for i in indices:
            self.model().setData(i, Qt.Checked if check else Qt.Unchecked, role=Qt.CheckStateRole)

    def createContextMenu(self, index: QModelIndex) -> QMenu:
        wrapper: SpectralProcessingModelCreatorAlgorithmWrapper = index.data(Qt.UserRole)

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


class SpectralProcessingWidget(QWidget, QgsProcessingContextGenerator):
    sigSpectralProcessingModelChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        QgsProcessingContextGenerator.__init__(self)
        loadUi(speclibUiPath('spectralprocessingwidget.ui'), self)

        # create 3 dummy blocks for testing
        self.mDummyBlocks: typing.List[SpectralProfileBlock] = []
        self.mDummyBlocks.append(SpectralProfileBlock.dummy(1, 7, 'nm'))
        self.mDummyBlocks.append(SpectralProfileBlock.dummy(1, 5, 'um'))
        self.mDummyBlocks.append(SpectralProfileBlock.dummy(1, 3, '-'))  # without unit

        self.mProcessingAlgorithmModel = SpectralProcessingAlgorithmModel(self)

        self.mProcessingFeedback: QgsProcessingFeedback = QgsProcessingFeedback()
        self.mProcessingWidgetContext: QgsProcessingParameterWidgetContext = QgsProcessingParameterWidgetContext()
        self.mProcessingWidgetContext.setMessageBar(self.mMessageBar)

        self.mProcessingContext: QgsProcessingContext = QgsProcessingContext()
        self.mProcessingContext.setFeedback(self.mProcessingFeedback)

        # self.mProcessingModel = SimpleProcessingModelAlgorithm()
        self.mProcessingModelTableModel = SpectralProcessingModelCreatorTableModel()
        self.mProcessingModelTableModel.setProcessingContext(self.mProcessingContext)
        self.mProcessingModelTableModel.dataChanged.connect(self.onModelDataChanged)
        self.mProcessingModelTableModel.dataChanged.connect(self.verifyModel)
        self.mProcessingModelTableModel.rowsInserted.connect(self.onRowsInserted)
        self.mProcessingModelTableModel.sigModelVerified.connect(self.onModelVerified)
        self.tbModelName.setText(self.mProcessingModelTableModel.modelName())
        self.tbModelGroup.setText(self.mProcessingModelTableModel.modelGroup())
        self.tbModelGroup.textChanged.connect(self.mProcessingModelTableModel.setModelGroup)
        self.tbModelName.textChanged.connect(self.mProcessingModelTableModel.setModelName)

        self.mTableView: SpectralProcessingModelCreatorTableView
        assert isinstance(self.mTableView, SpectralProcessingModelCreatorTableView)
        self.mTableView.setModel(self.mProcessingModelTableModel)
        self.mTableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mTableView.selectionModel().currentChanged.connect(self.onCurrentAlgorithmChanged)
        self.mTableView.setDragEnabled(True)
        self.mTableView.setAcceptDrops(True)
        self.mTableView.setDropIndicatorShown(True)
        self.mTreeViewAlgorithms: SpectralProcessingAlgorithmTreeView
        self.mTreeViewAlgorithms.header().setVisible(False)
        self.mTreeViewAlgorithms.setDragDropMode(QTreeView.DragOnly)
        self.mTreeViewAlgorithms.setDropIndicatorShown(True)
        self.mTreeViewAlgorithms.doubleClicked.connect(self.onAlgorithmTreeViewDoubleClicked)
        self.mTreeViewAlgorithms.setToolboxProxyModel(self.mProcessingAlgorithmModel)

        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: QgsProcessingAlgorithm = None

        self.actionRemoveFunction.triggered.connect(self.mTableView.onRemoveSelected)
        self.actionApplyModel.triggered.connect(self.onApplyModel)
        self.actionResetModel.triggered.connect(self.onResetModel)
        self.actionVerifyModel.triggered.connect(self.verifyModel)
        self.actionSaveModel.triggered.connect(self.saveModel)
        self.actionLoadModel.triggered.connect(self.openModel)

        self.actionCopyLog.triggered.connect(self.onCopyLog)
        self.actionClearLog.triggered.connect(self.tbLogs.clear)
        self.actionSaveLog.triggered.connect(self.onSaveLog)

        self.btnCopyLog.setDefaultAction(self.actionCopyLog)
        self.btnClearLog.setDefaultAction(self.actionClearLog)
        self.btnSaveLog.setDefaultAction(self.actionSaveLog)

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)

        self.verifyModel()

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        current = self.currentAlgorithm()
        idx = self.mProcessingModelTableModel.index(first, 0, parent)
        w = idx.data(Qt.UserRole)

        if not isinstance(current, SpectralProcessingModelCreatorAlgorithmWrapper) and \
                isinstance(w, SpectralProcessingModelCreatorAlgorithmWrapper):
            self.mTableView.setCurrentAlgorithmWrapper(w)

    def processingContext(self) -> QgsProcessingContext:
        return self.mProcessingContext

    def onCopyLog(self):
        mimeData = QMimeData()
        mimeData.setText(self.tbLogs.toPlainText())
        mimeData.setHtml(self.tbLogs.toHtml())
        QgsApplication.clipboard().setMimeData(mimeData)

    def onModelVerified(self, success: bool, message: str):

        self.actionApplyModel.setEnabled(success)

        self.mMessageBar.clearWidgets()
        if len(message) > 0:
            self.mMessageBar.pushMessage('', message, level=Qgis.Info, duration=0)
        else:
            self.mMessageBar.pushMessage('Model ready', level=Qgis.Success, duration=0)

    def onSaveLog(self):

        pass

    def currentAlgorithm(self) -> SpectralProcessingModelCreatorAlgorithmWrapper:
        return self.mTableView.currentAlgorithmWrapper()

    def onApplyModel(self, *args):
        # verify model
        valid, msg = self.verifyModel()
        if valid:
            self.sigSpectralProcessingModelChanged.emit()

    def onResetModel(self, *args):
        s = ""

    def onModelDataChanged(self, idx1: QModelIndex, idx2: QModelIndex, roles: typing.List[Qt.ItemDataRole]):

        wrapper = idx1.data(Qt.UserRole)
        current = self.currentAlgorithm()
        if isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            if wrapper == current:
                # update algorithm info
                self.gbParameterWidgets.setTitle(current.name)

    def openModel(self, filename):
        if isinstance(filename, bool):
            filename = None

        if filename is None:
            from processing.modeler.ModelerUtils import ModelerUtils

            filename, selected_filter = QFileDialog.getOpenFileName(self,
                                                                    self.tr('Open Model'),
                                                                    ModelerUtils.modelsFolders()[0],
                                                                    self.tr('Processing models (*.model3 *.MODEL3)'))
            if filename:
                self.loadModel(filename)

    def clearModel(self):
        self.mProcessingModelTableModel.clearModel()

    def loadModel(self, model: typing.Union[str, pathlib.Path, QgsProcessingModelAlgorithm]):
        if isinstance(model, str):
            model = pathlib.Path(model)
        if isinstance(model, pathlib.Path):
            assert model.is_file(), f'Not a model file: {model}'
            m = QgsProcessingModelAlgorithm()
            m.fromFile(model.as_posix())
            model = m
        assert isinstance(model, QgsProcessingModelAlgorithm)

        if not is_spectral_processing_model(model):
            s = ""
        assert is_spectral_processing_model(model)
        self.mProcessingModelTableModel.clearModel()

        for cName, cAlg in model.childAlgorithms().items():
            alg = cAlg.algorithm()
            sources = cAlg.parameterSources()
            w = self.mProcessingModelTableModel.addAlgorithm(alg.id(), name=cAlg.description())
            for p in w.algorithm().parameterDefinitions():
                if not isinstance(p, SpectralProcessingProfiles) and p.name() in sources.keys():
                    value = sources[p.name()][0].staticValue()
                    if value:
                        w.wrappers[p.name()].setParameterValue(value, self.mProcessingContext)
        self.tbModelName.setText(model.name())
        self.tbModelGroup.setText(model.group())

    def projectProvider(self) -> ProjectProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('project')

    def modelerAlgorithmProvider(self) -> ModelerAlgorithmProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('model')

    def saveModel(self, filename):
        model = self.mProcessingModelTableModel.createModel()
        if not isinstance(model, QgsProcessingModelAlgorithm):
            return
        if isinstance(filename, bool):
            filename = None

        projectProvider = self.projectProvider()

        destinations = ['Project', 'File']
        if filename is not None:
            destination = 'File'
        else:
            destination, success = QInputDialog.getItem(self, 'Save model', 'Save model to...', destinations,
                                                        editable=False, )
            if not success:
                return

        if destination == 'File' and filename is None:
            from processing.modeler.ModelerUtils import ModelerUtils
            name = model.name()
            if name == '':
                name = 'SpectralProcessingModel'
            default_path = pathlib.Path(ModelerUtils.modelsFolders()[0]) / f'{name}.model3'
            filename, filter = QFileDialog.getSaveFileName(self,
                                                           self.tr('Save Model'),
                                                           default_path.as_posix(),
                                                           self.tr('Processing models (*.model3 *.MODEL3)'))
        if destination == 'File' and filename is not None:
            # save to file
            filename = pathlib.Path(filename).as_posix()
            if not filename.endswith('.model3'):
                filename += '.model3'
            model.setSourceFilePath(filename)
            if not model.toFile(filename):
                QMessageBox.warning(self, self.tr('I/O error'),
                                    self.tr('Unable to save edits. Reason:\n {0}').format(str(sys.exc_info()[1])))
            else:
                modelerProvider = self.modelerAlgorithmProvider()
                # destFilename = os.path.join(ModelerUtils.modelsFolders()[0], os.path.basename(filename))
                # shutil.copyfile(filename, destFilename)
                modelerProvider.loadAlgorithms()

        elif destination == 'Project':
            # save to project
            projectProvider.add_model(model)

    def verifyModel(self, *args) -> typing.Tuple[bool, str]:
        messages = []
        rx_error_alg = re.compile('Error encountered while running (?P<algname>.+)$')
        model = self.processingTableModel().createModel()

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        success, msg = self.processingTableModel().verifyModel(self.mDummyBlocks, context, feedback)
        self.actionApplyModel.setEnabled(success)
        if success:
            self.mProcessingFeedback
        return success, msg

    def onCurrentAlgorithmChanged(self, current, previous):

        # clear grid
        grid: QGridLayout = self.gbParameterWidgets.layout()
        while grid.count() > 0:
            item = grid.takeAt(0)
            widget = item.widget()
            if isinstance(widget, QWidget):
                widget.setParent(None)

        wrapper = current.data(Qt.UserRole)
        if not isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            self.gbParameterWidgets.setTitle('<No Algorithm selected>')
            self.gbParameterWidgets.setVisible(False)
        else:
            self.gbParameterWidgets.setVisible(True)
            self.gbParameterWidgets.setTitle(wrapper.name)

            row = 0
            wrapper.setParent(self.gbParameterWidgets)
            grid.addWidget(wrapper, row, 0)

    def onAlgorithmTreeViewDoubleClicked(self, *args):

        alg = self.mTreeViewAlgorithms.selectedAlgorithm()
        if is_spectral_processing_model(alg, SpectralProfileIOFlag.Outputs | SpectralProfileIOFlag.Inputs):
            self.loadModel(alg)
        elif is_spectral_processing_algorithm(alg, SpectralProfileIOFlag.Outputs | SpectralProfileIOFlag.Inputs):
            self.mProcessingModelTableModel.addAlgorithm(alg)

    def processingTableModel(self) -> SpectralProcessingModelCreatorTableModel:
        return self.mProcessingModelTableModel

    def model(self) -> QgsProcessingModelAlgorithm:
        return self.processingTableModel().createModel()

    def onSelectionChanged(self, selected, deselected):

        self.actionRemoveFunction.setEnabled(selected.count() > 0)
        current: QModelIndex = self.mTableView.currentIndex()
        f = None
        if current.isValid():
            f = current.data(Qt.UserRole)

        if f != self.mCurrentFunction:
            self.mCurrentFunction = f

    def tableView(self) -> SpectralProcessingAlgorithmTreeView:
        return self.mTableView


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
