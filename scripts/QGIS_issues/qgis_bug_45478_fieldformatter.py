# see https://github.com/qgis/QGIS/issues/45478

from PyQt5.QtCore import QByteArray
import pickle
from qgis.utils import iface
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsProject
from qgis.PyQt.QtCore import QVariant

uri = "point?crs=epsg:4326"
lyr = QgsVectorLayer(uri, "Scratch point layer",  "memory")
lyr.startEditing()
lyr.addAttribute(QgsField('f1_blob', QVariant.ByteArray))
lyr.addAttribute(QgsField('f2_text', QVariant.String))
lyr.commitChanges(False)


# add feature, so that QgsAttributeTableModel shows data
f = QgsFeature(lyr.fields())
blob = pickle.dumps('some random stuff')
f.setAttribute('f1_blob', QByteArray(blob))
f.setAttribute('f2_text', 'foo')
f.setAttribute('f3_text', 'bar')
lyr.addFeature(f)
lyr.commitChanges()


# add to legend
QgsProject.instance().addMapLayer(lyr, True)
iface.showAttributeTable(lyr)

# add a new field
# activate debugger breakpoint in void QgsAttributeTableModel::loadAttributes()
# and observe length of mFieldFormatters compared to mWidgetFactories
lyr.startEditing()
lyr.addAttribute(QgsField('f3_text', QVariant.String))
lyr.commitChanges(False)

