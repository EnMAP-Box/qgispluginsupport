# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import unittest, pickle
from qgis import *
from qgis.core import *
from qgis.gui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *



class testClassTesting(unittest.TestCase):




    def test_init_core(self):

        if isinstance(QgsApplication.instance(), QgsApplication):
            QgsApplication.instance().quit()

        # self.assertTrue(QgsApplication.instance() is None)

        if False:
            import re
            if QOperatingSystemVersion.current().name() == 'macOS':
                # add location of Qt Libraries
                assert '.app' in qgis.__file__, 'Can not locate path of QGIS.app'
                PATH_QGIS_APP = re.search(r'.*\.app', qgis.__file__).group()

                libraryPath1 = os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns'])

                #libraryPath2 = os.path.join(PATH_QGIS_APP, *['Contents', 'PlugIns', 'qgis'])
                #QApplication.addLibraryPath(libraryPath2)

                QApplication.addLibraryPath(libraryPath1)

        from qgis.testing.mocked import get_iface

        iface = get_iface()
        self.assertIsInstance(QgsApplication.instance(), QgsApplication)
        self.assertIsInstance(iface, QgisInterface)
        QgsApplication.instance().quit()

        s = ""

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
    unittest.main()



