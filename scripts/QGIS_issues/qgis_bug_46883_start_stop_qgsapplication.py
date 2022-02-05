# relates to https://github.com/qgis/QGIS/issues/46883

from qgis.core import QgsApplication, Qgis
from qgis.testing import start_app, stop_app
import unittest

print(Qgis.version(), Qgis.devVersion(), flush=True)


class TestQGISAPP(unittest.TestCase):

    def test_StartAndClose(self):
        print(f'About to start: {QgsApplication.instance()}', flush=True)
        start_app()
        print(f'About to stop: {QgsApplication.instance()}', flush=True)
        stop_app()
        print(f'Stopped: {QgsApplication.instance()}', flush=True)


if __name__ == '__main__':
    unittest.main()
