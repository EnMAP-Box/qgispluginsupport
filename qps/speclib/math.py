import collections
import typing
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QPlainTextEdit, QWidget, QTableView
from qgis.core import QgsFeature
from qgis.gui import QgsCollapsibleGroupBox, QgsCodeEditorPython
import numpy as np
from .core import SpectralLibrary, SpectralProfile, speclibUiPath
from ..unitmodel import UnitConverterFunctionModel
from ..utils import loadUi

SpectralMathResult = collections.namedtuple('SpectralMathResult', ['x', 'y', 'x_unit', 'y_unit'])

class AbstractSpectralMathFunction(QObject):

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
    def applyFunctionStack(functionStack: typing.Iterable[typing.Optional['AbstractSpectralMathFunction']],
                           *args) -> SpectralMathResult:

        if isinstance(functionStack, AbstractSpectralMathFunction):
            functionStack = [functionStack]
        else:
            assert isinstance(functionStack, typing.Iterable)

        spectralMathResult, feature = AbstractSpectralMathFunction._unpack(*args)

        for f in functionStack:
            assert isinstance(f, AbstractSpectralMathFunction)

            spectralMathResult = f.apply(spectralMathResult, feature)
            if not AbstractSpectralMathFunction.is_valid_result(spectralMathResult):
                return None

        return spectralMathResult

    @staticmethod
    def _unpack(*args) -> typing.Tuple[SpectralMathResult, QgsFeature]:
        assert len(args) >= 1
        f = None
        if isinstance(args[0], SpectralProfile):
            sp: SpectralProfile = args[0]
            x = sp.xValues()
            y = sp.yValues()
            x_unit = sp.xUnit()
            y_unit = sp.yUnit()
            f = sp
        elif len(args) == 4:
            x, y, x_unit, y_unit = args
        elif len(args) >= 5:
            x, y, x_unit, y_unit, f = args[:5]

        x = np.asarray(x)
        y = np.asarray(y)

        return SpectralMathResult(x=x, y=y, x_unit=x_unit, y_unit=y_unit), f

    def __init__(self, name: str = None):

        if name is None:
            name = self.__class__.__name__
        self.mError = None
        self.mName: str = name
        self.mHelp: str = ''
        self.mIcon: QIcon = None

    def name(self) -> str:
        return self.mName

    def help(self) -> str:
        return self.mHelp

    def icon(self) -> QIcon:
        return self.mIcon

    def createWidget(self) -> QWidget:
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


class XUnitConversion(AbstractSpectralMathFunction):

    def __init__(self, x_unit:str):

        self.mTargetUnit = x_unit
        self.mUnitConverter = UnitConverterFunctionModel()

    def unitConverter(self) -> UnitConverterFunctionModel:
        return self.mUnitConverter

    def setTargetUnit(self, unit:str):
        self.mTargetUnit = unit

    def apply(self, result:SpectralMathResult, feature: QgsFeature) -> SpectralMathResult:

        f = self.mUnitConverter.convertFunction(result.x_unit, self.mTargetUnit)
        if callable(f):
            x = f(result.x)
            return SpectralMathResult(x=x, y=result.y, x_unit=self.mTargetUnit, y_unit=result.y_unit)
        else:
            return None

class GenericSpectralMathFunction(AbstractSpectralMathFunction):

    def __init__(self):
        super().__init__()
        self.mExpression = None

    def setExpression(self, expression:str):
        self.mExpression = expression

    def apply(self, spectralMathResult:SpectralMathResult, feature:QgsFeature) -> SpectralMathResult:

        values = spectralMathResult._asdict()
        self.mError = None
        try:
            exec(self.mExpression, values)
            return SpectralMathResult(x=values['x'], y=values['y'], x_unit=values['x_unit'], y_unit=values['y_unit'] )
        except Exception as ex:
            self.mError = str(ex)
        return None

    def createWidget(self) -> QgsCodeEditorPython:

        editor = QgsCodeEditorPython(title=self.name())

        return editor


class SpectralMathFunctionModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):
        super(SpectralMathFunctionModel, self).__init__(*args, **kwds)

        self.mFunctions: typing.List[AbstractSpectralMathFunction] = []
        self.mIsEnabled: typing.Dict[str, bool] = dict()

    def __len__(self):
        return len(self.mFunctions)

    def functionStack(self) -> typing.List[AbstractSpectralMathFunction]:
        return [f for f in self.mFunctions if self.mIsEnabled.get(f.name(), False)]

    def insertFunction(self, index: int, f: AbstractSpectralMathFunction):
        assert isinstance(f, AbstractSpectralMathFunction)
        self.beginInsertRows()

        self.endInsertRows()

    def addFunction(self, f: AbstractSpectralMathFunction):
        self.insertFunction(len(self), f)

    def removeFunction(self, f: AbstractSpectralMathFunction):
        if f in self.mFunctions:
            i = self.mFunctions.index(f)

            self.beginRemoveRows()
            self.endRemoveRows()

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mFunctions)

    def flags(self, index:QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
        return flags

    def columnCount(self, parent=None, *args, **kwargs):
        return 1

    def setData(self, index:QModelIndex, value, role=None):

        if not index.isValid():
            return False
        f: AbstractSpectralMathFunction = self.mFunctions[index.row()]

        changed = False
        if role == Qt.CheckStateRole and index.column() == 0:
            self.mIsEnabled[f.name()] = value == Qt.Checked
            changed = True

        if changed:
            self.dataChanged.emit(index, index)
        return changed

    def data(self, index:QModelIndex, role=None):
        if not index.isValid():
            return None

        f: AbstractSpectralMathFunction = self.mFunctions[index.row()]

        if role == Qt.DisplayRole:
            return f.name()

        if role == Qt.DecorationRole:
            return f.icon()

        if role == Qt.CheckStateRole:
            if self.mIsEnabled.get(f.name()):
                return Qt.Checked
            else:
                return Qt.Unchecked

        if role == Qt.UserRole:
            return f

        return None


class SpectralMathFunctionTableView(QTableView):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

class SpectralMathWidget(QgsCollapsibleGroupBox):
    sigSpectralMathChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectralmathwidget.ui'), self)

        self.mFunctionModel = SpectralMathFunctionModel()
        self.mFunctionModel.insertFunction(GenericSpectralMathFunction())

        self.mTestFunction: GenericSpectralMathFunction = GenericSpectralMathFunction()
        self.mTableView: SpectralMathFunctionTableView
        self.mTableView.setModel(self.mFunctionModel)

        self.mLastExpression = None
        self.mDefaultExpressionToolTip = self.tbExpression.toolTip()
        self.tbExpression.textChanged.connect(self.validate)
        self.mTestProfile = QgsFeature()

    def tableView(self) -> SpectralMathFunctionTableView:
        return self.mTableView

    def setTextProfile(self, f: QgsFeature):
        self.mTestProfile = f
        self.validate()

    def spectralMathStack(self) -> typing.List[AbstractSpectralMathFunction]:
        stack = []
        if self.is_valid():
            stack.append(self.mTestFunction)
        return stack

    def validate(self) -> bool:
        test = SpectralMathResult(x=[1,2], y=[1,2], x_unit='nm', y_unit='')
        expression: str = self.expression()
        self.mTestFunction.setExpression(expression)

        changed = expression != self.mLastExpression
        self.mLastExpression = expression
        result = self.mTestFunction.apply(test, self.mTestProfile)
        is_valid = AbstractSpectralMathFunction.is_valid_result(result)
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