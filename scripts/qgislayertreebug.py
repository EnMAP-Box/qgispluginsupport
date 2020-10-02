# code for QGIS console to reproduce error

# create an invalid vector layer

path = r'C:\Users\geo_beja\Repositories\QGIS_Plugins\qgispluginsupport\qpstestdata\hymap.tif'


path = r'NoneExitings\path'
lyr = QgsVectorLayer(path)
lyr.setName('Test')
print(lyr.isValid())

root = iface.layerTreeView().model().rootGroup()
grp = root.addGroup('testGroup')
grp.setItemVisibilityChecked(False)
root.addLayer(lyr)
iface.setActiveLayer(lyr)
iface.showLayerProperties(lyr)
print('done')
root

root.removeLayer(lyr)

#

