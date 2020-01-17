
import qgis.testing
app = qgis.testing.start_app()

# uncomment to fix the error
import re
app.setPkgDataPath(re.sub(r'(/envs/[^/]+)/\.$', r'\1/Library', app.pkgDataPath()))

print('PkgDataPath={}'.format(app.pkgDataPath()))
from qgis.gui import QgsMapCanvas
c = QgsMapCanvas()
c.show()

