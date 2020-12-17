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
PARAMETER_TYPE = 'SPECTRAL_MATH_PARAMETER'

class SpectralAlgorithmInputDefinition(QgsProcessingParameterDefinition):

    def __init__(self, name='', description='', optional:bool=False):
        super().__init__(name, description=description, optional=optional)

        self.setMetadata({
            #'widget_wrapper': 'processing.gui.wrappers.BasicWidgetWrapper'
            'widget_wrapper': 'processing.gui.wrappers.BasicWidgetWrapper'
        })

        self.mX = None
        self.mY = None

    def isDestination(self):
        return False

    def type(self):
        return 'spetral_profile'

    def clone(self):
        return SpectralAlgorithmInputDefinition()

    def description(self):
        return 'the spectral profile'

    def isDynamic(self):
        return True

    def toolTip(self):
        return 'The spectral profile'

    def toVariantMap(self):
        result = {
            'x': self.mX,
            'y': self.mY
        }
        return result

    def fromVariantMap(self, map:dict):
        self.mY = map.get('y', [])
        self.mX = map.get('x', [])
        return True


class SpectralAlgorithmInputType(QgsProcessingParameterType):

    def __init__(self):
        super().__init__()
        self.mName = 'PROFILE INPUT'
        self.mRefs = []

    def acceptedPythonType(self):
        return ['str']

    def description(self):
        return 'Spectral Profile Inputs'

    def name(self):
        return 'Spectral Profiles'

    def create(self, name):
        p = SpectralAlgorithmInputDefinition(name=name)

        self.mRefs.append(p)

        return p

    def metadata(self):
        return {'x':[], 'y':[]}

    def flags(self):
        return QgsProcessingParameterType.ExposeToModeler

    def id(self):
        print('#SpectralAlgorithmInputType:id')
        return self.__class__.__name__

    def acceptedPythonTypes(self):
        return ['SpectralProfile', 'ndarray']

    def acceptedStringValues(self):
        return ['Profile Input']

    def pythonImportString(self):
        return 'from qps.speclib.math import SpectralAlgorithmInputType'


class SpectralAlgorithmInputDefinitionWidget(QgsProcessingAbstractParameterDefinitionWidget):

    def __init__(self, context: QgsProcessingContext, widgetContext:QgsProcessingParameterWidgetContext,
                 definition: QgsProcessingParameterDefinition = None,
                 algorithm: QgsProcessingAlgorithm = None,
                 parent: QWidget = None):

        super().__init__(context, widgetContext, definition, algorithm, parent)
        self.mContext= context
        self.mDefinition = definition
        self.mAlgorithm = algorithm
        l = QVBoxLayout()
        self.mL = QLabel('Input Widget')
        l.addWidget(self.mL)
        self.mLayout = l
        self.setLayout(l)
    def createParameter(self, name:str, description:str, flags) -> SpectralAlgorithmInputDefinition:

        param = SpectralAlgorithmInputDefinition(name, description=description)
        param.setFlags(flags)
        return param

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

class SpectralMathParameterWidgetFactory(QgsProcessingParameterWidgetFactoryInterface):

    def __init__(self):
        super(SpectralMathParameterWidgetFactory, self).__init__()

    def createModelerWidgetWrapper(self,
                                   model:QgsProcessingModelAlgorithm,
                                   childId:str,
                                   paramter: QgsProcessingParameterDefinition,
                                   context: QgsProcessingContext
                                   ) -> QgsProcessingModelerParameterWidget:
        print('#SpectralMathParameterWidgetFactory:createModelerWidgetWrapper')
        return None

    def createParameterDefinitionWidget(self,
                                        context: QgsProcessingContext,
                                        widgetContext: QgsProcessingParameterWidgetContext,
                                        definition: QgsProcessingParameterDefinition =None,
                                        algorithm:QgsProcessingAlgorithm = None
                                        ) -> QgsProcessingAbstractParameterDefinitionWidget:
        print('#SpectralMathParameterWidgetFactory:createParameterDefinitionWidget')
        w = SpectralAlgorithmInputDefinitionWidget(context, widgetContext, definition, algorithm, None)
        return w

    def createWidgetWrapper(self,
                            parameter: QgsProcessingParameterDefinition,
                            wtype:  QgsProcessingGui.WidgetType) -> QgsAbstractProcessingParameterWidgetWrapper :
        print('#SpectralMathParameterWidgetFactory:createWidgetWrapper')
        return None

    def parameterType(self):
        print('#SpectralMathParameterWidgetFactory:parameterType')
        #return SpectralAlgorithmInputType.__class__.__name__
        return PARAMETER_TYPE


def function2mimedata(functions: typing.List[SpectralAlgorithm]) -> QMimeData:
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

def mimedata2functions(mimeData:QMimeData) -> typing.List[SpectralAlgorithm]:
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


