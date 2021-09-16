from qgis.testing import start_app, stop_app
app = start_app(cleanup=True)

import pathlib
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsField, QgsEditorWidgetSetup, QgsVectorFileWriter, QgsProject, QgsVectorLayer
from qgis.gui import QgsGui
QgsGui.editorWidgetRegistry().initEditors()

editor_widget_type = 'Color'
factory = QgsGui.instance().editorWidgetRegistry().factory(editor_widget_type)
assert factory.name() == editor_widget_type

# 1. create a vector
uri = "point?crs=epsg:4326&field=id:integer"
layer = QgsVectorLayer(uri, "Scratch point layer",  "memory")

# choose driver
# 'memory' works well, but 'ogr' Data provider formats fail
# driverName = 'memory'
driverName = 'GPKG'
# driverName = 'SHP'
# driverName = 'GeoJSON'
# driverName = 'GPX'

if driverName != 'memory':
    # save to local file
    context = QgsProject.instance().transformContext()
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = 'GPKG'
    # path = (pathlib.Path('~').expanduser() / 'test').as_posix()
    path = '/vsimem/test'
    error, _, path, name = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, context, options)
    layer = QgsVectorLayer(path, name=name)
    assert layer.isValid()

field1 = QgsField(name='field1', type=QVariant.String)
field2 = QgsField(name='field2', type=QVariant.String)
setup1 = QgsEditorWidgetSetup(editor_widget_type, {})
setup2 = QgsEditorWidgetSetup(editor_widget_type, {})

# 2. Add field, set editor widget after commitChanges()
assert layer.startEditing()
layer.addAttribute(field1)
assert layer.commitChanges(stopEditing=False)
i = layer.fields().lookupField(field1.name())
layer.setEditorWidgetSetup(i, setup1)

# 3. Add field, set editor widget before commitChanges()
field2.setEditorWidgetSetup(setup2)
layer.addAttribute(field2)
i = layer.fields().lookupField(field2.name())
# this is a workaround:
layer.setEditorWidgetSetup(i, field2.editorWidgetSetup())
assert layer.editorWidgetSetup(i).type() == editor_widget_type
assert layer.commitChanges(stopEditing=True)
# this fails for OGR provider formats
assert layer.editorWidgetSetup(i).type() == editor_widget_type

stop_app()