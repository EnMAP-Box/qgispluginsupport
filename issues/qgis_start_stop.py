from qgis.core import QgsApplication
from qgis.testing import start_app, stop_app

cleanup = True

assert not isinstance(QgsApplication.instance(), QgsApplication)
start_app(cleanup=cleanup)
assert isinstance(QgsApplication.instance(), QgsApplication)
stop_app()
assert not isinstance(QgsApplication.instance(), QgsApplication)

print('2nd start-stop')
start_app(cleanup=cleanup)
assert isinstance(QgsApplication.instance(), QgsApplication)
stop_app()
assert not isinstance(QgsApplication.instance(), QgsApplication)
