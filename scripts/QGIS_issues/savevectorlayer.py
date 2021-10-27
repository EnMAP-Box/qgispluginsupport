from qgis.testing.mocked import get_iface
from qps.testing import TestObjects
iface = get_iface()

lyr = TestObjects.createSpectralLibrary()



d = QgsVectorLayerSaveAsDialog()