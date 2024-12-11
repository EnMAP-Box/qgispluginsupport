from qgis.PyQt.QtWidgets import QMenu
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from qgis.gui import QgsMapMouseEvent
from qgis.testing import start_app

app = start_app()

canvas = QgsMapCanvas()
mapTool = QgsMapToolPan(canvas)
canvas.setMapTool(mapTool)


# alternatively, use the QGIS Desktop map canvas
# from qgis.utils import iface
# canvas = iface.mapCanvas()


def populateContextMenu(menu: QMenu, event: QgsMapMouseEvent):
    subMenu = menu.addMenu('My Menu')
    action = subMenu.addAction('My Action')
    action.triggered.connect(lambda *args:
                             print(f'Action triggered at {event.x},{event.y()}'))


canvas.contextMenuAboutToShow.connect(populateContextMenu)
canvas.show()

app.exec_()
