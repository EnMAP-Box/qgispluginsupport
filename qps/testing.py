# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/testing.py

    A module to support unittesting in context of GDAL and QGIS
    ---------------------
    Beginning            : 2019-01-11
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import enum
import inspect
import itertools
import os
import pathlib
import random
import sqlite3
import sys
import traceback
import typing
import uuid
import warnings
from unittest import mock

import numpy as np
from osgeo import gdal, ogr, osr, gdal_array

import qgis.testing
import qgis.testing.mocked
import qgis.utils
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, QPoint, QSize, pyqtSignal, QMimeData, QPointF, QDir, Qt, QThreadPool
from qgis.PyQt.QtGui import QImage, QDropEvent, QIcon
from qgis.PyQt.QtWidgets import QToolBar, QFrame, QHBoxLayout, QVBoxLayout, QMainWindow, QApplication, QWidget, QAction, \
    QMenu
from qgis.core import QgsField, QgsGeometry
from qgis.core import QgsLayerTreeLayer
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes, QgsFields, QgsApplication, \
    QgsCoordinateReferenceSystem, QgsProject, \
    QgsProcessingParameterNumber, QgsProcessingAlgorithm, QgsProcessingProvider, QgsPythonRunner, \
    QgsFeatureStore, QgsProcessingParameterRasterDestination, QgsProcessingParameterRasterLayer, \
    QgsProviderRegistry, QgsLayerTree, QgsLayerTreeModel, QgsLayerTreeRegistryBridge, \
    QgsProcessingModelAlgorithm, QgsProcessingRegistry, QgsProcessingContext, \
    QgsProcessingFeedback
from qgis.core import QgsVectorLayerUtils, QgsFeature, QgsCoordinateTransform
from qgis.gui import QgsMapLayerConfigWidgetFactory
from qgis.gui import QgsPluginManagerInterface, QgsLayerTreeMapCanvasBridge, QgsLayerTreeView, QgsMessageBar, \
    QgsMapCanvas, QgsGui, QgisInterface, QgsBrowserGuiModel
from .resources import findQGISResourceFiles, initResourceFile
from .speclib import createStandardFields, FIELD_VALUES
from .speclib.core import profile_fields as pFields, create_profile_field, is_profile_field, profile_field_indices
from .speclib.core.spectrallibrary import SpectralLibraryUtils
from .speclib.core.spectralprofile import prepareProfileValueDict, encodeProfileValueDict
from .utils import UnitLookup, px2geo, SpatialPoint, findUpwardPath

WMS_GMAPS = r'crs=EPSG:3857&' \
            r'format&' \
            r'type=xyz&' \
            r'url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'

WMS_OSM = r'referer=OpenStreetMap%20contributors,%20under%20ODbL&' \
          r'type=xyz&' \
          r'url=https://tiles.wmflabs.org/hikebike/%7Bz%7D/%7Bx%7D/%7By%7D.png&' \
          r'zmax=17&' \
          r'zmin=1'

