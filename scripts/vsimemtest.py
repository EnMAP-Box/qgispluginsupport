from osgeo import gdal

from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

# create an 2x2x1 in-memory raster
driver = gdal.GetDriverByName('GTiff')
if not (isinstance(driver, gdal.Driver)):
    raise AssertionError
path = '/vsimem/inmemorytestraster.tif'

dataSet = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
if not (isinstance(dataSet, gdal.Dataset)):
    raise AssertionError
c = QgsCoordinateReferenceSystem('EPSG:32632')
dataSet.SetProjection(c.toWkt())
dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
dataSet.FlushCache()
dataSet = None

ds2 = gdal.Open(path)
if not (isinstance(ds2, gdal.Dataset)):
    raise AssertionError

layer = QgsRasterLayer(path)
if not (isinstance(layer, QgsRasterLayer)):
    raise AssertionError
if not (layer.isValid()):
    raise AssertionError
