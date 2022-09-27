import re
import unittest

from osgeo import gdal


class EnviTest(unittest.TestCase):

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

        def readHeader():
            fp = gdal.VSIFOpenL(path_hdr, "rb")
            hdr: str = gdal.VSIFReadL(1, gdal.VSIStatL(path_hdr).size, fp).decode("utf-8")
            gdal.VSIFCloseL(fp)
            return hdr

        # see https://www.l3harrisgeospatial.com/docs/enviheaderfiles.html for definition of
        # ENVI header format
        hdr = readHeader()
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

        hdr = readHeader()
        # expected behaviour
        self.assertTrue(re.search('data gain values = {500, 500}', hdr))
        self.assertTrue(re.search('data offset values = {7, 7}', hdr))
