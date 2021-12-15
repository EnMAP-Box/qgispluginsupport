from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsPointXY, QgsFeature
from PyQt5.QtCore import QVariant

layer = QgsVectorLayer("Point", "test", "memory")
pr = layer.dataProvider()
pr.addAttributes([QgsField("name", QVariant.String)])
layer.updateFields()

initialGeom = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
f = QgsFeature()
f.setGeometry(initialGeom)
f.setAttributes(["Tom"])
layer.addFeatures([f])
added, (f,) = layer.dataProvider().addFeatures([f])
assert added
layer.startEditing()
editedGeom = QgsGeometry.fromPointXY(QgsPointXY(1, 1))
assert layer.changeGeometry(f.id(), editedGeom)
assert layer.changeAttributeValues(f.id(), {0: "Harry"})

for f in layer.getFeatures():
    print(f.id(), f.attributes(), f.geometry())

for f in layer.getFeatures("name = 'Harry'"):
    print(f.id(), f.attributes(), f.geometry())