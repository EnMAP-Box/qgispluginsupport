from qgis.PyQt.QtCore import NULL, pyqtSignal, Qt
from qgis.PyQt.QtWidgets import QWidgetAction, QComboBox, QWidget, QFrame, QGridLayout, QLabel
from ...unitmodel import UnitModel, BAND_NUMBER, BAND_INDEX, XUnitModel


class SpectralProfilePlotXAxisUnitModel(XUnitModel):
    """
    A unit model for the SpectralProfilePlot's X Axis
    """

    _instance = None

    @staticmethod
    def instance() -> 'SpectralProfilePlotXAxisUnitModel':
        """Returns a singleton of this class. Can be used to
           show the same units in different SpectralProfilePlot instances
        """
        if SpectralProfilePlotXAxisUnitModel._instance is None:
            SpectralProfilePlotXAxisUnitModel._instance = SpectralProfilePlotXAxisUnitModel()
        return SpectralProfilePlotXAxisUnitModel._instance

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def findUnit(self, unit) -> str:
        if unit in [None, NULL]:
            unit = BAND_NUMBER
        return super().findUnit(unit)


class SpectralProfilePlotXAxisUnitWidgetAction(QWidgetAction):
    sigUnitChanged = pyqtSignal(str)

    def __init__(self, parent, unit_model: UnitModel = None, **kwds):
        super().__init__(parent)
        self.mUnitModel: SpectralProfilePlotXAxisUnitModel
        if isinstance(unit_model, UnitModel):
            self.mUnitModel = unit_model
        else:
            self.mUnitModel = SpectralProfilePlotXAxisUnitModel.instance()
        self.mUnit: str = BAND_INDEX

    def unitModel(self) -> SpectralProfilePlotXAxisUnitModel:
        return self.mUnitModel

    def setUnit(self, unit: str):
        unit = self.mUnitModel.findUnit(unit)

        if isinstance(unit, str) and self.mUnit != unit:
            self.mUnit = unit
            self.sigUnitChanged.emit(unit)

    def unit(self) -> str:
        return self.mUnit

    def unitData(self, unit: str, role=Qt.DisplayRole) -> str:
        return self.mUnitModel.unitData(unit, role)

    def createUnitComboBox(self) -> QComboBox:
        unitComboBox = QComboBox()
        unitComboBox.setModel(self.mUnitModel)
        unitComboBox.setCurrentIndex(self.mUnitModel.unitIndex(self.unit()).row())
        unitComboBox.currentIndexChanged.connect(
            lambda: self.setUnit(unitComboBox.currentData(Qt.UserRole))
        )

        self.sigUnitChanged.connect(
            lambda unit, cb=unitComboBox: cb.setCurrentIndex(self.mUnitModel.unitIndex(unit).row()))
        return unitComboBox

    def createWidget(self, parent: QWidget) -> QWidget:
        # define the widget to set X-Axis options
        frame = QFrame(parent)
        gl = QGridLayout()
        frame.setLayout(gl)

        mCBXAxisUnit = self.createUnitComboBox()

        gl.addWidget(QLabel('Unit'), 2, 0)
        gl.addWidget(mCBXAxisUnit, 2, 1)
        gl.setMargin(0)
        gl.setSpacing(6)
        frame.setMinimumSize(gl.sizeHint())
        return frame
