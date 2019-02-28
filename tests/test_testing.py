# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, pickle
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *

from qps.testing import initQgisApplication

class testClassTesting(unittest.TestCase):


    def test_init(self):

        import qps.testing
        self.assertTrue(qps.testing != None)

        qgis_app = qps.testing.initQgisApplication()


        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)

        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0, msg='Standard QgsEditorWidgetWrapper not initialized')






if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



