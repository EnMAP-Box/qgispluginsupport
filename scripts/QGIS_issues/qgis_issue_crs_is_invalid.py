from qgis.testing import start_app
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, Qgis

print(f'QGIS Version: {Qgis.version()}  ({Qgis.versionInt()})')

# if a QgsCoordinateReferenceSystem instance is created before start_app(), the assert in the last line will fail
if True:
    QgsCoordinateReferenceSystem('EPSG:4326')

start_app()

crs1 = QgsCoordinateReferenceSystem('EPSG:4326')
assert crs1.isValid()
crs2 = QgsCoordinateReferenceSystem.fromWkt(crs1.toWkt())
assert crs2.isValid()
