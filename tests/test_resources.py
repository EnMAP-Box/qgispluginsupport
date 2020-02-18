import unittest, pathlib


path_rc = pathlib.Path(__file__).parents[1] / 'qgisresources' / 'images_rc.py'
class Tests(unittest.TestCase):


    @unittest.skipIf(not path_rc.is_file(), '{} does not exist'.format(path_rc))
    def test_rc(self):
        from qps.testing import start_app, scanResources
        from qgis.PyQt.QtWidgets import QWidget
        from qgis.PyQt.QtGui import QIcon

        app = start_app(resources=[path_rc])

        r = ':/images/themes/default/mActionZoomNext.svg'
        self.assertIsInstance(r, str)
        resources = list(scanResources())

        self.assertTrue(r in resources, '"{}" not loaded to resource system'.format(r))
        w = QWidget()
        w.setWindowIcon(QIcon(r))
        w.show()


if __name__ == '__main__':

    unittest.main()

