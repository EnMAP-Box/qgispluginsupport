from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout
# import sys
# from pathlib import Path
# sys.path.append(str(Path(__file__).parents[1]))
from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsRasterLayer, edit
from qgis.core import QgsFeature
from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsProject
from qgis.gui import QgsMapCanvas

from qps import initAll
from qps.maptools import CursorLocationMapTool
from qps.resources import findQGISResourceFiles
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import encodeProfileValueDict
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import start_app, TestObjects
from qps.utils import SpatialPoint

app = start_app(resources=findQGISResourceFiles())
initAll()

raster_layer = TestObjects.createRasterLayer(nb=100)

# create an empty in-memory spectral library
uri = "point?crs=epsg:4326&field=id:integer"
speclib = QgsVectorLayer(uri, "MySpeclib", "memory")

with edit(speclib):
    # add some attribute fields
    speclib.addAttribute(QgsField('name', QMetaType.Type.QString))
    speclib.addAttribute(QgsField('comments', QMetaType.Type.QString))
    # add a field for spectral profiles
    SpectralLibraryUtils.addSpectralProfileField(speclib, 'profiles')

# important: all layers must be added to the QgsProject
# that is used by the SpectralLibraryWidget
project = QgsProject.instance()
project.addMapLayers([speclib, raster_layer])
slw = SpectralLibraryWidget(speclib=speclib, project=project)
slw.show()
if speclib != slw.currentLayer():
    raise Exception("Spectral library layer is not the current layer")

canvas = QgsMapCanvas()

canvas.setLayers([raster_layer])
canvas.setDestinationCrs(raster_layer.crs())
canvas.setExtent(raster_layer.extent())
canvas.show()


def loadProfile(crs: QgsCoordinateReferenceSystem, pt: QgsPointXY):
    spatialPoint = SpatialPoint(crs, pt)

    # select a pixel profile from the 1st raster pixel touched

    # new profiles could be added for multiple vector layers
    # therefore we use a Dict[str <layer id>, List[QgsFeature]]
    new_profiles = dict()

    for layer in canvas.layers():
        if isinstance(layer, QgsRasterLayer):
            d = SpectralLibraryUtils.readProfileDict(layer, spatialPoint)
            if d == {}:
                continue
            # create a feature that contains the spectral profile data and addition descriptions
            feature = QgsFeature(speclib.fields())
            # 1. set feature attributes
            feature['name'] = f'{layer.name()} {speclib.featureCount() + 1}'
            target_field = speclib.fields()['profiles']
            feature['profiles'] = encodeProfileValueDict(d, encoding=target_field)
            feature['comments'] = f'Position {pt}'
            # 2. set feature geometry
            # convert the map coordinate into the crs of the spectral library
            pt = spatialPoint.toCrs(speclib.crs())
            g = QgsGeometry.fromPointXY(pt)
            feature.setGeometry(g)

            # this way you can add profile directly to the spectral library
            # with edit(speclib):
            #    speclib.addFeature(feature)

            # ... but we like to see them as "candidates" and confirm them manually

            new_profiles[speclib.id()] = new_profiles.get(speclib.id(), []) + [feature]

    slw.plotModel().addProfileCandidates(new_profiles)


m = CursorLocationMapTool(canvas)
m.sigLocationRequest.connect(loadProfile)
canvas.setMapTool(m)
slw.actionSelectProfilesFromMap.setVisible(True)
slw.sigLoadFromMapRequest.connect(lambda *args: canvas.setMapTool(m))

# emit a location request for the map canvas center
m.sigLocationRequest.emit(canvas.mapSettings().destinationCrs(), canvas.center())

layout = QVBoxLayout()
layout.addWidget(slw)
layout.addWidget(canvas)
widget = QWidget(None)
widget.setLayout(layout)
widget.setWindowTitle('Click on the raster layer')
widget.show()
app.exec()
