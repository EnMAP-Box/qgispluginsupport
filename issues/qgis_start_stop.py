import os
import pathlib

from qgis.core import QgsApplication

qgs_path = pathlib.Path(os.environ['QGIS_PREFIX_PATH'])
assert qgs_path.is_dir()
QgsApplication.setPrefixPath(qgs_path.as_posix())

guiEnabled = True
qgs = QgsApplication([], guiEnabled)
qgs.initQgis()
qgs.exitQgis()

print('2nd start')
qgs = QgsApplication([], guiEnabled)
print('initQgis')
qgs.initQgis()
print('exitQgis')
qgs.exitQgis()
print('Done')
