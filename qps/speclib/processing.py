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
import pathlib
import pickle
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QFontInfo
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
    QgsProcessingRegistry, QgsProcessingModelOutput

from qgis.gui import QgsCollapsibleGroupBox, QgsCodeEditorPython, QgsProcessingParameterWidgetFactoryInterface, \
    QgsProcessingModelerParameterWidget, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingParameterWidgetContext, QgsProcessingGui, \
    QgsProcessingToolboxModel, QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog, \
    QgsProcessingToolboxTreeView

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


def printCaller(prefix=''):
    """
    prints out the current code location in calling method
    :param prefix:
    :return:
    """
    curFrame = inspect.currentframe()
    outerFrames = inspect.getouterframes(curFrame)
    FOI = outerFrames[1]
    stack = inspect.stack()
    stack_class = stack[1][0].f_locals["self"].__class__.__name__
    stack_method = stack[1][0].f_code.co_name
    info = f'{stack_class}.{FOI.function}: {os.path.basename(FOI.filename)}:{FOI.lineno}'
    if len(prefix) > 0:
        prefix += ':'
    print(f'#{prefix}{info}')


class SpectralProcessingProfiles(QgsProcessingParameterDefinition):
    """
    SpectralAlgorithm Input definition, i.e. defines where the profiles come from
    """
    TYPE = 'spectral_profile'

    def __init__(self, name='Spectral Profile', description='Spectral Profile', optional: bool = False):
        super().__init__(name, description=description, optional=optional)

    def isDestination(self):
        return False

    def type(self):
        return self.TYPE

    def clone(self):
        # printCaller()
        return SpectralProcessingProfiles()

    def checkValueIsAcceptable(self, input, context:QgsProcessingContext =None) -> bool:
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

    def parameterAsSpectralProfileBlockList(self, parameters:dict, context: QgsProcessingContext) \
            -> typing.List[SpectralProfileBlock]:
        return parameterAsSpectralProfileBlockList(parameters, self.name(), context)

    def description(self):
        return 'the spectral profile'

    def isDynamic(self):
        return True

    def toolTip(self):
        return 'The spectral profile'


def parameterAsSpectralProfileBlockList(parameters: dict,
                                        name: str,
                                        context: QgsProcessingContext) -> typing.List[SpectralProfileBlock]:
    """
    Evaluates a parameter with matching name to a SpectralProcessingProfiles
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
        s = ""
        self.mSpectralProfileBlocks: typing.List[SpectralProfileBlock] = []

    def profileBlocks(self) -> typing.List[SpectralProfileBlock]:
        return self.mSpectralProfileBlocks

    def addProfileBlock(self, block: SpectralProfileBlock):
        self.mSpectralProfileBlocks.append(block)

    def type(self):
        printCaller()
        return self.TYPE


class SpectralProcessingProfilesOutputDestination(QgsProcessingDestinationParameter):

    def __init__(self, name: str, description: str = 'Spectra Profiles', defaultValue=None, optional: bool = False,
                 createByDefault=True):
        super().__init__(name, description, defaultValue, optional, createByDefault)

    def getTemporaryDestination(self) -> str:
        return 'None'

    def isSupportedOutputValue(self, value, context: QgsProcessingContext):
        error = ''
        result: bool = True

        return result, error

    def defaultFileExtension(self):
        return 'gpkg'

    def toOutputDefinition(self):
        return SpectralProcessingProfilesOutput(self.name(), self.description())

    def type(self):
        return SpectralProcessingProfiles.TYPE

    def clone(self):
        return SpectralProcessingProfilesOutputDestination(self.name(), self.description())


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


class SpectralProcessingModelTableView(QTableView):
    """
    A QTableView used in the SpectralProcessingWidget
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)


