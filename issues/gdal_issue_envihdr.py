import pathlib
import re
import unittest

from osgeo import gdal
from qgis.core import QgsRasterLayer


class EnviTest(unittest.TestCase):

    def readHeader(self, path_hdr: str):
        fp = gdal.VSIFOpenL(path_hdr, "rb")
        hdr: str = gdal.VSIFReadL(1, gdal.VSIStatL(path_hdr).size, fp).decode("utf-8")
        gdal.VSIFCloseL(fp)
        return hdr

    @unittest.skipIf(gdal.VersionInfo() < '306', 'Requires GDAL 3.6+')
    def test_EnviDataOffsetAndScale(self):
        path = '/vsimem/test.img'

        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        ds: gdal.Dataset = drv.Create(path, 1, 1, 2, eType=gdal.GDT_Byte)
        path_hdr = [f for f in ds.GetFileList() if f.endswith('.hdr')][0]
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            band.Fill(b + 1)
        ds.FlushCache()
        del band, ds

        # see https://www.l3harrisgeospatial.com/docs/enviheaderfiles.html for definition of
        # ENVI header format
        hdr = self.readHeader(path_hdr)
        hdr += 'data gain values = {500, 600}\n'
        hdr += 'data offset values = {7, 8}\n'
        fp = gdal.VSIFOpenL(path_hdr, "wb")
        gdal.VSIFWriteL(hdr, 1, len(hdr), fp)
        gdal.VSIFCloseL(fp)

        ds: gdal.Dataset = gdal.Open(path)
        data = ds.ReadAsArray()
        self.assertEqual(data[0, 0, 0], 1)
        self.assertEqual(data[1, 0, 0], 2)

        band1: gdal.Band = ds.GetRasterBand(1)
        # expected behaviour
        self.assertEqual(band1.GetScale(), 500)
        self.assertEqual(band1.GetOffset(), 7)

        band2: gdal.Band = ds.GetRasterBand(2)
        # expected behaviour
        self.assertEqual(band2.GetScale(), 600)
        self.assertEqual(band2.GetOffset(), 8)

        # update scale & offsets
        band2.SetScale(500)
        band2.SetOffset(7)
        ds.FlushCache()
        del band1, band2, ds

        hdr = self.readHeader(path_hdr)
        # expected behaviour
        self.assertTrue(re.search(r'data gain values = {500, 600}', hdr))
        self.assertTrue(re.search(r'data offset values = {7, 8}', hdr))

    def test_EnviBandName(self):

        path = '/vsimem/test.img'
        path = (pathlib.Path(__file__).parent / 'test.img').as_posix()

        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        ds: gdal.Dataset = drv.Create(path, 1, 2, 2, eType=gdal.GDT_Byte)
        path_hdr = [f for f in ds.GetFileList() if f.endswith('.hdr')][0]
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            band.Fill(b + 1)
            band.GetStatistics(1, 1)
        ds.FlushCache()
        del band, ds

        lyr = QgsRasterLayer(path)
        lyr.reload()

        ds = gdal.Open(path, gdal.GA_Update)

        ds.GetRasterBand(2).SetDescription('Changed Name')
        ds.FlushCache()

        lyr.reload()
        hdr = self.readHeader(path_hdr)
        self.assertTrue('Changed Name' in hdr)

        s = ""

    def test_EnviComments(self):

        pass

    def test_EnviSpectralLibrary(self):

        pass
