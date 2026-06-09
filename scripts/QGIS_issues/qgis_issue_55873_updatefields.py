from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsField, QgsEditorWidgetSetup, edit
from qgis.core import QgsVectorLayer
from qgis.gui import QgsGui
from qgis.testing import start_app

start_app()

if len(QgsGui.editorWidgetRegistry().factories()) == 0:
    QgsGui.editorWidgetRegistry().initEditors()


# Example 1: change editor widget setup

def onFieldsUpdated():
    print('-- updatedFields emitted!')


uri = "point?crs=epsg:4326&field=color:string"
layer = QgsVectorLayer(uri, "Scratch point layer", "memory")
layer.updatedFields.connect(onFieldsUpdated)

# Example 1: updatesFields is not emitted when changing the editorWidgetSetup
with edit(layer):
    # this emits the updatedFields signal
    print('Add QgsField')
    layer.addAttribute(QgsField('info', QMetaType.QString))

# this does not emit the updatedFields signal
print('Change QgsField editorWidgetSetup (no emit of updatedFields)')
layer.setEditorWidgetSetup(0, QgsEditorWidgetSetup('Color', {}))

# Example 2: editorWidgetSetup and comment not considered in field comparison
field1 = QgsField('info', QMetaType.QString)
field2 = QgsField('info', QMetaType.QString)
if not (field1 == field2):
    raise AssertionError
if not (field1.editorWidgetSetup().type() == field2.editorWidgetSetup().type()):
    raise AssertionError
if not (field1.comment() == field2.comment()):
    raise AssertionError

# change comment and editorWidgetSetup
field2.setEditorWidgetSetup(QgsEditorWidgetSetup('Color', {}))
field2.setComment('Color info value')

if not (field1.editorWidgetSetup().type() != field2.editorWidgetSetup().type()):
    raise AssertionError
if not (field1.comment() != field2.comment()):
    raise AssertionError

# different QgsEditorWidgetSetup types, but still same field?
if not (field1 != field2):
    raise AssertionError
