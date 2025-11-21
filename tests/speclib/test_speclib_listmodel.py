import unittest

from qgis.PyQt.QtTest import QAbstractItemModelTester
from qgis.PyQt.QtWidgets import QListView
from qgis.core import QgsProject
from qps.speclib.gui.spectrallibrarylistmodel import SpectralLibraryListModel
from qps.testing import TestCase, TestObjects, start_app

start_app()


class MyTestCase(TestCase):
    def test_speclib_list_model(self):
        model = SpectralLibraryListModel()
        model.setShowAll(False)
        self.assertEqual(model.project(), QgsProject.instance())

        sl1 = TestObjects.createSpectralLibrary(name='SL1')
        sl2 = TestObjects.createSpectralLibrary(name='SL2')
        rl1 = TestObjects.createRasterLayer(name='RL1')
        vl1 = TestObjects.createVectorLayer(name='VL1')

        p = QgsProject()

        model.setProject(p)
        self.assertEqual(p, model.project())
        self.assertEqual(0, model.rowCount())

        p.addMapLayer(sl1)
        self.assertEqual(1, model.rowCount())

        p.addMapLayer(sl2)
        self.assertEqual(2, model.rowCount())
        p.addMapLayers([rl1, vl1])
        self.assertEqual(2, model.rowCount())

        p.takeMapLayer(sl1)
        self.assertEqual(1, model.rowCount())

        self.assertEqual([sl2], model.spectralLibraries())

        p.addMapLayer(sl1)

        tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
        view = QListView()
        view.setModel(model)

        self.showGui(view)


if __name__ == '__main__':
    unittest.main()
