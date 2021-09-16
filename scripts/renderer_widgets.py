from qgis.core import QgsProject, QgsRasterLayer
from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas, QgsPalettedRendererWidget
from qps.testing import start_app, TestObjects
app = start_app()

lyr1 = TestObjects.createRasterLayer(nb=10)
lyr2 = TestObjects.createRasterLayer(nb=2)

QgsProject.instance().addMapLayers([lyr1, lyr2])
w = QgsPalettedRendererWidget(None)
w.setWindowTitle('QgsPalettedRendererWidget')
cb = QgsMapLayerComboBox()

def onLayerChanged(*args):
    lyr = cb.currentLayer()
    c = QgsMapCanvas()
    if isinstance(lyr, QgsRasterLayer):
        w.setRasterLayer(lyr)
    s = ""

cb.layerChanged.connect(onLayerChanged)

w.show()
cb.show()
app.exec_()

