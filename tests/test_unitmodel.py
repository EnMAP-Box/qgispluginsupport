import calendar
import datetime

import numpy as np
from qps.testing import TestCase, start_app
from qps.unitmodel import UnitConverterFunctionModel, UnitLookup, UnitModel, UnitWrapper, XUnitModel, datetime64, \
    days_per_year

from qgis.PyQt.QtCore import QDate, QDateTime, Qt
from qgis.PyQt.QtWidgets import QComboBox

start_app()


class UnitModelTests(TestCase):

    def test_baseunits(self):

        # describe expected output and input
        cases = [
            ('m', 'meters'),
            ('nm', 'nanometer'),
            ('μm', 'MiCroMetErS'),
            ('μm', 'um'),
            ('km²', 'km²'),
            ('km²', 'km2'),
            ('km²', 'square kilometer'),
            ('km²', 'square kilometers'),
            ('km²', 'kilometer²'),
            ('km²', 'kilometers²'),
            ('yd²', 'yards2'),
            ('yd²', 'square yard'),
            ('yd²', 'square yards'),
            ('in²', 'square inches'),
            ('in²', 'sq.in.'),
            ('ft²', 'sq.ft'),
            ('yd²', 'sq.yd'),
            ('mi²', 'sq.mi'),
            ('mi²', 'square mile'),
            ('mi²', 'square miles'),
        ]

        for (u1, u2) in cases:
            self.assertEqual(u1, UnitLookup.baseUnit(u2),
                             msg=f'Failed to normalize "{u2}" to "{u1}"')

    def test_unitmodel(self):

        model = UnitModel()
        # same unit string + same description?
        model.addUnit('cm', description='Wavelength [cm]')
        model.addUnit('cm', description='Wavelength [cm]')
        self.assertEqual(model.rowCount(), 1)

        # allow for units with different descriptions
        model.addUnit('cm', description='Distance [cm]')
        self.assertEqual(model.rowCount(), 2)

        model = UnitModel()
        model.addUnit('unit A', description='descr A')
        model.addUnit('unit B')
        self.assertEqual(model.rowCount(), 2)
        model.setAllowEmptyUnit(True, text='Empty', tooltip='No unit')
        self.assertEqual(model.rowCount(), 3)
        model.setAllowEmptyUnit(False)
        self.assertEqual(model.rowCount(), 2)

        self.assertEqual(model.findUnit('unit A'), 'unit A')
        self.assertEqual(model.findUnit('descr A'), 'unit A')
        self.assertEqual(model.findUnit('DESCR A'), 'unit A')

        model.removeUnit('unit A')
        self.assertEqual(model.rowCount(), 1)

        model.addUnit('unit B', description='Other description')
        self.assertEqual(model.rowCount(), 2)
        model.removeUnit('unit B')
        self.assertEqual(model.rowCount(), 0)

    def test_length_unit_conversion(self):

        # value, unit1, unit2, result

        TEST_VALUES = [
            (1, 'm', 'cm', 100),
            (1000, 'm', 'km', 1),
            (100, 'cm', 'm', 1),
            (1000, 'mm', 'm', 1),
            (100, 'um', 'μm', 100),
        ]

        for (v1, u1, u2, v2) in TEST_VALUES:
            self.assertEqual(v2, UnitLookup.convertUnit(v1, u1, u2),
                             msg=f'Failed to convert {v1} {u1} into {u2}')
            self.assertEqual(v1, UnitLookup.convertUnit(v2, u2, u1),
                             msg=f'Failed to convert {v2} {u2} into {u1}')

        TEST_VALUES_IMPERIAL = [
            (42, 'inch', 'yard', 1.166667),
            (42, 'inch', 'm', 1.0668),
            (42, 'kilometer', 'miles', 26.09759),
        ]
        for (v1, u1, u2, v2) in TEST_VALUES_IMPERIAL:
            self.assertAlmostEqual(v2, UnitLookup.convertUnit(v1, u1, u2), 4,
                                   msg=f'Failed to convert {v1} {u1} into {v2} {u2}')

            self.assertAlmostEqual(v1, UnitLookup.convertUnit(v2, u2, u1), 4,
                                   msg=f'Failed to convert {v2} {u2} into {v1} {u1}')

    def test_area_unit_conversion(self):

        # value, unit1, unit2, result

        TEST_VALUES = [
            (1, 'm²', 'cm²', 10000),
            (1, 'm²', 'dm²', 100),
            (10, 'm²', 'dm²', 1000),
            (100 * 100, 'm²', 'ha', 1),
            (1000, 'cm²', 'ha', 0.00001),
            (42, 'km²', 'ha', 4200),
            (42, 'km²', 'yard²', 50231581.945),
            (42, 'km²', 'sq.mi', 16.216290659),
        ]
        places = 3
        for (v1, u1, u2, v2) in TEST_VALUES:
            self.assertIsInstance(UnitLookup.baseUnit(u1), str,
                                  msg=f'Unknown base unit for "{u1}"')
            self.assertIsInstance(UnitLookup.baseUnit(u2), str,
                                  msg=f'Unknown base unit for "{u2}"')
            self.assertAlmostEqual(v2, UnitLookup.convertUnit(v1, u1, u2),
                                   places,
                                   msg=f'Failed to convert {v1} {u1} into {v2} {u2}')
            self.assertAlmostEqual(v1, UnitLookup.convertUnit(v2, u2, u1),
                                   places,
                                   msg=f'Failed to convert {v2} {u2} into {v1} {u1}')

    def test_xunitmodel(self):
        model = XUnitModel()
        model.setAllowEmptyUnit(False)

        uw = model[3]
        self.assertIsInstance(uw, UnitWrapper)
        cb = QComboBox()
        cb.setModel(model)

        self.showGui(cb)

        model = XUnitModel()
        w = model.findUnitWrapper('foobar')
        self.assertTrue(w is None)
        idx = model.unitIndex('')
        cb.setCurrentIndex(idx.row())

        u = cb.currentData(Qt.UserRole)

        s = ""
        wrappers = model[:]
        for i, w in enumerate(wrappers):
            w2 = model.findUnitWrapper(w.description)
            self.assertEqual(w, w2)

    def test_UnitConverterFunctionModel(self):

        m = UnitConverterFunctionModel()

        v = np.asarray([100, 200, 300])

        for dst in ['um', 'μm', u'μm']:
            f = m.convertFunction('nm', dst)
            r = f(v, 'X')
            self.assertListEqual(list(r), [0.1, 0.2, 0.3], msg='Failed to convert from nm to {}'.format(dst))

        r = m.convertFunction('nm', 'nm')(v, 'X')
        self.assertListEqual(list(r), [100, 200, 300])

    def test_convertMetricUnits(self):

        self.assertEqual(UnitLookup.convertLengthUnit(100, 'm', 'km'), 0.1)
        self.assertEqual(UnitLookup.convertLengthUnit(0.1, 'km', 'm'), 100)

        self.assertEqual(UnitLookup.convertLengthUnit(400, 'nm', 'μm'), 0.4)
        self.assertEqual(UnitLookup.convertLengthUnit(0.4, 'μm', 'nm'), 400)

        self.assertEqual(UnitLookup.convertUnit(400, 'nm', 'km'), 4e-10)

    def test_decimalYearConversions(self):
        baseDate = np.datetime64('2020-01-01')
        for seconds in range(0, 200000, 13):
            dateA = baseDate + np.timedelta64(seconds, 's')
            decimalDate = UnitLookup.convertDateUnit(dateA, 'DecimalYear')
            DOY = UnitLookup.convertDateUnit(decimalDate, 'DOY')
            self.assertTrue(DOY >= 1)

            is_leap_year = calendar.isleap(dateA.astype(object).year)
            if is_leap_year:
                self.assertTrue(DOY <= 366)
            else:
                self.assertTrue(DOY <= 365)

            self.assertIsInstance(decimalDate, float)
            dateB = datetime64(decimalDate)
            self.assertIsInstance(dateB, np.datetime64)
            self.assertEqual(dateA, dateB)

        for days in range(0, 5000):
            dateA = baseDate + np.timedelta64(days, 'D')
            decimalDate = UnitLookup.convertDateUnit(dateA, 'DecimalYear')
            self.assertIsInstance(decimalDate, float)
            dateB = datetime64(decimalDate)
            self.assertIsInstance(dateB, np.datetime64)
            self.assertEqual(dateA, dateB)

    def test_convertTimeUnits(self):

        refDate = np.datetime64('2020-01-01')
        self.assertEqual(datetime64(refDate), refDate)  # datetime64 to datetime64
        self.assertEqual(datetime64('2020-01-01'), refDate)  # string to datetime64
        self.assertEqual(datetime64(QDate(2020, 1, 1)), refDate)
        self.assertEqual(datetime64(QDateTime(2020, 1, 1, 0, 0)), refDate)
        self.assertEqual(datetime64(datetime.date(year=2020, month=1, day=1)), refDate)
        self.assertEqual(datetime64(datetime.datetime(year=2020, month=1, day=1)), refDate)
        self.assertEqual(datetime64(2020), refDate)  # decimal year to datetime64

        date_arrays = [np.asarray(['2020-01-01', '2019-01-01'], dtype=np.datetime64),
                       np.asarray([2020, 2019]),
                       np.asarray([2020.023, 2019.023]),
                       ]
        for array in date_arrays:
            dpy = days_per_year(array)
            self.assertIsInstance(dpy, np.ndarray)
            self.assertTrue(np.array_equal(dpy, np.asarray([366, 365])))

        leap_years = [2020,
                      2020.034,
                      np.datetime64('2020', 'Y'),
                      datetime.date(year=2020, month=1, day=1),
                      datetime.date(year=2020, month=12, day=31),
                      datetime.datetime(year=2020, month=1, day=1, hour=0, minute=0, second=0),
                      datetime.datetime(year=2020, month=12, day=31, hour=23, minute=59, second=59)
                      ]
        non_leap_years = [2019,
                          2019.034,
                          np.datetime64('2019', 'Y'),
                          datetime.date(year=2019, month=1, day=1),
                          datetime.date(year=2019, month=12, day=31),
                          datetime.datetime(year=2019, month=1, day=1, hour=0, minute=0, second=0),
                          datetime.datetime(year=2019, month=12, day=31, hour=23, minute=59, second=59)
                          ]

        for y in leap_years:
            dpy = days_per_year(y)
            if not dpy == 366:
                s = ""
            self.assertEqual(dpy, 366)

        for y in non_leap_years:
            dpy = days_per_year(y)
            self.assertEqual(dpy, 365)

        self.assertEqual(UnitLookup.convertDateUnit('2020-01-01', 'DOY'), 1)
        self.assertEqual(UnitLookup.convertDateUnit('2020-12-31', 'DOY'), 366)
        self.assertEqual(UnitLookup.convertDateUnit('2020-12-31', 'Y'), 2020)

        self.assertEqual(UnitLookup.convertDateUnit('2019-01-01', 'DOY'), 1)
        self.assertEqual(UnitLookup.convertDateUnit('2019-12-31', 'DOY'), 365)

        self.assertEqual(UnitLookup.convertDateUnit('2019-01-01', 'M'), 1)
        self.assertEqual(UnitLookup.convertDateUnit('2019-01-01', 'D'), 1)
        self.assertEqual(UnitLookup.convertDateUnit('2019-07-08', 'M'), 7)
        self.assertEqual(UnitLookup.convertDateUnit('2019-07-08', 'D'), 8)
        self.assertEqual(UnitLookup.convertDateUnit('2019-07-08', 'Y'), 2019)

        for dtg in ['2019-01-01T00:00:00',
                    '2019-12-31T23:59:59',
                    '2020-01-01T00:00:00',
                    '2020-12-31T23:59:59']:

            dj0a = UnitLookup.convertDateUnit(dtg, 'DecimalYear')
            dj0b = UnitLookup.convertDateUnit(dtg, 'DecimalYear[365]')
            dj0c = UnitLookup.convertDateUnit(dtg, 'DecimalYear[366]')

            year = np.datetime64(dtg).astype(object).year
            doy = int((np.datetime64(dtg) - np.datetime64('{:04}-01-01'.format(year)))
                      .astype('timedelta64[D]')
                      .astype(int)) + 1

            self.assertEqual(year, int(dj0a))

            if not calendar.isleap(year):
                self.assertEqual(dj0a, dj0b)
                self.assertEqual(int((dj0a - int(dj0a)) * 365 + 1), doy)

            else:
                self.assertEqual(dj0a, dj0c)
                self.assertEqual(int((dj0a - int(dj0a)) * 366 + 1), doy)
