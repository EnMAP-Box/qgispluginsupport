# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, pickle
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *



class testClassTesting(unittest.TestCase):


    def test_init(self):

        from qps.testing import initQgisApplication

        app = initQgisApplication()
        self.assertIsInstance(app, QgsApplication)

        import qps
        qps.registerEditorWidgets()

        import qps.speclib.spectrallibraries
        self.assertIsInstance(qps.speclib.spectrallibraries.SPECTRAL_PROFILE_EDITOR_WIDGET_FACTORY, QgsEditorWidgetFactory)

        import qps.plotstyling.plotstyling
        self.assertIsInstance(qps.plotstyling.plotstyling.PLOTSTYLE_EDITOR_WIDGET_FACTORY,
                              QgsEditorWidgetFactory)

        import qps.classification.classificationscheme
        self.assertIsInstance(qps.classification.classificationscheme.CLASS_SCHEME_EDITOR_WIDGET_FACTORY,
                              QgsEditorWidgetFactory)




if __name__ == "__main__":
    SHOW_GUI = False
    unittest.main()



