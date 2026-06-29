# relates to https://github.com/qgis/QGIS/issues/45490

import pathlib
import random

from qgis.PyQt.QtGui import QColor
from qgis.core import QgsApplication, QgsVectorLayer, QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory, \
    QgsFillSymbol
from qgis.testing import start_app

app = start_app()

path = pathlib.Path(QgsApplication.prefixPath()) / 'resources' / 'data' / 'world_map.gpkg|layername=countries'
lyr = QgsVectorLayer(path.as_posix(), 'World')
if not (lyr.isValid()):
    raise AssertionError

r = QgsCategorizedSymbolRenderer('NAME')
for name in lyr.uniqueValues(lyr.fields().lookupField('NAME')):
    if not isinstance(name, str):
        continue
    symbol = QgsFillSymbol.createSimple({})
    symbol.setColor(QColor(random.randint(0, 255),  # nosec B311
                           random.randint(0, 255),  # nosec B311
                           random.randint(0, 255)))  # nosec B311
    cat = QgsRendererCategory(name, symbol, name)
    r.addCategory(cat)

lyr.setRenderer(r)
QgsProject.instance().addMapLayer(lyr, True)
lyr.styleChanged.connect(lambda: print('Renderer Changed'))
