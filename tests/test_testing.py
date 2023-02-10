# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest

import qps.testing
from qgis.core import QgsProject, QgsApplication, QgsProcessingRegistry, QgsLayerTree, QgsLayerTreeModel
from qgis.gui import QgsLayerTreeView, QgisInterface, QgsGui


@unittest.skipIf(isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication must be None')
class TestCasesClassTesting(unittest.TestCase):

    def setUp(self) -> None:
        app = QgsApplication.instance()
        import qgis.testing
        if hasattr(qgis.testing, 'QGISAPP'):
            qgis.testing.stop_app()

    @unittest.skipIf(isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication must be None')
    def test_init(self):
        self.assertTrue(qps.testing is not None)

        qgis_app = qps.testing.start_app(options=qps.testing.StartOptions.All)
        print(f'qgis_app: {qgis_app}', flush=True)
        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)

        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0,
                        msg='Standard QgsEditorWidgetWrapper not initialized')

        # test iface
        import qgis.utils
        iface = qgis.utils.iface

        self.assertIsInstance(iface, QgisInterface)
        self.assertIsInstance(iface, qps.testing.QgisMockup)

        lyr1 = qps.testing.TestObjects.createVectorLayer()
        lyr2 = qps.testing.TestObjects.createVectorLayer()

        self.assertIsInstance(iface.layerTreeView(), QgsLayerTreeView)
        self.assertIsInstance(iface.layerTreeView().layerTreeModel(), QgsLayerTreeModel)
        root = iface.layerTreeView().layerTreeModel().rootGroup()
        self.assertIsInstance(root, QgsLayerTree)
        self.assertEqual(len(root.findLayers()), 0)

        # QgsProject.instance().layersAdded.connect(lambda : print('ADDED'))
        # QgsProject.instance().legendLayersAdded.connect(lambda: print('ADDED LEGEND'))

        QgsProject.instance().addMapLayer(lyr1, False)
        QgsProject.instance().addMapLayer(lyr2, True)

        QgsApplication.processEvents()

        self.assertTrue(lyr1.id() not in root.findLayerIds())
        self.assertTrue(lyr2.id() in root.findLayerIds())

        app = QgsApplication.instance()
        ENV = app.systemEnvVars()
        for k in sorted(ENV.keys()):
            print('{}={}'.format(k, ENV[k]))

        # qps.testing.stop_app()


if __name__ == "__main__":
    unittest.main(buffer=False)
