from osgeo import gdal
from qgis.core import QgsRasterLayer, QgsProject

import os


import pathlib
path = pathlib.Path(__file__).parent / 'landsat_4326.tif'
path = path.resolve()
print(path)

path = r'D:\Repositories\enmap-box\enmapboxtestdata\enmap_berlin.bsq'
layer = QgsRasterLayer(path)
layer.setName(os.path.basename(path))
QgsProject.instance().addMapLayer(layer)
print(f'Before: {layer.bandName(1)}')

ds: gdal.Dataset = gdal.Open(path)
ds.SetMetadataItem('MyKey', 'MyValue', 'MyDomain')
ds.FlushCache()
del ds


layer.reload()
print(f'After: {layer.bandName(1)}')
s = ""