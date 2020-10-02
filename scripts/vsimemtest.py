from osgeo import gdal
from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

# create an 2x2x1 in-memory raster
driver = gdal.GetDriverByName('GTiff')
assert isinstance(driver, gdal.Driver)
path = '/vsimem/inmemorytestraster.tif'

dataSet = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
assert isinstance(dataSet, gdal.Dataset)
c = QgsCoordinateReferenceSystem('EPSG:32632')
dataSet.SetProjection(c.toWkt())
dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
dataSet.FlushCache()
dataSet = None

ds2 = gdal.Open(path)
assert isinstance(ds2, gdal.Dataset)

layer = QgsRasterLayer(path)
assert isinstance(layer, QgsRasterLayer)
assert layer.isValid()