import pathlib
import re

import numpy as np
from osgeo import gdal, gdal_array

DIR = pathlib.Path(__file__).parent

array = np.ones((3, 10, 5), dtype=int)
path = DIR / 'enviexample.bsq'

drv: gdal.Driver = gdal.GetDriverByName('ENVI')
ds: gdal.Dataset = drv.Create(path.as_posix(),
                              array.shape[2], array.shape[1], bands=array.shape[0],
                              eType=gdal_array.flip_code(array.dtype))

assert ds.RasterCount == array.shape[0]

wl = []
for b in range(ds.RasterCount):
    band: gdal.Band = ds.GetRasterBand(b + 1)
    band.SetDescription(f'name {b + 1}')
    band.WriteArray(array[b, :, :])
    wl.append(str(b + 1))

ds.SetMetadataItem('wavelength', '{' + ','.join(wl) + '}', 'ENVI')
ds.SetMetadataItem('wavelength units', 'nm')
ds.SetMetadataItem('something_else', 'foobar', 'ENVI')
ds.FlushCache()
del ds
pathHdr = path.parent / re.sub(r'\..*$', '.hdr', path.name)

with open(pathHdr, 'r', encoding='utf-8') as file:
    hdr = file.read()
print('### ENVI HEADER ####')
print(hdr)
print('### GDAL METADATE ENVI DOMAIN ####')

ds: gdal.Dataset = gdal.Open(path.as_posix())
for k, v in ds.GetMetadata_Dict('ENVI').items():
    print(f'{k}={v}')
for b in range(ds.RasterCount):
    band: gdal.Band = ds.GetRasterBand(b + 1)
    for k, v in band.GetMetadata_Dict('ENVI').items():
        print(f'Band {b + 1}::{k}={v}')