class SpectralMathFunctionModel(QAbstractTableModel):

    sigChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralMathFunctionModel, self).__init__(*args, **kwds)

        self.mFunctions: typing.List[SpectralAlgorithm] = []
        self.mIsEnabled: typing.Dict[SpectralAlgorithm, bool] = dict()

        self.mColumnNames = ['Steps']

    def __iter__(self):
        return iter(self.mFunctions)

    def __len__(self):
        return len(self.mFunctions)

    def __eq__(self, other):
        if isinstance(other, SpectralMathFunctionModel):
            if len(self) != len(other):
                return False
            for f1, f2 in zip(self, other):
                if f1 != f2:
                    return False
                if self.mIsEnabled.get(f1) != other.mIsEnabled.get(f2):
                    return False
            return True
        else:
            return False

    @staticmethod
    def readXml(element: QDomElement):
        modelNode = element.firstChildElement('SpectralMathFunctionModel')
        if not modelNode.isNull():
            model = SpectralMathFunctionModel()
            is_checked = dict()
            functions = []
            functionNode = modelNode.firstChildElement(XML_SPECTRALMATHFUNCTION)
            while not functionNode.isNull():
                f = SpectralAlgorithm.readXml(functionNode)
                if isinstance(f, SpectralAlgorithm):
                    functions.append(f)
                    is_checked[f] = str(functionNode.attribute('checked', 'true')).lower() in ['1', 'true']
                functionNode = functionNode.nextSiblingElement(XML_SPECTRALMATHFUNCTION)

            if len(functions) > 0:
                model.addFunctions(functions)
                for f, c in is_checked.items():
                    model.mIsEnabled[f] = c


            return model
        else:
            return None

    def writeXml(self, element: QDomElement, doc: QDomDocument):

        parent = doc.createElement('SpectralMathFunctionModel')
        for f in self:
            f: SpectralAlgorithm
            node = f.writeXml(parent, doc)
            node.setAttribute('checked', str(self.mIsEnabled.get(f, False)))
        element.appendChild(parent)

    def validate(self, test: SpectralMathResult) -> bool:

        stack = self.functionStack()
        for f in self:
            f.mError = None

        result = SpectralAlgorithm.applyFunctionStack(stack, test)
        roles = [Qt.DecorationRole, Qt.ToolTipRole]
        self.dataChanged.emit(
            self.createIndex(0, 0),
            self.createIndex(len(self)-1, 0),
            roles
        )
        return isinstance(result, SpectralMathResult)

    def headerData(self, i, orientation, role=None):

        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.mColumnNames[i]
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return f'{i+1}'
        return None

    def index(self, row:int, col:int, parent: QModelIndex=None):
        return self.createIndex(row, col, self.mFunctions[row])

    def functionStack(self) -> typing.List[SpectralAlgorithm]:
        return [f for f in self.mFunctions if self.mIsEnabled.get(f, False)]

    def insertFunctions(self, row: int, functions: typing.Iterable[SpectralAlgorithm]):
        n = len(functions)
        row = min(max(0, row), len(self))
        i1 = row + n - 1
        self.beginInsertRows(QModelIndex(), row, i1)

        for i, f in enumerate(functions):
            f.sigChanged.connect(self.sigChanged)
            self.mFunctions.insert(row + i, f)
            self.mIsEnabled[f] = True
        self.endInsertRows()

    def addFunctions(self, functions):
        if isinstance(functions, SpectralAlgorithm):
            functions = [functions]
        for f in functions:
            assert isinstance(f, SpectralAlgorithm)
        self.insertFunctions(len(self), functions)

    def removeFunctions(self, functions):
        if isinstance(functions, SpectralAlgorithm):
            functions = [functions]
        for f in functions:
            assert isinstance(f, SpectralAlgorithm)
        for f in functions:
            if f in self.mFunctions:
                i = self.mFunctions.index(f)
                self.beginRemoveRows(QModelIndex(), i, i)
                self.mFunctions.remove(f)
                self.endRemoveRows()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mFunctions)

    def supportedDragActions(self) -> Qt.DropActions:
        return Qt.MoveAction

    def supportedDropActions(self) -> Qt.DropActions:
        return Qt.CopyAction | Qt.MoveAction

    def mimeTypes(self) -> typing.List[str]:
        return [MIMEFORMAT_SPECTRAL_MATH_FUNCTION]

    def mimeData(self, indexes: typing.Iterable[QModelIndex]) -> QMimeData:

        functions = []
        for idx in indexes:
            if idx.isValid():
                f = idx.data(Qt.UserRole)
                if isinstance(f, SpectralAlgorithm):
                    functions.append(f)

        return function2mimedata(functions)

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:

        if not self.canDropMimeData(data, action, row, column, parent):
            return False
        if action == Qt.IgnoreAction:
            return False

        functions = mimedata2functions(data)

        if len(functions) > 0:
            self.insertFunctions(row, functions)
            return True
        return False

    def removeRows(self, row: int, count: int, parent: QModelIndex = None) -> bool:
        if parent is None:
            parent = QModelIndex()

        functions = [self.mFunctions[row + i] for i in range(count)]
        if len(functions) > 0:
            self.removeFunctions(functions)
            return True
        else:
            return False

    def flags(self, index:QModelIndex):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | \
                Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        return flags

    def columnCount(self, parent=None, *args, **kwargs):
        return 1

    def setData(self, index:QModelIndex, value, role=None):

        if not index.isValid():
            return False
        f: SpectralAlgorithm = self.mFunctions[index.row()]

        changed = False
        if role == Qt.CheckStateRole and index.column() == 0:
            self.mIsEnabled[f] = value == Qt.Checked
            changed = True
        if role == Qt.EditRole and index.column() == 0:
            name = str(value)
            if len(name) > 0:
                f.setName(name)
                changed = True
        if changed:
            self.dataChanged.emit(index, index)
        return changed

    def data(self, index:QModelIndex, role=None):
        if not index.isValid():
            return None

        f: SpectralAlgorithm = self.mFunctions[index.row()]

        if role == Qt.DisplayRole:
            return f.name()

        if role == Qt.EditRole:
            return f.name()

        if role == Qt.DecorationRole:
            return f.icon()

        if role == Qt.FontRole and self.mIsEnabled.get(f, False) == False:
            font = QFont()
            font.setStrikeOut(True)
            return font

        if role == Qt.ToolTipRole:
            if f.mError:
                return str(f.mError)
            else:
                return None
        if role == Qt.TextColorRole:
            if f.mError:
                return QColor('red')
            else:
                return None

        if role == Qt.CheckStateRole:
            if self.mIsEnabled.get(f, False) == True:
                return Qt.Checked
            else:
                return Qt.Unchecked

        if role == Qt.UserRole:
            return f

        return None