class SpectralProcessingAlgorithmTreeView(QgsProcessingToolboxTreeView):
    """
    The QTreeView used to show SpectraProcessingAlgorithms in the SpectralProcessingWidget
    """
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


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
                for output in alg.outputDefinitions():
                    if isinstance(output, SpectralProcessingProfilesOutput):
                        return True
                return False
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
        self.mProcessingModelTableModel = SpectralProcessingAlgorithmChainModel()

        # self.mProcessingModel.addFunction(GenericSpectralMathFunction())
        # self.mProcessingModel.sigChanged.connect(self.validate)
        self.mTableView: SpectralProcessingModelTableView
        self.mTableView.setModel(self.mProcessingModelTableModel)

        self.mTableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mTreeView: SpectralProcessingAlgorithmTreeView
        self.mTreeView.header().setVisible(False)
        self.mTreeView.setDragDropMode(QTreeView.DragOnly)
        self.mTreeView.setDropIndicatorShown(True)
        self.mTreeView.doubleClicked.connect(self.onTreeViewDoubleClicked)
        self.mTreeView.setToolboxProxyModel(self.mAlgorithmModel)
        s = ""

        # self.mLastExpression = None
        # self.mDefaultExpressionToolTip = self.tbExpression.toolTip()
        # self.tbExpression.textChanged.connect(self.validate)
        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: QgsProcessingAlgorithm = None

        m = QMenu()
        m.setToolTipsVisible(True)
        a = m.addAction('Add X Unit Conversion')
        # a.triggered.connect(lambda *args: self.functionModel().addFunctions([XUnitConversion()]))

        a = m.addAction('Add Python Expression')
        # a.triggered.connect(lambda *args : self.functionModel().addFunctions([GenericSpectralAlgorithm()]))

        self.actionAddFunction.setMenu(m)
        # self.actionRemoveFunction.triggered.connect(self.onRemoveFunctions)

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)

    def onTreeViewDoubleClicked(self, *args):

        alg = self.mTreeView.selectedAlgorithm()
        if alg:
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


def is_spectral_processing_algorithm(alg: QgsProcessingAlgorithm,
                                     check_in: bool = True,
                                     check_out: bool = True) -> bool:
    """
    Checks if a QgsProcessingAlgorithm is a SpectralProcessing Algorithms.
    :param alg: QgsProcessingAlgorithm
    :param check_in: if True (default), alg needs to define one or multiple SpectralAlgorithmInputs
    :param check_out: if True (default), alg need to define one or multiple SpectralAlgorithmOutputs
    :return: bool
    """
    assert isinstance(alg, QgsProcessingAlgorithm)

    bIn = False
    bOut = False

    for input in alg.parameterDefinitions():
        if isinstance(input, SpectralProcessingProfiles):
            bIn = True
            break

    for output in alg.outputDefinitions():
        if isinstance(output, SpectralProcessingProfilesOutput):
            bOut = True
            break

    if not (bIn or bOut):
        return False
    if check_in and not bIn:
        return False
    if check_out and not bOut:
        return False
    return True


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

    def __init__(self,
                 parameter: QgsProcessingParameterDefinition,
                 wtype: QgsProcessingGui.WidgetType,
                 parent=None):
        super(SpectralProcessingProfilesWidgetWrapper, self).__init__(parameter, wtype, parent)

    def createWidget(self):
        l = QLabel('Spectral Profiles')
        return l

    def setWidgetValue(self, value, context: QgsProcessingContext):
        printCaller()
        pass

    def widgetValue(self):
        printCaller()
        v = dict()
        return v

    def createLabel(self) -> QLabel:
        pdef = self.parameterDefinition()
        return QLabel(pdef.name())


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

        # widget = super(SpectralProcessingAlgorithmInputWidgetFactory, self).createModelerWidgetWrapper(model, childId, parameter, context)

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
        # wrapper.destroyed.connect(self._onWrapperDestroyed)
        # self.mWrappers.append(wrapper)
        keepRef(wrapper)
        return wrapper

    def parameterType(self):
        printCaller()
        return SpectralProcessingProfilesOutput.TYPE  # 'spectral_profile' #SpectralProcessingProfileType.__class__.__name__

    def compatibleDataTypes(self, parameter):
        #    printCaller()
        return [SpectralProcessingProfiles.TYPE]

    def compatibleOutputTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]

    def compatibleParameterTypes(self):
        printCaller()
        return [SpectralProcessingProfilesOutput.TYPE]


