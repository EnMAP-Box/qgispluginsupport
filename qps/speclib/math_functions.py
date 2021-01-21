import collections
import typing
import importlib
import inspect
import pickle
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QFontInfo
from qgis.PyQt.QtXml import QDomElement, QDomDocument, QDomNode, QDomCDATASection
from qgis.PyQt.QtWidgets import QPlainTextEdit, QWidget, QTableView, QLabel, QComboBox, \
    QHBoxLayout, QVBoxLayout, QSpacerItem, QMenu, QAction, QToolButton, QGridLayout
from qgis.core import QgsFeature, QgsProcessingAlgorithm, QgsProcessingContext, \
    QgsRuntimeProfiler, QgsProcessingProvider, QgsProcessingParameterDefinition, QgsProcessingFeedback, \
    QgsProcessingParameterType, \
     QgsProcessingParameterDefinition, QgsProcessingModelAlgorithm

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

SpectralMathResult = collections.namedtuple('SpectralMathResult', ['x', 'y', 'x_unit', 'y_unit'])

MIMEFORMAT_SPECTRAL_MATH_FUNCTION = 'qps.speclib.math.spectralmathfunction'

XML_SPECTRALMATHFUNCTION = 'SpectralMathFunction'



def function2mimedata(functions: typing.List['SpectralAlgorithm']) -> QMimeData:
    doc = QDomDocument()
    node = doc.createElement('root')

    for f in functions:
        assert isinstance(f, SpectralAlgorithm)
        f.writeXml(node, doc)

    doc.appendChild(node)
    ba = doc.toByteArray()

    mimeData = QMimeData()
    mimeData.setData(MIMEFORMAT_SPECTRAL_MATH_FUNCTION, ba)

    return mimeData

def mimedata2functions(mimeData:QMimeData) -> typing.List['SpectralAlgorithm']:
    assert isinstance(mimeData, QMimeData)
    results = []
    if MIMEFORMAT_SPECTRAL_MATH_FUNCTION in mimeData.formats():
        ba = mimeData.data(MIMEFORMAT_SPECTRAL_MATH_FUNCTION)
        doc = QDomDocument()
        doc.setContent(ba)
        root = doc.firstChildElement('root')
        if not root.isNull():
            fNode = root.firstChildElement(XML_SPECTRALMATHFUNCTION)
            while not fNode.isNull():
                f = SpectralAlgorithm.readXml(fNode)
                if isinstance(f, SpectralAlgorithm):
                    results.append(f)
                fNode = fNode.nextSiblingElement(XML_SPECTRALMATHFUNCTION)

    return results


