import os, pathlib, unittest
from qps.testing import TestCase, StartOptions, start_app

from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import QSize, QFile, QDir
from qgis.core import QgsApplication

qgis_images_resources = pathlib.Path(__file__).parents[1] / 'qgisresources' / 'images_rc.py'

class Example1(unittest.TestCase):

    @unittest.skipIf(not qgis_images_resources.is_file(), 'Resource file does not exist: {}'.format(qgis_images_resources))
    def test_startQgsApplication(self):
        """
        This example shows how to initialize a QgsApplication on TestCase start up
        """
        resource_path = ':/images/icons/qgis_icon.svg'
        self.assertFalse(QFile(resource_path).exists())

        # StartOptions:
        # Minimized = just the QgsApplication
        # EditorWidgets = initializes EditorWidgets to manipulate vector attributes
        # ProcessingFramework = initializes teh QGIS Processing Framework
        # PythonRunner = initializes a PythonRunner, which is required to run expressions on vector layer fields
        # PrintProviders = prints the QGIS data providers
        # All = EditorWidgets | ProcessingFramework | PythonRunner | PrintProviders

        app = start_app(options=StartOptions.Minimized, resources=[qgis_images_resources])
        self.assertIsInstance(app, QgsApplication)
        self.assertTrue(QFile(resource_path).exists())


class ExampleCase(TestCase):
    """
    This example shows how to run unit tests using a QgsApplication
    that has the QGIS resource icons loaded
    """
    @classmethod
    def setUpClass(cls) -> None:
        # this initializes the QgsApplication with resources from images loaded
        resources = []
        if qgis_images_resources.is_file():
            resources.append(qgis_images_resources)
        super().setUpClass(cleanup=True, options=StartOptions.Minimized, resources=resources)

    @unittest.skipIf(not qgis_images_resources.is_file(),
                     'Resource file does not exist: {}'.format(qgis_images_resources))
    def test_show_raster_icon(self):
        """
        This example show the QGIS Icon in a 200x200 px label.
        """
        icon = QIcon(':/images/icons/qgis_icon.svg')
        self.assertIsInstance(icon, QIcon)

        label = QLabel()
        label.setPixmap(icon.pixmap(QSize(200,200)))

        # In case the the environmental variable 'CI' is not set,
        # .showGui([list-of-widgets]) function will show and calls QApplication.exec_()
        # to keep the widget open
        self.showGui(label)



if __name__ == '__main__':

    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
