from qgis.core import QgsExpressionContext, QgsVectorLayer, QgsExpressionContextUtils

lyr = QgsVectorLayer('point?crs=epsg:4326&field=id:integer', 'dummy', 'memory')

context = QgsExpressionContext()
context.appendScope(QgsExpressionContextUtils.layerScope(lyr))
print(f'name={context.variable("layer_name")}')

# this raises: TypeError: unable to convert a C++ 'QPointer<QgsMapLayer>' instance to a Python object
lyr2 = context.variable('layer')
