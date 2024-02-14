from qgis.PyQt.QtCore import QVariant
from qgis._core import QgsVectorLayer
from qgis.core import QgsField, QgsEditorWidgetSetup, edit

from qgis.gui import QgsGui
from qgis.testing import start_app

start_app()

if len(QgsGui.editorWidgetRegistry().factories()) == 0:
    QgsGui.editorWidgetRegistry().initEditors()

# Example 1: change editor widget setup

def onFieldsUpdated():
    print('-- updatedFields emitted!')

uri = "point?crs=epsg:4326&field=color:string"
layer = QgsVectorLayer(uri, "Scratch point layer",  "memory")
layer.updatedFields.connect(onFieldsUpdated)

# Example 1: updatesFields is not emitted when changing the editorWidgetSetup
with edit(layer):
    # this emits the updatedFields signal
    print('Add QgsField')
    layer.addAttribute(QgsField('info', QVariant.String))

# this does not emit the updatedFields signal
print('Change QgsField editorWidgetSetup (no emit of updatedFields)')
layer.setEditorWidgetSetup(0, QgsEditorWidgetSetup('Color', {}))

# Example 2: editorWidgetSetup and comment not considered in field comparison
field1 = QgsField('info', QVariant.String)
field2 = QgsField('info', QVariant.String)
assert field1 == field2
assert field1.editorWidgetSetup().type() == field2.editorWidgetSetup().type()
assert field1.comment() == field2.comment()

# change comment and editorWidgetSetup
field2.setEditorWidgetSetup(QgsEditorWidgetSetup('Color', {}))
field2.setComment('Color info value')

assert field1.editorWidgetSetup().type() != field2.editorWidgetSetup().type()
assert field1.comment() != field2.comment()

# different QgsEditorWidgetSetup types, but still same field?
assert field1 != field2