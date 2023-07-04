from qgis.PyQt.QtWidgets import QComboBox
from qps.testing import TestCaseBase, start_app
from qps.unitmodel import UnitModel, XUnitModel, UnitLookup

start_app()


class UnitModelTests(TestCaseBase):

    def test_unitmodel(self):

        model = UnitModel()
        model.setAllowRedundantUnits(True)
        model.addUnit('unit A', description='descr A')
        model.addUnit('unit A')
        self.assertEqual(model.rowCount(), 1)

        model = UnitModel()
        model.addUnit('unit A', description='descr A')
        model.addUnit('unit A')
        self.assertEqual(model.rowCount(), 1)
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

    def test_length_unit_conversion(self):

        # value, unit1, unit2, result

        TEST_VALUES = [
            (1, 'm', 'cm', 100),
            (1000, 'm', 'km', 1),
            (100, 'cm', 'm', 1),
            (1000, 'mm', 'm', 1),
        ]

        for (v1, u1, u2, v2) in TEST_VALUES:
            self.assertEqual(v2, UnitLookup.convertLengthUnit(v1, u1, u2),
                             msg=f'Failed to convert {v1} {u1} into {u2}')
            self.assertEqual(v1, UnitLookup.convertLengthUnit(v2, u2, u1),
                             msg=f'Failed to convert {v2} {u2} into {u1}')

        TEST_VALUES_IMPERIAL = [
            (42, 'inch', 'yard', 1.166667),
            (42, 'inch', 'm', 1.0668),
            (42, 'kilometer', 'miles', 26.09759),
        ]
        for (v1, u1, u2, v2) in TEST_VALUES_IMPERIAL:
            self.assertAlmostEqual(v2, UnitLookup.convertLengthUnit(v1, u1, u2), 4,
                                   msg=f'Failed to convert {v1} {u1} into {v2} {u2}')

            self.assertAlmostEqual(v1, UnitLookup.convertLengthUnit(v2, u2, u1), 4,
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
            (42, 'km²', 'sqmi', 16.216290659),
        ]
        places = 5
        for (v1, u1, u2, v2) in TEST_VALUES:
            self.assertIsInstance(UnitLookup.baseUnit(u1), str,
                                  msg=f'Unknown base unit for "{u1}"')
            self.assertIsInstance(UnitLookup.baseUnit(u2), str,
                                  msg=f'Unknown base unit for "{u2}"')
            self.assertAlmostEqual(v2, UnitLookup.convertAreaUnit(v1, u1, u2),
                                   places,
                                   msg=f'Failed to convert {v1} {u1} into {v2} {u2}')
            self.assertAlmostEqual(v1, UnitLookup.convertAreaUnit(v2, u2, u1),
                                   places,
                                   msg=f'Failed to convert {v2} {u2} into {v1} {u1}')

    def test_xunitmodel(self):
        model = XUnitModel()
        model.setAllowEmptyUnit(False)

        cb = QComboBox()
        cb.setModel(model)

        self.showGui(cb)
