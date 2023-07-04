from qgis.PyQt.QtWidgets import QWidgetAction, QComboBox, QWidget, QFrame, QGridLayout, QLabel
from qgis.PyQt.QtCore import NULL, pyqtSignal, Qt
from qps.unitmodel import UnitModel, BAND_NUMBER, BAND_INDEX, UnitLookup


class SpectralProfilePlotXAxisUnitModel(UnitModel):
    """
    A unit model for the SpectralProfilePlot's X Axis
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.addUnit(BAND_NUMBER, description=BAND_NUMBER, tooltip=f'{BAND_NUMBER} (1st band = 1)')
        self.addUnit(BAND_INDEX, description=BAND_INDEX, tooltip=f'{BAND_INDEX} (1st band = 0)')

        # add Wavelength

        for u in ['Nanometer',
                  'Micrometer',
                  'Millimeter',
                  'Meter']:
            baseUnit = UnitLookup.baseUnit(u)
            assert isinstance(baseUnit, str), u
            self.addUnit(baseUnit, description=f'Wavelength [{baseUnit}]', tooltip=f'Wavelength in {u} [{baseUnit}]')

        # add Time Units
        self.addUnit('DateTime', description='Date Time', tooltip='Date Time in ISO 8601 format')
        self.addUnit('DecimalYear', description='Decimal Year', tooltip='Decimal year')
        self.addUnit('DOY', description='Day of Year', tooltip='Day of Year (DOY)')

        # add Distance Units
        for u in ['Meter', 'Kilometer']:
            baseUnit = UnitLookup.baseUnit(u)
            self.addUnit(baseUnit, description=f'Distance [{baseUnit}', tooltip=f'Distance in {u} [{baseUnit}]')

    def findUnit(self, unit):
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
            self.mUnitModel = SpectralProfilePlotXAxisUnitModel()
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
