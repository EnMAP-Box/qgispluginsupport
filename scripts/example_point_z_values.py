from qgis.core import QgsWkbTypes

from qgis.testing import start_app, stop_app
from qps.testing import TestObjects

start_app()

vl = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point)

for feature in vl.getFeatures():
    print(feature.geometry().get().z())

stop_app()

