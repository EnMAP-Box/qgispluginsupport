from typing import List

from qgis.core import QgsFeature
from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsRasterLayer
from qgis.gui import QgsMapCanvas
from qps import initAll
from qps.maptools import CursorLocationMapTool
from qps.resources import findQGISResourceFiles
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import start_app, TestObjects
from qps.utils import SpatialPoint

app = start_app(resources=findQGISResourceFiles())
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
    profiles: List[QgsFeature] = []
    for layer in canvas.layers():
        if isinstance(layer, QgsRasterLayer):
            d = SpectralLibraryUtils.readProfileDict(layer, spatialPoint)
            s = ""
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
