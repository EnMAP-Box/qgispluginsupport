from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLabel
from qgis.testing import start_app

app = start_app()

# this is the Qt resource path that contains the QGIS magnifier icon
icon_path = r':/images/themes/default/mActionZoomIn.svg'

if True:
    # load resource file
    path_rc = Path(__file__).parents[2] / 'qgisresources/images_rc.py'
    from qps.resources import initResourceFile

    initResourceFile(path_rc)

icon = QIcon(icon_path)
label = QLabel()
label.setPixmap(icon.pixmap(256, 256))
label.show()
app.exec_()
