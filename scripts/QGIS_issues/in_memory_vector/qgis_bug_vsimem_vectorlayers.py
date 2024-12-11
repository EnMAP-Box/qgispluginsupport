import pathlib

from osgeo import ogr

from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsVectorLayer
from qps.testing import start_app

wkt = 'GEOGCRS["WGS 84",ENSEMBLE["World Geodetic System 1984 ensemble",MEMBER["World Geodetic System 1984 (Transit)"],MEMBER["World Geodetic System 1984 (G730)"],MEMBER["World Geodetic System 1984 (G873)"],MEMBER["World Geodetic System 1984 (G1150)"],MEMBER["World Geodetic System 1984 (G1674)"],MEMBER["World Geodetic System 1984 (G1762)"],MEMBER["World Geodetic System 1984 (G2139)"],ELLIPSOID["WGS 84",6378137,298.257223563,LENGTHUNIT["metre",1]],ENSEMBLEACCURACY[2.0]],PRIMEM["Greenwich",0,ANGLEUNIT["degree",0.0174532925199433]],CS[ellipsoidal,3],AXIS["geodetic latitude (Lat)",north,ORDER[1],ANGLEUNIT["degree",0.0174532925199433]],AXIS["geodetic longitude (Lon)",east,ORDER[2],ANGLEUNIT["degree",0.0174532925199433]],AXIS["ellipsoidal height (h)",up,ORDER[3],LENGTHUNIT["metre",1]],USAGE[SCOPE["Geodesy. Navigation and positioning using GPS satellite system."],AREA["World."],BBOX[-90,-180,90,180]],ID["EPSG",4979]]'
QgsCoordinateReferenceSystem(wkt)
# QgsCoordinateReferenceSystem('TEST WKT')
# QgsCoordinateReferenceSystem('EPSG:4326')# .isValid()
# QgsCoordinateReferenceSystem.fromWkt('')


ogr.UseExceptions()
start_app()

wkt = 'GEOGCRS["WGS 84",ENSEMBLE["World Geodetic System 1984 ensemble",MEMBER["World Geodetic System 1984 (Transit)"],MEMBER["World Geodetic System 1984 (G730)"],MEMBER["World Geodetic System 1984 (G873)"],MEMBER["World Geodetic System 1984 (G1150)"],MEMBER["World Geodetic System 1984 (G1674)"],MEMBER["World Geodetic System 1984 (G1762)"],MEMBER["World Geodetic System 1984 (G2139)"],ELLIPSOID["WGS 84",6378137,298.257223563,LENGTHUNIT["metre",1]],ENSEMBLEACCURACY[2.0]],PRIMEM["Greenwich",0,ANGLEUNIT["degree",0.0174532925199433]],CS[ellipsoidal,3],AXIS["geodetic latitude (Lat)",north,ORDER[1],ANGLEUNIT["degree",0.0174532925199433]],AXIS["geodetic longitude (Lon)",east,ORDER[2],ANGLEUNIT["degree",0.0174532925199433]],AXIS["ellipsoidal height (h)",up,ORDER[3],LENGTHUNIT["metre",1]],USAGE[SCOPE["Geodesy. Navigation and positioning using GPS satellite system."],AREA["World."],BBOX[-90,-180,90,180]],ID["EPSG",4979]]'
assert QgsCoordinateReferenceSystem(wkt).isValid()

path1 = pathlib.Path(__file__).parent / 'testvectordata.geojson'
path2 = r'/vsimem/myvector.gpkg'

assert path1.is_file()
ds1: ogr.DataSource = ogr.Open(path1.as_posix())
lyr1 = QgsVectorLayer(path1.as_posix())
assert lyr1.isValid()
assert lyr1.crs().isValid()
drv: ogr.Driver = ogr.GetDriverByName('GPKG')
ds2 = drv.CopyDataSource(ds1, path2)
assert isinstance(ds2, ogr.DataSource)
lyr2: ogr.Layer = ds2.GetLayer(0)
assert lyr2.GetSpatialRef().Validate() == ogr.OGRERR_NONE
del lyr2, ds2

lyr2 = QgsVectorLayer(path2)
assert lyr2.isValid()
assert lyr2.crs().isValid()

print('Done')
