import unittest


class TestQGISEnums(unittest.TestCase):

    def test_enums(self):

        import qps.qgisenums

        VARS = vars(qps.qgisenums)

        for k, v in VARS.items():
            if k.startswith('QGIS_'):
                self.assertTrue(v is not None, msg=f'{k} is undefined!')
