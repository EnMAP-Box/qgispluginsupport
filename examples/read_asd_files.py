# script that shows how to import ASD files

import os
import pathlib

from osgeo import gdal

from qgis.core import QgsVectorLayer
from qgis.testing import start_app
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.io.asd import ASDBinaryFile
from qps.speclib.io.envi import EnviSpectralLibraryWriter
from qps.speclib.io.geojson import GeoJSONSpectralLibraryWriter
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryWriter

gdal.UseExceptions()
app = start_app()

DIR_INPUTS = pathlib.Path(__file__).parents[1] / 'qpstestdata/asd/gps'
DIR_OUTPUTS = pathlib.Path(__file__).parent
os.makedirs(DIR_OUTPUTS, exist_ok=True)
files = []
for entry in os.scandir(DIR_INPUTS):
    if entry.is_file() and entry.name.endswith('.asd'):
        files.append(entry.path)

profiles = []
for file in files:
    profiles.extend(ASDBinaryFile(file).asFeatures())
assert len(profiles) == len(files)

# create an in-memory spectral library
layer = SpectralLibraryUtils.createSpectralLibrary([])
assert isinstance(layer, QgsVectorLayer)
layer.startEditing()
SpectralLibraryUtils.addProfiles(layer, profiles, addMissingFields=True)
assert layer.commitChanges(), layer.error()
assert layer.featureCount() == len(files)

features = list(layer.getFeatures())

# write as GeoPackage
gpkgFiles = GeoPackageSpectralLibraryWriter(crs=layer.crs()).writeFeatures(DIR_OUTPUTS / 'speclibGPKG.gpkg',
                                                                           features)
print(f'Geopackage(s): {gpkgFiles}')

# write as GeoJSON
layer.startEditing()
# layer.deleteAttribute(layer.fields().lookupField('Reference'))
# layer.deleteAttribute(layer.fields().lookupField('Spectrum'))

layer.commitChanges()
jsonFiles = GeoJSONSpectralLibraryWriter().writeFeatures(DIR_OUTPUTS / 'speclibJSON.geojson', features)
print(f'GeoJSON File(s): {jsonFiles}')

# write as ENVI Spectral Library
enviFiles = EnviSpectralLibraryWriter().writeFeatures(DIR_OUTPUTS / 'speclibENVI.sli', features)
print(f'ENVI Spectral Libraries: {enviFiles}')

if True:
    # show profiles in a SpectralLibraryWidget
    from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget

    w = SpectralLibraryWidget(speclib=layer)
    w.show()
    app.exec()
