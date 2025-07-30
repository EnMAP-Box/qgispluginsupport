from osgeo import gdal

from qps.gdal_utils import GDALConfigChanges
from qps.testing import TestCase


class GDALUtilsTests(TestCase):

    def test_gdal_config_changes(self):
        changes = {'GDAL_VRT_ENABLE_RAWRASTERBAND': 'YES',
                   'foobar': None}
        gdal.SetConfigOption('foobar', 'yes')
        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')

        with GDALConfigChanges(changes) as changer:
            assert gdal.GetConfigOption('GDAL_VRT_ENABLE_RAWRASTERBAND') == 'YES'
            assert gdal.GetConfigOption('foobar') is None

        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')
        assert gdal.GetConfigOption('GDAL_VRT_ENABLE_RAWRASTERBAND') is None
        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')
