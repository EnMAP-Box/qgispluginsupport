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
                                                                                                                                                 *
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
import random
import sqlite3
import traceback
import typing
import uuid
import warnings

import mock
import numpy as np
import sip
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QHBoxLayout
from osgeo import gdal, ogr, osr, gdal_array
from qgis.core import QgsField

import qgis.testing
import qgis.utils
from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes, QgsFields, QgsApplication, \
    QgsCoordinateReferenceSystem, QgsProject, \
    QgsProcessingParameterNumber, QgsProcessingAlgorithm, QgsProcessingProvider, QgsPythonRunner, \
    QgsFeatureStore, QgsProcessingParameterRasterDestination, QgsProcessingParameterRasterLayer, \
    QgsProviderRegistry, QgsLayerTree, QgsLayerTreeModel, QgsLayerTreeRegistryBridge, \
    QgsProcessingModelAlgorithm, QgsProcessingRegistry, QgsProcessingModelChildAlgorithm, \
    QgsProcessingModelParameter, QgsProcessingModelChildParameterSource, QgsProcessingModelOutput, \
    QgsProcessingContext, \
    QgsProcessingFeedback

from qgis.gui import QgsPluginManagerInterface, QgsLayerTreeMapCanvasBridge, QgsLayerTreeView, QgsMessageBar, \
    QgsMapCanvas, QgsGui, QgisInterface, QgsBrowserGuiModel, QgsProcessingGuiRegistry

from .resources import *
from .speclib import createStandardFields
from .speclib.processing import SpectralProcessingAlgorithmInputWidgetFactory, \
    SpectralProcessingProfilesOutputWidgetFactory, SpectralProcessingProfileType, SpectralProcessingProfilesOutput, \
    SpectralProcessingProfiles
from .speclib.processingalgorithms import SpectralPythonCodeProcessingAlgorithm
from .utils import UnitLookup

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

TEST_VECTOR_KML = pathlib.Path(__file__).parent / 'testvectordata.kml'


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