class SpectralAlgorithm(QgsProcessingAlgorithm):

    @staticmethod
    def is_valid_result(result: SpectralMathResult) -> bool:
        if not isinstance(result, SpectralMathResult):
            return False
        if not isinstance(result.x, (np.ndarray, list)):
            return False
        if not isinstance(result.y, (np.ndarray, list)):
            return False
        return True

    @staticmethod
    def applyFunctionStack(functionStack: typing.Iterable[typing.Optional['SpectralAlgorithm']],
                           *args) -> SpectralMathResult:

        if isinstance(functionStack, SpectralAlgorithm):
            functionStack = [functionStack]
        else:
            assert isinstance(functionStack, typing.Iterable)

        spectralMathResult, feature = SpectralAlgorithm._unpack(*args)

        for f in functionStack:
            assert isinstance(f, SpectralAlgorithm)

            spectralMathResult = f.apply(spectralMathResult, feature)
            if not SpectralAlgorithm.is_valid_result(spectralMathResult):
                return None

        return spectralMathResult

    @staticmethod
    def _unpack(*args) -> typing.Tuple[SpectralMathResult, QgsFeature]:
        assert len(args) >= 1
        f = None
        if isinstance(args[-1], QgsFeature):
            f = args[-1]

        if isinstance(args[0], SpectralProfile):
            sp: SpectralProfile = args[0]
            x = sp.xValues()
            y = sp.yValues()
            x_unit = sp.xUnit()
            y_unit = sp.yUnit()
            f = sp
        elif isinstance(args[0], SpectralMathResult):
            return args[0], f
        elif len(args) == 4:
            x, y, x_unit, y_unit = args
        elif len(args) >= 5:
            x, y, x_unit, y_unit, f = args[:5]

        x = np.asarray(x)
        y = np.asarray(y)

        return SpectralMathResult(x=x, y=y, x_unit=x_unit, y_unit=y_unit), f

    def __init__(self, name: str = None):
        super().__init__()
        if name is None:
            name = self.__class__.__name__
        self.mError = None
        self.mName: str = name
        self.mHelp: str = None
        self.mIcon: QIcon = QIcon(':/qps/ui/icons/profile.svg')
        self.mToolTip: str = None

    def __eq__(self, other):
        if not isinstance(other, SpectralAlgorithm):
            return False
        if self.id() != other.id():
            return False
        return self.__dict__ == other.__dict__

    def __hash__(self):
        # hash on instance
        return hash(id(self))

    def initAlgorithm(self, configuration:dict):

        self.addParameter(SpectralAlgorithmInputDefinition())

        from qgis.core import QgsProcessingParameterNumber, QgsProcessingParameterString
        """
        class ParameterRasterCalculatorExpression(QgsProcessingParameterString):

            def __init__(self, name='', description='', multiLine=False):
                super().__init__(name, description, multiLine=multiLine)
                self.setMetadata({
                    'widget_wrapper': 'processing.algs.qgis.ui.RasterCalculatorWidgets.ExpressionWidgetWrapper'
                })

            def type(self):
                return 'raster_calc_expression'

            def clone(self):
                return ParameterRasterCalculatorExpression(self.name(), self.description(), self.multiLine())

        self.addParameter(ParameterRasterCalculatorExpression())
        """

        self.addParameter(QgsProcessingParameterNumber('TESTNUMBER',
                                                       'info testnumber',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0.0, defaultValue=0.0, optional=True))

    def processAlgorithm(self,  parameters: dict, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        s = ""
        result = parameters
        return result

    def createInstance(self):
        return type(self)()

    def name(self) -> str:
        return 'spectral_algorithm'

    def displayName(self) -> str:
        return 'Spectral Algorithm'

    def flags(self):
        return super().flags()

    def group(self):
        return 'Spectral Math'

    def groupId(self):
        return 'spectralmath'

    def hasHtmlOutputs(self) -> bool:
        return False

    def shortDescription(self) -> str:
        return f'Not implemented: Short description of {self.name()}'

    def shortHelpString(self) -> str:
        return self.mHelp

    def icon(self) -> QIcon:
        return QIcon(self.svgIconPath())

    def toolTip(self) -> str:
        return self.mToolTip

    def svgIconPath(self) -> str:
        return ':/qps/ui/icons/profile.svg'

    def tags(self) -> typing.List[str]:
        return ['spectral math']

    def validateInputCrs(self, parameters: dict, context:QgsProcessingContext):
        return super().validateInputCrs(parameters, context)


    sigChanged = pyqtSignal()

    @staticmethod
    def readXml(element: QDomElement) -> typing.Optional['SpectralAlgorithm']:
        assert element.nodeName() == XML_SPECTRALMATHFUNCTION
        functionType = element.attribute('ftype')
        functionName = element.attribute('fname', functionType)
        moduleName = element.attribute('fmodule')
        module = importlib.import_module(moduleName)
        functionClass_ = getattr(module, functionType)
        function: SpectralAlgorithm = functionClass_()
        function.setName(functionName)
        return function

    def writeXml(self, parent:QDomElement, doc:QDomDocument) -> QDomElement:
        """
        Writes the
        :param element:
        :type element:
        :param doc:
        :type doc:
        :return:
        :rtype:
        """
        node: QDomElement = doc.createElement(XML_SPECTRALMATHFUNCTION)
        node.setAttribute('ftype', str(self.id()))
        node.setAttribute('fmodule', inspect.getmodule(self).__name__)
        node.setAttribute('fname', str(self.name()))
        parent.appendChild(node)
        return node

    def createCustomParametersWidget(self) -> QWidget:
        """
        Create a QWidget to configure this function
        :return:
        """
        return None

    def apply(self, spectralMathResult:SpectralMathResult, feature:QgsFeature) -> SpectralMathResult:
        """

        :param x: x values, e.g. wavelength or band indices
        :param y: y values, e.g. spectral values
        :param x_units: str, e.g. wavelength unit
        :param y_units: str
        :param feature: QgsFeature, e.g. with metadata
        :return: tuple with manipulated (x,y, x_units, y_units) or None if failed
        """
        return None

class XUnitConversion(SpectralAlgorithm):

    def __init__(self, x_unit:str=BAND_INDEX, x_unit_model:XUnitModel=None):
        super().__init__()
        self.mTargetUnit = x_unit
        self.mUnitConverterFunctionModel = UnitConverterFunctionModel()

        if not isinstance(x_unit_model, XUnitModel):
            x_unit_model = XUnitModel()
        self.mUnitModel = x_unit_model

    def unitConverter(self) -> UnitConverterFunctionModel:
        return self.mUnitConverterFunctionModel

    def setTargetUnit(self, unit:str):
        self.mTargetUnit = unit

    def createCustomParametersWidget(self) -> QWidget:

        w = QWidget()
        l = QGridLayout()
        l.addWidget(QLabel('X Unit'), 0, 0)

        cb = QComboBox()
        cb.setModel(self.mUnitModel)
        cb.currentIndexChanged[str].connect(self.setTargetUnit)

        idx = self.mUnitModel.unitIndex(self.mTargetUnit)
        if idx.isValid():
            cb.setCurrentIndex(idx.row())
        l.addWidget(cb, 0, 1)
        w.setLayout(l)
        return w

    def apply(self, result:SpectralMathResult, feature: QgsFeature) -> SpectralMathResult:

        f = self.mUnitConverterFunctionModel.convertFunction(result.x_unit, self.mTargetUnit)
        if callable(f):
            x = f(result.x)
            return SpectralMathResult(x=x, y=result.y, x_unit=self.mTargetUnit, y_unit=result.y_unit)
        else:
            return None

class GenericSpectralAlgorithm(SpectralAlgorithm):

    def __init__(self):
        super().__init__()
        self.mExpression = None

    def setExpression(self, expression:str):
        changed = expression != self.mExpression
        self.mExpression = expression

        if changed:
            self.sigChanged.emit()

    def apply(self, spectralMathResult:SpectralMathResult, feature:QgsFeature) -> SpectralMathResult:
        self.mError = None

        if self.mExpression:
            values = spectralMathResult._asdict()

            try:
                exec(self.mExpression, values)
                return SpectralMathResult(x=values['x'], y=values['y'], x_unit=values['x_unit'], y_unit=values['y_unit'] )
            except Exception as ex:
                self.mError = str(ex)
                return None
        else:
            return spectralMathResult

    def createCustomParametersWidget(self) -> QgsCodeEditorPython:

        editor = QgsCodeEditorPython()
        editor.setTitle(self.name())
        editor.setText(self.mExpression)
        editor.textChanged.connect(lambda *args, e=editor: self.setExpression(e.text()))
        return editor
