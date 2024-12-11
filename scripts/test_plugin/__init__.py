import pathlib
import site
from typing import List

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QWidget
from qgis.core import QgsFeature
from qgis.core import QgsField
from qgis.core import QgsProject, QgsWkbTypes, edit
from qgis.gui import QgisInterface
from qgis.gui import QgsFieldCalculator


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

    def __init__(self, *args):

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
        self.loadStartScripts()
        for w in self.mWidgets:
            w.show()

    def loadStartScripts(self):

        # todo:

        if False:
            from qps.testing import TestObjects

            rl = TestObjects.createRasterLayer(nb=25)
            rl.setName('QPS Raster')
            vl1 = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point)
            vl1.setName('QPS Point')
            vl2 = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon)
            vl2.setName('QPS Polygon')
            QgsProject.instance().addMapLayers([vl1, vl2, rl])

        if True:
            from qps.qgisenums import QMETATYPE_QSTRING
            from qps.speclib.core.spectralprofile import encodeProfileValueDict

            from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
            sl = SpectralLibraryUtils.createSpectralLibrary(['profile'])
            expected = {
                'A': [2.5, 4.0, 3.5],
                'B': [1, 1, 1],
                'C': [2.5, 3, 3.5, 5.5]

            }

            data = [
                {'x': [1, 2, 3], 'y': [2, 2, 2], 'class': 'A'},  # A should average t 2.5, 4.0, 3.5
                {'x': [1, 2, 3], 'y': [3, 4, 5], 'class': 'A'},
                {'x': [1, 2, 3], 'y': [1, 1, 1], 'class': 'B'},  # B should average to 1 1 1
                {'x': [4, 5, 6, 7], 'y': [2, 2, 2, 5], 'class': 'C'},  # C should average to 2.5, 3, 3.5, 5.5
                {'x': [4, 5, 6, 7], 'y': [3, 4, 5, 6], 'class': 'C'},
                # {'x': [1, 2, 3, 4], 'y': [5, 4, 3, 4], 'class': 'D'},  # D should fail, because arrays have different values
                # {'x': [1, 2], 'y': [5, 4], 'class': 'D'},
                #
            ]
            QgsProject.instance().addMapLayer(sl)
            with edit(sl):
                sl.addAttribute(QgsField('class', QMETATYPE_QSTRING))
                for item in data:
                    f = QgsFeature(sl.fields())

                    data = {'x': item['x'], 'y': item['y']}
                    dump = encodeProfileValueDict(data, sl.fields()['profile'])
                    f.setAttribute('profile', dump)
                    f.setAttribute('class', item['class'])
                    assert sl.addFeature(f)

                gui = QgsFieldCalculator(sl, None)
                # create new string field "agr"
                # entry expression 'mean_profile("profile", "class")'

                gui.exec_()

            for f in sl.getFeatures():
                f: QgsFeature
                print(f.attributeMap())
            s = ""

    def unload(self):
        for w in self.mWidgets:
            w.close()
        from qgis.utils import iface
        if isinstance(iface, QgisInterface):
            for action in self.mToolbarActions:
                iface.removeToolBarIcon(action)

    def tr(self, message):
        return QCoreApplication.translate(self.title, message)
