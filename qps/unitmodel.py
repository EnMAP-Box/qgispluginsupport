import calendar
import copy
import datetime
import re
import warnings
from math import log10
from typing import Iterator, List, Union, Optional

import numpy as np

from qgis.PyQt.QtCore import NULL, QAbstractListModel, QDate, QDateTime, QModelIndex, Qt
from qgis.PyQt.QtGui import QIcon

BAND_INDEX = 'Band Index'
BAND_NUMBER = 'Band Number'
UNKNOWN_UNIT = 'unknown'

# Exponents of base 10 to 1 meter [m]
METRIC_EXPONENTS = {
    'nm': -9, 'μm': -6, 'mm': -3, 'cm': -2, 'dm': -1, 'm': 0, 'hm': 2, 'km': 3
}


class UnitWrapper(object):

    def __init__(self,
                 unit: str,
                 description: str = None,
                 tooltip: str = None,
                 icon: QIcon = QIcon()
                 ):
        # if possible, ensure that a known base-unit is used
        # bunit = UnitLookup.baseUnit(unit)
        # if isinstance(bunit, str):
        #    unit = bunit
        self.unit: str = unit
        self.description: str = description if isinstance(description, str) else unit
        self.tooltip: str = tooltip if isinstance(tooltip, str) else self.description
        self.icon: QIcon = icon

    def __repr__(self):
        return super().__repr__() + f' {self.unit}:{self.description}'

    def __hash__(self):
        return hash((self.unit, self.description))


