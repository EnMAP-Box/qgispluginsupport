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
import gc
import inspect
import itertools
import os
import pathlib
import random
import shutil
import sys
import traceback
import uuid
import warnings
from time import sleep
from typing import List, Set, Tuple, Union
from unittest import mock

import numpy as np
from osgeo import gdal, gdal_array, ogr, osr

import qgis.utils
from qgis.core import edit, Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, \
    QgsFeatureStore, QgsField, QgsFields, QgsGeometry, QgsLayerTree, QgsLayerTreeLayer, QgsLayerTreeModel, \
    QgsLayerTreeRegistryBridge, QgsMapLayer, QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingFeedback, \
    QgsProcessingModelAlgorithm, QgsProcessingParameterNumber, QgsProcessingParameterRasterDestination, \
    QgsProcessingParameterRasterLayer, QgsProcessingProvider, QgsProcessingRegistry, QgsProject, QgsPythonRunner, \
    QgsRasterLayer, QgsTemporalController, QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes
from qgis.gui import QgisInterface, QgsAbstractMapToolHandler, QgsBrowserGuiModel, QgsGui, QgsLayerTreeMapCanvasBridge, \
    QgsLayerTreeView, QgsMapCanvas, QgsMapLayerConfigWidgetFactory, QgsMapTool, QgsMessageBar, QgsPluginManagerInterface
from qgis.PyQt import sip
from qgis.PyQt.QtCore import pyqtSignal, QMimeData, QObject, QPoint, QPointF, QSize, Qt
from qgis.PyQt.QtGui import QDropEvent, QIcon, QImage
from qgis.PyQt.QtWidgets import QAction, QApplication, QDockWidget, QFrame, QHBoxLayout, QMainWindow, QMenu, QToolBar, \
    QVBoxLayout, QWidget
from .qgisenums import QGIS_WKBTYPE
from .resources import initResourceFile
from .utils import findUpwardPath, px2geo, SpatialPoint

TEST_VECTOR_GEOJSON = pathlib.Path(__file__).parent / 'testvectordata.4326.geojson'

_QGIS_MOCKUP = None
_PYTHON_RUNNER = None


def start_app(cleanup: bool = True,
              init_processing: bool = True,
              init_python_runner: bool = True,
              init_editor_widgets: bool = True,
              init_iface: bool = True,
              resources: List[Union[str, pathlib.Path]] = []) -> QgsApplication:
    app = qgis.testing.start_app(cleanup)

    from qgis.core import QgsCoordinateReferenceSystem
    assert QgsCoordinateReferenceSystem('EPSG:4326').isValid()

    providers = QgsApplication.processingRegistry().providers()
    global _PYTHON_RUNNER
    global _QGIS_MOCKUP

    if init_iface:
        get_iface()

    if init_processing and len(providers) == 0:
        from processing.core.Processing import Processing

        Processing.initialize()

    if init_python_runner and not QgsPythonRunner.isValid():
        _PYTHON_RUNNER = QgsPythonRunnerMockup()
        QgsPythonRunner.setInstance(_PYTHON_RUNNER)

    # init standard EditorWidgets
    if init_editor_widgets and len(QgsGui.editorWidgetRegistry().factories()) == 0:
        QgsGui.editorWidgetRegistry().initEditors()

    for path in resources:
        initResourceFile(path)

    crs1 = QgsCoordinateReferenceSystem('EPSG:4326')
    assert crs1.isValid(), 'Failed to initialize QGIS SRS database'
    crs2 = QgsCoordinateReferenceSystem.fromWkt(crs1.toWkt())
    assert crs2.isValid(), ('Failed to initialize QGIS SRS database. '
                            'Is a QgsCoordinateSystem instance created before a '
                            'QgsApplication.instance() is created, e.g. using `qgis.testing.start_app()`.')

    return app


