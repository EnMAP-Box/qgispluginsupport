
from osgeo import ogr
from qps.testing import start_app
start_app()
p = r'D:\Repositories\qgispluginsupport\test-outputs\speclib2vector\speclib_kml.kml'

lyrName = 'SpectralLibrary'
lyr = QgsVectorLayer(p + f'|layername={lyrName}')
print(lyr.fields().names())

ds = ogr.Open(p)
lyr = ds.GetLayerByName(lyrName)

ldef = lyr.GetLayerDefn()
fieldNames = [ldef.GetFieldDefn(i).GetName() for i in range(ldef.GetFieldCount())]
print(fieldNames)
drv = ds.GetDriver()
print(drv.GetName())
s = ""