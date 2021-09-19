import typing

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLineEdit, QHBoxLayout, QWidget, QCheckBox
from qgis._core import QgsVectorLayer, QgsFeature, QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsRendererCategory, \
    QgsRenderContext, QgsProperty, QgsPropertyTransformer,  QgsPropertyDefinition

from qgis._gui import QgsPropertyOverrideButton, QgsPropertyAssistantWidget
from qps.speclib.core.spectrallibrary import SpectralLibrary
from qps.utils import nextColor
from qps.testing import start_app, StartOptions
app = start_app(options=StartOptions.All)
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


property = QgsProperty()
property.setStaticValue(QColor('blue'))


if False:
    btn = QgsPropertyOverrideButton()
    btn.registerExpressionContextGenerator(lyr)
    btn.setProperty('Color', property)

    cb = QCheckBox()
    tb = QLineEdit()
    btn.registerExpressionWidget(tb)
    btn.registerCheckedWidget(cb)

    l = QHBoxLayout()
    l.addWidget(tb)
    l.addWidget(cb)
    l.addWidget(btn)
    w = QWidget()
    w.setLayout(l)


    w.show()

if True:
    definition = QgsPropertyDefinition(
        'Color', 'Line Color',  QgsPropertyDefinition.String
    )
    state = QgsProperty()
    state.setField('name')
    # state.setStaticValue(QColor('red'))

    w = QgsPropertyAssistantWidget(
        definition=definition,
        initialState = state,
        layer=lyr)
    w.registerExpressionContextGenerator(lyr)
    w.setDockMode(True)
    w.show()
app.exec()