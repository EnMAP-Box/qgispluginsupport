from osgeo import osr, ogr

ogr.UseExceptions()
projection = osr.SpatialReference()
err = projection.ImportFromEPSG(int(4326))
assert err == ogr.OGRERR_NONE
