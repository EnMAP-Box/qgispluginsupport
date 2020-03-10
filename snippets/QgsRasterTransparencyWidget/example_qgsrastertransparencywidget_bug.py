from qgis.testing.mocked import get_iface
from qgis.core import QgsRasterLayer, QgsApplication
from qgis.gui import QgsRasterTransparencyWidget
from qgis.PyQt.QtWidgets import QPushButton, QHBoxLayout, QVBoxLayout, QWidget

iface = get_iface()
layer = QgsRasterLayer('landsat_4326.tif')
assert layer.isValid()

tw = QgsRasterTransparencyWidget(layer, iface.mapCanvas())

def apply_and_sync():
    tw.apply()
    tw.syncToLayer()

btn = QPushButton('Apply and Sync')
btn.clicked.connect(apply_and_sync)

l = QVBoxLayout()
l.addWidget(btn)
l.addWidget(tw)

w = QWidget()
w.setLayout(l)
w.show()

QgsApplication.instance().exec_()



