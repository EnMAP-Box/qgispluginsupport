"""
This script replicates a crash of the QGIS if run in the QGIS Python console
"""

from qgis.gui import *
from qgis.core import *
from qgis.utils import iface

assert isinstance(iface, QgisInterface)

layer = iface.mapCanvas().layers()[0]
assert isinstance(layer, QgsRasterLayer)
assert layer.bandCount() > 1
renderer = layer.renderer()
assert renderer.band() == 1
assert isinstance(renderer, QgsSingleBandPseudoColorRenderer)

# clone the render
newRenderer = renderer.clone()
#newRenderer.setInput(renderer.input()) #<-solution
newRenderer.setBand(2)
layer.setRenderer(newRenderer)




