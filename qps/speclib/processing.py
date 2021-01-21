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
    QgsProcessingRegistry

from qgis.gui import QgsCollapsibleGroupBox, QgsCodeEditorPython, QgsProcessingParameterWidgetFactoryInterface, \
    QgsProcessingModelerParameterWidget, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingParameterWidgetContext, QgsProcessingGui, \
    QgsProcessingToolboxModel, QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog

from processing import ProcessingConfig, Processing
from processing.core.ProcessingConfig import Setting
from processing.modeler.ModelerDialog import ModelerParametersDialog
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
        self.mSpectralLibrary: SpectralLibrary = None
        self.mSpectralLibraryField: str = None

    def setSpectralLibrary(self, speclib: SpectralLibrary, field: str = None):
        from ..speclib.core import spectralValueFields
        blob_fields = [f.name() for f in spectralValueFields(speclib)]
        assert len(blob_fields) >= 1, f'{speclib.name()} does not contain a SpectralProfile field'
        if isinstance(field, str):
            assert field in blob_fields, f'Field {field} is not a SpectralProfile field'
        else:
            field = blob_fields[0]
        self.mSpectralLibrary = speclib
        self.mSpectralLibraryField = field

    def profileBlocks(self) -> typing.List[SpectralProfileBlock]:
        return self.mSpectralProfileBlocks

    def isDestination(self):
        # printCaller()
        return False

    def type(self):
        # printCaller()
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
        printCaller(f'#{id(self)}')
        result = super(SpectralAlgorithmInput, self).toVariantMap()
        result['spectral_profile_blocks'] = self.mSpectralProfileBlocks
        return result

    def fromVariantMap(self, map: dict):
        printCaller()
        super(SpectralAlgorithmInput, self).fromVariantMap(map)
        self.mSpectralProfileBlocks = map.get('spectral_profile_blocks', [])

        return True


class SpectralAlgorithmOutput(QgsProcessingOutputDefinition):
    TYPE = SpectralAlgorithmInput.TYPE

    def __init__(self, name: str, description='Spectral Profile'):
        super(SpectralAlgorithmOutput, self).__init__(name, description=description)
        s = ""

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


from qgis.gui import QgsProcessingToolboxTreeView


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
        self.mProcessingModelTableModel = SimpleProcessingModelAlgorithmChain()

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
        self.actionRemoveFunction.triggered.connect(self.onRemoveFunctions)

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

    def onRemoveFunctions(self, *args):

        to_remove = set()
        for idx in self.mTableView.selectedIndexes():
            f = idx.data(Qt.UserRole)
            if isinstance(f, SpectralAlgorithm):
                to_remove.add(f)

        if len(to_remove) > 0:
            self.functionModel().removeFunctions(list(to_remove))

    def onSelectionChanged(self, selected, deselected):

        self.actionRemoveFunction.setEnabled(selected.count() > 0)
        current: QModelIndex = self.mTableView.currentIndex()
        f = None
        if current.isValid():
            f = current.data(Qt.UserRole)

        if f != self.mCurrentFunction:
            wOld = self.scrollArea.takeWidget()
            self.mCurrentFunction = f

            if isinstance(f, SpectralAlgorithm):
                w = self.mCurrentFunction.createWidget()
                self.scrollArea.setWidget(w)

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


