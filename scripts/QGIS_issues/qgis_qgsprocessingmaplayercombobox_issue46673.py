from qgis.PyQt.QtWidgets import QWidget, QGridLayout
from qgis.core import QgsProcessingParameterMultipleLayers, QgsProcessingContext, \
    QgsVectorLayer, QgsProject, QgsProcessingParameterVectorLayer

from qgis.gui import QgsProcessingGui, QgsGui, QgsProcessingParameterWidgetContext
from qgis.testing.mocked import start_app
APP = start_app()

uri = 'Point?crs=epsg:4326&field=id:integer&field=name:string(20)'
layerA = QgsVectorLayer(uri, 'Layer A', 'memory')
QgsProject.instance().addMapLayer(layerA)

layerB = QgsVectorLayer(uri, 'Layer B', 'memory')
localProject = QgsProject()
localProject.addMapLayer(layerB)
localWidgetContext = QgsProcessingParameterWidgetContext()
localWidgetContext.setProject(localProject)
localProcessingContext = QgsProcessingContext()
localProcessingContext.setProject(localProject)

param1 = QgsProcessingParameterVectorLayer('SINGLE_LAYER', 'Single Layer')
param2 = QgsProcessingParameterMultipleLayers('MULTIPLE_LAYERS', 'Multiple Layers')

l = QGridLayout()
for row, param in enumerate([param1, param2]):
    wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(param, QgsProcessingGui.Standard)
    wrapper.setWidgetContext(localWidgetContext)
    l.addWidget(wrapper.createWrappedLabel(), row, 0)
    l.addWidget(wrapper.createWrappedWidget(localProcessingContext), row, 1)

w = QWidget()
w.setLayout(l)
w.show()
APP.exec_()