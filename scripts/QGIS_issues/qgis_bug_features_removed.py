"""
Example for Workaround for https://github.com/qgis/QGIS/issues/45228
"""
from qgis.core import QgsVectorLayer, QgsFeature

temp_fids = []


def onFeaturesDeleted(deleted_fids):
    if not (len(deleted_fids) == len(temp_fids)):
        raise AssertionError(f'featuresDeleted returned {deleted_fids} instead {temp_fids}')
    for d in deleted_fids:
        if not (d in temp_fids):
            raise AssertionError


layer = QgsVectorLayer("point?crs=epsg:4326&field=name:string", "Scratch point layer", "memory")
layer.featuresDeleted.connect(onFeaturesDeleted)

layer.startEditing()
layer.beginEditCommand('add 2 features')
layer.addFeature(QgsFeature(layer.fields()))
layer.addFeature(QgsFeature(layer.fields()))
layer.endEditCommand()
temp_fids.extend(layer.allFeatureIds())

layer.commitChanges()

print('Finished')
