from qgis.testing import TestCase
from qps.testing import start_app as start_app2


class PlotStyleTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = start_app2(cleanup=True)

    def test_case1(self):
        self.assertTrue(True)
