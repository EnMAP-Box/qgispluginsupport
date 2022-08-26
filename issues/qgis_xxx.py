from osgeo import ogr, osr

from qgis._core import QgsVectorLayer

drv: ogr.Driver = ogr.GetDriverByName('GPKG')

pathDst = '/vsimem/test.gpkg'
dsDst = drv.CreateDataSource(pathDst)
assert isinstance(dsDst, ogr.DataSource)

srs = osr.SpatialReference()
srs.SetFromUserInput('EPSG:4326')
lyrDst: ogr.Layer = dsDst.CreateLayer('testlayer', srs=srs, geom_type=ogr.wkbPolygon)
assert isinstance(lyrDst, ogr.Layer)
dsDst.FlushCache()
del lyrDst
del dsDst

lyrQgis = QgsVectorLayer(pathDst, 'MyLayer', 'ogr')
assert lyrQgis.isValid()