class SpectralMathFunctionTableView(QTableView):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)


class SpectralMathWidget(QgsCollapsibleGroupBox):
    sigSpectralMathChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralmathwidget.ui'), self)

        self.mFunctionModel = SpectralMathFunctionModel()
        # self.mFunctionModel.addFunction(GenericSpectralMathFunction())
        self.mFunctionModel.sigChanged.connect(self.validate)
        self.mTableView: SpectralMathFunctionTableView
        self.mTableView.setModel(self.mFunctionModel)
        self.mTableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        #self.mLastExpression = None
        #self.mDefaultExpressionToolTip = self.tbExpression.toolTip()
        #self.tbExpression.textChanged.connect(self.validate)
        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: SpectralAlgorithm = None

        m = QMenu()
        m.setToolTipsVisible(True)
        a = m.addAction('Add X Unit Conversion')
        a.triggered.connect(lambda *args: self.functionModel().addFunctions([XUnitConversion()]))

        a = m.addAction('Add Python Expression')
        a.triggered.connect(lambda *args : self.functionModel().addFunctions([GenericSpectralAlgorithm()]))

        self.actionAddFunction.setMenu(m)
        self.actionRemoveFunction.triggered.connect(self.onRemoveFunctions)

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)


    def functionModel(self) -> SpectralMathFunctionModel:
        return self.mFunctionModel

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

    def tableView(self) -> SpectralMathFunctionTableView:
        return self.mTableView

    def setTextProfile(self, f: QgsFeature):
        self.mTestProfile = f
        self.validate()

    def spectralMathStack(self) -> typing.List[SpectralAlgorithm]:
        stack = []
        if self.is_valid():
            stack.append(self.mTestFunction)
        return stack

    def validate(self) -> bool:
        test = SpectralMathResult(x=[1, 2], y=[1, 2], x_unit='nm', y_unit='')

        b = self.mFunctionModel.validate(test)

        return b
        expression: str = self.expression()
        self.mTestFunction.setExpression(expression)

        changed = expression != self.mLastExpression
        self.mLastExpression = expression
        result = self.mTestFunction.apply(test, self.mTestProfile)
        is_valid = SpectralAlgorithm.is_valid_result(result)
        if is_valid:
            self.tbExpression.setToolTip(self.mDefaultExpressionToolTip)
            self.tbExpression.setStyleSheet('')
        else:
            self.tbExpression.setToolTip(str(self.mTestFunction.mError))
            self.tbExpression.setStyleSheet('color:red')

        if changed:
            self.sigSpectralMathChanged.emit()

        return is_valid

    def is_valid(self) -> bool:
        return self.validate()

    def expression(self) -> str:
        return self.tbExpression.toPlainText()



class QPSAlgorithmProvider(QgsProcessingProvider):

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
        return QIcon(self.svgIconPath())

    def svgIconPath(self):
        return r':/qps/ui/icons/profile.svg'

    def loadAlgorithms(self):
        self.algs = [

        ]

        for a in self.algs:
            self.addAlgorithm(a)

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True

    def tr(self, string, context=''):
        if context == '':
            context = 'GdalAlgorithmProvider'
        return QCoreApplication.translate(context, string)
