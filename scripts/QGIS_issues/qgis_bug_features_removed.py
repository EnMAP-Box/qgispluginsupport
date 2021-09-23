"""
Example for Workaround for https://github.com/qgis/QGIS/issues/45228
"""
from qgis.core import QgsVectorLayer, QgsFeature, edit

uri = "point?crs=epsg:4326&field=name:string"
lyr = QgsVectorLayer(uri, "Scratch point layer",  "memory")

def onFeaturesDeleted(fids):
    print(f'deleted feature IDs: {fids}')

lyr.featuresDeleted.connect(onFeaturesDeleted)

features = []
for i in range(2):
    f = QgsFeature(lyr.fields())
    f.setAttribute('name', f'F{i+1}')
    features.append(f)

if False:
    with edit(lyr):
        lyr.addFeatures(features)
else:
    lyr.startEditing()
    lyr.beginEditCommand(f'added {len(features)} features')
    lyr.addFeatures(features)
    lyr.endEditCommand()
    print(f'added feature IDs: {lyr.allFeatureIds()}')

    wrap_commit = True

    if wrap_commit:
        print('wrap commit with editcommand')
        lyr.beginEditCommand('Wrap Commit')
    lyr.commitChanges(stopEditing=False)

    if wrap_commit:
        lyr.endEditCommand()

print(f'committed features IDs: {lyr.allFeatureIds()}')

s = ""