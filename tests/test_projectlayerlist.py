import unittest

from qgis.PyQt.QtCore import QSortFilterProxyModel
from qgis.PyQt.QtWidgets import QTableView
from qgis.core import QgsProject
from qps.projectlayers import ProjectLayerTableModel, SelectProjectLayersDialog
from qps.testing import TestCase, TestObjects, start_app

start_app()


class TestProjectLayerListModel(TestCase):
    def test_listmodel(self):
        p = QgsProject()
        layers = [TestObjects.createVectorLayer(),
                  TestObjects.createRasterLayer(),
                  ]

        p.addMapLayers(layers)

        model = ProjectLayerTableModel()
        self.assertEqual(model.project(), QgsProject.instance())

        model.setProject(p)
        self.assertEqual(model.project(), p)
        self.assertEqual(model.rowCount(), len(p.mapLayers()))

        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(model)
        view = QTableView()
        view.setSortingEnabled(True)
        view.setModel(proxyModel)
        self.showGui(view)

    def test_dialog(self):
        p = QgsProject()
        p.setTitle('MyProject')
        layers = [TestObjects.createVectorLayer(name='SL1'),
                  TestObjects.createRasterLayer(name='RL1'),
                  TestObjects.createVectorLayer(name='SL2'),
                  ]

        d = SelectProjectLayersDialog()
        self.assertEqual(d.project(), QgsProject.instance())

        d = SelectProjectLayersDialog(project=p)
        self.assertEqual(d.project(), p)
        p.addMapLayers(layers)
        to_select = layers[0:2]
        d.setSelectedLayers(to_select)
        selected_layers = d.selectedLayers()
        self.assertEqual(len(selected_layers), len(to_select))
        for lyr in to_select:
            self.assertTrue(lyr in selected_layers)

        self.showGui(d)


if __name__ == '__main__':
    unittest.main()