css = """
QGroupBox{ font-weight: 600; }
QListWidget#mOptionsListWidget { background-color: rgba(69, 69, 69, 0); outline: 0;}
QFrame#mOptionsListFrame { background-color: rgba(69, 69, 69, 220);}
QListWidget#mOptionsListWidget::item { color: white; padding: 3px;}
QListWidget#mOptionsListWidget::item::selected { color: palette(window-text); background-color:palette(window); padding-right: 0px;}
QTreeView#mOptionsTreeView { background-color: rgba(69, 69, 69, 0); outline: 0;}
QFrame#mOptionsListFrame { background-color: rgba(69, 69, 69, 220);}
QTreeView#mOptionsTreeView::item { color: white; padding: 3px;}
QTreeView#mOptionsTreeView::item::selected, QTreeView#mOptionsTreeView::branch::selected { color: palette(window-text); background-color:palette(window); padding-right: 0px;}
QTableView { selection-background-color: #0078d7; selection-color: #ffffff;}
QgsPropertyOverrideButton { background: none; border: 1px solid rgba(0, 0, 0, 0%); }
QgsPropertyOverrideButton:focus { border: 1px solid palette(highlight); }'
"""


class QgisMockup(QgisInterface):
    """
    A "fake" QGIS Desktop instance that should provide all the interfaces a
    plugin developer might need (and nothing more)
    """

    def __init__(self, *args):
        super(QgisMockup, self).__init__()

        self.mActionSaveProject = QAction('Save Project')
        self.mActionSaveProject.triggered.connect(self._onSaveProject)
        self.mMapLayerPanelFactories: List[QgsMapLayerConfigWidgetFactory] = []

        self.mTemporalController = QgsTemporalController()
        self.mCanvas = QgsMapCanvas()
        self.mCanvas.setTemporalController(self.mTemporalController)
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mLayerTreeView.currentLayerChanged.connect(self.activateDeactivateLayerRelatedActions)
        self.mMapToolHandler: List[QgsAbstractMapToolHandler] = []

        self.mRootNode = QgsLayerTree()
        self.mLayerTreeRegistryBridge = QgsLayerTreeRegistryBridge(self.mRootNode, QgsProject.instance())
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
        self.mLayerTreeModel.setFlag(QgsLayerTreeModel.Flag.AllowNodeReorder, True)
        self.mLayerTreeModel.setFlag(QgsLayerTreeModel.Flag.AllowNodeRename, True)
        self.mLayerTreeModel.setFlag(QgsLayerTreeModel.Flag.AllowNodeChangeVisibility, True)

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

        self.mSelectionToolBar = QToolBar()
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
        self.ui.setStyleSheet(css)
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
        to_remove: List[QgsLayerTreeLayer] = []
        for lyr in self.mRootNode.findLayers():
            lyr: QgsLayerTreeLayer
            if lyr.layerId() in layerIDs:
                to_remove.append(lyr)
        for lyr in reversed(to_remove):
            lyr.parent().removeChildNode(lyr)

    def _onSaveProject(self):

        p = QgsProject.instance()
        p.write()

    def actionSaveProject(self) -> QAction:
        return self.mActionSaveProject

    def activeLayer(self) -> QgsMapLayer:
        return self.mLayerTreeView.currentLayer()

    def registerMapToolHandler(self, handler: QgsAbstractMapToolHandler) -> None:

        assert isinstance(handler, QgsAbstractMapToolHandler)
        assert isinstance(handler.action(), QAction) and \
               isinstance(handler.mapTool(), QgsMapTool), 'Map tool handler is not properly constructed'

        self.mMapToolHandler.append(handler)
        handler.action().setCheckable(True)
        handler.mapTool().setAction(handler.action())
        handler.action().triggered.connect(self.switchToMapToolViaHandler)
        context = QgsAbstractMapToolHandler.Context()
        handler.action().setEnabled(handler.isCompatibleWithLayer(self.activeLayer(), context))

    def unregisterMapToolHandler(self, handler: QgsAbstractMapToolHandler) -> None:
        assert isinstance(handler, QgsAbstractMapToolHandler)
        if handler in self.mMapToolHandler:
            self.mMapToolHandler.remove(handler)
            if isinstance(handler.action(), QAction):
                handler.action().triggered.disconnect(self.switchToMapToolViaHandler)

    def switchToMapToolViaHandler(self):
        action: QAction = self.sender()
        if not isinstance(action, QAction):
            return

        for h in self.mMapToolHandler:
            h: QgsAbstractMapToolHandler
            if h.action() == action and self.mapCanvas().mapTool() != h.mapTool():
                h.setLayerForTool(self.activeLayer())
                self.mapCanvas().setMapTool(h.mapTool())
                return

    def activateDeactivateLayerRelatedActions(self, layer: QgsMapLayer):

        context = QgsAbstractMapToolHandler.Context()
        for h in self.mMapToolHandler:
            h: QgsAbstractMapToolHandler
            h.action().setEnabled(h.isCompatibleWithLayer(layer, context))
            if h.mapTool() == self.mapCanvas().mapTool():
                if not h.action().isEnabled():
                    self.mapCanvas().unsetMapTool(h.mapTool())
                    # self.mMapToolPan.trigger()
                else:
                    h.setLayerForTool(layer)

    def registerMapLayerConfigWidgetFactory(self, factory: QgsMapLayerConfigWidgetFactory):
        assert isinstance(factory, QgsMapLayerConfigWidgetFactory)

        self.mMapLayerPanelFactories.append(factory)

    def unregisterMapLayerConfigWidgetFactory(self, factory: QgsMapLayerConfigWidgetFactory):
        assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
        self.mMapLayerPanelFactories = [f for f in self.mMapLayerPanelFactories if f.title() != factory.title()]

    def addLegendLayers(self, mapLayers: List[QgsMapLayer]):
        for lyr in mapLayers:
            self.mRootNode.addLayer(lyr)

    def pluginManagerInterface(self) -> QgsPluginManagerInterface:
        return self.mPluginManager

    def setActiveLayer(self, mapLayer: QgsMapLayer):
        self.mLayerTreeView.setCurrentLayer(mapLayer)

    def selectionToolBar(self) -> QToolBar:
        return self.mSelectionToolBar

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

    def addToolBar(self, name: str) -> QToolBar:
        return self.mainWindow().addToolBar(name)

    def addDockWidget(self, area: Qt.DockWidgetArea, dockwidget: QDockWidget) -> None:

        return self.mainWindow().addDockWidget(area, dockwidget)

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

    def mapCanvases(self) -> List[QgsMapCanvas]:
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


