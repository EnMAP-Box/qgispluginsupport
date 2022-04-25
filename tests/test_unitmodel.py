from qgis.PyQt.QtWidgets import QComboBox
from qps.testing import TestCase
from qps.unitmodel import UnitModel, XUnitModel


class UnitModelTests(TestCase):

    def test_unitmodel(self):
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

    def test_xunitmodel(self):
        model = XUnitModel()
        model.setAllowEmptyUnit(False)

        cb = QComboBox()
        cb.setModel(model)

        self.showGui(cb)