class UnitModel(QAbstractListModel):
    _instance = None

    @classmethod
    def instance(cls) -> 'UnitModel':
        """Returns a singleton of this class. Can be used to
           show the same units in different SpectralProfilePlot instances
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mUnits: List[UnitWrapper] = []
        self.mRedundantUnits: bool = False

        self.mEmpty = UnitWrapper(None, 'None')

    def setAllowEmptyUnit(self,
                          allowEmpty: bool,
                          text: str = '',
                          tooltip: str = 'None',
                          icon: QIcon = QIcon()):

        self.mEmpty.description = text
        self.mEmpty.tooltip = tooltip
        self.mEmpty.icon = icon

        self.beginResetModel()
        if allowEmpty:
            if self.mEmpty not in self.mUnits:
                self.beginInsertRows(QModelIndex(), 0, 0)
                self.mUnits.insert(0, self.mEmpty)
                self.endInsertRows()
        else:
            if self.mEmpty in self.mUnits:
                r = self.mUnits.index(self.mEmpty)
                self.beginRemoveRows(QModelIndex(), r, r)
                self.mUnits.pop(r)
                self.endRemoveRows()

    def __contains__(self, item) -> bool:
        return item in self.mUnits or any([u.unit == item for u in self.mUnits])

    def __iter__(self) -> Iterator[UnitWrapper]:
        return iter(self.mUnits)

    def __getitem__(self, slice):
        return self.mUnits[slice]

    def rowCount(self, parent=None, *args, **kwargs) -> int:
        return len(self.mUnits)

    def findUnitWrapper(self, value: Union[str, UnitWrapper]) -> UnitWrapper:
        """
        Returns a matching unit wrapper. Tries to convert unit description strings,
        e.g., searching for 'Nanometers' return the UnitWrapper mit unit 'nm'
        """
        if isinstance(value, UnitWrapper) and value in self.mUnits:
            return value

        elif value is None and self.mEmpty in self.mUnits:
            return self.mEmpty

        elif isinstance(value, str):
            base_unit = UnitLookup.baseUnit(value)
            if isinstance(base_unit, str):
                for w in self.mUnits:
                    if w.unit == base_unit:
                        return w
            else:
                v_low = value.lower()
                for w in self.mUnits:
                    for v in [w.unit, w.description]:
                        if isinstance(v, str) and v.lower() == v_low:
                            return w
        return None

    def findUnit(self, value: Union[str, UnitWrapper]) -> Optional[str]:
        """
        Returns a matching unit string, e.g. `nm` for `Nanometers`
        :param value:
        :return:
        """
        w = self.findUnitWrapper(value)
        if isinstance(w, UnitWrapper):
            return w.unit

        return None

    def removeUnit(self, unit: Union[str, UnitWrapper]):
        """
        Removes a unit from this model
        :param unit: str
        """

        while w := self.findUnitWrapper(unit):
            r = self.mUnits.index(w)
            self.beginRemoveRows(QModelIndex(), r, r)
            self.mUnits.pop(r)
            self.endRemoveRows()

    def addUnit(self,
                unit: Union[str, UnitWrapper],
                description: str = None,
                tooltip: str = None,
                icon: str = None) -> bool:
        """
        Adds a unit to the unit model
        :param unit:
        :type unit:
        :param description:

        :type description:
        :param tooltip:
        :type tooltip:
        :return:
        :rtype:
        """

        if not isinstance(unit, UnitWrapper):
            if isinstance(unit, str):
                base_unit = UnitLookup.baseUnit(unit)
                if isinstance(base_unit, str):
                    unit = base_unit

            unit = UnitWrapper(unit,
                               description=description,
                               tooltip=tooltip, icon=icon)

        for u in self:
            if u.unit == unit.unit and u.description == unit.description:
                # unit + unit description already exists
                return False

        r = len(self.mUnits)
        self.beginInsertRows(QModelIndex(), r, r)
        self.mUnits.insert(r, unit)
        self.endInsertRows()
        return True

    def unitIndex(self, unit: Union[str, UnitWrapper]) -> QModelIndex:
        """
        Returns the QModelIndex of a unit.
        :param unit:
        :type unit:
        :return:
        :rtype:
        """
        w = self.findUnitWrapper(unit)
        if isinstance(w, UnitWrapper):
            return self.index(self.mUnits.index(w), 0)
        return QModelIndex()

    def unitData(self, unit: Union[str, UnitWrapper], role=Qt.DisplayRole):
        """
        Convenience function to access unit metadata
        :param unit:
        :type unit:
        :param role:
        :type role:
        :return:
        :rtype:
        """
        return self.data(self.unitIndex(unit), role=role)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        w = self.mUnits[index.row()]

        if role == Qt.DisplayRole:
            return w.description
        if role == Qt.ToolTipRole:
            return w.tooltip
        if role == Qt.DecorationRole:
            return w.icon
        if role == Qt.UserRole:
            return w.unit
        if role == Qt.UserRole + 1:
            return w


class UnitConverterFunctionModel(object):
    _instance = None

    @staticmethod
    def instance() -> 'UnitConverterFunctionModel':
        """
        Returns a singleton instance of the UnitConverterFunctionModel,
        which can be used to share updates
        -------

        """
        if UnitConverterFunctionModel._instance is None:
            UnitConverterFunctionModel._instance = UnitConverterFunctionModel()
        return UnitConverterFunctionModel._instance

    def __init__(self):

        # look-up table with functions to convert from unit1 to unit2, with unit1 != unit2 and
        # unit1 != None and unit2 != None
        self.mLUT = dict()

        self.func_return_band_index = lambda v, *args: np.arange(len(v))
        self.func_return_band_number = lambda v, *args: np.arange(len(v)) + 1
        self.func_return_none = lambda v, *args: None
        self.func_return_same = lambda v, *args: v
        self.func_return_decimalyear = lambda v, *args: UnitLookup.convertDateUnit(v, 'DecimalYear')

        # length units
        for u1, e1 in UnitLookup.LENGTH_UNITS.items():
            for u2, e2 in UnitLookup.LENGTH_UNITS.items():
                key = (u1, u2)
                if key not in self.mLUT.keys():
                    if u1 != u2:
                        self.mLUT[key] = lambda v, *args, k1=u1, k2=u2: UnitLookup.convertLengthUnit(v, k1, k2)

        # time units
        # convert between DecimalYear and DateTime stamp
        self.mLUT[('DecimalYear', 'DateTime')] = lambda v, *args: datetime64(v)
        self.mLUT[('DateTime', 'DecimalYear')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DecimalYear')

        # convert to DOY (reversed operation is not possible)
        self.mLUT[('DecimalYear', 'DOY')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DOY')
        self.mLUT[('DateTime', 'DOY')] = lambda v, *args: UnitLookup.convertDateUnit(v, 'DOY')

    def __iter__(self):
        return iter(self.mLUT.items())

    def sourceUnits(self) -> List[str]:
        return sorted(set([k[0] for k in self.mLUT.keys()]))

    def destinationUnits(self) -> List[str]:
        return sorted(set([k[1] for k in self.mLUT.keys()]))

    def addConvertFunc(self, unitSrc: str, unitDst: str, func):
        """
        Adds a function to convert values from unitStr to unitDst
        The function must have a
        signature func(values: Union[number(s), numpy-array, list], *args) -> Union[np.ndarray or single value]
        list/array inputs must return list/array outputs of the same shape
        single number input must return a single number output
        """
        # test func with dummy variables
        assert not isinstance(func(1), (list, np.ndarray))
        assert len(func([1, 2])) == 2
        assert len(func(np.asarray([1, 2]))) == 2

        k = (unitSrc, unitDst)

        assert k not in self.mLUT, k
        self.mLUT[k] = func

    def convertFunction(self, unitSrc: Optional[str], unitDst: Optional[str]):
        if unitDst == BAND_INDEX:
            return self.func_return_band_index
        elif unitDst in UNKNOWN_UNIT:
            return self.func_return_same
        elif unitDst in [BAND_NUMBER, None, '']:
            return self.func_return_band_number

        if unitSrc is None or unitDst is None:
            return self.func_return_none

        _unitSrc = UnitLookup.baseUnit(unitSrc)
        _unitDst = UnitLookup.baseUnit(unitDst)
        for key in [
            (unitSrc, unitDst),  # units exist
            (unitSrc, _unitDst),  # destination unit's base-unit is known
            (_unitSrc, unitDst),  # source unit's base-unit is known
            (_unitSrc, _unitDst)  # base-unit's derivable for both
        ]:
            if key in self.mLUT:
                return self.mLUT[key]

            k1, k2 = key
            if isinstance(k1, str) and isinstance(k2, str) and k1 == k2:
                return self.func_return_same

        return self.func_return_none


class XUnitModel(UnitModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setAllowEmptyUnit(False)
        self.addUnit(BAND_NUMBER, description=BAND_NUMBER)
        self.addUnit(BAND_INDEX, description=BAND_INDEX)
        for u in ['Nanometers',
                  'Micrometers',
                  'Millimeters']:
            baseUnit = UnitLookup.baseUnit(u)
            assert isinstance(baseUnit, str), u
            self.addUnit(baseUnit,
                         description=f'Wavelength [{baseUnit}]',
                         tooltip=f'Wavelength in {u} [{baseUnit}]')

        self.addUnit('DateTime', description='Date Time')
        self.addUnit('DecimalYear', description='Decimal Year')
        self.addUnit('DOY', description='Day of Year')

        for u in ['Meters', 'Kilometers', 'Yards', 'Miles']:
            baseUnit = UnitLookup.baseUnit(u)
            assert isinstance(baseUnit, str), u
            self.addUnit(baseUnit,
                         description=f'Distance [{baseUnit}]',
                         tooltip=f'Distance in {u} [{baseUnit}]')

        self.mUnknownUnit = UnitWrapper(UNKNOWN_UNIT, 'Unknown Unit', tooltip='Unknown units / raw values')
        self.addUnit(self.mUnknownUnit)

    def findUnit(self, unit) -> str:
        if unit in [None, NULL]:
            if self.mEmpty not in self.mUnits:
                unit = BAND_NUMBER
        return super(XUnitModel, self).findUnit(unit)


def square_with_sign(v):
    if v >= 0:
        return v ** 2
    else:
        return -(v ** 2)


def log10_with_sign(v):
    if v >= 0:
        return log10(v)
    else:
        return -(log10(abs(v)))


class UnitLookup(object):
    DATE_UNITS = ['DateTime', 'DOY', 'DecimalYear', 'DecimalYear[366]', 'DecimalYear[365]', 'Y', 'M', 'W', 'D']
    TIME_UNITS = ['h', 'min', 's', 'ms', 'us', 'ns', 'ps', 'fs', 'as']

    IMPERIAL_LENGTH_UNITS = {
        # values in log10(m) (m = si meters)
        'in': 0.0254, 'ft': 0.3048, 'yd': 0.9144, 'mi': 1609.344, 'nmi': 1852
    }

    IMPERIAL_AREA_UNITS = {
        # values in sqm (si square meters)
        'acre': 4046.8564224, 'sqmi': 2589988.110336
    }

    # Length units with exponents related to 1 SI meter [m]
    LENGTH_UNITS = METRIC_EXPONENTS.copy()
    LENGTH_UNITS.update({k: log10(v) for k, v in IMPERIAL_LENGTH_UNITS.items()})

    # Area units with exponents related to 1 SI square meter [m²]
    # AREA_UNITS = {f'{k}²': square_with_sign(v) for k, v in LENGTH_UNITS.items()}
    # AREA_UNITS.update({f'{k}': log10_with_sign(v) for k, v in IMPERIAL_AREA_UNITS.items()})
    AREA_UNITS = {f'{k}²': 2 * v for k, v in LENGTH_UNITS.items()}
    AREA_UNITS['ha'] = 4  # because 10^4 m = 1 ha
    AREA_UNITS.update({f'{k}': 2 * v for k, v in IMPERIAL_AREA_UNITS.items()})

    # a dictionary to lookup other names of length or area units
    # e.g. UNIT_LOOKUP['meters'] = 'm'
    # will be filled dynamically
    UNIT_LOOKUP = {BAND_INDEX: BAND_INDEX,
                   BAND_NUMBER: BAND_NUMBER,
                   None: None}

    @staticmethod
    def metric_units() -> List[str]:
        warnings.warn(DeprecationWarning('Use area_units() or length_units()'), stacklevel=2)
        return list(METRIC_EXPONENTS.keys())

    @staticmethod
    def length_units() -> List[str]:
        return list(UnitLookup.LENGTH_UNITS.keys())

    @staticmethod
    def area_units() -> List[str]:
        return list(UnitLookup.AREA_UNITS.keys())

    @staticmethod
    def date_units() -> List[str]:
        return list(UnitLookup.DATE_UNITS)

    @staticmethod
    def time_units() -> List[str]:
        return list(UnitLookup.TIME_UNITS)

    @staticmethod
    def baseUnit(unit: str) -> str:
        """
        Tries to return the basic physical unit
        e.g. "m" for string of "Meters"

        :param unit:
        :type unit:
        :return:
        :rtype:
        """
        if not isinstance(unit, str):
            return None

        unit = unit.strip()

        if unit in UnitLookup.UNIT_LOOKUP.keys():
            return UnitLookup.UNIT_LOOKUP[unit]

        # so far this unit is unknown. Try to find the base unit
        # store unit string in Lookup table for fast conversion into its base unit
        # e.g. to convert string like "MiKrOMetErS" to "μm"
        base_unit = None

        if unit in UnitLookup.length_units() + \
                UnitLookup.area_units() + \
                UnitLookup.date_units() + \
                UnitLookup.time_units():
            return unit

        # Area units?
        RX1 = re.compile(r'((sq[. ]|square )(?P<core>.*[^.2²])\.?)$', re.I)
        RX2 = re.compile(r'(?P<core>.*)[2²]$', re.I)
        for rx in [RX1, RX2]:
            match = rx.match(unit)
            if match:
                length_unit = UnitLookup.baseUnit(match.group('core'))
                if isinstance(length_unit, str):
                    area_unit = length_unit + '²'
                    if area_unit in UnitLookup.AREA_UNITS.keys():
                        return area_unit

        # imperial area units
        if re.search(r'^acres?$', unit, re.I):
            base_unit = 'acre'
        elif re.search(r'^square miles?$', unit, re.I):
            base_unit = 'sqmi'

        # Volumetric units?

        elif re.search(r'^(Nanomet(er|re)s?)$', unit, re.I):
            base_unit = 'nm'
        elif re.search(r'^(Micromet(er|re)s?|um|μm)$', unit, re.I):
            base_unit = 'μm'
        elif re.search(r'^(Millimet(er|re)s?)$', unit, re.I):
            base_unit = 'mm'
        elif re.search(r'^(Centimet(er|re)s?)$', unit, re.I):
            base_unit = 'cm'
        elif re.search(r'^(Decimet(er|re)s?)$', unit, re.I):
            base_unit = 'dm'
        elif re.search(r'^(Met(er|re)s?)$', unit, re.I):
            base_unit = 'm'
        elif re.search(r'^(Hectomet(er|re)s?)$', unit, re.I):
            base_unit = 'hm'
        elif re.search(r'^(Kilomet(er|re)s?)$', unit, re.I):
            base_unit = 'km'
        # date units
        elif re.search(r'(Date([_\- ]?Time)?([_\- ]?Group)?|DTG)$', unit, re.I):
            base_unit = 'DateTime'
        elif re.search(r'^(doy|Day[-_ ]?Of[-_ ]?Year?)$', unit, re.I):
            base_unit = 'DOY'
        elif re.search(r'decimal[_\- ]?years?$', unit, re.I):
            base_unit = 'DecimalYear'
        elif re.search(r'decimal[_\- ]?years?\[356\]$', unit, re.I):
            base_unit = 'DecimalYear[365]'
        elif re.search(r'decimal[_\- ]?years?\[366\]$', unit, re.I):
            base_unit = 'DecimalYear[366]'
        elif re.search(r'^Years?$', unit, re.I):
            base_unit = 'Y'
        elif re.search(r'^Months?$', unit, re.I):
            base_unit = 'M'
        elif re.search(r'^Weeks?$', unit, re.I):
            base_unit = 'W'
        elif re.search(r'^Days?$', unit, re.I):
            base_unit = 'D'
        elif re.search(r'^Hours?$', unit, re.I):
            base_unit = 'h'
        elif re.search(r'^Minutes?$', unit, re.I):
            base_unit = 'min'
        elif re.search(r'^Seconds?$', unit, re.I):
            base_unit = 's'
        elif re.search(r'^MilliSeconds?$', unit, re.I):
            base_unit = 'ms'
        elif re.search(r'^MicroSeconds?$', unit, re.I):
            base_unit = 'us'
        elif re.search(r'^NanoSeconds?$', unit, re.I):
            base_unit = 'ns'
        elif re.search(r'^Picoseconds?$', unit, re.I):
            base_unit = 'ps'
        elif re.search(r'^Femtoseconds?$', unit, re.I):
            base_unit = 'fs'
        elif re.search(r'^Attoseconds?$', unit, re.I):
            base_unit = 'as'

        # imperial length units
        elif re.search(r'^inch(es)?$', unit, re.I):
            base_unit = 'in'
        elif re.search(r'^foot$', unit, re.I):
            base_unit = 'ft'
        elif re.search(r'^yards?$', unit, re.I):
            base_unit = 'yd'
        elif re.search(r'^miles?$', unit, re.I):
            base_unit = 'mi'
        elif re.search(r'^nautical[_ ]miles?$', unit, re.I):
            base_unit = 'nmi'

        if base_unit:
            # store the base_unit, unit pair into a global lookup table
            UnitLookup.UNIT_LOOKUP[unit] = base_unit
        return base_unit

    @staticmethod
    def isMetricUnit(unit: str) -> bool:
        baseUnit = UnitLookup.baseUnit(unit)
        return baseUnit in METRIC_EXPONENTS.keys()

    @staticmethod
    def isTemporalUnit(unit: str) -> bool:
        baseUnit = UnitLookup.baseUnit(unit)
        return baseUnit in UnitLookup.time_units() + UnitLookup.date_units()

    @staticmethod
    def convertUnit(value: Union[float, np.ndarray], u1: str, u2: str) -> float:

        u1 = UnitLookup.baseUnit(u1)
        u2 = UnitLookup.baseUnit(u2)

        if isinstance(u1, str) and isinstance(u2, str):

            if u1 in UnitLookup.LENGTH_UNITS and u2 in UnitLookup.LENGTH_UNITS:
                return UnitLookup.convertLengthUnit(value, u1, u2)
            elif u1 in UnitLookup.AREA_UNITS and u2 in UnitLookup.AREA_UNITS:
                return UnitLookup.convertAreaUnit(value, u1, u2)
            elif u1 in UnitLookup.TIME_UNITS and u2 in UnitLookup.TIME_UNITS:
                return UnitLookup.convertTimeUnit(value, u1, u2)
            else:
                return None

    @staticmethod
    def convertMetricUnit(*args, **kwds) -> float:
        warnings.warn(DeprecationWarning('Use convertLengthUnit'), stacklevel=2)
        return UnitLookup.convertLengthUnit(*args, **kwds)

    @staticmethod
    def convertLengthUnit(
            value: Union[float, np.ndarray],
            u1: str,
            u2: str) -> Union[None, float, List[float], np.ndarray]:
        """
        Converts a length value `value` from unit `u1` into unit `u2`
        :param value: float | int | might work with numpy arrays as well
        :param u1: str, identifier of unit 1
        :param u2: str, identifier of unit 2
        :return: float | numpy.array, converted values
                 or None in case conversion is not possible
        """
        assert isinstance(u1, str), 'Source length unit (str)'
        assert isinstance(u2, str), 'Destination length unit (str)'
        u1 = UnitLookup.baseUnit(u1)
        u2 = UnitLookup.baseUnit(u2)

        # get exponents to convert from unit to meters [m]
        e1 = UnitLookup.LENGTH_UNITS.get(u1)
        e2 = UnitLookup.LENGTH_UNITS.get(u2)

        if all([arg is not None for arg in [value, e1, e2]]):
            if e1 == e2:
                return copy.copy(value)
            elif isinstance(value, list):
                return [v * 10 ** (e1 - e2) for v in value]
            else:
                return value * 10 ** (e1 - e2)
        else:
            return None

    @staticmethod
    def convertAreaUnit(value: Union[float, np.ndarray], u1: str, u2: str) -> float:
        """
        Converts an area value `value` from unit `u1` into unit `u2`
        :param value: float | int | might work with numpy arrays as well
        :param u1: str, identifier of unit 1
        :param u2: str, identifier of unit 2
        :return: float | numpy.array, converted values
                 or None in case conversion is not possible
        """
        assert isinstance(u1, str), 'Source area unit (str)'
        assert isinstance(u2, str), 'Destination area unit (str)'

        # get the base unit, e.g. 'm2' instead 'square meters'
        u1 = UnitLookup.baseUnit(u1)
        u2 = UnitLookup.baseUnit(u2)

        # get exponents to convert from unit to square meters [m²]
        e1 = UnitLookup.AREA_UNITS.get(u1)
        e2 = UnitLookup.AREA_UNITS.get(u2)

        if all([arg is not None for arg in [value, e1, e2]]):
            if e1 == e2:
                return copy.copy(value)
            elif isinstance(value, list):
                return [v * 10 ** (e1 - e2) for v in value]
            else:
                return value * 10 ** (e1 - e2)
        else:
            return None

    @staticmethod
    def convertDateUnit(value: np.datetime64, unit: str):
        """
        Converts a
        :param value: numpy.datetime64 | datetime.date | datetime.datetime | float | int
                      int values are interpreted as year
                      float values are interpreted as decimal year
        :param unit: output unit
                    (integer) Y - Year, M - Month, W - Week, D - Day, DOY - Day-of-Year
                    (float) DecimalYear (based on True number of days per year)
                    (float) DecimalYear[365] (based on 365 days per year, i.e. wrong for leap years)
                    (float) DecimalYear[366] (based on 366 days per year, i.e. wrong for none-leap years)

        :return: float (if unit is decimal year), int else
        """
        unit = UnitLookup.baseUnit(unit)
        if not UnitLookup.isTemporalUnit(unit):
            return None
        # see https://numpy.org/doc/stable/reference/arrays.datetime.html#arrays-dtypes-dateunits
        # for valid date units
        if isinstance(value, (np.ndarray, list)):
            func = np.vectorize(UnitLookup.convertDateUnit)
            return func(value, unit)

        value = datetime64(value)
        if unit == 'Y':
            return value.astype(object).year
        elif unit == 'M':
            return value.astype(object).month
        elif unit == 'D':
            return value.astype(object).day
        elif unit == 'W':
            return value.astype(object).week
        elif unit == 'DOY':
            return ((value - value.astype('datetime64[Y]')).astype('timedelta64[D]') + 1).astype(int)

        elif unit.startswith('DecimalYear'):
            year = value.astype(object).year
            year64 = value.astype('datetime64[Y]')

            # second of year
            soy = (value - year64).astype('timedelta64[s]').astype(np.float64)

            # seconds per year
            if unit == 'DecimalYear[366]':
                spy = 366 * 86400
            elif unit == 'DecimalYear[365]':
                spy = 365 * 86400
            else:
                spy = 366 if calendar.isleap(year) else 365
                spy *= 86400
            spy2 = np.datetime64('{:04}-01-01T00:00:00'.format(year + 1)) - np.datetime64(
                '{:04}-01-01T00:00:00'.format(year))
            spy2 = int(spy2.astype(int))
            if spy != spy2:
                s = ""
            return float(year + soy / spy)
        else:
            raise NotImplementedError()


def datetime64(value, dpy: int = None) -> np.datetime64:
    """
    Converts an input value into a numpy.datetime64 value.
    :param value: the value to be converted into a numpy.datetime64 value
    :param dpy: days per year. If `value` is a float, it is considered to be a decimal year value.
                    By default it is assumed that the year fraction is calculated on 366 year in leap years and 365
                    in none-leap year. However, dpy can be used to use any other number of days per year to convert
                    the fraction back into days.
    :return: numpy.datetime64
    """
    if isinstance(value, np.datetime64):
        return value
    elif isinstance(value, QDate):
        return np.datetime64(value.toPyDate())
    elif isinstance(value, QDateTime):
        return np.datetime64(value.toPyDateTime())
    elif isinstance(value, (str, datetime.date, datetime.datetime)):
        return np.datetime64(value)
    elif isinstance(value, int):
        # expect a year
        return np.datetime64('{:04}-01-01'.format(value))
    elif isinstance(value, float):
        # expect a decimal year
        year = int(value)
        fraction = value - year

        if dpy is None:
            dpy = 366 if calendar.isleap(year) else 365
        else:
            assert dpy in [365, 366]
        # seconds of year
        soy = np.round(fraction * dpy * 86400).astype(int)
        return np.datetime64('{:04}-01-01'.format(year)) + np.timedelta64(soy, 's')

    if isinstance(value, np.ndarray):
        func = np.vectorize(datetime64)
        return func(value)
    elif isinstance(value, list):
        return datetime64(np.asarray(value), dpy=dpy)
    else:
        raise NotImplementedError('Unsupported input value: {}'.format(value))


def day_of_year(date: np.datetime64) -> int:
    """
    Returns a date's Day-of-Year (DOY) (considering leap-years)
    :param date: numpy.datetime64
    :return: numpy.ndarray[int]
    """
    if not isinstance(date, np.datetime64):
        date = np.datetime64(date)

    dt = date - date.astype('datetime64[Y]') + 1
    return dt.astype(int)


def days_per_year(year):
    """
    Returns the days per year
    :param year:
    :return:
    """
    # is it a leap year?
    if isinstance(year, float):
        year = int(year)
    elif isinstance(year, np.number):
        year = int(year)
    elif isinstance(year, np.datetime64):
        year = year.astype(object).year
    elif isinstance(year, datetime.date):
        year = year.year
    elif isinstance(year, datetime.datetime):
        year = year.year
    elif isinstance(year, np.ndarray):
        func = np.vectorize(days_per_year)
        return func(year)

    return 366 if calendar.isleap(year) else 365

    """
    1. If the year is evenly divisible by 4, go to step 2. Otherwise, False.
    2. If the year is evenly divisible by 100, go to step 3. Otherwise, False
    3. If the year is evenly divisible by 400, True Otherwise, False

    """
    """
    Every year that is exactly divisible by four is a leap year, except for years that are exactly divisible by 100,
    but these centurial years are leap years, if they are exactly divisible by 400.
    """
    # is_leap = (year % 4 == 0 and not year % 100 == 0) or (year % 100 == 0 and year % 400 == 0)
    # return np.where(is_leap, 366, 365)
