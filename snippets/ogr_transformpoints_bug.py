from osgeo import ogr, osr, gdal
import numpy as np

print(gdal.VersionInfo(''))

srsSrc = osr.SpatialReference()
srsDst = osr.SpatialReference()
srsSrc.ImportFromEPSG(32633)
srsDst.ImportFromEPSG(4326)

# IMPORTANT FOR GDAL 3.0+ ###################################
# use this to define and return coordinates in x,y,(z) order!
srsSrc.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
srsDst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
#############################################################

trans = osr.CoordinateTransformation(srsSrc, srsDst)

#                  UTM x value   y value
pointsUTM = np.asarray([
                     [384792.37, 5817942.35],
                     [384822.37, 5817942.35],
                     [384852.37, 5817942.35],
                     [384882.37, 5817942.35],
                    ])

# transform from UTM to Lat/Lon
pointsLatLon = trans.TransformPoints(pointsUTM)

print('UTM x y -> Lon/Lat x y z')
for i in range(pointsUTM.shape[0]):
    x1, y1 = pointsUTM[i,:]
    x2, y2, z2 = pointsLatLon[i]
    print('{} {} -> {} {} {}'.format(x1, y1, x2, y2, z2))

# QGIS Example
print('Transformation with QGIS')
from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsPointXY
crs1 = QgsCoordinateReferenceSystem(32633)
crs2 = QgsCoordinateReferenceSystem(4326)
trans = QgsCoordinateTransform()
trans.setSourceCrs(crs1)
trans.setDestinationCrs(crs2)
print('UTM x y -> Lon/Lat x y z')
for i in range(pointsUTM.shape[0]):
    p1 = QgsPointXY(*pointsUTM[i,:])
    p2 = trans.transform(p1)
    print('{} {} -> {} {}'.format(p1.x(), p1.y(), p2.x(), p2.y()))
