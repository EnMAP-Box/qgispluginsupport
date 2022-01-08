"""
Example that addresses https://github.com/qgis/QGIS/issues/

"""
from qgis.PyQt.QtWidgets import QWidget, QGridLayout
from qgis.core import QgsFeature
from qgis.core import QgsProcessingParameterMultipleLayers, QgsProcessingContext, \
    QgsVectorLayer, QgsProject, QgsProcessingParameterVectorLayer

from qgis.gui import QgsProcessingGui, QgsGui, QgsProcessingParameterWidgetContext
from qgis.testing.mocked import start_app

uri = 'Point?crs=epsg:4326&field=name:string(20)'
layer = QgsVectorLayer(uri, 'Layer', 'memory')
layer.startEditing()

for name in ['A', 'B']:
    f = QgsFeature(layer.fields())
    f.setAttribute('name', name)
    layer.addFeature(f)

# toggle to see the difference
COMMIT_FEATURES_FIRST = False

if COMMIT_FEATURES_FIRST:
    layer.commitChanges(False)
    print('Features committed first')
else:
    print('Features not committed')


def onAttributeValueChanged(fid, i, newValue):
    print(f'attribute changed: fid={fid}, field={i}, new value={newValue}')


def onEditCommandEnded(*args):
    print(f'buffered changes: {layer.editBuffer().changedAttributeValues()}')
    for f in layer.getFeatures():
        print(f'FID {f.id()} name={f.attribute("name")}')


layer.attributeValueChanged.connect(onAttributeValueChanged)
layer.editCommandEnded.connect(onEditCommandEnded)

layer.beginEditCommand('Update attribute value')
i = layer.fields().lookupField('name')
for f in layer.getFeatures():
    old_value = f.attribute('name')
    layer.changeAttributeValue(f.id(), i, f'{old_value} updated')
layer.endEditCommand()
