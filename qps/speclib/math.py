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
from qgis.PyQt.QtWidgets import QPlainTextEdit, QWidget, QTableView, QLabel, QComboBox, \
    QHBoxLayout, QVBoxLayout, QSpacerItem, QMenu, QAction, QToolButton, QGridLayout
from qgis.core import QgsFeature, QgsProcessingAlgorithm, QgsProcessingContext, \
    QgsRuntimeProfiler, QgsProcessingProvider, QgsProcessingParameterDefinition, QgsProcessingFeedback, \
    QgsProcessingParameterType, QgsProcessingModelChildParameterSource, \
    QgsProcessingModelAlgorithm, \
    QgsProcessingFeatureSource, QgsProcessingOutputDefinition

from qgis.gui import QgsCollapsibleGroupBox, QgsCodeEditorPython, QgsProcessingParameterWidgetFactoryInterface, \
    QgsProcessingModelerParameterWidget, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingParameterWidgetContext, QgsProcessingGui
from processing import ProcessingConfig, Processing
from processing.core.ProcessingConfig import Setting
import numpy as np
from .core import SpectralLibrary, SpectralProfile, speclibUiPath
from ..unitmodel import UnitConverterFunctionModel, BAND_INDEX, XUnitModel
from ..utils import loadUi
from ..models import TreeModel, TreeNode
import sip
import weakref
SpectralMathResult = collections.namedtuple('SpectralMathResult', ['x', 'y', 'x_unit', 'y_unit'])

MIMEFORMAT_SPECTRAL_MATH_FUNCTION = 'qps.speclib.math.spectralmathfunction'

XML_SPECTRALMATHFUNCTION = 'SpectralMathFunction'

REFS = dict()

def keepRef(o):
    #to_remove = [d for d in REFS if sip.isdeleted(d)]
    #for d in to_remove:
    #    pass
        #REFS.remove(d)
    REFS[id(o)] = o

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

    def __init__(self, name='Spectral Profile', description='Spectral Profile', optional:bool=False):
        super().__init__(name, description=description, optional=optional)

        #self.setMetadata({
            #'widget_wrapper': 'processing.gui.wrappers.BasicWidgetWrapper'
            #'widget_wrapper': 'processing.gui.wrappers.BasicWidgetWrapper'
        #})
        #self.destroyed.connect(self.sigAboutToBeDestroyed.emit)
        self.mX = []
        self.mY = []

    def isDestination(self):
        #printCaller()
        return False

    def type(self):
        #printCaller()
        return 'spectral_profile'

    def clone(self):
        printCaller()
        return SpectralAlgorithmInput()

    def description(self):
        return 'the spectral profile'

    def isDynamic(self):
        return True

    def toolTip(self):
        return 'The spectral profile'

    def toVariantMap(self):
        printCaller()
        result = {
            'x': self.mX,
            'y': self.mY
        }
        return result

    def fromVariantMap(self, map:dict):
        printCaller()
        self.mY = map.get('y', [])
        self.mX = map.get('x', [])
        return True


class SpectralAlgorithmOutput(QgsProcessingOutputDefinition):
    def __init__(self, name:str, description='Spectral Profile'):
        super(SpectralAlgorithmOutput, self).__init__(name, description=description)

    def type(self):
        printCaller()
        return 'spectral_profile'


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
        #global REFS
        keepRef(p)
        #REFS.append(p)
        #self.mRefs.append(p)
        return p

    def metadata(self):
        printCaller()
        return {'x':[], 'y':[]}

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


        #label = QLabel('Profiles')
        #self.layout().addWidget(label)

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
    def __init__(self, context: QgsProcessingContext, widgetContext:QgsProcessingParameterWidgetContext,
                 definition: QgsProcessingParameterDefinition = None,
                 algorithm: QgsProcessingAlgorithm = None,
                 parent: QWidget = None):

        printCaller()
        super().__init__(context, widgetContext, definition, algorithm, parent)

        self.mContext= context
        self.mDefinition = definition
        self.mAlgorithm = algorithm
        l = QVBoxLayout()
        self.mL = QLabel('Placeholder Input Widget')
        l.addWidget(self.mL)
        self.mLayout = l
        self.setLayout(l)
        self.mPARAMETERS = dict()

    def _wasDestroyed(self, pid):
        printCaller()
        self.mPARAMETERS.pop(pid)

    def createParameter(self, name:str, description:str, flags) -> SpectralAlgorithmInput:
        printCaller()

        param = SpectralAlgorithmInput(name, description=description)

        param.setFlags(flags)
        keepRef(param)
        #pid = id(param)
        #self.mPARAMETERS[pid] = param
        #param.sigAboutToBeDestroyed.connect(lambda *args, p=pid: self._wasDestroyed(p))
        return param

