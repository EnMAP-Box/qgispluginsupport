import unittest

from qgis.PyQt.QtWidgets import QApplication
from qgis.core import QgsApplication
from qgis.testing import start_app, stop_app


class StartStopTest(unittest.TestCase):

    def tearDown(self) -> None:
        print(f' {self.id()} finished')

    def test_start_stop_QApplication(self):
        print('Start & stop 1st QApplication')
        self.assertTrue(QApplication.instance() is None)
        app = QApplication([])
        self.assertEqual(QApplication.instance(), app)
        app.exit(0)
        del app
        self.assertTrue(QApplication.instance() is None)

        print('Start & stop 2nd QApplication')
        app = QApplication([])
        self.assertEqual(QApplication.instance(), app)
        app.exit(0)
        del app
        self.assertTrue(QApplication.instance() is None)

    def test_start_stop_QgsApplication(self):
        print('Start & stop 1st QgsApplication')
        self.assertTrue(QgsApplication.instance() is None)

        start_app(cleanup=False)
        self.assertIsInstance(QgsApplication.instance(), QgsApplication)
        stop_app()
        self.assertTrue(QgsApplication.instance() is None)

        print('Start & stop 2nd QgsApplication')
        start_app(cleanup=False)
        self.assertIsInstance(QgsApplication.instance(), QgsApplication)
        stop_app()
        self.assertTrue(QgsApplication.instance() is None)


if __name__ == '__main__':
    unittest.main(buffer=False)
