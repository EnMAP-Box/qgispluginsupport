import typing

from PyQt5.QtGui import QColor
from qgis._core import QgsVectorLayer, QgsFeature, QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsRendererCategory, \
    QgsRenderContext
from qps.speclib.core.spectrallibrary import SpectralLibrary
from qps.utils import nextColor

lyr = QgsVectorLayer('point?crs=epsg:4326&field=name:string(20)', 'myLayer', 'memory')
lyr.startEditing()
names = ['A', 'B', 'C']
for name in names:
    f = QgsFeature(lyr.fields())
    f.setAttribute('name', name)
    lyr.addFeature(f)

assert lyr.commitChanges()

renderer = QgsCategorizedSymbolRenderer('name', [])
colors: typing.Dict[str, QColor] = dict()
color = QColor('red')
for name in names:
    symbol = QgsMarkerSymbol()
    symbol.setColor(color)
    colors[name] = QColor(color)
    color = nextColor(color)
    cat = QgsRendererCategory(name, symbol, name.upper(), render=True)
    renderer.addCategory(cat)

context = QgsRenderContext()
context.setExpressionContext(lyr.createExpressionContext())
renderer.startRender(context, lyr.fields())

for feature in lyr.getFeatures():
    symbol = renderer.symbolForFeature(feature, context)
    c1 = colors[feature.attribute('name')]
    c2 = symbol.color()
    print(c1.name())
    assert c1 == c2
