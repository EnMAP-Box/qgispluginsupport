from qgis.core import QgsFeature, QgsVectorLayer
from qgis.core import edit
from qgis.gui import QgsFieldCalculator
from qgis.testing import start_app

start_app()

uri = "point?crs=epsg:4326&field=value:integer"
lyr = QgsVectorLayer(uri, "Scratch point layer", "memory")

with edit(lyr):
    for i in range(5):
        f = QgsFeature(lyr.fields())
        f.setAttribute('value', i)
        assert lyr.addFeature(f)

# QgsProject.instance().addMapLayer(lyr)

with edit(lyr):
    w = QgsFieldCalculator(lyr, None)
    # try to create a new field, e.g. int "value2",
    # and calculate its values, e.g. using an expression like "value" * 2
    w.exec_()

for f in lyr.getFeatures():
    f: QgsFeature
    print(f.attributeMap())