def _set_iface(ifaceMock: QgisInterface):
    """
    Replaces the iface variable in other plugins, i.e. the  QGIS processing plugin
    :param ifaceMock: QgisInterface
    """

    # enhance this list with further positions where iface needs to be replaced or remains None otherwise
    import processing.ProcessingPlugin
    import processing.tools.general
    modules = [processing.ProcessingPlugin,
               processing.tools.general,
               processing]

    for m in modules:
        m.iface = ifaceMock

    s = ""


# APP = None


if Qgis.versionInt() >= 33400:
    from qgis.testing import QgisTestCase as _BASECLASS
else:
    from qgis.testing import TestCase as _BASECLASS


class TestCaseBase(_BASECLASS):
    gdal.UseExceptions()

    @staticmethod
    def check_empty_layerstore(name: str):
        error = None
        if len(QgsProject.instance().mapLayers()) > 0:
            error = f'QgsProject layers store is not empty:\n{name}:'
            for lyr in QgsProject.instance().mapLayers().values():
                error += f'\n\t{lyr.id()}: "{lyr.name()}"'
            raise AssertionError(error)

    def setUp(self):
        self.check_empty_layerstore(f'{self.__class__.__name__}::{self._testMethodName}')

    def tearDown(self):
        self.check_empty_layerstore(f'{self.__class__.__name__}::{self._testMethodName}')
        # call gc and processEvents to fail fast
        gc.collect()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.processEvents()
        gc.collect()

    @classmethod
    def setUpClass(cls):
        cls.check_empty_layerstore(cls.__class__)

    @classmethod
    def tearDownClass(cls):
        cls.check_empty_layerstore(cls.__class__)

    @classmethod
    def showGui(cls, widgets: Union[QWidget, List[QWidget]] = None) -> bool:
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

        if cls.runsInCI():
            return False

        app = QApplication.instance()
        if isinstance(app, QApplication) and keepOpen:
            app.exec_()

        return True

    @staticmethod
    def runsInCI() -> True:
        """
        Returns True if this the environment is supposed to run in a CI environment
        and should not open blocking dialogs
        """
        r = str(os.environ.get('CI', '')).lower() not in ['', 'none', 'false', '0']

        if Qgis.versionInt() >= 33400:
            from qgis.testing import QgisTestCase
            r = r or QgisTestCase.is_ci_run()
        return r

    @classmethod
    def createProcessingContextFeedback(cls) -> Tuple[QgsProcessingContext, QgsProcessingFeedback]:
        """
        Create a QgsProcessingContext with connected QgsProcessingFeedback
        """

        def onProgress(progress: float):
            sys.stdout.write('\r{:0.2f} %'.format(progress))
            sys.stdout.flush()

            if progress == 100:
                print('')

        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(onProgress)

        context = QgsProcessingContext()
        context.setFeedback(feedback)

        return context, feedback

    @classmethod
    def createProcessingFeedback(cls) -> QgsProcessingFeedback:
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
        path = pathlib.Path(path)
        assert path.is_file()

        ds: gdal.Dataset = gdal.Open(path.as_posix())
        assert isinstance(ds, gdal.Dataset)
        drv: gdal.Driver = ds.GetDriver()

        testdir = self.createTestOutputDirectory() / 'images'
        os.makedirs(testdir, exist_ok=True)
        bn, ext = os.path.splitext(os.path.basename(path))

        newpath = testdir / f'{bn}{ext}'
        i = 0
        if newpath.is_file():
            deleted = False
            if overwrite_existing:
                ds2: gdal.Dataset = gdal.Open(newpath.as_posix())
                path2 = ds2.GetFileList()[0]
                drv2: gdal.Driver = ds2.GetDriver()
                del ds2
                n_tries = 5
                while not deleted and n_tries > 5:
                    try:
                        drv2.Delete(path2)
                        deleted = True
                    except RuntimeError as ex:
                        sleep(1)
                        n_tries -= 1

            if not deleted:
                while newpath.is_file():
                    i += 1
                    newpath = testdir / f'{bn}{i}{ext}'

        drv.CopyFiles(newpath.as_posix(), path.as_posix())

        return newpath.as_posix()

    def createTestOutputDirectory(self,
                                  name: str = 'test-outputs',
                                  subdir: str = None) -> pathlib.Path:
        """
        Returns the path to a test output directory
        :return:
        """
        if name is None:
            name = 'test-outputs'
        repo = findUpwardPath(inspect.getfile(self.__class__), '.git').parent

        if subdir is None:
            subdir = f'{self.__module__}.{self.__class__.__name__}'

        testDir = repo / name / subdir

        os.makedirs(testDir, exist_ok=True)

        return testDir

    def createTestCaseDirectory(self,
                                basename: str = None,
                                testclass: bool = True,
                                testmethod: bool = True
                                ):

        d = self.createTestOutputDirectory(name=basename)
        if testclass:
            d = d / self.__class__.__name__
        if testmethod:
            d = d / self._testMethodName

        os.makedirs(d, exist_ok=True)
        return d

    @classmethod
    def assertImagesEqual(cls, image1: QImage, image2: QImage):
        if image1.size() != image2.size():
            return False
        if image1.format() != image2.format():
            return False

        for x in range(image1.width()):
            for y in range(image1.height()):
                if image1.pixel(x, y) != image2.pixel(x, y):
                    return False
        return True

    def tempDir(self, subdir: str = None, cleanup: bool = False) -> pathlib.Path:
        """
        Returns the <enmapbox-repository/test-outputs/test name> directory
        :param subdir:
        :param cleanup:
        :return: pathlib.Path
        """
        DIR_REPO = findUpwardPath(__file__, '.git').parent
        if isinstance(self, TestCaseBase):
            foldername = self.__class__.__name__
        else:
            foldername = self.__name__
        p = pathlib.Path(DIR_REPO) / 'test-outputs' / foldername
        if isinstance(subdir, str):
            p = p / subdir
        if cleanup and p.exists() and p.is_dir():
            shutil.rmtree(p)
        os.makedirs(p, exist_ok=True)
        return p

    @classmethod
    def _readVSIMemFiles(cls) -> Set[str]:

        r = gdal.ReadDirRecursive('/vsimem/')
        if r is None:
            return set([])
        return set(r)


