# script that shows how to import ASD files

import os
import pathlib

from qgis.core import QgsVectorLayer

from qgis.testing import start_app
from qps.speclib.core import profile_field_names
from qps.speclib.io.asd import ASDSpectralLibraryIO
from qps.speclib.io.envi import EnviSpectralLibraryIO
from qps.speclib.io.geojson import GeoJsonSpectralLibraryIO
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils

app = start_app()

DIR_INPUTS = pathlib.Path(__file__).parents[1] / 'qpstestdata/asd/gps'
DIR_OUTPUTS = pathlib.Path(__file__).parent
os.makedirs(DIR_OUTPUTS, exist_ok=True)
files = []
for entry in os.scandir(DIR_INPUTS):
    if entry.is_file() and entry.name.endswith('.asd'):
        files.append(entry.path)

profiles = ASDSpectralLibraryIO.importProfiles(DIR_INPUTS)

assert len(profiles) == len(files)

# create an in-memory spectral library
layer = SpectralLibraryUtils.createSpectralLibrary([])
assert isinstance(layer, QgsVectorLayer)
layer.startEditing()
SpectralLibraryUtils.addProfiles(layer, profiles, addMissingFields=True)
assert layer.commitChanges(), layer.error()
assert layer.featureCount() == len(files)

# write as GeoPackage
gpkgFiles = GeoPackageSpectralLibraryIO.exportProfiles(DIR_OUTPUTS / 'speclibGPKG.gpkg', layer)
print(f'Geopackage(s): {gpkgFiles}')

# write as GeoJSON
layer.startEditing()
# layer.deleteAttribute(layer.fields().lookupField('Reference'))
# layer.deleteAttribute(layer.fields().lookupField('Spectrum'))

layer.commitChanges()
jsonFiles = GeoJsonSpectralLibraryIO.exportProfiles(DIR_OUTPUTS / 'speclibJSON.geojson', layer)
print(f'GeoJSON File(s): {jsonFiles}')

# write as ENVI Spectral Library
enviFiles = []
for name in profile_field_names(layer):
    settings = {'profile_field': name}
    files = EnviSpectralLibraryIO.exportProfiles(
        DIR_OUTPUTS / f'speclibENVI_{name}.sli', layer, exportSettings=settings)
    enviFiles.extend(files)
print(f'ENVI Spectral Libraries: {enviFiles}')

if True:
    # show profiles in a SpectralLibraryWidget
    from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget

    w = SpectralLibraryWidget(speclib=layer)
    w.show()
    app.exec_()
