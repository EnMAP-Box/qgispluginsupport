from osgeo import gdal

from qps.gdal_utils import GDALConfigChanges
from qps.testing import TestCase


class GDALUtilsTests(TestCase):

    def test_gdal_config_changes(self):
        changes = {'GDAL_VRT_ENABLE_RAWRASTERBAND': 'YES',
                   'foobar': None}
        gdal.SetConfigOption('foobar', 'yes')
        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')

        with GDALConfigChanges(changes) as _:
            self.assertEqual(gdal.GetConfigOption('GDAL_VRT_ENABLE_RAWRASTERBAND'), 'YES')
            self.assertIsNone(gdal.GetConfigOption('foobar'))

        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')
        self.assertIsNone(gdal.GetConfigOption('GDAL_VRT_ENABLE_RAWRASTERBAND'))
        self.assertEqual(gdal.GetConfigOption('foobar'), 'yes')