def start_app(cleanup=True, options=StartOptions.Minimized, resources: list = None) -> QgsApplication:
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
        r = QgsPythonRunnerMockup()
        QgsPythonRunner.setInstance(r)

    # init standard EditorWidgets
    if StartOptions.EditorWidgets in options and len(QgsGui.editorWidgetRegistry().factories()) == 0:
        QgsGui.editorWidgetRegistry().initEditors()

    # test SRS
    if True:
        assert os.path.isfile(QgsApplication.qgisUserDatabaseFilePath()), \
            'QgsApplication.qgisUserDatabaseFilePath() does not exists: {}'.format(
                QgsApplication.qgisUserDatabaseFilePath())

        con = sqlite3.connect(QgsApplication.qgisUserDatabaseFilePath())
        cursor = con.execute(r"SELECT name FROM sqlite_master WHERE type='table'")
        tables = [v[0] for v in cursor.fetchall() if v[0] != 'sqlite_sequence']
        if 'tbl_srs' not in tables:
            info = ['{} misses "tbl_srs"'.format(QgsApplication.qgisSettingsDirPath())]
            info.append(
                'Settings directory might be outdated: {}'.format(QgsApplication.instance().qgisSettingsDirPath()))
            print('\n'.join(info), file=sys.stderr)

    if not isinstance(qgis.utils.iface, QgisInterface):
        iface = QgisMockup()
        qgis.utils.initInterface(sip.unwrapinstance(iface))
        assert iface == qgis.utils.iface

    # set 'home_plugin_path', which is required from the QGIS Plugin manager
    qgis.utils.home_plugin_path = (pathlib.Path(QgsApplication.instance().qgisSettingsDirPath())
                                   / 'python' / 'plugins').as_posix()

    # initialize the QGIS processing framework
    if StartOptions.ProcessingFramework in options:

        pfProviderIds = [p.id() for p in QgsApplication.processingRegistry().providers()]
        if not 'native' in pfProviderIds:
            from qgis.analysis import QgsNativeAlgorithms
            QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

        qgisCorePythonPluginDir = pathlib.Path(QgsApplication.pkgDataPath()) \
                                  / 'python' / 'plugins'
        assert os.path.isdir(qgisCorePythonPluginDir)
        if not qgisCorePythonPluginDir in sys.path:
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
    A "fake" QGIS Desktop instance that should provide all the interfaces a plugin developer might need (and nothing more)
    """

    def __init__(self, *args):
        super(QgisMockup, self).__init__()

        self.mCanvas = QgsMapCanvas()
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mRootNode = QgsLayerTree()
        self.mLayerTreeRegistryBridge = QgsLayerTreeRegistryBridge(self.mRootNode, QgsProject.instance())
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
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
        l = QHBoxLayout()
        l.addWidget(self.mLayerTreeView)
        l.addWidget(self.mCanvas)
        v = QVBoxLayout()
        v.addWidget(self.mMessageBar)
        v.addLayout(l)
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
                except:
                    setattr(self, n, getattr(self._mock, n))

    def addLegendLayers(self, mapLayers: typing.List[QgsMapLayer]):
        for l in mapLayers:
            self.mRootNode.addLayer(l)

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
        """
        # todo: implement
        pasteVectorLayer.beginEditCommand('Features pasted')
        features = self.mClipBoard.transformedCopyOf(pasteVectorLayer.crs(), pasteVectorLayer.fields())
        nTotalFeatures = features.count()
        context = pasteVectorLayer.createExpressionContext()
        compatibleFeatures = QgsVectorLayerUtils.makeFeatureCompatible(features, pasteVectorLayer)
        """

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

        l = QgsVectorLayer(path, basename, providerkey)
        assert l.isValid()
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()

    def legendInterface(self):
        return None

    def layerTreeCanvasBridge(self) -> QgsLayerTreeMapCanvasBridge:
        return self.mLayerTreeMapCanvasBridge

    def layerTreeView(self) -> QgsLayerTreeView:
        return self.mLayerTreeView

    def addRasterLayer(self, path, baseName: str = '') -> QgsRasterLayer:
        l = QgsRasterLayer(path, os.path.basename(path))
        self.lyrs.append(l)
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        return l

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


class TestCase(qgis.testing.TestCase):

    @classmethod
    def setUpClass(cls, cleanup: bool = True, options=StartOptions.All, resources: list = None) -> None:

        if resources is None:
            resources = []
        # try to find QGIS resource files
        for r in findQGISResourceFiles():
            if r not in resources:
                resources.append(r)

        cls.app = start_app(cleanup=cleanup, options=options, resources=resources)

        from osgeo import gdal
        gdal.AllRegister()

    @classmethod
    def tearDownClass(cls):
        if False and isinstance(QgsApplication.instance(), QgsApplication):
            QgsApplication.exitQgis()
            QApplication.quit()
            import gc
            gc.collect()

    # @unittest.skip("deprectated method")
    # def testOutputDirectory(self, *args, **kwds):
    #    warnings.warn('Use createTestOutputDirectory(...) instead', DeprecationWarning)
    #    self.createTestOutputDirectory(*args, **kwds)

    def createTestOutputDirectory(self, name: str = 'test-outputs') -> pathlib.Path:
        """
        Returns the path to a test output directory
        :return:
        """
        repo = findUpwardPath(__file__, '.git').parent

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

    def setUp(self):
        print('\nSET UP {}'.format(self.id()))

    def tearDown(self):

        print('TEAR DOWN {}'.format(self.id()))

    def showGui(self, widgets: typing.Union[QWidget, typing.List[QWidget]] = None) -> bool:
        """
        Call this to show GUI(s) in case we do not run within a CI system
        """
        if str(os.environ.get('CI')).lower() not in ['', 'none', 'false', '0']:
            return False
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


class TestAlgorithmProvider(QgsProcessingProvider):
    NAME = 'TestAlgorithmProvider'

    def __init__(self):
        super().__init__()
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

    def __init__(self, n_bands_per_field: typing.Union[int, typing.List[int]]):
        if not isinstance(n_bands_per_field, list):
            n_bands_per_field = [n_bands_per_field]

        self.coredata, self.wl, self.wlu, self.gt, self.wkt = TestObjects.coreData()
        self.cnb, self.cnl, self.cns = self.coredata.shape
        n_bands_per_field = [self.cnb if nb == -1 else nb for nb in n_bands_per_field]
        for nb in n_bands_per_field:
            assert 0 < nb
            #assert 0 < nb <= self.cnb, f'Max. number of bands can be {self.cnb}'
        self.band_indices: typing.List[np.ndarray] = []
        for nb in n_bands_per_field:
            idx: np.ndarray = None
            if nb <= self.cnb:
                idx = np.linspace(0, self.cnb - 1, num=nb, dtype=np.int16)
            else:
                # get nb bands positions along wavelength
                idx = np.linspace(self.wl[0], self.wl[-1], num=nb, dtype=float)

            self.band_indices.append(idx)

    def __iter__(self):
        return self

    def __next__(self):

        x = random.randint(0, self.coredata.shape[2] - 1)
        y = random.randint(0, self.coredata.shape[1] - 1)

        results = []
        for band_indices in self.band_indices:
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
        return results


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

        return TestObjects._coreData, TestObjects._coreDataWL, TestObjects._coreDataWLU, \
               TestObjects._coreDataGT, TestObjects._coreDataWkt

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
                         profile_fields: typing.List[typing.Union[int, str, QgsField]] = None):

        if fields is None:
            fields = createStandardFields()
        from .speclib.core.spectrallibrary import SpectralProfile

        if profile_fields is None:
            profile_fields = [f for f in fields if f.type() == QVariant.ByteArray]
        if n_bands is None:
            n_bands = [-1 for f in profile_fields]
        elif isinstance(n_bands, int):
            n_bands = [n_bands]

        assert len(n_bands) == len(profile_fields)

        profileGenerator = SpectralProfileDataIterator(n_bands)
        for i in range(n):
            field_data = profileGenerator.__next__()
            profile = SpectralProfile(fields=fields)
            profile.setId(i + 1)
            for j, field in enumerate(profile_fields):
                (data, wl, data_wlu) = field_data[j]
                if wlu is None:
                    wlu = data_wlu
                elif wlu == '-':
                    wl = wlu = None
                elif wlu != data_wlu:
                    wl = UnitLookup.convertMetricUnit(wl, data_wlu, wlu)

                profile.setValues(profile_field=field, y=data, x=wl, xUnit=wlu)
            yield profile

    """
    Class with static routines to create test objects
    """

    @staticmethod
    def createSpectralLibrary(n: int = 10,
                              n_empty: int = 0,
                              n_bands: typing.Union[int, typing.List[int], np.ndarray] = [-1],
                              profile_field_names: typing.List[str] = None,
                              wlu: str = None) -> 'SpectralLibrary':
        """
        Creates an Spectral Library
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
        assert n > 0
        assert 0 <= n_empty <= n
        from .speclib.core.spectrallibrary import SpectralLibrary, FIELD_VALUES
        from .speclib.core import profile_field_indices

        if isinstance(n_bands, int):
            n_bands = np.asarray([[n_bands, ]])
        elif isinstance(n_bands, list):
            n_bands = np.asarray(n_bands)
            if n_bands.ndim == 1:
                n_bands = n_bands.reshape((1, n_bands.shape[0]))

        assert isinstance(n_bands, np.ndarray)
        assert n_bands.ndim == 2
        slib: SpectralLibrary = SpectralLibrary()
        assert slib.startEditing()
        n_profile_columns = n_bands.shape[1]
        for i in range(len(slib.spectralProfileFields()), n_profile_columns):
            slib.addSpectralProfileField(f'{FIELD_VALUES}{i}')

        if isinstance(profile_field_names, list):
            profile_field_idx = profile_field_indices(slib)
            for i in range(min(len(profile_field_idx), n_profile_columns)):
                slib.renameAttribute(profile_field_idx[i], profile_field_names[i])

        slib.commitChanges(stopEditing=False)

        profile_field_indices = profile_field_indices(slib)

        for j in range(n_bands.shape[0]):

            profiles = list(TestObjects.spectralProfiles(n,
                                                         fields=slib.fields(),
                                                         n_bands=n_bands[j, :].tolist(),
                                                         wlu=wlu,
                                                         profile_fields=profile_field_indices))

            slib.addProfiles(profiles, addMissingFields=False)

        for i in range(n_empty):
            p = slib[i]
            p.setValues([], [])
            assert slib.updateFeature(p)

        assert slib.commitChanges()
        return slib

    @staticmethod
    def inMemoryImage(*args, **kwds):

        warnings.warn(''.join(traceback.format_stack()) + '\nUse createRasterDataset instead')
        return TestObjects.createRasterDataset(*args, **kwds)

    @staticmethod
    def createRasterDataset(ns=10, nl=20, nb=1,
                            crs=None, gt=None,
                            eType: int = gdal.GDT_Int16,
                            nc: int = 0,
                            path: typing.Union[str, pathlib.Path] = None,
                            drv: typing.Union[str, gdal.Driver] = None,
                            wlu: str = None,
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
        if no_data_rectangle > 0:
            no_data_rectangle = min([no_data_rectangle, ns])
            no_data_rectangle = min([no_data_rectangle, nl])
            for b in range(ds.RasterCount):
                band: gdal.Band = ds.GetRasterBand(b + 1)
                band.SetNoDataValue(no_data_value)

        coredata, core_wl, core_wlu, core_gt, core_wkt = TestObjects.coreData()

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
    def createProcessingProvider() -> typing.Optional['TestAlgorithmProvider']:
        """
        Returns an
        :return:
        """
        procReg = QgsApplication.instance().processingRegistry()
        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        provider_names = [p.name() for p in procReg.providers()]
        if TestAlgorithmProvider.NAME not in provider_names:
            procGuiReg.addParameterWidgetFactory(SpectralProcessingAlgorithmInputWidgetFactory())
            procGuiReg.addParameterWidgetFactory(SpectralProcessingProfilesOutputWidgetFactory())
            assert procReg.addParameterType(SpectralProcessingProfileType())
            provider = TestAlgorithmProvider()
            assert procReg.addProvider(provider)
            TestObjects.TEST_PROVIDER = provider
        for p in procReg.providers():
            if p.name() == TestAlgorithmProvider.NAME:
                return p
        return None

    @staticmethod
    def createSpectralProcessingAlgorithm() -> QgsProcessingAlgorithm:

        alg = SpectralPythonCodeProcessingAlgorithm()
        provider = TestObjects.createProcessingProvider()
        if not isinstance(provider.algorithm(alg.name()), SpectralPythonCodeProcessingAlgorithm):
            provider.addAlgorithm(alg)

        assert isinstance(provider.algorithm(alg.name()), SpectralPythonCodeProcessingAlgorithm)

        return provider.algorithm(alg.name())

    @staticmethod
    def createSpectralProcessingModel(name: str = 'Example Model') -> QgsProcessingModelAlgorithm:

        configuration = {}
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        model = QgsProcessingModelAlgorithm()
        model.setName(name)

        def createChildAlgorithm(algorithm_id: str, description='') -> QgsProcessingModelChildAlgorithm:
            alg = QgsProcessingModelChildAlgorithm(algorithm_id)
            alg.generateChildId(model)
            alg.setDescription(description)
            return alg

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg = TestObjects.createSpectralProcessingAlgorithm()

        # self.testProvider().addAlgorithm(alg)
        # self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralProcessingAlgorithmExample)
        # create child algorithms, i.e. instances of QgsProcessingAlgorithms
        cid: str = model.addChildAlgorithm(createChildAlgorithm(alg.id(), 'Process Step 1'))

        # set model input / output
        pname_src_profiles = 'input_profiles'
        pname_dst_profiles = 'processed_profiles'
        model.addModelParameter(SpectralProcessingProfiles(pname_src_profiles, description='Source profiles'),
                                QgsProcessingModelParameter(pname_src_profiles))

        # connect child inputs and outputs
        calg = model.childAlgorithm(cid)
        calg.addParameterSources(
            alg.INPUT,
            [QgsProcessingModelChildParameterSource.fromModelParameter(pname_src_profiles)])

        code = "profiledata=profiledata*1.25"
        calg.addParameterSources(
            alg.CODE,
            [QgsProcessingModelChildParameterSource.fromStaticValue(code)]
        )

        # allow to write the processing alg outputs as new SpectralLibraries
        model.addOutput(SpectralProcessingProfilesOutput(pname_dst_profiles))
        childOutput = QgsProcessingModelOutput(pname_dst_profiles)
        childOutput.setChildOutputName(alg.OUTPUT)
        childOutput.setChildId(calg.childId())
        calg.setModelOutputs({pname_dst_profiles: childOutput})

        model.initAlgorithm(configuration)

        # set the positions for parameters and algorithms in the model canvas:
        x = 150
        y = 50
        dx = 100
        dy = 75
        components = model.parameterComponents()
        for n, p in components.items():
            p.setPosition(QPointF(x, y))
            x += dx
        model.setParameterComponents(components)

        y = 150
        x = 250
        for calg in [calg]:
            calg: QgsProcessingModelChildAlgorithm
            calg.setPosition(QPointF(x, y))
            y += dy

        return model

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
        pathSrc = TEST_VECTOR_KML
        assert pathSrc.is_file(), 'Unable to find {}'.format(pathSrc)

        dsSrc = ogr.Open(pathSrc.as_posix())
        assert isinstance(dsSrc, ogr.DataSource)
        lyrSrc = dsSrc.GetLayerByName('landcover')
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

    def replaceWithCopyOf(self, src):
        if isinstance(src, QgsVectorLayer):
            self.mFeatureFields = src.fields()
            self.mFeatureClipboard = src.selectedFeatures()
            self.mCRS = src.crs()
            self.mSrcLayer = src

            """
                        self.setSystemClipBoard()
                        self.mUseSystemClipboard = False
                        self.changed.emit()
            """
            return


        elif isinstance(src, QgsFeatureStore):
            raise NotImplementedError()

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
