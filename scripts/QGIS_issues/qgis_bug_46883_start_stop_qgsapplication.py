from qgis.core import QgsApplication, Qgis
from qgis.testing import start_app, stop_app

print(Qgis.version(), Qgis.devVersion())

print(f'About to start: {QgsApplication.instance()}', flush=True)
start_app()
print(f'About to stop: {QgsApplication.instance()}', flush=True)
stop_app()
print(f'Stopped: {QgsApplication.instance()}', flush=True)