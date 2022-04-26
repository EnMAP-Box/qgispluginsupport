import os
import pathlib
import shutil
from time import sleep
from qgis.core import QgsVectorLayer, QgsApplication
DIR = pathlib.Path(__file__).parent
path_original = DIR / 'test.geojson'
path_tmp = DIR / 'tmpfile.geojson'
shutil.copy(path_original, path_tmp)
lyr = QgsVectorLayer(path_tmp.as_posix())

# critical operation
features = list(lyr.getFeatures())

# this should release all file handles
del lyr
os.remove(path_tmp)
print('Done')