class SpectralProcessingAlgorithmChainModel(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super(SpectralProcessingAlgorithmChainModel, self).__init__(*args, **kwds)
        self.mPModel: QgsProcessingModelAlgorithm = QgsProcessingModelAlgorithm()
        self.mPModel.setName('SimpleModel')
        self.mPModel.setGroup('')
        self.mChilds: typing.List[str] = []

    def processingModel(self) -> QgsProcessingModelAlgorithm:
        return self.mPModel

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self.mChilds)

    def columnCount(self, parent: QModelIndex = None) -> int:
        return 1

    def index(self, row: int, column: int = ..., parent: QModelIndex = ...) -> QModelIndex:

        childId = self.mChilds[row]

        return self.createIndex(row, column, childId)

    def childAlgorithm(self, childId: str) -> QgsProcessingModelAlgorithm:
        return self.mPModel.childAlgorithm(childId)

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if not index.isValid():
            return None

        childAlgo: QgsProcessingModelChildAlgorithm = self.childAlgorithm(index.internalPointer())

        if role == Qt.DisplayRole:
            pass
        if role == Qt.DisplayRole:
            return childAlgo.childId()

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if orientation == Qt.Horizontal:
            return 'Algorithm'

    """
    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        if not parent.isValid():
            return QModelIndex()

        alg = self.mChilds[row]
        return self.createIndex(row, column, alg)
    """

    def insertAlgorithm(self, alg, index: int):

        if isinstance(alg, str):
            procReg = QgsApplication.instance().processingRegistry()
            assert isinstance(procReg, QgsProcessingRegistry)
            alg = procReg.algorithmById(alg)

        if isinstance(alg, QgsProcessingAlgorithm):
            # create new child algorithm
            alg = self.createChildAlgorithm(alg)

        assert isinstance(alg, QgsProcessingModelChildAlgorithm)
        keepRef(alg)
        self.beginInsertRows(QModelIndex(), index, index)
        childID = self.mPModel.addChildAlgorithm(alg)
        assert childID not in self.mChilds
        self.mChilds.insert(index, alg.childId())

        self.endInsertRows()

        self.update_child_connections()
        s = ""

    def update_child_connections(self):

        # model output(s) are taken from last algorithm
        n_total = len(self.mChilds)
        i_last = n_total - 1
        for i, childId in enumerate(self.mChilds):
            child: QgsProcessingModelChildAlgorithm = self.childAlgorithm(childId)
            previous: QgsProcessingModelChildAlgorithm = None
            if i > 0:
                previous = self.childAlgorithm(self.mChilds[i - 1])

            alg: QgsProcessingAlgorithm = child.algorithm()
            inputParams = alg.parameterDefinitions()
            outputParams = alg.outputDefinitions()
            destinationParams = alg.destinationParameterDefinitions()
            outputs = {}
            if i == 0:
                # this is the very first algorithm. Use its inputs as model input
                s = ""
            if i == i_last:

                for output in destinationParams:
                    if isinstance(output, SpectralProcessingProfilesOutputDestination):
                        output.setFlags(output.flags() | QgsProcessingParameterDefinition.FlagIsModelOutput)
                    if output.flags() & QgsProcessingParameterDefinition.FlagIsModelOutput:
                        if output.name() not in outputs:
                            model_output = QgsProcessingModelOutput(output.name(), output.name())
                            model_output.setChildId(child.childId())
                            model_output.setChildOutputName(output.name())
                            outputs[output.name()] = model_output
                    else:
                        s = ""

                pass

            child.setModelOutputs(outputs)

        s = ""

    def addAlgorithm(self, alg):
        self.insertAlgorithm(alg, -1)

    def removeAlgorithm(self, childId):

        s = ""

    def moveAlgorithm(self):
        pass

    def createChildAlgorithm(self, _alg: QgsProcessingAlgorithm) -> QgsProcessingModelChildAlgorithm:

        # todo: replace use of ModelerParametersDialog by own routines that don't require a widget
        # from qgis.PyQt.QtWidgets import QDialog
        # d = ModelerParametersDialog(_alg, self.mPModel)
        # d.createAlgorithm()
        # return childAlg

        alg = QgsProcessingModelChildAlgorithm(_alg.id())
        alg.generateChildId(self.mPModel)
        alg.setDescription('')
        # algorithm with configuration?

        # add parameter sources? -> done in update
        # define mode outputs -> do in update
        # alg.setModelOutputs(outputs)
        # np dependencies
        # alg.setDependencies(self.dependencies_panel.value())

        return alg
