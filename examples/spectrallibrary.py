from qps.testing import start_app, TestObjects, findQGISResourceFiles, StartOptions
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem, QgsPointXY
from qps import initAll
from qps.speclib.core.spectralprofile import SpectralProfile
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qgis.gui import QgsMapCanvas
from qps.maptools import CursorLocationMapTool
from qps.utils import SpatialPoint

app = start_app(resources=findQGISResourceFiles(), options=StartOptions.EditorWidgets)
initAll()


slw = SpectralLibraryWidget()
slw.show()

canvas = QgsMapCanvas()
layer = TestObjects.createRasterLayer(nb=100)
canvas.setLayers([layer])
canvas.setDestinationCrs(layer.crs())
canvas.setExtent(layer.extent())
canvas.show()


def loadProfile(crs: QgsCoordinateReferenceSystem, pt: QgsPointXY):
    spatialPoint = SpatialPoint(crs, pt)
    profiles = []
    for layer in canvas.layers():
        if isinstance(layer, QgsRasterLayer):
            profile = SpectralProfile.fromRasterLayer(layer, spatialPoint)
            if isinstance(profile, SpectralProfile):
                profiles.append(profile)

    slw.setCurrentProfiles(profiles)


m = CursorLocationMapTool(canvas)
m.sigLocationRequest.connect(loadProfile)
canvas.setMapTool(m)
slw.actionSelectProfilesFromMap.setVisible(True)
slw.sigLoadFromMapRequest.connect(lambda *args: canvas.setMapTool(m))

# show canvas left to SpectralLibraryWidget
p = canvas.pos()
p.setX(p.x() - canvas.width())
p.setY(slw.pos().y())
canvas.move(p)
app.exec_()
