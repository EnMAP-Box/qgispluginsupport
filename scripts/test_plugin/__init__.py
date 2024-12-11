import pathlib
import site
from typing import List

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QWidget
from qgis.core import QgsProject, QgsWkbTypes
from qgis.gui import QgisInterface


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
        self.loadTestData()
        for w in self.mWidgets:
            w.show()

    def loadTestData(self):

        from qps.testing import TestObjects

        rl = TestObjects.createRasterLayer(nb=25)
        rl.setName('QPS Raster')
        vl1 = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point)
        vl1.setName('QPS Point')
        vl2 = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon)
        vl2.setName('QPS Polygon')
        QgsProject.instance().addMapLayers([vl1, vl2, rl])

    def unload(self):
        for w in self.mWidgets:
            w.close()
        from qgis.utils import iface
        if isinstance(iface, QgisInterface):
            for action in self.mToolbarActions:
                iface.removeToolBarIcon(action)

    def tr(self, message):
        return QCoreApplication.translate(self.title, message)
