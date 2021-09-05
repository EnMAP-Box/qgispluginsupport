from qps.testing import start_app, TestObjects, findQGISResourceFiles
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem, QgsPointXY
from qps import initAll

app = start_app(resources=findQGISResourceFiles())
initAll()

from qps.speclib.core import SpectralProfile
from qps.speclib.gui import SpectralLibraryWidget
from qgis.gui import QgsMapCanvas
from qps.maptools import CursorLocationMapTool
from qps.utils import SpatialPoint

slw = SpectralLibraryWidget()
slw.show()

c = QgsMapCanvas()
l = TestObjects.createRasterLayer(nb=100)
c.setLayers([l])
c.setDestinationCrs(l.crs())
c.setExtent(l.extent())
c.show()


def loadProfile(crs: QgsCoordinateReferenceSystem, pt: QgsPointXY):
    spatialPoint = SpatialPoint(crs, pt)
    profiles = []
    for layer in c.layers():
        if isinstance(layer, QgsRasterLayer):
            profile = SpectralProfile.fromRasterLayer(layer, spatialPoint)
            if isinstance(profile, SpectralProfile):
                profiles.append(profile)

    slw.setCurrentProfiles(profiles)


m = CursorLocationMapTool(c)
m.sigLocationRequest.connect(loadProfile)

slw.actionSelectProfilesFromMap.setVisible(True)
slw.sigLoadFromMapRequest.connect(lambda *args: c.setMapTool(m))

# show canvas left to SpectralLibraryWidget
p = c.pos()
p.setX(p.x() - c.width())
p.setY(slw.pos().y())
c.move(p)
app.exec_()