class SpectralProfileReader(QgsProcessingAlgorithm):
    INPUT = 'input_speclib'
    OUTPUT = 'output_profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Reads spectral profiles'

    def initAlgorithm(self, configuration: dict):
        printCaller()

        p1 = QgsProcessingParameterVectorLayer(self.INPUT)
        self.addParameter(p1, createOutput=True)

        o1 = SpectralAlgorithmOutput(self.OUTPUT)
        self.addOutput(o1)
        pass

    def asPythonCommand(self) -> str:
        pass

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def createInstance(self):
        printCaller()
        alg = SpectralProfileReader()
        return alg

    def displayName(self) -> str:
        return 'Spectral Profile Reader'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Loader Help String'

    def name(self):
        return 'SpectralProfileReader'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        speclib = self.parameterAsVectorLayer(parameters, context)

        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class SpectralProfileWriter(QgsProcessingAlgorithm):
    INPUT = 'input_profiles'
    OUTPUT = 'output_speclib'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Writes spectral profiles'

    def initAlgorithm(self, configuration: dict):
        printCaller()

        p1 = SpectralAlgorithmInput(self.INPUT)
        self.addParameter(p1)

        o1 = SpectralAlgorithmOutput(self.OUTPUT)
        self.addOutput(o1)
        self.mParameters.append([p1, o1])

    def asPythonCommand(self) -> str:
        pass

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def createInstance(self):
        printCaller()
        alg = SpectralProfileReader()
        return alg

    def displayName(self) -> str:
        return 'SpectralProfileReader'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Loader Help String'

    def name(self):
        return 'Spectral Profile Loader'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        speclib = self.parameterAsVectorLayer(parameters, context)

        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class DummyAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'Input Profiles'
    OUTPUT = 'Output Profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mFunction: typing.Callable = None

    def description(self) -> str:
        return 'Dummy Algorithm Description'

    def initAlgorithm(self, configuration: dict):
        printCaller()

        p1 = SpectralAlgorithmInput(self.INPUT, description='Input Profiles')
        self.addParameter(p1, createOutput=False)

        o1 = SpectralAlgorithmOutputDestination(self.OUTPUT, description='Modified profiles')
        self.addParameter(o1)
        pass

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)

            if isinstance(self.mFunction, typing.Callable):
                profileBlock = self.mFunction(profileBlock)

            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS

    def setProcessingFunction(self, function: typing.Callable):

        assert isinstance(function, typing.Callable)
        self.mFunction = function

    def asPythonCommand(self) -> str:
        printCaller()
        pass

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        printCaller()
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def createCustomParametersWidget(self) -> QWidget:

        w = QWidget()
        label = QLabel('Placeholder custom widget')
        l = QHBoxLayout()
        l.addWidget(label)
        w.setLayout(l)
        return w

    def createExpressionContext(self,
                                parameter: dict,
                                context: QgsProcessingContext,
                                source: QgsProcessingFeatureSource,
                                ):

        printCaller()
        return None

    def createInstance(self):
        printCaller()
        alg = DummyAlgorithm()
        return alg

    def displayName(self) -> str:

        return 'Dummy Profile Algorithm'

    def flags(self):

        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):

        return 'qps'

    def helpString(self) -> str:
        return 'Dummy Alg Help String'

    def name(self):
        return 'Dummy Alg Name'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        printCaller()
        return True


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


class SpectralProcessingParameterWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralProcessingParameterWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model: QgsProcessingModelAlgorithm,
                                   childId: str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()
        # widget = super(SpectralProcessingParameterWidgetFactory, self).createModelerWidgetWrapper(model, childId, parameter, context)
        widget = SpectralAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )
        compatibleParameterTypes = [SpectralAlgorithmInput.TYPE]
        compatibleOuptutTypes = [SpectralAlgorithmInput.TYPE]
        compatibleDataTypes = []
        widget.populateSources(compatibleParameterTypes, compatibleOuptutTypes, compatibleDataTypes)
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


class SpectralAlgorithmProvider(QgsProcessingProvider):
    NAME = 'SpectralAlgorithmProvider'
    def __init__(self):
        super().__init__()
        self.algs = []

    def load(self):
        with QgsRuntimeProfiler.profile('QPS Provider'):
            ProcessingConfig.settingIcons[self.name()] = self.icon()
            ProcessingConfig.addSetting(Setting(self.name(), 'ACTIVATE_QPS',
                                                self.tr('Activate'), True))
            ProcessingConfig.readSettings()
            self.refreshAlgorithms()
        return True

    def unload(self):
        ProcessingConfig.removeSetting('ACTIVATE_QPS')

    def isActive(self):
        return ProcessingConfig.getSetting('ACTIVATE_QPS')

    def setActive(self, active):
        ProcessingConfig.setSettingValue('ACTIVATE_QPS', active)

    def name(self):
        return 'SpectralMath'

    def longName(self):
        from .. import __version__
        return f'SpectralMath ({__version__})'

    def id(self):
        return 'spectralmath'

    def helpId(self):
        return 'spectralmath'

    def icon(self):
        return QIcon(r':/qps/ui/icons/profile_expression.svg')

    def svgIconPath(self):
        return r':/qps/ui/icons/profile_expression.svg'

    def loadAlgorithms(self):
        self.algs = [
            DummyAlgorithm(),
            # SpectralProfileReader(),
            SpectralProfileReader(),
            SpectralProfileWriter(),
        ]

        for a in self.algs:
            self.addAlgorithm(a)

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True


