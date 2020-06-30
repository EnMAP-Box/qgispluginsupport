import pathlib
from osgeo import gdal
from qps.testing import start_app
app = start_app()
DIR = pathlib.Path(__file__).parent

path = r'D:\Temp\EnMAP\L1B_Alps_1\ENMAP01-____L1B-DT000326721_20170626T102020Z_001_V000204_20200406T154119Z-SPECTRAL_IMAGE_VNIR.TIF'
path = (DIR / 'DLR_Logo.svg.png').as_posix()
# via GDAL API
from osgeo import gdal
ds = gdal.Open(path)
ds2 = gdal.AutoCreateWarpedVRT(ds)

# QGIS calls GDALAutoCreateWarpedVRT as well
from qgis.core import QgsRasterLayer
lyr = QgsRasterLayer(path)
s  = ""