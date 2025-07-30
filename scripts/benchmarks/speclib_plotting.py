import datetime

from qgis.core import QgsVectorLayer
from qps import initAll
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import start_app

app = start_app()
initAll()

path_large_speclib = r'D:\Repositories\qgispluginsupport\tmp\largespeclib\speclib_namibia2024.gpkg'

t0 = datetime.datetime.now()
layer = QgsVectorLayer(path_large_speclib)
assert layer.isValid()
t1 = datetime.datetime.now()

w = SpectralLibraryWidget(speclib=layer)
w.show()
app.processEvents()
if hasattr(w, 'plotModel'):
    model = w.plotModel()
    model.setMaxProfiles(999999)
    model.flushProxySignals()

t2 = datetime.datetime.now()

items = list(model.plotWidget().spectralProfilePlotDataItems())
print(f'Load and visualize {layer.featureCount()} features with {len(items)} profiles:')
print(f'Open Layer: {t1 - t0}')
print(f'Load Widget: {t2 - t1}')
app.exec_()
