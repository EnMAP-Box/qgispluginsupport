import pathlib
import unittest

from osgeo import gdal


class EnviTest(unittest.TestCase):

    def test_EnviDataOffsetAndScale(self):
        path = '/vsimem/test.img'
        path = pathlib.Path(__file__).parent / 'test.img'

        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        ds: gdal.Dataset = drv.Create(path.as_posix(), 1, 1, 1, eType=gdal.GDT_Byte)
        path_hdr = [f for f in ds.GetFileList() if f.endswith('.hdr')][0]
        band: gdal.Band = ds.GetRasterBand(1)
        band.Fill(2)
        ds.FlushCache()
        del band, ds

        fp = gdal.VSIFOpenL(path_hdr, "rb")
        hdr: str = gdal.VSIFReadL(1, gdal.VSIStatL(path_hdr).size, fp).decode("utf-8")
        gdal.VSIFCloseL(fp)
        hdr += 'data gain values = {10000}\n'
        hdr += 'data offset values = {5}\n'
        fp = gdal.VSIFOpenL(path_hdr, "wb")
        gdal.VSIFWriteL(hdr, 1, len(hdr), fp);
        gdal.VSIFCloseL(fp)

        ds: gdal.Dataset = gdal.Open(path.as_posix())
        data = ds.ReadAsArray()
        print('ENVI Hdr:')
        with open(path_hdr, 'r') as f:
            print(f.read())

        print(f'GDAL Pixel Data: {data}')
        band: gdal.Band = ds.GetRasterBand(1)
        print(f'GDAL Band Offset: {band.GetOffset()}')
        print(f'GDAL Band Scale: {band.GetScale()}')
