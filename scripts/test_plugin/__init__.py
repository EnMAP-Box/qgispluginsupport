import pathlib
import site
from typing import List

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QAction, QWidget
from qgis._gui import QgisInterface


# the init to be used in the test plugin
def classFactory(iface):  # pylint: disable=invalid-name
    """Load the EO Time Series Viewer Plugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """

    d = pathlib.Path(__file__).parent
    site.addsitedir(d)

    return QGISPluginsSupportPlugin(iface)


class QGISPluginsSupportPlugin(object):
    title = 'QPS'

    def __init__(self, iface):

        self.mWidgets: List[QWidget] = []
        # dirPlugin = os.path.dirname(__file__)
        # site.addsitedir(dirPlugin)
        self.mToolbarActions: List[QAction] = []

        import qps
        qps.initAll()

    def initGui(self):
        from qgis.utils import iface
        assert isinstance(iface, QgisInterface)

        # init main UI
        action = QAction(self.title, iface)
        action.triggered.connect(self.run)
        self.mToolbarActions.append(action)

        for action in self.mToolbarActions:
            iface.addToolBarIcon(action)
            iface.addPluginToRasterMenu(self.title, action)

        from qps.testing import TestObjects
        from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
        sl = TestObjects.createSpectralLibrary()
        slw = SpectralLibraryWidget(speclib=sl)
        self.mWidgets.append(slw)

    def initProcessing(self):
        """
        dummy
        """
        pass

    def run(self):
        for w in self.mWidgets:
            w.show()

    def unload(self):
        for w in self.mWidgets:
            w.close()
        from qgis.utils import iface
        if isinstance(iface, QgisInterface):
            for action in self.mToolbarActions:
                iface.removeToolBarIcon(action)

    def tr(self, message):
        return QCoreApplication.translate(self.title, message)
