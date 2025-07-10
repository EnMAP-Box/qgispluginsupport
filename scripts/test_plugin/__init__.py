import os
import pathlib
import site
from pathlib import Path
from typing import List

from console import show_console
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QWidget
from qgis.PyQt.QtWidgets import QMenu
from qgis.core import QgsProcessingProvider, QgsProcessingAlgorithm, QgsApplication
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


class QPSProcessingProvider(QgsProcessingProvider):
    NAME = 'QPSProcessingProvider'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._algs = []

    def load(self):
        self.refreshAlgorithms()
        return True

    def name(self):
        return self.NAME

    def longName(self):
        return self.NAME

    def id(self):
        return self.NAME.lower()

    def helpId(self):
        return self.id()

    def icon(self):
        return QIcon(r':/qps/ui/icons/profile_expression.svg')

    def svgIconPath(self):
        return r':/qps/ui/icons/profile_expression.svg'

    def loadAlgorithms(self):
        for a in self._algs:
            self.addAlgorithm(a.createInstance())

    def supportedOutputRasterLayerExtensions(self):
        return []

    def supportsNonFileBasedOutput(self) -> True:
        return True

    def addAlgorithm(self, algorithm: QgsProcessingAlgorithm, **kwargs) -> bool:
        result = super().addAlgorithm(algorithm)
        if result:
            # keep reference
            self._algs.append(algorithm)
        return result


class QGISPluginsSupportPlugin(object):
    title = 'QPS'

    def __init__(self, *args):

        self.mWidgets: List[QWidget] = []
        # dirPlugin = os.path.dirname(__file__)
        # site.addsitedir(dirPlugin)
        self.mToolbarActions: List[QAction] = []

        import qps
        qps.initAll()

        registry = QgsApplication.instance().processingRegistry()
        self.mProvider = QPSProcessingProvider()

        from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
        self.mProvider.addAlgorithm(ImportSpectralProfiles())
        registry.addProvider(self.mProvider)

    def initGui(self):
        from qgis.utils import iface
        assert isinstance(iface, QgisInterface)

        # init main UI
        action = QAction(self.title, iface)
        # action.triggered.connect(self.run)
        self.mToolbarActions.append(action)

        m = QMenu('Start')
        self.populateMenu(m)
        action.setMenu(m)

        for action in self.mToolbarActions:
            iface.addToolBarIcon(action)
            iface.addPluginToRasterMenu(self.title, action)

    def initProcessing(self):
        """
        dummy
        """
        pass

    # def run(self):
    #    self.loadStartScripts()

    def populateMenu(self, menu: QMenu):
        assert isinstance(menu, QMenu)

        folder = Path(__file__).parent / 'startscripts'
        assert folder.is_dir()

        py_files = []
        for e in os.scandir(folder):
            if e.is_file() and e.name.endswith('.py'):
                py_files.append(Path(e.path))
        py_files = sorted(py_files, key=lambda p: p.name)
        for py_file in py_files:
            a: QAction = menu.addAction(py_file.name)
            a.setToolTip(f'Execute code in {py_file}')
            a.triggered.connect(lambda *args, f=py_file: self.execute_py_file(f))

        return

    def execute_py_file(self, path: Path):

        console = show_console()
        console.setUserVisible(True)
        console.activate()

        path = Path(path)
        print(f'Execute {path}')
        with open(path) as f:
            code = f.read()
        exec(code)

    def unload(self):
        for w in self.mWidgets:
            w.close()
        from qgis.utils import iface
        if isinstance(iface, QgisInterface):
            for action in self.mToolbarActions:
                iface.removeToolBarIcon(action)

        registry = QgsApplication.instance().processingRegistry()
        registry.removeProvider(self.mProvider)

    def tr(self, message):
        return QCoreApplication.translate(self.title, message)
