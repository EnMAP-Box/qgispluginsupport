from typing import Union

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtWidgets import QWidgetAction, QComboBox, QWidget, QFrame, QGridLayout, QLabel

from ...unitmodel import UnitModel, BAND_INDEX, XUnitModel, UnitWrapper


class SpectralProfilePlotXAxisUnitModel(XUnitModel):
    """
    A unit model for the SpectralProfilePlot's X Axis
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class SpectralProfilePlotXAxisUnitWidgetAction(QWidgetAction):
    sigUnitChanged = pyqtSignal(UnitWrapper)

    def __init__(self, parent, unit_model: UnitModel = None, **kwds):
        super().__init__(parent)
        self.mUnitModel: SpectralProfilePlotXAxisUnitModel
        if isinstance(unit_model, UnitModel):
            self.mUnitModel = unit_model
        else:
            self.mUnitModel = SpectralProfilePlotXAxisUnitModel.instance()
        self.mUnit: UnitWrapper = self.mUnitModel.findUnitWrapper(BAND_INDEX)

    def unitModel(self) -> SpectralProfilePlotXAxisUnitModel:
        return self.mUnitModel

    def setUnit(self, unit: Union[str, UnitWrapper]):
        unit = self.mUnitModel.findUnitWrapper(unit)

        if self.mUnit != unit:
            self.mUnit = unit
            self.sigUnitChanged.emit(unit)

    def unit(self) -> UnitWrapper:
        return self.mUnit.unit

    def unitData(self, unit: Union[str, UnitWrapper], role=Qt.ItemDataRole.DisplayRole) -> str:
        return self.mUnitModel.unitData(unit, role)

    def createUnitComboBox(self) -> QComboBox:
        unitComboBox = QComboBox()
        unitComboBox.setModel(self.mUnitModel)
        unitComboBox.setCurrentIndex(self.mUnitModel.unitIndex(self.unit()).row())
        unitComboBox.currentIndexChanged.connect(
            lambda: self.setUnit(unitComboBox.currentData(Qt.ItemDataRole.UserRole + 1))
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
