import os, sys, re, io, importlib, typing, traceback
import uuid, warnings, pathlib, time, site, mock, inspect, types, enum
import sip
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
import qgis.testing
import qgis.utils
import numpy as np
from osgeo import gdal, ogr, osr, gdal_array



WMS_GMAPS = r'crs=EPSG:3857&format&type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D&zmax=19&zmin=0'
WMS_OSM = r'referer=OpenStreetMap%20contributors,%20under%20ODbL&type=xyz&url=http://tiles.wmflabs.org/hikebike/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=17&zmin=1'
WFS_Berlin = r'restrictToRequestBBOX=''1'' srsname=''EPSG:25833'' typename=''fis:re_postleit'' url=''http://fbinter.stadt-berlin.de/fb/wfs/geometry/senstadt/re_postleit'' version=''auto'''


def missingTestdata() -> bool:
    """
    Returns (True, message:str) if testdata can not be loaded,
     (False, None) else
    :return: (bool, str)
    """
    try:
        import enmapboxtestdata
        assert os.path.isfile(enmapboxtestdata.enmap)
        return False
    except Exception as ex:
        print(ex, file=sys.stderr)
        return True


def installTestdata(overwrite_existing=False):
    """
    Downloads and installs the EnMAP-Box Example Data
    """
    if not missingTestdata() and not overwrite_existing:
        print('Testdata already installed and up to date.')
        return

    btn = QMessageBox.question(None, 'Testdata is missing or outdated',
                               'Download testdata from \n{}\n?'.format(URL_TESTDATA))
    if btn != QMessageBox.Yes:
        print('Canceled')
        return

    if DIR_TESTDATA is None:
        s = ""

    pathLocalZip = os.path.join(os.path.dirname(DIR_TESTDATA), 'enmapboxtestdata.zip')
    url = QUrl(URL_TESTDATA)
    dialog = QgsFileDownloaderDialog(url, pathLocalZip, 'Download {}'.format(os.path.basename(URL_TESTDATA)))

    def onCanceled():
        print('Download canceled')
        return

    def onCompleted():
        print('Download completed')
        print('Unzip {}...'.format(pathLocalZip))

        targetDir = DIR_TESTDATA
        os.makedirs(targetDir, exist_ok=True)
        import zipfile
        zf = zipfile.ZipFile(pathLocalZip)

        names = zf.namelist()
        names = [n for n in names if re.search(r'[^/]/enmapboxtestdata/..*', n) and not n.endswith('/')]
        for name in names:
            # create directory if doesn't exist

            pathRel = re.search(r'[^/]+/enmapboxtestdata/(.*)$', name).group(1)
            subDir, baseName = os.path.split(pathRel)
            fullDir = os.path.normpath(os.path.join(targetDir, subDir))
            os.makedirs(fullDir, exist_ok=True)

            if not name.endswith('/'):
                fullPath = os.path.normpath(os.path.join(targetDir, pathRel))
                with open(fullPath, 'wb') as outfile:
                    outfile.write(zf.read(name))
                    outfile.flush()

        zf.close()
        del zf

        print('Testdata installed.')
        spec = importlib.util.spec_from_file_location('enmapboxtestdata', os.path.join(targetDir, '__init__.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules['enmapboxtestdata'] = module

    def onDownloadError(messages):
        raise Exception('\n'.join(messages))

    def deleteFileDownloadedFile():

        pass
        # dirty patch for Issue #167
        #
        # print('Remove {}...'.format(pathLocalZip))
        # os.remove(pathLocalZip)

    def onDownLoadExited():

        from qgis.PyQt.QtCore import QTimer
        QTimer.singleShot(5000, deleteFileDownloadedFile)

    def onDownloadProgress(received, total):
        print('\r{:0.2f} %'.format(100. * received / total), end=' ', flush=True)
        time.sleep(0.1)

    dialog.downloadCanceled.connect(onCanceled)
    dialog.downloadCompleted.connect(onCompleted)
    dialog.downloadError.connect(onDownloadError)
    dialog.downloadExited.connect(onDownLoadExited)
    dialog.downloadProgress.connect(onDownloadProgress)

    dialog.open()
    dialog.exec_()


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
    return start_app(cleanup=True, options=StartOptions.All())


@enum.unique
class StartOptions(enum.IntFlag):
    Minimized = 0
    EditorWidgets = 1
    ProcessingFramework = 2
    PythonRunner = 4
    PrintProviders = 8
    All = EditorWidgets | ProcessingFramework | PythonRunner | PrintProviders

def start_app(cleanup=True, options=StartOptions.Minimized)->QgsApplication:
    if isinstance(QgsApplication.instance(), QgsApplication):
        print('Found existing QgsApplication.instance()')
        return QgsApplication.instance()
    else:
        qgsApp = qgis.testing.start_app(cleanup=cleanup)
        if not QgsProviderRegistry.instance().libraryDirectory().exists():
            s = ""
        assert QgsProviderRegistry.instance().libraryDirectory().exists(), \
            'Directory: {} does not exist'.format(QgsProviderRegistry.instance().libraryDirectory().path())

        # initialize things not done by qgis.test.start_app()...
        if StartOptions.PythonRunner in options:
            # initiate a PythonRunner instance if None exists
            if not QgsPythonRunner.isValid():
                r = QgsPythonRunnerMockup()
                QgsPythonRunner.setInstance(r)

        # init standard EditorWidgets
        if StartOptions.EditorWidgets in options:
            QgsGui.editorWidgetRegistry().initEditors()

        if not isinstance(qgis.utils.iface, QgisInterface):
            iface = QgisMockup()
            qgis.utils.initInterface(sip.unwrapinstance(iface))
            assert iface == qgis.utils.iface

        # set 'home_plugin_path', which is required from the QGIS Plugin manager
        qgis.utils.home_plugin_path = os.path.join(QgsApplication.instance().qgisSettingsDirPath(),
                                                   *['python', 'plugins'])

        # initialize the QGIS processing framework
        if StartOptions.ProcessingFramework in options:
            from qgis.analysis import QgsNativeAlgorithms
            QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

            qgisCorePythonPluginDir = pathlib.Path(QgsApplication.pkgDataPath()) / 'python' / 'plugins'
            assert os.path.isdir(qgisCorePythonPluginDir)
            if not qgisCorePythonPluginDir in sys.path:
                sys.path.append(qgisCorePythonPluginDir.as_posix())

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

        #mock.MagicMock.__init__(self, spec=QgisInterface, name='QgisMockup')


        #super(QgisMockup, self).__init__(spec=QgisInterface, name='QgisMockup')
        #mock.MagicMock.__init__(self, spec=QgisInterface)
        #QgisInterface.__init__(self)


        self.mCanvas = QgsMapCanvas()
        self.mCanvas.blockSignals(False)
        self.mCanvas.setCanvasColor(Qt.black)
        self.mCanvas.extentsChanged.connect(self.testSlot)
        self.mLayerTreeView = QgsLayerTreeView()
        self.mRootNode = QgsLayerTree()
        self.mLayerTreeModel = QgsLayerTreeModel(self.mRootNode)
        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeMapCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mRootNode, self.mCanvas)
        self.mLayerTreeMapCanvasBridge.setAutoSetupOnFirstLayer(True)

        import pyplugin_installer.installer
        PI = pyplugin_installer.instance()
        self.mPluginManager = QgsPluginManagerMockup()

        self.ui = QMainWindow()

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



    def pluginManagerInterface(self) -> QgsPluginManagerInterface:
        return self.mPluginManager

    def activeLayer(self):
        return self.mapCanvas().currentLayer()

    def setActiveLayer(self, mapLayer:QgsMapLayer):
        if mapLayer in self.mapCanvas().layers():
            self.mapCanvas().setCurrentLayer(mapLayer)


    def cutSelectionToClipboard(self, mapLayer: QgsMapLayer):
        if isinstance(mapLayer, QgsVectorLayer):
            self.mClipBoard.replaceWithCopyOf(mapLayer)
            mapLayer.beginEditCommand('Features cut')
            mapLayer.deleteSelectedFeatures()
            mapLayer.endEditCommand()

    def copySelectionToClipboard(self, mapLayer: QgsMapLayer):
        if isinstance(mapLayer, QgsVectorLayer):
            self.mClipBoard.replaceWithCopyOf(mapLayer)

    def pasteFromClipboard(self, pasteVectorLayer: QgsMapLayer):
        if not isinstance(pasteVectorLayer, QgsVectorLayer):
            return

        return
        # todo: implement
        pasteVectorLayer.beginEditCommand('Features pasted')
        features = self.mClipBoard.transformedCopyOf(pasteVectorLayer.crs(), pasteVectorLayer.fields())
        nTotalFeatures = features.count()
        context = pasteVectorLayer.createExpressionContext()
        compatibleFeatures = QgsVectorLayerUtils.makeFeatureCompatible(features, pasteVectorLayer)
        newFeatures

    def iconSize(self, dockedToolbar=False):
        return QSize(30, 30)

    def testSlot(self, *args):
        # print('--canvas changes--')
        s = ""

    def mainWindow(self):
        return self.ui

    def addToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def removeToolBarIcon(self, action):
        assert isinstance(action, QAction)

    def addVectorLayer(self, path, basename=None, providerkey=None):
        if basename is None:
            basename = os.path.basename(path)
        if providerkey is None:
            bn, ext = os.path.splitext(basename)

            providerkey = 'ogr'
        l = QgsVectorLayer(path, basename, providerkey)
        assert l.isValid()
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        self.mLayerTreeMapCanvasBridge.setCanvasLayers()
        s = ""

    def legendInterface(self):
        return None

    def layerTreeCanvasBridge(self) -> QgsLayerTreeMapCanvasBridge:
        return self.mLayerTreeMapCanvasBridge

    def layerTreeView(self) -> QgsLayerTreeView:
        return self.mLayerTreeView

    def addRasterLayer(self, path, baseName:str='')->QgsRasterLayer:
        l = QgsRasterLayer(path, os.path.basename(path))
        self.lyrs.append(l)
        QgsProject.instance().addMapLayer(l, True)
        self.mRootNode.addLayer(l)
        # self.mCanvas.setLayers(self.mCanvas.layers() + l)
        return l

    def createActions(self):
        m = self.ui.menuBar().addAction('Add Vector')
        m = self.ui.menuBar().addAction('Add Raster')

    def mapCanvas(self):
        return self.mCanvas

    def mapNavToolToolBar(self):
        super().mapNavToolToolBar()

    def messageBar(self, *args, **kwargs):
        return self.mMessageBar

    def rasterMenu(self):
        super().rasterMenu()

    def vectorMenu(self):
        super().vectorMenu()

    def viewMenu(self):
        super().viewMenu()

    def windowMenu(self):
        super().windowMenu()

    def zoomFull(self, *args, **kwargs):
        super().zoomFull(*args, **kwargs)


class TestCase(qgis.testing.TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All) -> None:
        app = start_app(cleanup=cleanup, options=options)

        from osgeo import gdal
        gdal.AllRegister()

    @classmethod
    def tearDownClass(cls):


        if isinstance(QgsApplication.instance(), QgsApplication):
            QgsApplication.exitQgis()
            QApplication.quit()
            import gc
            gc.collect()

        s = ""

    def showGui(self, widgets)->bool:
        """
        Call this to show GUI(s) in case we do not run within a CI system
        """

        if str(os.environ.get('CI')).lower() not in ['', 'none', 'false', '0']:
            return False

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

class TestObjects():
    """
    Creates objects to be used for testing. It is preferred to generate objects in-memory.
    """

    _coreData = _coreDataWL = _coreDataWLU = None

    @staticmethod
    def coreData()->typing.Tuple[np.ndarray, typing.List[float], str]:
        if TestObjects._coreData is None:
            source_raster = pathlib.Path(__file__).parent / 'enmap.tif'
            assert source_raster.is_file()

            ds = gdal.Open(source_raster.as_posix())
            assert isinstance(ds, gdal.Dataset)
            TestObjects._coreData = ds.ReadAsArray()

            from .utils import parseWavelength
            TestObjects._coreDataWL, TestObjects._coreDataWLU = parseWavelength(ds)

        return TestObjects._coreData, TestObjects._coreDataWL, TestObjects._coreDataWLU


    @staticmethod
    def createDropEvent(mimeData: QMimeData) -> QDropEvent:
        """Creates a QDropEvent containing the provided QMimeData ``mimeData``"""
        return QDropEvent(QPointF(0, 0), Qt.CopyAction, mimeData, Qt.LeftButton, Qt.NoModifier)

    @staticmethod
    def spectralProfiles(n=10):
        """
        Returns n random spectral profiles from the test data
        :return: lost of (N,3) array of floats specifying point locations.
        """

        coredata, wl, wlu = TestObjects.coreData()

        results = []
        import random
        assert n > 0
        i = 0
        while i < n:
            x = random.randint(0, coredata.shape[2] - 1)
            y = random.randint(0, coredata.shape[1] - 1)
            profile = coredata[:, y, x]
            results.append(profile)
            i += 1

        return results

    """
    Class with static routines to create test objects
    """

    @staticmethod
    def inMemoryImage(*args, **kwds):

        warnings.warn(''.join(traceback.format_stack())+'\nUse createRasterDataset instead')
        return TestObjects.createRasterDataset(*args, **kwds)

    @staticmethod
    def createRasterDataset(ns=10, nl=20, nb=1, crs='EPSG:32632',
                            eType:int = gdal.GDT_Byte, nc: int = 0, path: str = None) -> gdal.Dataset:
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


        drv = gdal.GetDriverByName('GTiff')
        assert isinstance(drv, gdal.Driver)

        if not isinstance(path, str):
            if nc > 0:
                path = '/vsimem/testClassification.{}.tif'.format(str(uuid.uuid4()))
            else:
                path = '/vsimem/testImage.{}.tif'.format(str(uuid.uuid4()))

        ds = drv.Create(path, ns, nl, bands=nb, eType=eType)
        dt_out = gdal_array.flip_code(eType)
        assert isinstance(ds, gdal.Dataset)
        if isinstance(crs, str):
            c = QgsCoordinateReferenceSystem(crs)
            ds.SetProjection(c.toWkt())
        ds.SetGeoTransform([0, 1.0, 0, \
                            0, 0, -1.0])

        assert isinstance(ds, gdal.Dataset)

        if nc > 0:
            for b in range(nb):
                band = ds.GetRasterBand(b+1)
                assert isinstance(band, gdal.Band)

                nodata = band.GetNoDataValue()
                array = np.empty((nl, ns), dtype = dt_out)
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
                band.WriteArray(array)
        else:
            # fill with test data

            coredata, wl, wlu = TestObjects.coreData()
            coredata = coredata.astype(dt_out)
            cb, cl, cs = coredata.shape
            if nb > coredata.shape[0]:
                coreddata2 = np.empty((nb, cl, cs), dtype=dt_out)
                coreddata2[0:cb, :, :] = coredata
                # todo: increase the number of output bands by linear interpolation instead just repeated the last band
                for b in range(cb, nb):
                    coreddata2[b, :, :] = coredata[-1, :, :]
                coredata = coreddata2

            xoff = 0
            while xoff < ns - 1:
                xsize = min(cs, ns - xoff)
                yoff = 0
                while yoff < nl - 1:
                    ysize = min(cl, nl - yoff)

                    ds.WriteRaster(xoff, yoff, xsize, ysize, coredata[:,0:ysize, 0:xsize].tobytes())
                    yoff += ysize
                xoff += xsize

        ds.FlushCache()
        return ds

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
    def createVectorDataSet(wkb=ogr.wkbPolygon) -> ogr.DataSource:
        """
        Create an in-memory ogr.DataSource
        :return: ogr.DataSource
        """
        ogr.UseExceptions()
        assert wkb in [ogr.wkbPoint, ogr.wkbPolygon, ogr.wkbLineString]

        # find the QGIS world_map.shp
        pkgPath = QgsApplication.instance().pkgDataPath()
        assert os.path.isdir(pkgPath)

        pathSrc = None
        potentialPathes = [
            os.path.join(os.path.dirname(__file__), 'testpolygons.geojson'),
            os.path.join(pkgPath, *['resources', 'data', 'world_map.shp']),
        ]
        for p in potentialPathes:
            if os.path.isfile(p):
                pathSrc = p
                break

        assert os.path.isfile(pathSrc), 'Unable to find QGIS "world_map.shp". QGIS Pkg path = {}'.format(pkgPath)

        dsSrc = ogr.Open(pathSrc)
        assert isinstance(dsSrc, ogr.DataSource)
        lyrSrc = dsSrc.GetLayer(0)
        assert isinstance(lyrSrc, ogr.Layer)

        ldef = lyrSrc.GetLayerDefn()
        assert isinstance(ldef, ogr.FeatureDefn)

        srs = lyrSrc.GetSpatialRef()
        assert isinstance(srs, osr.SpatialReference)

        drv = ogr.GetDriverByName('ESRI Shapefile')
        assert isinstance(drv, ogr.Driver)

        # set temp path
        if wkb == ogr.wkbPolygon:
            lname = 'polygons'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.polygons.shp'
        elif wkb == ogr.wkbPoint:
            lname = 'points'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.centroids.shp'
        elif wkb == ogr.wkbLineString:
            lname = 'lines'
            pathDst = '/vsimem/tmp' + str(uuid.uuid4()) + '.test.line.shp'
        else:
            raise NotImplementedError()

        if wkb == ogr.wkbPolygon:
            dsDst = drv.CopyDataSource(dsSrc, pathDst)
        else:
            dsDst = drv.CreateDataSource(pathDst)
            assert isinstance(dsDst, ogr.DataSource)
            lyrDst = dsDst.CreateLayer(lname, srs=srs, geom_type=wkb)
            assert isinstance(lyrDst, ogr.Layer)

            # copy field definitions
            for i in range(ldef.GetFieldCount()):
                fieldDefn = ldef.GetFieldDefn(i)
                assert isinstance(fieldDefn, ogr.FieldDefn)
                lyrDst.CreateField(fieldDefn)

            # copy features

            for fSrc in lyrSrc:
                assert isinstance(fSrc, ogr.Feature)
                g = fSrc.geometry()

                fDst = ogr.Feature(lyrDst.GetLayerDefn())
                assert isinstance(fDst, ogr.Feature)

                if isinstance(g, ogr.Geometry):
                    if wkb == ogr.wkbPoint:
                        g = g.Centroid()
                    elif wkb == ogr.wkbLineString:
                        g = g.GetBoundary()
                    else:
                        raise NotImplementedError()

                fDst.SetGeometry(g)

                for i in range(ldef.GetFieldCount()):
                    fDst.SetField(i, fSrc.GetField(i))

                assert lyrDst.CreateFeature(fDst) == ogr.OGRERR_NONE

        assert isinstance(dsDst, ogr.DataSource)
        dsDst.FlushCache()
        return dsDst

    @staticmethod
    def createVectorLayer(wkbType: QgsWkbTypes = QgsWkbTypes.Polygon) -> QgsVectorLayer:
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
        dsSrc = TestObjects.createVectorDataSet(wkb)

        assert isinstance(dsSrc, ogr.DataSource)
        lyr = dsSrc.GetLayer(0)
        assert isinstance(lyr, ogr.Layer)
        assert lyr.GetFeatureCount() > 0
        uri = '{}|{}'.format(dsSrc.GetName(), lyr.GetName())

        # dsSrc = None
        vl = QgsVectorLayer(uri, 'testlayer', 'ogr', lyrOptions)
        assert isinstance(vl, QgsVectorLayer)
        assert vl.isValid()
        assert vl.featureCount() == lyr.GetFeatureCount()
        return vl

    @staticmethod
    def createDropEvent(mimeData: QMimeData):
        """Creates a QDropEvent conaining the provided QMimeData"""
        return QDropEvent(QPointF(0, 0), Qt.CopyAction, mimeData, Qt.LeftButton, Qt.NoModifier)

    @staticmethod
    def processingAlgorithm():

        from qgis.core import QgsProcessingAlgorithm

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

            return

            self.setSystemClipBoard()
            self.mUseSystemClipboard = False
            self.changed.emit()

        elif isinstance(src, QgsFeatureStore):
            raise NotImplementedError()

    def setSystemClipBoard(self):

        raise NotImplementedError()
        cb = QApplication.clipboard()
        textCopy = self.generateClipboardText()

        m = QMimeData()
        m.setText(textCopy)

        # todo: set HTML

    def generateClipboardText(self):

        raise NotImplementedError()
        pass
        textFields = ['wkt_geom'] + [n for n in self.mFeatureFields]

        textLines = '\t'.join(textFields)
        textFields.clear()

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
            return False
        return True


