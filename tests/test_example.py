import pathlib
import unittest

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLabel
from qps.testing import TestCase, start_app

# image resource location
qgis_images_resources = pathlib.Path(__file__).parents[1] / 'qgisresources' / 'images_rc.py'

start_app()


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
        super().setUpClass(resources=resources)

    @unittest.skipIf(not qgis_images_resources.is_file(),
                     'Resource file does not exist: {}'.format(qgis_images_resources))
    def test_show_raster_icon(self):
        """
        This example show the QGIS Icon in a 200x200 px label.
        """
        icon = QIcon(':/images/icons/qgis_icon.svg')
        self.assertIsInstance(icon, QIcon)

        label = QLabel()
        label.setPixmap(icon.pixmap(QSize(200, 200)))

        # In case the environmental variable 'CI' is not set,
        # .showGui([list-of-widgets]) function will show and calls QApplication.exec_()
        # to keep the widget open
        self.showGui(label)


if __name__ == '__main__':
    unittest.main(buffer=False)
