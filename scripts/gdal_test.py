from osgeo import osr, ogr

ogr.UseExceptions()
projection = osr.SpatialReference()
err = projection.ImportFromEPSG(int(4326))
if not (err == ogr.OGRERR_NONE):
    raise AssertionError
