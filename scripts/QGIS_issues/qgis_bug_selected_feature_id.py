"""
This example shows that feature ids of deleted features
are still part of selectedFeatureIds()
see https://github.com/qgis/QGIS/issues/44921
"""
# create test layer
import qgis.utils
from qgis.core import QgsVectorLayer, QgsFeature, Qgis

print(Qgis.QGIS_DEV_VERSION)
print(qgis.utils.Qgis.QGIS_VERSION)
uri = "point?crs=epsg:4326&field=id:integer"
layer = QgsVectorLayer(uri, "Scratch point layer", "memory")
layer.startEditing()
layer.addFeature(QgsFeature(layer.fields()))
layer.commitChanges()

if not (layer.featureCount() == 1):
    raise AssertionError


def onFeaturesDeleted(deleted_fids):
    selected = layer.selectedFeatureIds()
    for fid in selected:
        if not (fid not in deleted_fids):
            raise AssertionError(f'Feature with id {fid} was deleted but is still selected')


layer.featuresDeleted.connect(onFeaturesDeleted)

layer.startEditing()
layer.selectAll()
layer.deleteSelectedFeatures()
layer.commitChanges()

if not (layer.featureCount() == 0):
    raise AssertionError
if not (layer.selectedFeatureIds() == []):
    raise AssertionError
