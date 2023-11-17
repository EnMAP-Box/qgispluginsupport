from qgis.testing import start_app
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, Qgis

print(f'QGIS Version: {Qgis.version()}  ({Qgis.versionInt()})')

# if a QgsCoordinateReferenceSystem instance is created before start_app(), the assert in the last line will fail
if True:
    # something like the following definition might be used deep in a nested python project structure
    # and this way become hard to detect
    def myCrs(crs: QgsCoordinateReferenceSystem = QgsCoordinateReferenceSystem('EPSG:4326')):
        print(f'CRS: {crs}')

start_app()

crs1 = QgsCoordinateReferenceSystem('EPSG:4326')
assert crs1.isValid()
crs2 = QgsCoordinateReferenceSystem.fromWkt(crs1.toWkt())
assert crs1.toWkt() == crs2.toWkt()
assert crs2.isValid()  # <-- raises error