class SimpleProcessingModelAlgorithmChain(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super(SimpleProcessingModelAlgorithmChain, self).__init__(*args, **kwds)
        self.mPModel: QgsProcessingModelAlgorithm = QgsProcessingModelAlgorithm()
        self.mChilds = []

    def processingModel(self) -> QgsProcessingModelAlgorithm:
        return self.mPModel

    def rowCount(self, parent: QModelIndex = None) -> int:
        return len(self.mChilds)

    def columnCount(self, parent: QModelIndex = None) -> int:
        return 1

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if not index.isValid():
            return None

        i = index.row()
        self.mPModel

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if orientation == Qt.Horizontal:
            return 'Algorithm'

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        if not parent.isValid():
            return None

        return None

    def insertAlgorithm(self, alg, index:int):

        if isinstance(alg, QgsProcessingAlgorithm):
            alg = alg.id()

        self.mPModel.addChildAlgorithm(childAlg)
        s = ""

    def addAlgorithm(self, alg):
        self.insertAlgorithm(alg, -1)

    def removeAlgorithm(self, childId):

        s = ""

    def moveAlgorithm(self):
        pass

    def createChildAlgorithm(self):

        alg = QgsProcessingModelChildAlgorithm(self._alg.id())
        if not self.childId:
            alg.generateChildId(self.model)
        else:
            alg.setChildId(self.childId)
        alg.setDescription(self.descriptionBox.text())
        if self.algorithmItem:
            alg.setConfiguration(self.algorithmItem.configuration())
            self._alg = alg.algorithm().create(self.algorithmItem.configuration())
        for param in self._alg.parameterDefinitions():
            if param.isDestination() or param.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue
            try:
                wrapper = self.wrappers[param.name()]
                if issubclass(wrapper.__class__, WidgetWrapper):
                    val = wrapper.value()
                elif issubclass(wrapper.__class__, QgsProcessingModelerParameterWidget):
                    val = wrapper.value()
                else:
                    val = wrapper.parameterValue()
            except InvalidParameterValue:
                val = None

            if isinstance(val, QgsProcessingModelChildParameterSource):
                val = [val]
            elif not (isinstance(val, list) and all(
                    [isinstance(subval, QgsProcessingModelChildParameterSource) for subval in val])):
                val = [QgsProcessingModelChildParameterSource.fromStaticValue(val)]

            valid = True
            for subval in val:
                if (isinstance(subval, QgsProcessingModelChildParameterSource)
                    and subval.source() == QgsProcessingModelChildParameterSource.StaticValue
                    and not param.checkValueIsAcceptable(subval.staticValue())) \
                        or (subval is None and not param.flags() & QgsProcessingParameterDefinition.FlagOptional):
                    valid = False
                    break

            if valid:
                alg.addParameterSources(param.name(), val)

        outputs = {}
        for output in self._alg.destinationParameterDefinitions():
            if not output.flags() & QgsProcessingParameterDefinition.FlagHidden:
                wrapper = self.wrappers[output.name()]

                if wrapper.isModelOutput():
                    name = wrapper.modelOutputName()
                    if name:
                        model_output = QgsProcessingModelOutput(name, name)
                        model_output.setChildId(alg.childId())
                        model_output.setChildOutputName(output.name())
                        outputs[name] = model_output
                else:
                    val = wrapper.value()

                    if isinstance(val, QgsProcessingModelChildParameterSource):
                        val = [val]

                    alg.addParameterSources(output.name(), val)

            if output.flags() & QgsProcessingParameterDefinition.FlagIsModelOutput:
                if output.name() not in outputs:
                    model_output = QgsProcessingModelOutput(output.name(), output.name())
                    model_output.setChildId(alg.childId())
                    model_output.setChildOutputName(output.name())
                    outputs[output.name()] = model_output

        alg.setModelOutputs(outputs)
        alg.setDependencies(self.dependencies_panel.value())

        return alg