class TestCase(TestCaseBase):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def setUpClass(cls, *args, **kwargs) -> None:
        resources = kwargs.pop('resources', [])

        super().setUpClass(*args, **kwargs)
        from . import QPS_RESOURCE_FILE
        resources.append(QPS_RESOURCE_FILE)
        start_app(cleanup=kwargs.get('cleanup'), resources=resources)

    def assertIconsEqual(self, icon1: QIcon, icon2: QIcon):
        self.assertIsInstance(icon1, QIcon)
        self.assertIsInstance(icon2, QIcon)
        size = QSize(256, 256)
        self.assertEqual(icon1.actualSize(size), icon2.actualSize(size))

        img1 = QImage(icon1.pixmap(size))
        img2 = QImage(icon2.pixmap(size))
        self.assertImagesEqual(img1, img2)


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

    def addAlgorithm(self, algorithm):
        result = super().addAlgorithm(algorithm)
        if result:
            # keep reference
            self._algs.append(algorithm)
        return result


class SpectralProfileDataIterator(object):

    def __init__(self,
                 n_bands_per_field: Union[int, List[int]],
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
        self.band_indices: List[np.ndarray] = []
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
    def coreData() -> Tuple[np.ndarray, np.ndarray, str, tuple, str]:
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

        results = TestObjects._coreData, \
            TestObjects._coreDataWL, \
            TestObjects._coreDataWLU, \
            TestObjects._coreDataGT, \
            TestObjects._coreDataWkt
        return results

    @staticmethod
    def createDropEvent(mimeData: QMimeData) -> QDropEvent:
        """Creates a QDropEvent containing the provided QMimeData ``mimeData``"""
        return QDropEvent(QPointF(0, 0), Qt.CopyAction, mimeData, Qt.LeftButton, Qt.NoModifier)

    @staticmethod
    def spectralProfileData(n: int = 10,
                            n_bands: List[int] = None):
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
                         n_bands: List[int] = None,
                         wlu: str = None,
                         profile_fields: List[Union[str, QgsField]] = None,
                         crs: QgsCoordinateReferenceSystem = None):

        from .speclib import createStandardFields
        from .speclib.core import create_profile_field, is_profile_field
        from .speclib.core.spectralprofile import prepareProfileValueDict, encodeProfileValueDict
        from .speclib.core import profile_fields as pFields
        from .unitmodel import UnitLookup

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
            f'Number of bands list ({n_bands}) has different lengths that number of profile fields'

        profileGenerator: SpectralProfileDataIterator = SpectralProfileDataIterator(n_bands, target_crs=crs)

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
                        wl = UnitLookup.convertLengthUnit(wl, data_wlu, wlu)

                    profileDict = prepareProfileValueDict(y=data, x=wl, xUnit=wlu)
                    value = encodeProfileValueDict(profileDict, profile_field)
                    profile.setAttribute(profile_field.name(), value)

            yield profile

    @staticmethod
    def createSpectralLibrary(n: int = 10,
                              n_empty: int = 0,
                              n_bands: Union[int, List[int], np.ndarray] = [-1],
                              profile_field_names: List[str] = None,
                              wlu: str = None,
                              crs: QgsCoordinateReferenceSystem = None) -> QgsVectorLayer:
        """
        Creates a Spectral Library
        :param crs:
        :param profile_field_names:
        :param n_bands:
        :type n_bands:
        :param wlu:
        :type wlu:
        :param n: total number of profiles
        :type n: int
        :param n_empty: number of empty profiles, SpectralProfiles with empty x/y values
        :type n_empty: int
        :return: QgsVectorLayer
        :rtype: QgsVectorLayer
        """
        from .speclib.core.spectrallibrary import SpectralLibraryUtils
        from .speclib.core import profile_field_indices
        from .speclib import FIELD_VALUES

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

        slib: QgsVectorLayer = SpectralLibraryUtils.createSpectralLibrary(profile_fields=profile_field_names, crs=crs)
        with edit(slib):

            pfield_indices = profile_field_indices(slib)

            assert len(pfield_indices) == len(profile_field_names)

            if n > 0:
                # slib.beginEditCommand(f'Add {n} features')
                # and random profiles
                for groupIndex in range(n_bands.shape[0]):
                    bandsPerField = n_bands[groupIndex].tolist()
                    profiles = list(TestObjects.spectralProfiles(n,
                                                                 fields=slib.fields(),
                                                                 n_bands=bandsPerField,
                                                                 wlu=wlu,
                                                                 profile_fields=pfield_indices,
                                                                 crs=crs))

                    SpectralLibraryUtils.addProfiles(slib, profiles, addMissingFields=False)

                # delete empty profiles
                for i, feature in enumerate(slib.getFeatures()):
                    if i >= n_empty:
                        break
                    for field in profile_field_names:
                        feature.setAttribute(field, None)
                    slib.updateFeature(feature)
                # slib.endEditCommand()
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
    def repoDirGDAL(local='gdal') -> pathlib.Path:
        """
        Returns the path to a local GDAL repository.
        GDAL must be installed into the same path / upward path of this repository
        """
        d = findUpwardPath(__file__, local + '/.git', is_directory=True)
        if d:
            return d.parent
        else:
            return None

    @staticmethod
    def repoDirQGIS(local='QGIS') -> pathlib.Path:
        """
        Returns the path to a local QGIS repository.
        QGIS must be installed into the same path / upward path of this repository
        """
        d = findUpwardPath(__file__, local + '/.git', is_directory=True)
        if d:
            return d.parent
        else:
            return None

    @staticmethod
    def tmpDirPrefix() -> str:
        if True:
            path_dir = pathlib.Path('/vsimem/tmp')
        else:
            path_dir = findUpwardPath(__file__, '.git').parent / 'test-outputs' / 'vsimem' / 'tmp'
            os.makedirs(path_dir, exist_ok=True)

        return path_dir.as_posix() + '/'

    @staticmethod
    def createRasterDataset(ns=10, nl=20, nb=1,
                            crs=None, gt=None,
                            eType: int = gdal.GDT_Int16,
                            nc: int = 0,
                            path: Union[str, pathlib.Path] = None,
                            drv: Union[str, gdal.Driver] = None,
                            wlu: str = None,
                            pixel_size: float = None,
                            no_data_rectangle: int = 0,
                            no_data_value: Union[int, float] = -9999) -> gdal.Dataset:
        """
        Generates a gdal.Dataset of arbitrary size based on true data from a smaller EnMAP raster image
        """
        # gdal.AllRegister()
        from .classification.classificationscheme import ClassificationScheme
        scheme = None
        if nc is None:
            nc = 0

        if nc > 0:
            eType = gdal.GDT_Byte if nc < 256 else gdal.GDT_Int16
            scheme = ClassificationScheme()
            scheme.createClasses(nc)
        if gdal.GetDriverCount() == 0:
            gdal.AllRegister()

        if isinstance(drv, str):
            drv = gdal.GetDriverByName(drv)
        elif drv is None:
            drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver), 'Unable to load GDAL Driver'

        if isinstance(path, pathlib.Path):
            path = path.as_posix()
        elif path is None:
            ext = drv.GetMetadataItem('DMD_EXTENSION')
            prefix = TestObjects.tmpDirPrefix()
            if len(ext) > 0:
                ext = f'.{ext}'
            if nc > 0:
                path = f'{prefix}testClassification.{uuid.uuid4()}{ext}'
            else:
                path = f'{prefix}testImage.{uuid.uuid4()}{ext}'
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
                from .unitmodel import UnitLookup
                wl = UnitLookup.convertLengthUnit(wl, core_wlu, wlu)

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
    def createVectorDataSet(wkb=ogr.wkbPolygon,
                            n_features: int = None,
                            path: Union[str, pathlib.Path] = None) -> ogr.DataSource:
        """
        Create an in-memory ogr.DataSource
        :return: ogr.DataSource
        """
        # ogr.RegisterAll()
        # ogr.UseExceptions()
        assert wkb in [ogr.wkbPoint, ogr.wkbPolygon, ogr.wkbLineString]

        # find the QGIS world_map.shp
        # pkgPath = QgsApplication.instance().pkgDataPath()
        # assert os.path.isdir(pkgPath)

        # pathSrc = pathlib.Path(__file__).parent / 'landcover_polygons.geojson'
        pathSrc = TEST_VECTOR_GEOJSON
        assert pathSrc.is_file(), 'Unable to find {}'.format(pathSrc)

        dsSrc: ogr.DataSource = ogr.Open(pathSrc.as_posix())
        if not isinstance(dsSrc, gdal.Dataset):
            lyr = QgsVectorLayer(pathSrc.as_posix())
            assert lyr.isValid(), f'Unable to load QGS Layer: {pathSrc.as_posix()}'
        assert isinstance(dsSrc, ogr.DataSource), f'Unable to load {pathSrc}'
        lyrSrc: ogr.Layer = dsSrc.GetLayerByIndex(0)
        assert isinstance(lyrSrc, ogr.Layer)

        ldef = lyrSrc.GetLayerDefn()
        assert isinstance(ldef, ogr.FeatureDefn)

        srs = lyrSrc.GetSpatialRef()
        assert isinstance(srs, osr.SpatialReference)

        drv = ogr.GetDriverByName('GPKG')
        assert isinstance(drv, ogr.Driver)

        # set temp path
        if path:
            pathDst = pathlib.Path(path).as_posix()
            lname = os.path.basename(pathDst)
        else:
            prefix = TestObjects.tmpDirPrefix() + str(uuid.uuid4())

            if wkb == ogr.wkbPolygon:
                lname = 'polygons'
                pathDst = prefix + '.test.polygons.gpkg'
            elif wkb == ogr.wkbPoint:
                lname = 'points'
                pathDst = prefix + '.test.centroids.gpkg'
            elif wkb == ogr.wkbLineString:
                lname = 'lines'
                pathDst = prefix + '.test.line.gpkg'
            else:
                raise NotImplementedError()

        dsDst: ogr.DataSource = drv.CreateDataSource(pathDst)
        assert isinstance(dsDst, ogr.DataSource)
        lyrDst = dsDst.CreateLayer(lname, srs=srs, geom_type=wkb)
        assert isinstance(lyrDst, ogr.Layer)

        if n_features is None:
            n_features = lyrSrc.GetFeatureCount()

        assert n_features >= 0

        # copy features
        TMP_FEATURES: List[ogr.Feature] = []
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
            g: ogr.Geometry = fSrc.geometry()
            fDst = ogr.Feature(lyrDst.GetLayerDefn())
            assert isinstance(fDst, ogr.Feature)

            if isinstance(g, ogr.Geometry):
                if wkb == ogr.wkbPolygon:
                    g.FlattenTo2D()
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
    def createEmptyMemoryLayer(fields: QgsFields,
                               name: str = 'memory layer',
                               crs: QgsCoordinateReferenceSystem = None,
                               wkbType: QGIS_WKBTYPE = QGIS_WKBTYPE.NoGeometry):

        """
            Class with static routines to create test objects
            """
        uri = ''
        if wkbType != QGIS_WKBTYPE.NoGeometry:
            uri += QgsWkbTypes.displayString(wkbType)
        else:
            uri += 'none'
        uri += '?'
        if isinstance(crs, QgsCoordinateReferenceSystem):
            uri += f'crs=epsg:{crs.srsid()}'
        options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)
        lyr = QgsVectorLayer(uri, name, 'memory', options=options)
        lyr.setCustomProperty('skipMemoryLayerCheck', 1)

        assert lyr.isValid()
        with edit(lyr):
            for a in fields:
                success = lyr.addAttribute(a)
                if success:
                    i = lyr.fields().lookupField(a.name())
                    if i > -1:
                        lyr.setEditorWidgetSetup(i, a.editorWidgetSetup())
        return lyr

    @staticmethod
    def createVectorLayer(wkbType: QgsWkbTypes = QgsWkbTypes.Polygon,
                          n_features: int = None,
                          path: Union[str, pathlib.Path] = None,
                          crs: QgsCoordinateReferenceSystem = None) -> QgsVectorLayer:
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
        dsSrc = TestObjects.createVectorDataSet(wkb=wkb, n_features=n_features, path=path)

        assert isinstance(dsSrc, ogr.DataSource)
        lyr = dsSrc.GetLayer(0)
        assert isinstance(lyr, ogr.Layer)
        assert lyr.GetFeatureCount() > 0
        # uri = '{}|{}'.format(dsSrc.GetName(), lyr.GetName())
        uri = dsSrc.GetName()

        vl = QgsVectorLayer(uri, 'testlayer', 'ogr', lyrOptions)
        assert isinstance(vl, QgsVectorLayer)
        assert vl.isValid()
        if not vl.crs().isValid():
            srs = lyr.GetSpatialRef()
            srs_wkt = srs.ExportToWkt()
            crs2 = QgsCoordinateReferenceSystem(srs_wkt)
            assert crs2.isValid()
            s = ""

        assert vl.crs().isValid()
        assert vl.featureCount() == lyr.GetFeatureCount()

        if isinstance(crs, QgsCoordinateReferenceSystem) and vl.crs() != crs:
            trans = QgsCoordinateTransform(vl.crs(), crs, QgsProject.instance())
            with edit(vl):
                for f in vl.getFeatures():
                    g = f.geometry()
                    assert g.transform(trans) == Qgis.GeometryOperationResult.Success
                    f.setGeometry(g)
                    vl.updateFeature(f)
            vl.setCrs(crs)

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

    def transformedCopyOf(self, crs: QgsCoordinateReferenceSystem, fields: QgsFields) -> List[QgsFeature]:

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
