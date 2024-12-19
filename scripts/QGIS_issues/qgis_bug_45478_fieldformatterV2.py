# see https://github.com/qgis/QGIS/issues/45478

import pickle

from qgis.PyQt.QtCore import QByteArray
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, QgsFeature
from qgis.gui import QgsDualView
from qgis.gui import QgsMapCanvas
from qgis.testing import start_app, stop_app
from qps.qgisenums import QMETATYPE_QSTRING

app = start_app()

uri = "point?crs=epsg:4326"
lyr = QgsVectorLayer(uri, "Scratch point layer", "memory")
lyr.startEditing()
lyr.addAttribute(QgsField('blob', QVariant.ByteArray))
lyr.addAttribute(QgsField('text1', QMETATYPE_QSTRING))
lyr.addAttribute(QgsField('text2', QMETATYPE_QSTRING))
lyr.commitChanges(False)

canvas = QgsMapCanvas()
canvas.setLayers([lyr])
view = QgsDualView()
view.init(lyr, canvas)
view.show()

# add feature, so that QgsAttributeTableModel shows data
f = QgsFeature(lyr.fields())
blob = pickle.dumps('some random stuff')
f.setAttribute('blob', QByteArray(blob))
f.setAttribute('text1', 'foo')
f.setAttribute('text2', 'bar')
lyr.addFeature(f)
lyr.commitChanges(False)

lyr.deleteAttribute(1)
s = ""

# add to legend
# QgsProject.instance().addMapLayer(lyr, True)
# iface.showAttributeTable(lyr)

# add a new field
# activate debugger breakpoint in void QgsAttributeTableModel::loadAttributes()
# and observe length of mFieldFormatters compared to mWidgetFactories
# lyr.startEditing()
# lyr.addAttribute(QgsField('text3', QMETATYPE_QSTRING))
# lyr.commitChanges(False)

app.exec_()

stop_app()
