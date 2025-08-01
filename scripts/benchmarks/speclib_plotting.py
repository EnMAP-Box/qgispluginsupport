import datetime
import logging
from typing import Optional

from qgis.core import QgsVectorLayer
from qps import initAll
from qps.speclib.gui.spectrallibraryplotitems import SpectralProfilePlotDataItem
from qps.speclib.gui.spectrallibraryplotwidget import SpectralProfilePlotModel
import qps.speclib.gui.spectrallibraryplotwidget
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import start_app

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(module)s %(funcName)s: %(message)s',
                    handlers=[
                        # logging.FileHandler("debug.log"),  # Log to a file
                        logging.StreamHandler()  # Log to console
                    ])

app = start_app()
initAll()

path_large_speclib = r'D:\Repositories\qgispluginsupport\tmp\largespeclib\speclib_namibia2024.gpkg'

t0 = datetime.datetime.now()
TIMES = dict()
qps.speclib.gui.spectrallibraryplotwidget.MAX_PROFILES_DEFAULT = 10000


def measure(step: str, end: Optional[str] = None):
    global t0
    dt = datetime.datetime.now() - t0
    TIMES[step] = dt
    print(f'{dt}: {step}', end=end)
    t0 = datetime.datetime.now()


def n_items(w: SpectralLibraryWidget):
    items = [item for item in w.plotWidget().getPlotItem().items if isinstance(item, SpectralProfilePlotDataItem)]
    return len(items)


t0 = datetime.datetime.now()
layer = QgsVectorLayer(path_large_speclib)
assert layer.isValid()
# layer.setSubsetString('"fid" <= 550')

measure(f'Open Layer with {layer.featureCount()} features')

w = SpectralLibraryWidget(speclib=layer, profile_fields_check=False)
model: SpectralProfilePlotModel = w.plotModel() if hasattr(w, 'plotModel') else w.plotControl()
w.show()
app.processEvents()
measure(f'Open Widget ({n_items(w)} profiles, max: {model.maxProfiles()})')

t0 = datetime.datetime.now()
model.setMaxProfiles(99999)
app.processEvents()
if hasattr(model, 'flushProxySignals'):
    model.flushProxySignals()

measure(f'Increase maxProfiles to 99999 ({n_items(w)} profiles)')

model.updatePlot()
measure(f'Replot all ({n_items(w)} profiles)')

# app.exec_()