WFS_Berlin = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' ' \
             'typename=''fis:re_postleit'' ' \
             'url=''https://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' ' \
             'version=''auto'''

TEST_VECTOR_GEOJSON = pathlib.Path(__file__).parent / 'testvectordata.geojson'


def initQgisApplication(*args, qgisResourceDir: str = None,
                        loadProcessingFramework=True,
                        loadEditorWidgets=True,
                        loadPythonRunner=True,
                        minimal=False,
                        **kwds) -> QgsApplication:
    """
    Initializes a QGIS Environment
    :param qgisResourceDir: path to folder with QGIS resource modules. default = None
    :param loadProcessingFramework:  True, loads the QgsProcessingFramework plugins
    :param loadEditorWidgets: True, load the Editor widgets
    :param loadPythonRunner:  True, initializes a Python Runner
    :param minimal: False, if set on True, will deactivate the `load*` and return only a basic QgsApplication
    :return:
    """
    """

    :return: QgsApplication instance of local QGIS installation
    """
    warnings.warn('Use qps.testing.start_app instead', DeprecationWarning)
    return start_app(cleanup=True, options=StartOptions.All)


@enum.unique
class StartOptions(enum.IntFlag):
    Minimized = 0
    EditorWidgets = 1
    ProcessingFramework = 2
    PythonRunner = 4
    PrintProviders = 8
    All = EditorWidgets | ProcessingFramework | PythonRunner | PrintProviders


def stop_app():
    """
    Stops the QGIS Application, if started via qgis.test.start_app()
    """
    global _QGIS_MOCKUP
    global _PYTHON_RUNNER
    _PYTHON_RUNNER = None
    _QGIS_MOCKUP = None
    QgsPythonRunner.setInstance(None)
    import qgis.utils
    if isinstance(qgis.utils.iface, QgisInterface):
        from qgis.PyQt.sip import unwrapinstance
        unwrapinstance(qgis.utils.iface)
        qgis.utils.iface = None

    import qgis.testing as qtest
    if isinstance(getattr(qtest, 'QGISAPP', None), QgsApplication):
        try:
            qtest.stop_app()
        except NameError as ex:
            s = ""
        except Exception as ex2:
            s = ""
            pass
    import gc
    gc.collect()


_QGIS_MOCKUP = None
_PYTHON_RUNNER = None


def start_app(cleanup: bool = True,
              options=StartOptions.Minimized,
              resources: typing.List[typing.Union[str, pathlib.Path]] = None) -> QgsApplication:
    """
    :param cleanup:
    :param options: combination of StartOptions
    :param resources: list of resource files (*_rc.py) to load on start-up into Qt resource system
    :return:
    """

    global _PYTHON_RUNNER
    global _QGIS_MOCKUP
    global _APP

    if resources is None:
        resources = []

    if isinstance(QgsApplication.instance(), QgsApplication):
        print('Found existing QgsApplication.instance()')
        qgsApp = QgsApplication.instance()
    else:
        # load resource files, e.g to make icons available
        for path in resources:
            initResourceFile(path)

        qgsApp = qgis.testing.start_app(cleanup=cleanup)
        # _APP = qgsApp
        # initialize things not done by qgis.test.start_app()...
        if not QgsProviderRegistry.instance().libraryDirectory().exists():
            libDir = pathlib.Path(QgsApplication.instance().pkgDataPath()) / 'plugins'
            QgsProviderRegistry.instance().setLibraryDirectory(QDir(libDir.as_posix()))

        # check for potentially missing qt plugin folders
        if not os.environ.get('QT_PLUGIN_PATH'):
            existing = [pathlib.Path(p).resolve() for p in qgsApp.libraryPaths()]

            prefixDir = pathlib.Path(qgsApp.pkgDataPath()).resolve()
            candidates = [prefixDir / 'qtplugins',
                          prefixDir / 'plugins',
                          prefixDir / 'bin']
            for candidate in candidates:
                if candidate.is_dir() and candidate not in existing:
                    qgsApp.addLibraryPath(candidate.as_posix())

        assert QgsProviderRegistry.instance().libraryDirectory().exists(), \
            'Directory: {} does not exist. Please check if QGIS_PREFIX_PATH correct'.format(
                QgsProviderRegistry.instance().libraryDirectory().path())

        # initiate a PythonRunner instance if None exists
        if StartOptions.PythonRunner in options and not QgsPythonRunner.isValid():
            if not isinstance(_PYTHON_RUNNER, QgsPythonRunnerMockup):
                _PYTHON_RUNNER = QgsPythonRunnerMockup()
            QgsPythonRunner.setInstance(_PYTHON_RUNNER)

        # init standard EditorWidgets
        if StartOptions.EditorWidgets in options and len(QgsGui.editorWidgetRegistry().factories()) == 0:
            QgsGui.editorWidgetRegistry().initEditors()

        # test SRS
        assert os.path.isfile(QgsApplication.qgisUserDatabaseFilePath()), \
            'QgsApplication.qgisUserDatabaseFilePath() does not exists: {}'.format(
                QgsApplication.qgisUserDatabaseFilePath())

        con = sqlite3.connect(QgsApplication.qgisUserDatabaseFilePath())
        cursor = con.execute(r"SELECT name FROM sqlite_master WHERE type='table'")
        tables = [v[0] for v in cursor.fetchall() if v[0] != 'sqlite_sequence']
        if 'tbl_srs' not in tables:
            info = ['{} misses "tbl_srs"'.format(QgsApplication.qgisSettingsDirPath()),
                    'Settings directory might be outdated: {}'.format(QgsApplication.instance().qgisSettingsDirPath())]
            print('\n'.join(info), file=sys.stderr)

        get_iface()  # creates a QGIS Mockup

        # set 'home_plugin_path', which is required from the QGIS Plugin manager
        qgis.utils.home_plugin_path = (pathlib.Path(QgsApplication.instance().qgisSettingsDirPath())
                                       / 'python' / 'plugins').as_posix()

        # initialize the QGIS processing framework
        if StartOptions.ProcessingFramework in options:

            pfProviderIds = [p.id() for p in QgsApplication.processingRegistry().providers()]
            if 'native' not in pfProviderIds:
                from qgis.analysis import QgsNativeAlgorithms
                QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

            qgisCorePythonPluginDir = pathlib.Path(QgsApplication.pkgDataPath()) / 'python' / 'plugins'
            assert os.path.isdir(qgisCorePythonPluginDir)
            if qgisCorePythonPluginDir not in sys.path:
                sys.path.append(qgisCorePythonPluginDir.as_posix())

            required = ['qgis', 'gdal']  # at least these should be available
            missing = [p for p in required if p not in pfProviderIds]
            if len(missing) > 0:
                from processing.core.Processing import Processing
                Processing.initialize()

        if StartOptions.PrintProviders in options:
            providers = QgsProviderRegistry.instance().providerList()
            print('Providers: {}'.format(', '.join(providers)))

    return qgsApp


class QgisMockup(QgisInterface):
    """
    A "fake" QGIS Desktop instance that should provide all the interfaces a
    plugin developer might need (and nothing more)
    """

    def __init__(self, *args):
        super(QgisMockup, self).__init__()

        self.mMapLayerPanelFactories: typing.List[QgsMapLayerConfigWidgetFactory] = []

        self.mCanvas = QgsMapCanvas()
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mRootNode = QgsLayerTree()
        self.mLayerTreeRegistryBridge = QgsLayerTreeRegistryBridge(self.mRootNode, QgsProject.instance())
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
        QgsProject.instance().layersWillBeRemoved.connect(self._onRemoveLayers)

        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeMapCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mRootNode, self.mCanvas)
        self.mLayerTreeMapCanvasBridge.setAutoSetupOnFirstLayer(True)
        # QgsProject.instance().legendLayersAdded.connect(self.addLegendLayers)
        self.mPluginManager = QgsPluginManagerMockup()

        self.mBrowserGuiModel = QgsBrowserGuiModel()
        self.ui = QMainWindow()

        self.mViewMenu = self.ui.menuBar().addMenu('View')
        self.mVectorMenu = self.ui.menuBar().addMenu('Vector')
        self.mRasterMenu = self.ui.menuBar().addMenu('Raster')
        self.mWindowMenu = self.ui.menuBar().addMenu('Window')

        self.mMessageBar = QgsMessageBar()
        mainFrame = QFrame()
        self.ui.setCentralWidget(mainFrame)
        self.ui.setWindowTitle('QGIS Mockup')
        hl = QHBoxLayout()
        hl.addWidget(self.mLayerTreeView)
        hl.addWidget(self.mCanvas)
        v = QVBoxLayout()
        v.addWidget(self.mMessageBar)
        v.addLayout(hl)
        mainFrame.setLayout(v)
        self.ui.setCentralWidget(mainFrame)
        self.lyrs = []
        self.createActions()
        self.mClipBoard = QgsClipboardMockup()

        # mock other functions
        excluded = QObject.__dict__.keys()
        self._mock = mock.Mock(spec=QgisInterface)
        for n in self._mock._mock_methods:
            assert isinstance(n, str)
            if not n.startswith('_') and n not in excluded:
                try:
                    inspect.getfullargspec(getattr(self, n))
                except Exception:
                    setattr(self, n, getattr(self._mock, n))

    def _onRemoveLayers(self, layerIDs):
        to_remove: typing.List[QgsLayerTreeLayer] = []
        for lyr in self.mRootNode.findLayers():
            lyr: QgsLayerTreeLayer
            if lyr.layerId() in layerIDs:
                to_remove.append(lyr)
        for lyr in reversed(to_remove):
            lyr.parent().removedChildren(lyr)

    def registerMapLayerConfigWidgetFactory(self, factory: QgsMapLayerConfigWidgetFactory):
        assert isinstance(factory, QgsMapLayerConfigWidgetFactory)

        self.mMapLayerPanelFactories.append(factory)

    def unregisterMapLayerConfigWidgetFactory(self, factory: QgsMapLayerConfigWidgetFactory):
        assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
        self.mMapLayerPanelFactories = [f for f in self.mMapLayerPanelFactories if f.title() != factory.title()]

    def addLegendLayers(self, mapLayers: typing.List[QgsMapLayer]):
        for lyr in mapLayers:
            self.mRootNode.addLayer(lyr)

    def pluginManagerInterface(self) -> QgsPluginManagerInterface:
        return self.mPluginManager

    def activeLayer(self):
        return self.mapCanvas().currentLayer()

    def setActiveLayer(self, mapLayer: QgsMapLayer):
        if mapLayer in self.mapCanvas().layers():
            self.mapCanvas().setCurrentLayer(mapLayer)

    def cutSelectionToClipboard(self, mapLayer: QgsMapLayer):
        if isinstance(mapLayer, QgsVectorLayer):
            self.mClipBoard.replaceWithCopyOf(mapLayer)
            mapLayer.beginEditCommand('Features cut')
            mapLayer.deleteSelectedFeatures()
            mapLayer.endEditCommand()

    def browserModel(self) -> QgsBrowserGuiModel:
        self.mBrowserGuiModel

    def copySelectionToClipboard(self, mapLayer: QgsMapLayer):
        if isinstance(mapLayer, QgsVectorLayer):
            self.mClipBoard.replaceWithCopyOf(mapLayer)

    def pasteFromClipboard(self, pasteVectorLayer: QgsMapLayer):
        if not isinstance(pasteVectorLayer, QgsVectorLayer):
            return

        # todo: implement

        features = self.mClipBoard.transformedCopyOf(pasteVectorLayer.crs(), pasteVectorLayer.fields())
        compatibleFeatures = []
        for f in features:
            compatibleFeatures.extend(QgsVectorLayerUtils.makeFeatureCompatible(f, pasteVectorLayer))
        pasteVectorLayer.beginEditCommand('Features pasted')
        pasteVectorLayer.addFeatures(compatibleFeatures)
        pasteVectorLayer.endEditCommand()

        return

    def iconSize(self, dockedToolbar=False):
        return QSize(30, 30)

    def mainWindow(self):
        return self.ui

    def addToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def removeToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def addVectorLayer(self, path, basename=None, providerkey: str = 'ogr'):
        if basename is None:
            basename = os.path.basename(path)

        lyr = QgsVectorLayer(path, basename, providerkey)
        assert lyr.isValid()
        QgsProject.instance().addMapLayer(lyr, True)
        self.mRootNode.addLayer(lyr)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()

    def legendInterface(self):
        return None

    def layerTreeCanvasBridge(self) -> QgsLayerTreeMapCanvasBridge:
        return self.mLayerTreeMapCanvasBridge

    def layerTreeView(self) -> QgsLayerTreeView:
        return self.mLayerTreeView

    def addRasterLayer(self, path, baseName: str = '') -> QgsRasterLayer:
        lyr = QgsRasterLayer(path, os.path.basename(path))
        self.lyrs.append(lyr)
        QgsProject.instance().addMapLayer(lyr, True)
        self.mRootNode.addLayer(lyr)
        return lyr

    def createActions(self):
        m = self.ui.menuBar().addAction('Add Vector')
        m = self.ui.menuBar().addAction('Add Raster')

    def mapCanvas(self) -> QgsMapCanvas:
        return self.mCanvas

    def mapCanvases(self) -> typing.List[QgsMapCanvas]:
        return [self.mCanvas]

    def mapNavToolToolBar(self) -> QToolBar:
        return self.mMapNavToolBar

    def messageBar(self, *args, **kwargs) -> QgsMessageBar:
        return self.mMessageBar

    def rasterMenu(self) -> QMenu:
        return self.mRasterMenu

    def vectorMenu(self) -> QMenu:
        return self.mVectorMenu

    def viewMenu(self) -> QMenu:
        return self.mViewMenu

    def windowMenu(self) -> QMenu:
        return self.mWindowMenu

    def zoomFull(self, *args, **kwargs):
        self.mCanvas.zoomToFullExtent()


def get_iface() -> QgisInterface:
    if not isinstance(qgis.utils.iface, QgisInterface):
        iface = QgisMockup()
        qgis.utils.initInterface(sip.unwrapinstance(iface))
        # we use our own QgisInterface, so replace it where it might have been imported
        # like `iface = qgis.utils.iface`
        _set_iface(iface)

    return qgis.utils.iface


def _set_iface(ifaceMock):
    """
    Replaces the iface variable in other plugins, i.e. the  QGIS processing plugin
    :param ifaceMock: QgisInterface
    """
    import processing.ProcessingPlugin

    # enhance this list with further positions where iface needs to be replaces or remains None otherwise
    modules = [processing.ProcessingPlugin]

    for m in modules:
        m.iface = ifaceMock


class TestCase(qgis.testing.TestCase):
    IFACE = None

    @staticmethod
    def runsInCI() -> True:
        """
        Returns True if this the environment is supposed to run in a CI environment
        and should not open blocking dialogs
        """
        return str(os.environ.get('CI', '')).lower() not in ['', 'none', 'false', '0']

    @classmethod
    def setUpClass(cls, cleanup: bool = True, options=StartOptions.All, resources: list = None) -> None:
        if not isinstance(QgsApplication.instance(), QgsApplication):
            qgis.testing.start_app()

            if TestCase.IFACE is None:
                TestCase.IFACE = get_iface()

            from processing.core.Processing import Processing
            Processing.initialize()

            QgsGui.editorWidgetRegistry().initEditors()

        return

        if resources is None:
            resources = []
        # try to find QGIS resource files
        for r in findQGISResourceFiles():
            if r not in resources:
                resources.append(r)

        start_app(cleanup=cleanup, options=options, resources=resources)

        from osgeo import gdal
        gdal.AllRegister()

    def tearDown(self):
        return
        # let failures fail fast

        # return
        QApplication.processEvents()
        QThreadPool.globalInstance().waitForDone()
        # QgsProject.instance().removeAllMapLayers()

        import gc
        gc.collect()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        if False:  # bug in qgis
            try:
                stop_app()
            except NameError as ex:
                s = ""
                pass

    def createTestOutputDirectory(self, name: str = 'test-outputs') -> pathlib.Path:
        """
        Returns the path to a test output directory
        :return:
        """
        repo = findUpwardPath(inspect.getfile(self.__class__), '.git').parent

        testDir = repo / name
        os.makedirs(testDir, exist_ok=True)
        return testDir

    def createProcessingFeedback(self) -> QgsProcessingFeedback:
        """
        Creates a QgsProcessingFeedback.
        :return:
        """
        feedback = QgsProcessingFeedback()

        return feedback

    def createImageCopy(self, path, overwrite_existing: bool = True) -> str:
        """
        Creates a save image copy to manipulate metadata
        :param path: str, path to valid raster image
        :type path:
        :return:
        :rtype:
        """
        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        ds: gdal.Dataset = gdal.Open(path)
        assert isinstance(ds, gdal.Dataset)
        drv: gdal.Driver = ds.GetDriver()

        testdir = self.createTestOutputDirectory() / 'images'
        os.makedirs(testdir, exist_ok=True)
        bn, ext = os.path.splitext(os.path.basename(path))

        newpath = testdir / f'{bn}{ext}'
        i = 0
        if overwrite_existing and newpath.is_file():
            drv.Delete(newpath.as_posix())
        else:
            while newpath.is_file():
                i += 1
                newpath = testdir / f'{bn}{i}{ext}'

        drv.CopyFiles(newpath.as_posix(), path)

        return newpath.as_posix()

    def showGui(self, widgets: typing.Union[QWidget, typing.List[QWidget]] = None) -> bool:
        """
        Call this to show GUI(s) in case we do not run within a CI system
        """

        if widgets is None:
            widgets = []
        if not isinstance(widgets, list):
            widgets = [widgets]

        keepOpen = False

        for w in widgets:
            if isinstance(w, QWidget):
                w.show()
                keepOpen = True
            elif callable(w):
                w()

        if self.runsInCI():
            return False

        app = QApplication.instance()
        if isinstance(app, QApplication) and keepOpen:
            app.exec_()

        return True

    def assertIconsEqual(self, icon1, icon2):
        self.assertIsInstance(icon1, QIcon)
        self.assertIsInstance(icon2, QIcon)
        size = QSize(256, 256)
        self.assertEqual(icon1.actualSize(size), icon2.actualSize(size))

        img1 = QImage(icon1.pixmap(size))
        img2 = QImage(icon2.pixmap(size))
        self.assertImagesEqual(img1, img2)

    def assertImagesEqual(self, image1: QImage, image2: QImage):
        if image1.size() != image2.size():
            return False
        if image1.format() != image2.format():
            return False

        for x in range(image1.width()):
            for y in range(image1.height()):
                s = image1.bits()
                if image1.pixel(x, y, ) != image2.pixel(x, y):
                    return False
        return True


class ExampleAlgorithmProvider(QgsProcessingProvider):
    NAME = 'TestAlgorithmProvider'

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


class SpectralProfileDataIterator(object):

    def __init__(self,
                 n_bands_per_field: typing.Union[int, typing.List[int]],
                 target_crs=None):

        if not isinstance(n_bands_per_field, list):
            n_bands_per_field = [n_bands_per_field]

        if not isinstance(target_crs, QgsCoordinateReferenceSystem):
            target_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        self.target_crs = target_crs
        self.coredata, self.wl, self.wlu, self.gt, self.wkt = TestObjects.coreData()

        px1 = px2geo(QPoint(0, 0), self.gt, pxCenter=False)
        px2 = px2geo(QPoint(1, 1), self.gt, pxCenter=False)

        self.dx = abs(px2.x() - px1.x())
        self.dy = abs(px2.y() - px1.y())

        self.source_crs = QgsCoordinateReferenceSystem(self.wkt)
        self.cnb, self.cnl, self.cns = self.coredata.shape
        n_bands_per_field = [self.cnb if nb == -1 else nb for nb in n_bands_per_field]
        for nb in n_bands_per_field:
            assert nb is None or 0 < nb
            # assert 0 < nb <= self.cnb, f'Max. number of bands can be {self.cnb}'
        self.band_indices: typing.List[np.ndarray] = []
        for nb in n_bands_per_field:
            if nb is None:
                self.band_indices.append(None)
            else:
                idx: np.ndarray = None
                if nb <= self.cnb:
                    idx = np.linspace(0, self.cnb - 1, num=nb, dtype=np.int16)
                else:
                    # get nb bands positions along wavelength
                    idx = np.linspace(self.wl[0], self.wl[-1], num=nb, dtype=float)

            self.band_indices.append(idx)

    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        return self.source_crs

    def targetCrs(self) -> QgsCoordinateReferenceSystem:
        return self.target_crs

    def __iter__(self):
        return self

    def __next__(self):

        x = random.randint(0, self.coredata.shape[2] - 1)
        y = random.randint(0, self.coredata.shape[1] - 1)

        px = QPoint(x, y)
        # from .utils import px2geo
        pt = px2geo(px, self.gt, pxCenter=False)
        pt = SpatialPoint(self.sourceCrs(),
                          pt.x() + self.dx * random.uniform(0, 1),
                          pt.y() - self.dy * random.uniform(0, 1))
        pt = pt.toCrs(self.targetCrs())
        results = []
        for band_indices in self.band_indices:
            if band_indices is None:
                results.append((None, None, None))
            else:
                if band_indices.dtype == np.int16:
                    yValues = self.coredata[band_indices, y, x]
                    xValues = self.wl[band_indices]
                elif band_indices.dtype == float:
                    xValues = band_indices
                    yValues = self.coredata[:, y, x]
                    yValues = np.interp(xValues, self.wl, yValues)
                else:
                    raise NotImplementedError()
                results.append((yValues, xValues, self.wlu))
        return results, pt


class TestObjects(object):
    """
    Creates objects to be used for testing. It is preferred to generate objects in-memory.
    """

    _coreData = _coreDataWL = _coreDataWLU = _coreDataWkt = _coreDataGT = None

    @staticmethod
    def coreData() -> typing.Tuple[np.ndarray, np.ndarray, str, tuple, str]:
        if TestObjects._coreData is None:
            source_raster = pathlib.Path(__file__).parent / 'enmap.tif'
            assert source_raster.is_file()

            ds = gdal.Open(source_raster.as_posix())
            assert isinstance(ds, gdal.Dataset)
            TestObjects._coreData = ds.ReadAsArray()
            TestObjects._coreDataGT = ds.GetGeoTransform()
            TestObjects._coreDataWkt = ds.GetProjection()
            from .utils import parseWavelength
            TestObjects._coreDataWL, TestObjects._coreDataWLU = parseWavelength(ds)

        results = TestObjects._coreData, TestObjects._coreDataWL, TestObjects._coreDataWLU, \
                  TestObjects._coreDataGT, TestObjects._coreDataWkt
        return results

    @staticmethod
    def createDropEvent(mimeData: QMimeData) -> QDropEvent:
        """Creates a QDropEvent containing the provided QMimeData ``mimeData``"""
        return QDropEvent(QPointF(0, 0), Qt.CopyAction, mimeData, Qt.LeftButton, Qt.NoModifier)

    @staticmethod
    def spectralProfileData(n: int = 10,
                            n_bands: typing.List[int] = None):
        """
        Returns n random spectral profiles from the test data
        :return: lost of (N,3) array of floats specifying point locations.
        """

        coredata, wl, wlu, gt, wkt = TestObjects.coreData()
        cnb, cnl, cns = coredata.shape
        assert n > 0
        if n_bands is None:
            n_bands = [-1]
        if not isinstance(n_bands, list):
            n_bands = [n_bands]
        assert isinstance(n_bands, list)
        for i in range(len(n_bands)):
            nb = n_bands[i]
            if nb == -1:
                n_bands[i] = cnb
            else:
                assert 0 < nb <= cnb, f'Number of bands need to be in range 0 < nb <= {cnb}.'

        n_bands = [nb if nb > 0 else cnb for nb in n_bands]

        for nb in n_bands:
            band_indices = np.linspace(0, cnb - 1, num=nb, dtype=np.int16)
            i = 0
            while i < n:
                x = random.randint(0, coredata.shape[2] - 1)
                y = random.randint(0, coredata.shape[1] - 1)
                yield coredata[band_indices, y, x], wl[band_indices], wlu
                i += 1

    @staticmethod
    def spectralProfiles(n=10,
                         fields: QgsFields = None,
                         n_bands: typing.List[int] = None,
                         wlu: str = None,
                         profile_fields: typing.List[typing.Union[str, QgsField]] = None):

        if fields is None:
            fields = createStandardFields()

        add_names: bool = 'name' in fields.names()

        if profile_fields is None:
            # use
            profile_fields = pFields(fields)
        else:
            for i, f in enumerate(profile_fields):
                if isinstance(f, str):
                    fields.append(create_profile_field(f'profile{i}'))
                elif isinstance(f, QgsField):
                    fields.append(f)
            profile_fields = pFields(fields)

        assert isinstance(profile_fields, QgsFields)

        for f in profile_fields:
            assert is_profile_field(f)

        if n_bands is None:
            n_bands = [-1 for f in profile_fields]
        elif isinstance(n_bands, int):
            n_bands = [n_bands]

        assert len(n_bands) == profile_fields.count(), \
            f'Number of bands list ({n_bands}) has different lenghts that number of profile fields'

        profileGenerator: SpectralProfileDataIterator = SpectralProfileDataIterator(n_bands)

        for i in range(n):
            profile = QgsFeature(fields)

            field_data, pt = profileGenerator.__next__()
            g = QgsGeometry.fromQPointF(pt.toQPointF())
            profile.setGeometry(g)

            if add_names:
                profile.setAttribute('name', f'Profile {i}')
            profile.setId(i + 1)
            for j, profile_field in enumerate(profile_fields):

                (data, wl, data_wlu) = field_data[j]
                if data is None:
                    profile.setAttribute(profile_field.name(), None)
                else:
                    if wlu is None:
                        wlu = data_wlu
                    elif wlu == '-':
                        wl = wlu = None
                    elif wlu != data_wlu:
                        wl = UnitLookup.convertMetricUnit(wl, data_wlu, wlu)
                    profileDict = prepareProfileValueDict(y=data, x=wl, xUnit=wlu)
                    value = encodeProfileValueDict(profileDict, profile_field)
                    profile.setAttribute(profile_field.name(), value)

            yield profile

    """
    Class with static routines to create test objects
    """

    @staticmethod
    def createSpectralLibrary(n: int = 10,
                              n_empty: int = 0,
                              n_bands: typing.Union[int, typing.List[int], np.ndarray] = [-1],
                              profile_field_names: typing.List[str] = None,
                              wlu: str = None) -> QgsVectorLayer:
        """
        Creates a Spectral Library
        :param profile_field_names:
        :param n_bands:
        :type n_bands:
        :param wlu:
        :type wlu:
        :param n: total number of profiles
        :type n: int
        :param n_empty: number of empty profiles, SpectralProfiles with empty x/y values
        :type n_empty: int
        :return: SpectralLibrary
        :rtype: SpectralLibrary
        """
        assert n >= 0
        assert 0 <= n_empty <= n

        if isinstance(n_bands, int):
            n_bands = np.asarray([[n_bands, ]])
        elif isinstance(n_bands, list):
            n_bands = np.asarray(n_bands)
            if n_bands.ndim == 1:
                n_bands = n_bands.reshape((1, n_bands.shape[0]))

        assert isinstance(n_bands, np.ndarray)
        assert n_bands.ndim == 2

        n_profile_columns = n_bands.shape[-1]
        if not isinstance(profile_field_names, list):
            profile_field_names = [f'{FIELD_VALUES}{i}' for i in range(n_profile_columns)]

        slib: QgsVectorLayer = SpectralLibraryUtils.createSpectralLibrary(profile_fields=profile_field_names)
        assert slib.startEditing()

        pfield_indices = profile_field_indices(slib)

        assert len(pfield_indices) == len(profile_field_names)

        if n == 0:
            slib.commitChanges()
            return slib

        # and random profiles
        for groupIndex in range(n_bands.shape[0]):
            bandsPerField = n_bands[groupIndex].tolist()
            profiles = list(TestObjects.spectralProfiles(n,
                                                         fields=slib.fields(),
                                                         n_bands=bandsPerField,
                                                         wlu=wlu,
                                                         profile_fields=pfield_indices))

            SpectralLibraryUtils.addProfiles(slib, profiles, addMissingFields=False)

        # delete empty profiles
        for i, feature in enumerate(slib.getFeatures()):
            if i >= n_empty:
                break
            for field in profile_field_names:
                feature.setAttribute(field, None)
            slib.updateFeature(feature)

        assert slib.commitChanges()
        return slib

    @staticmethod
    def inMemoryImage(*args, **kwds):

        warnings.warn(''.join(traceback.format_stack()) + '\nUse createRasterDataset instead')
        return TestObjects.createRasterDataset(*args, **kwds)

    @staticmethod
    def createMultiMaskExample(*args, **kwds) -> QgsRasterLayer:

        path = '/vsimem/testMaskImage.{}.tif'.format(str(uuid.uuid4()))
        ds = TestObjects.createRasterDataset(*args, **kwds)
        nb = ds.RasterCount
        nl, ns = ds.RasterYSize, ds.RasterXSize
        arr: np.ndarray = ds.ReadAsArray()
        arr = arr.reshape((nb, nl, ns))
        nodata_values = []

        d = int(min(nl, ns) * 0.25)

        global_nodata = -9999
        for b in range(nb):
            x = random.randint(0, ns - 1)
            y = random.randint(0, nl - 1)

            # nodata = b
            nodata = global_nodata
            nodata_values.append(nodata)
            arr[b, max(y - d, 0):min(y + d, nl - 1), max(x - d, 0):min(x + d, ns - 1)] = nodata

        ds2: gdal.Dataset = gdal_array.SaveArray(arr, path, prototype=ds)

        for b, nd in enumerate(nodata_values):
            band: gdal.Band = ds2.GetRasterBand(b + 1)
            band.SetNoDataValue(nd)
            band.SetDescription(ds.GetRasterBand(b + 1).GetDescription())
        ds2.FlushCache()
        lyr = QgsRasterLayer(path)
        lyr.setName('Multiband Mask')
        assert lyr.isValid()

        return lyr

    @staticmethod
    def createRasterDataset(ns=10, nl=20, nb=1,
                            crs=None, gt=None,
                            eType: int = gdal.GDT_Int16,
                            nc: int = 0,
                            path: typing.Union[str, pathlib.Path] = None,
                            drv: typing.Union[str, gdal.Driver] = None,
                            wlu: str = None,
                            pixel_size: float = None,
                            no_data_rectangle: int = 0,
                            no_data_value: typing.Union[int, float] = -9999) -> gdal.Dataset:
        """
        Generates a gdal.Dataset of arbitrary size based on true data from a smaller EnMAP raster image
        """
        from .classification.classificationscheme import ClassificationScheme
        scheme = None
        if nc is None:
            nc = 0

        if nc > 0:
            eType = gdal.GDT_Byte if nc < 256 else gdal.GDT_Int16
            scheme = ClassificationScheme()
            scheme.createClasses(nc)

        if isinstance(drv, str):
            drv = gdal.GetDriverByName(drv)
        elif drv is None:
            drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)

        if isinstance(path, pathlib.Path):
            path = path.as_posix()
        elif path is None:
            if nc > 0:
                path = '/vsimem/testClassification.{}.tif'.format(str(uuid.uuid4()))
            else:
                path = '/vsimem/testImage.{}.tif'.format(str(uuid.uuid4()))
        assert isinstance(path, str)

        ds: gdal.Driver = drv.Create(path, ns, nl, bands=nb, eType=eType)
        assert isinstance(ds, gdal.Dataset)
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            band.SetDescription(f'Test Band {b + 1}')

        if no_data_rectangle > 0:
            no_data_rectangle = min([no_data_rectangle, ns])
            no_data_rectangle = min([no_data_rectangle, nl])
            for b in range(ds.RasterCount):
                band: gdal.Band = ds.GetRasterBand(b + 1)
                band.SetNoDataValue(no_data_value)

        coredata, core_wl, core_wlu, core_gt, core_wkt = TestObjects.coreData()

        if pixel_size:
            core_gt = (core_gt[0], abs(pixel_size), core_gt[2],
                       core_gt[3], core_gt[4], -abs(pixel_size))

        dt_out = gdal_array.flip_code(eType)
        if isinstance(crs, str) or gt is not None:
            assert isinstance(gt, list) and len(gt) == 6
            assert isinstance(crs, str) and len(crs) > 0
            c = QgsCoordinateReferenceSystem(crs)
            ds.SetProjection(c.toWkt())
            ds.SetGeoTransform(gt)
        else:
            ds.SetProjection(core_wkt)
            ds.SetGeoTransform(core_gt)

        if nc > 0:
            for b in range(nb):
                band: gdal.Band = ds.GetRasterBand(b + 1)
                assert isinstance(band, gdal.Band)

                array = np.empty((nl, ns), dtype=dt_out)
                assert isinstance(array, np.ndarray)

                array.fill(0)
                y0 = 0

                step = int(np.ceil(float(nl) / len(scheme)))

                for i, c in enumerate(scheme):
                    y1 = min(y0 + step, nl - 1)
                    array[y0:y1, :] = c.label()
                    y0 += y1 + 1
                band.SetCategoryNames(scheme.classNames())
                band.SetColorTable(scheme.gdalColorTable())

                if no_data_rectangle > 0:
                    array[0:no_data_rectangle, 0:no_data_rectangle] = no_data_value
                band.WriteArray(array)
        else:
            # fill with test data
            coredata = coredata.astype(dt_out)
            cb, cl, cs = coredata.shape
            if nb > coredata.shape[0]:
                coreddata2 = np.empty((nb, cl, cs), dtype=dt_out)
                coreddata2[0:cb, :, :] = coredata
                # todo: increase the number of output bands by linear interpolation instead just repeating the last band
                for b in range(cb, nb):
                    coreddata2[b, :, :] = coredata[-1, :, :]
                coredata = coreddata2

            xoff = 0
            while xoff < ns - 1:
                xsize = min(cs, ns - xoff)
                yoff = 0
                while yoff < nl - 1:
                    ysize = min(cl, nl - yoff)
                    ds.WriteRaster(xoff, yoff, xsize, ysize, coredata[:, 0:ysize, 0:xsize].tobytes())
                    yoff += ysize
                xoff += xsize

            if no_data_rectangle > 0:
                arr = np.empty((nb, no_data_rectangle, no_data_rectangle), dtype=coredata.dtype)
                arr.fill(no_data_value)
                ds.WriteRaster(0, 0, no_data_rectangle, no_data_rectangle, arr.tobytes())

            wl = []
            if nb > cb:
                wl.extend(core_wl.tolist())
                for b in range(cb, nb):
                    wl.append(core_wl[-1])
            else:
                wl = core_wl[:nb].tolist()
            assert len(wl) == nb

            if wlu is None:
                wlu = core_wlu
            elif wlu != core_wlu:
                wl = UnitLookup.convertMetricUnit(wl, core_wlu, wlu)

            domain = None
            if drv.ShortName == 'ENVI':
                domain = 'ENVI'

            ds.SetMetadataItem('wavelength units', wlu, domain)
            ds.SetMetadataItem('wavelength', ','.join([str(w) for w in wl]), domain)

        ds.FlushCache()
        return ds

    TEST_PROVIDER = None

    @staticmethod
    def createRasterProcessingModel(name: str = 'Example Raster Model') -> QgsProcessingModelAlgorithm:

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg = reg.algorithmById('gdal:rearrange_bands')

        return alg

    @staticmethod
    def createRasterLayer(*args, **kwds) -> QgsRasterLayer:
        """
        Creates an in-memory raster layer.
        See arguments & keyword for `inMemoryImage()`
        :return: QgsRasterLayer
        """
        ds = TestObjects.createRasterDataset(*args, **kwds)
        assert isinstance(ds, gdal.Dataset)
        path = ds.GetDescription()

        lyr = QgsRasterLayer(path, os.path.basename(path), 'gdal')
        assert lyr.isValid()
        return lyr

    @staticmethod
    def createVectorDataSet(wkb=ogr.wkbPolygon, n_features: int = None) -> ogr.DataSource:
        """
        Create an in-memory ogr.DataSource
        :return: ogr.DataSource
        """
        ogr.UseExceptions()
        assert wkb in [ogr.wkbPoint, ogr.wkbPolygon, ogr.wkbLineString]

        # find the QGIS world_map.shp
        pkgPath = QgsApplication.instance().pkgDataPath()
        assert os.path.isdir(pkgPath)

        # pathSrc = pathlib.Path(__file__).parent / 'landcover_polygons.geojson'
        pathSrc = TEST_VECTOR_GEOJSON
        assert pathSrc.is_file(), 'Unable to find {}'.format(pathSrc)

        dsSrc = ogr.Open(pathSrc.as_posix())
        assert isinstance(dsSrc, ogr.DataSource)
        lyrSrc = dsSrc.GetLayerByIndex(0)
        assert isinstance(lyrSrc, ogr.Layer)

        ldef = lyrSrc.GetLayerDefn()
        assert isinstance(ldef, ogr.FeatureDefn)

        srs = lyrSrc.GetSpatialRef()
        assert isinstance(srs, osr.SpatialReference)

        drv = ogr.GetDriverByName('GPKG')
        assert isinstance(drv, ogr.Driver)

        # set temp path
        if wkb == ogr.wkbPolygon:
            lname = 'polygons'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.polygons.gpkg'
        elif wkb == ogr.wkbPoint:
            lname = 'points'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.centroids.gpkg'
        elif wkb == ogr.wkbLineString:
            lname = 'lines'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.line.gpkg'
        else:
            raise NotImplementedError()

        dsDst = drv.CreateDataSource(pathDst)
        assert isinstance(dsDst, ogr.DataSource)
        lyrDst = dsDst.CreateLayer(lname, srs=srs, geom_type=wkb)
        assert isinstance(lyrDst, ogr.Layer)

        if n_features is None:
            n_features = lyrSrc.GetFeatureCount()

        assert n_features >= 0

        # copy features
        TMP_FEATURES: typing.List[ogr.Feature] = []
        for fSrc in lyrSrc:
            assert isinstance(fSrc, ogr.Feature)
            TMP_FEATURES.append(fSrc)

        # copy field definitions
        for i in range(ldef.GetFieldCount()):
            fieldDefn = ldef.GetFieldDefn(i)
            assert isinstance(fieldDefn, ogr.FieldDefn)
            lyrDst.CreateField(fieldDefn)

        n = 0
        for fSrc in itertools.cycle(TMP_FEATURES):
            g = fSrc.geometry()
            fDst = ogr.Feature(lyrDst.GetLayerDefn())
            assert isinstance(fDst, ogr.Feature)

            if isinstance(g, ogr.Geometry):
                if wkb == ogr.wkbPolygon:
                    pass
                elif wkb == ogr.wkbPoint:
                    g = g.Centroid()
                elif wkb == ogr.wkbLineString:
                    g = g.GetBoundary()
                else:
                    raise NotImplementedError()

            fDst.SetGeometry(g)

            for i in range(ldef.GetFieldCount()):
                fDst.SetField(i, fSrc.GetField(i))

            assert lyrDst.CreateFeature(fDst) == ogr.OGRERR_NONE
            n += 1

            if n >= n_features:
                break
        assert isinstance(dsDst, ogr.DataSource)
        dsDst.FlushCache()
        return dsDst

    @staticmethod
    def createVectorLayer(wkbType: QgsWkbTypes = QgsWkbTypes.Polygon, n_features: int = None) -> QgsVectorLayer:
        """
        Create a QgsVectorLayer
        :return: QgsVectorLayer
        """
        lyrOptions = QgsVectorLayer.LayerOptions(loadDefaultStyle=False, readExtentFromXml=False)

        wkb = None

        if wkbType in [QgsWkbTypes.Point, QgsWkbTypes.PointGeometry]:
            wkb = ogr.wkbPoint
        elif wkbType in [QgsWkbTypes.LineString, QgsWkbTypes.LineGeometry]:
            wkb = ogr.wkbLineString
        elif wkbType in [QgsWkbTypes.Polygon, QgsWkbTypes.PolygonGeometry]:
            wkb = ogr.wkbPolygon

        assert wkb is not None
        dsSrc = TestObjects.createVectorDataSet(wkb=wkb, n_features=n_features)

        assert isinstance(dsSrc, ogr.DataSource)
        lyr = dsSrc.GetLayer(0)
        assert isinstance(lyr, ogr.Layer)
        assert lyr.GetFeatureCount() > 0
        # uri = '{}|{}'.format(dsSrc.GetName(), lyr.GetName())
        uri = dsSrc.GetName()
        # dsSrc = None
        vl = QgsVectorLayer(uri, 'testlayer', 'ogr', lyrOptions)
        assert isinstance(vl, QgsVectorLayer)
        assert vl.isValid()
        assert vl.featureCount() == lyr.GetFeatureCount()
        return vl

    @staticmethod
    def processingAlgorithm():

        class TestProcessingAlgorithm(QgsProcessingAlgorithm):

            def __init__(self):
                super(TestProcessingAlgorithm, self).__init__()
                s = ""

            def createInstance(self):
                return TestProcessingAlgorithm()

            def name(self):
                return 'exmaplealg'

            def displayName(self):
                return 'Example Algorithm'

            def groupId(self):
                return 'exampleapp'

            def group(self):
                return 'TEST APPS'

            def initAlgorithm(self, configuration=None):
                self.addParameter(QgsProcessingParameterRasterLayer('pathInput', 'The Input Dataset'))
                self.addParameter(
                    QgsProcessingParameterNumber('value', 'The value', QgsProcessingParameterNumber.Double, 1, False,
                                                 0.00, 999999.99))
                self.addParameter(QgsProcessingParameterRasterDestination('pathOutput', 'The Output Dataset'))

            def processAlgorithm(self, parameters, context, feedback):
                assert isinstance(parameters, dict)
                assert isinstance(context, QgsProcessingContext)
                assert isinstance(feedback, QgsProcessingFeedback)

                outputs = {}
                return outputs

        return TestProcessingAlgorithm()


class QgsPluginManagerMockup(QgsPluginManagerInterface):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def addPluginMetadata(self, *args, **kwargs):
        super().addPluginMetadata(*args, **kwargs)

    def addToRepositoryList(self, *args, **kwargs):
        super().addToRepositoryList(*args, **kwargs)

    def childEvent(self, *args, **kwargs):
        super().childEvent(*args, **kwargs)

    def clearPythonPluginMetadata(self, *args, **kwargs):
        # super().clearPythonPluginMetadata(*args, **kwargs)
        pass

    def clearRepositoryList(self, *args, **kwargs):
        super().clearRepositoryList(*args, **kwargs)

    def connectNotify(self, *args, **kwargs):
        super().connectNotify(*args, **kwargs)

    def customEvent(self, *args, **kwargs):
        super().customEvent(*args, **kwargs)

    def disconnectNotify(self, *args, **kwargs):
        super().disconnectNotify(*args, **kwargs)

    def isSignalConnected(self, *args, **kwargs):
        return super().isSignalConnected(*args, **kwargs)

    def pluginMetadata(self, *args, **kwargs):
        super().pluginMetadata(*args, **kwargs)

    def pushMessage(self, *args, **kwargs):
        super().pushMessage(*args, **kwargs)

    def receivers(self, *args, **kwargs):
        return super().receivers(*args, **kwargs)

    def reloadModel(self, *args, **kwargs):
        super().reloadModel(*args, **kwargs)

    def sender(self, *args, **kwargs):
        return super().sender(*args, **kwargs)

    def senderSignalIndex(self, *args, **kwargs):
        return super().senderSignalIndex(*args, **kwargs)

    def showPluginManager(self, *args, **kwargs):
        super().showPluginManager(*args, **kwargs)

    def timerEvent(self, *args, **kwargs):
        super().timerEvent(*args, **kwargs)


class QgsClipboardMockup(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super(QgsClipboardMockup, self).__init__(parent)

        self.mFeatureFields = None
        self.mFeatureClipboard = None
        self.mCRS = None
        self.mSrcLayer = None
        self.mUseSystemClipboard = False
        QApplication.clipboard().dataChanged.connect(self.systemClipboardChanged)

    def replaceWithCopyOf(self, src: QgsVectorLayer):
        if isinstance(src, QgsVectorLayer):
            self.mFeatureFields = src.fields()
            self.mFeatureClipboard = src.selectedFeatures()
            self.mCRS = src.crs()
            self.mSrcLayer = src

            return

        elif isinstance(src, QgsFeatureStore):
            raise NotImplementedError()

    def copyOf(self, field: QgsFields):

        return self.mFeatureClipboard

    def transformedCopyOf(self, crs: QgsCoordinateReferenceSystem, fields: QgsFields) -> typing.List[QgsFeature]:

        features = self.copyOf(fields)
        ct = QgsCoordinateTransform(self.mCRS, crs, QgsProject.instance())

        for f in features:
            g: QgsGeometry = f.geometry()
            g.transform(ct)
            f.setGeometry(g)

        return features

    def setSystemClipBoard(self):
        """
        cb = QApplication.clipboard()
        textCopy = self.generateClipboardText()

        m = QMimeData()
        m.setText(textCopy)

        # todo: set HTML
        """
        raise NotImplementedError()

    def generateClipboardText(self):

        """
        textFields = ['wkt_geom'] + [n for n in self.mFeatureFields]

        textLines = '\t'.join(textFields)
        textFields.clear()
        """

        raise NotImplementedError()

    def systemClipboardChanged(self):
        pass


class QgsPythonRunnerMockup(QgsPythonRunner):
    """
    A Qgs PythonRunner implementation
    """

    def __init__(self):
        super(QgsPythonRunnerMockup, self).__init__()

    def evalCommand(self, cmd: str, result: str):
        try:
            o = compile(cmd)
        except Exception as ex:
            result = str(ex)
            return False
        return True

    def runCommand(self, command, messageOnError=''):
        try:
            o = compile(command, 'fakemodule', 'exec')
            exec(o)
        except Exception as ex:
            messageOnError = str(ex)
            command = ['{}:{}'.format(i + 1, l) for i, l in enumerate(command.splitlines())]
            print('\n'.join(command), file=sys.stderr)
            raise ex
        return True