class DummyAlgorithm(QgsProcessingAlgorithm):

    def __init__(self):

        super().__init__()

        self.mParameters = []

    def description(self) -> str:
        return 'Dummy Algorithm Description'

    def initAlgorithm(self, configuration:dict):
        printCaller()

        p1 = SpectralAlgorithmInput()
        self.addParameter(p1, createOutput=True)
        #o1 = SpectralAlgorithmOutput('dst_profile')
        #self.addOutput(o1, )
        self.mParameters.append(p1)
        #s = ""
        pass

    def asPythonCommand(self) -> str:
        printCaller()
        pass

    def canExecute(self, parameters:dict, context:QgsProcessingContext) -> bool:
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
                                parameter:dict,
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

        return QgsProcessingAlgorithm.FlagSupportsBatch

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

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        printCaller()
        OUTPUTS = dict()

        return OUTPUTS

class SpectralAlgorithmInputWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter: QgsProcessingParameterDefinition,
                 wtype: QgsProcessingGui.WidgetType,
                 parent=None):
        super(SpectralAlgorithmInputWidgetWrapper, self).__init__(parameter, wtype, parent)

    def createWidget(self):
        l = QLabel('CUST_WIDGET')
        return l

    def setWidgetValue(self, value, context:QgsProcessingContext):
        printCaller()
        pass

    def widgetValue(self):
        printCaller()
        v = dict()
        return v

    def createLabel(self) -> QLabel:
        return QLabel('SpectralAlgLAbel')


class SpectralMathParameterWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralMathParameterWidgetFactory, self).__init__()
        self.mWrappers = []

    def createModelerWidgetWrapper(self,
                                   model:QgsProcessingModelAlgorithm,
                                   childId:str,
                                   parameter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        printCaller()

        widget = SpectralAlgorithmInputModelerParameterWidget(
            model, childId, parameter, context
        )
        return widget


    def createParameterDefinitionWidget(self,
                                        context: QgsProcessingContext,
                                        widgetContext: QgsProcessingParameterWidgetContext,
                                        definition: QgsProcessingParameterDefinition =None,
                                        algorithm:QgsProcessingAlgorithm = None
                                        ) -> QgsProcessingAbstractParameterDefinitionWidget:
        printCaller(f'#{id(self)}')
        w = SpectralAlgorithmInputWidget(context, widgetContext, definition, algorithm, None)
        #self.mWrappers.append(w)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype:  QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper :

        printCaller()
        wrapper = SpectralAlgorithmInputWidgetWrapper(parameter, wtype)
        #wrapper.destroyed.connect(self._onWrapperDestroyed)
        self.mWrappers.append(wrapper)
        return wrapper


    def parameterType(self):
        printCaller()
        return 'spectral_profile' #SpectralAlgorithmInputType.__class__.__name__



class SpectralAlgorithmProvider(QgsProcessingProvider):

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
        return 'QPS'

    def longName(self):
        from .. import __version__
        return f'QPS ({__version__})'

    def id(self):
        return 'qps'

    def helpId(self):
        return 'qps'

    def icon(self):
        return QIcon(r':/qps/ui/icons/profile.svg')

    def svgIconPath(self):
        return r':/qps/ui/icons/profile.svg'

    def loadAlgorithms(self):
        self.algs = [
            DummyAlgorithm()
        ]

        for a in self.algs:
            self.addAlgorithm(a)

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True
