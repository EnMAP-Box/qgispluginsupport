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


class SpectralAlgorithmInput(QgsProcessingParameterDefinition):
    """
    SpectralAlgorithm Input definition, i.e. defines where the profiles come from
    """
    TYPE = 'spectral_profile'

    def __init__(self, name='Spectral Profile', description='Spectral Profile', optional: bool = False):
        super().__init__(name, description=description, optional=optional)

        self.mSpectralProfileBlocks: typing.List[SpectralProfileBlock] = list()

    def n_blocks(self) -> int:
        return len(self.mSpectralProfileBlocks)

    def setFromSpectralLibrary(self, speclib: SpectralLibrary, field: str = None):
        from ..speclib.core import spectralValueFields
        blob_fields = [f.name() for f in spectralValueFields(speclib)]
        assert len(blob_fields) >= 1, f'{speclib.name()} does not contain a SpectralProfile field'
        if isinstance(field, str):
            assert field in blob_fields, f'Field {field} is not a SpectralProfile field'
        else:
            field = blob_fields[0]
        self.mSpectralProfileBlocks.extend(
            speclib.profileBlocks(value_fields=[field]))

    def profileBlocks(self) -> typing.List[SpectralProfileBlock]:
        return self.mSpectralProfileBlocks

    def isDestination(self):
        return False

    def type(self):
        return self.TYPE

    def clone(self):
        # printCaller()
        return SpectralAlgorithmInput()

    def description(self):
        return 'the spectral profile'

    def isDynamic(self):
        return True

    def toolTip(self):
        return 'The spectral profile'

    def toVariantMap(self):
        result = super(SpectralAlgorithmInput, self).toVariantMap()
        result['spectral_profile_blocks'] = self.mSpectralProfileBlocks
        return result

    def fromVariantMap(self, map: dict):
        super(SpectralAlgorithmInput, self).fromVariantMap(map)
        self.mSpectralProfileBlocks = map.get('spectral_profile_blocks', [])

        return True


class SpectralAlgorithmOutput(QgsProcessingOutputDefinition):
    TYPE = SpectralAlgorithmInput.TYPE

    def __init__(self, name: str= 'Spectral Profile', description='Spectral Profile'):
        super(SpectralAlgorithmOutput, self).__init__(name, description=description)
        s = ""
        self.mSpectralProfileBlocks: typing.List[SpectralProfileBlock] = []

    def addProfileBlock(self, block: SpectralProfileBlock):
        self.mSpectralProfileBlocks.append(block)

    def type(self):
        printCaller()
        return self.TYPE


class SpectralAlgorithmOutputDestination(QgsProcessingDestinationParameter):

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
        return SpectralAlgorithmOutput(self.name(), self.description())

    def type(self):
        return SpectralAlgorithmInput.TYPE

    def clone(self):
        return SpectralAlgorithmOutputDestination(self.name(), self.description())


class SpectralAlgorithmInputType(QgsProcessingParameterType):
    """
    Describes a SpectralAlgorithmInput in the Modeler's parameter type list
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
        return 'SpectralAlgorithmInputType'

    def create(self, name):
        printCaller()
        p = SpectralAlgorithmInput(name=name)
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
        return 'from .speclib.math import SpectralAlgorithmInputType'


class SpectralAlgorithmInputModelerParameterWidget(QgsProcessingModelerParameterWidget):

    def __init__(self,
                 model: QgsProcessingModelAlgorithm,
                 childId: str,
                 parameter: QgsProcessingParameterDefinition,
                 context: QgsProcessingContext,
                 parent: QWidget = None
                 ):
        super(SpectralAlgorithmInputModelerParameterWidget, self).__init__(model,
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


class SpectralAlgorithmInputWidget(QgsProcessingAbstractParameterDefinitionWidget):
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

    def createParameter(self, name: str, description: str, flags) -> SpectralAlgorithmInput:
        printCaller()

        param = SpectralAlgorithmInput(name, description=description)
        param.setFlags(flags)
        keepRef(param)

        return param


class SpectralProcessingModelTableView(QTableView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)





class SpectralProcessingAlgorithmTreeView(QgsProcessingToolboxTreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class SpectralProcessingAlgorithmModel(QgsProcessingToolboxProxyModel):

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
                    if isinstance(output, SpectralAlgorithmOutput):
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
        self.mProcessingModelTableModel = ProcessingModelAlgorithmChain()

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
        #self.actionRemoveFunction.triggered.connect(self.onRemoveFunctions)

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


def spectral_algorithms() -> typing.List[QgsProcessingAlgorithm]:
    """
    Returns all QgsProcessingAlgorithms that can output a SpectralProfile
    :return:
    """
    spectral_algos = []
    for alg in QgsApplication.instance().processingRegistry().algorithms():
        for output in alg.outputDefinitions():
            if isinstance(output, SpectralAlgorithmOutput):
                spectral_algos.append(alg)
                break
    return spectral_algos


class SpectralAlgorithmInputWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter: QgsProcessingParameterDefinition,
                 wtype: QgsProcessingGui.WidgetType,
                 parent=None):
        super(SpectralAlgorithmInputWidgetWrapper, self).__init__(parameter, wtype, parent)

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


class SpectralAlgorithmInputWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralAlgorithmInputWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model: QgsProcessingModelAlgorithm,
                                   childId: str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()

        # widget = super(SpectralAlgorithmInputWidgetFactory, self).createModelerWidgetWrapper(model, childId, parameter, context)

        widget = SpectralAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )

        compatible_parameter_types = [SpectralAlgorithmInput.TYPE]
        compatible_ouptut_types = [SpectralAlgorithmInput.TYPE]
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
        w = SpectralAlgorithmInputWidget(context, widgetContext, definition, algorithm, None)
        keepRef(w)
        # self.mWrappers.append(w)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype: QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper:
        printCaller()
        wrapper = SpectralAlgorithmInputWidgetWrapper(parameter, wtype)
        # wrapper.destroyed.connect(self._onWrapperDestroyed)
        # self.mWrappers.append(wrapper)
        keepRef(wrapper)
        return wrapper

    def parameterType(self):
        return SpectralAlgorithmInput.TYPE  # 'spectral_profile' #SpectralAlgorithmInputType.__class__.__name__

    def compatibleDataTypes(self):
        #    printCaller()
        return []

    def compatibleOutputTypes(self):
        printCaller()
        return [SpectralAlgorithmOutput.TYPE]

    def compatibleParameterTypes(self):
        printCaller()
        return [SpectralAlgorithmOutput.TYPE]


class SpectralAlgorithmOutputWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralAlgorithmOutputWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model: QgsProcessingModelAlgorithm,
                                   childId: str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()

        # widget = super(SpectralAlgorithmInputWidgetFactory, self).createModelerWidgetWrapper(model, childId, parameter, context)

        widget = SpectralAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )

        compatible_parameter_types = [SpectralAlgorithmInput.TYPE]
        compatible_ouptut_types = [SpectralAlgorithmInput.TYPE]
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
        w = SpectralAlgorithmInputWidget(context, widgetContext, definition, algorithm, None)
        keepRef(w)
        # self.mWrappers.append(w)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype: QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper:
        printCaller()
        wrapper = SpectralAlgorithmInputWidgetWrapper(parameter, wtype)
        # wrapper.destroyed.connect(self._onWrapperDestroyed)
        # self.mWrappers.append(wrapper)
        keepRef(wrapper)
        return wrapper

    def parameterType(self):
        printCaller()
        return SpectralAlgorithmOutput.TYPE  # 'spectral_profile' #SpectralAlgorithmInputType.__class__.__name__

    def compatibleDataTypes(self, parameter):
        #    printCaller()
        return [SpectralAlgorithmInput.TYPE]

    def compatibleOutputTypes(self):
        printCaller()
        return [SpectralAlgorithmOutput.TYPE]

    def compatibleParameterTypes(self):
        printCaller()
        return [SpectralAlgorithmOutput.TYPE]

class ProcessingModelAlgorithmChain(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super(ProcessingModelAlgorithmChain, self).__init__(*args, **kwds)
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

    def childAlgorithm(self, childId:str) -> QgsProcessingModelAlgorithm:
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

    def insertAlgorithm(self, alg, index:int):

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
        i_last = n_total-1
        for i, childId in enumerate(self.mChilds):
            child: QgsProcessingModelChildAlgorithm = self.childAlgorithm(childId)
            previous: QgsProcessingModelChildAlgorithm = None
            if i > 0:
                previous = self.childAlgorithm(self.mChilds[i-1])

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
                    if isinstance(output, SpectralAlgorithmOutputDestination):
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

    def createChildAlgorithm(self, _alg:QgsProcessingAlgorithm) -> QgsProcessingModelChildAlgorithm:

        # todo: replace use of ModelerParametersDialog by own routines that don't require a widget
        #from qgis.PyQt.QtWidgets import QDialog
        #d = ModelerParametersDialog(_alg, self.mPModel)
        #d.createAlgorithm()
        #return childAlg

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
