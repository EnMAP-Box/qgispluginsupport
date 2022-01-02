import site
import pathlib
import importlib

from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QGridLayout

if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

TESTS = REPO / 'tests' / 'speclib'
site.addsitedir(TESTS)
from qgis._core import QgsMapLayerModel, QgsApplication, QgsRasterDataProvider, Qgis, QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterMultipleLayers, QgsProcessingContext, QgsVectorLayer, QgsProcessingRegistry

from qgis._gui import QgsMapToolIdentify, QgsProcessingContextGenerator, QgsProcessingParameterWidgetContext, \
    QgsProcessingGui
from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas
from qgis.core import QgsProject, QgsRasterLayer, QgsContrastEnhancement
from qps import initAll
from qps.speclib.core.spectralprofile import groupBySpectralProperties
from qps.speclib.gui.spectralprocessingwidget import SpectralProcessingRasterLayerWidgetWrapper, \
    SpectralProcessingWidget
from qps.speclib.core import spectrallibraryrasterdataprovider, profile_fields

importlib.reload(spectrallibraryrasterdataprovider)
from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider, VectorLayerFieldRasterDataProvider
from qps.testing import TestObjects, start_app, StartOptions
from qps.utils import qgisAppQgisInterface
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
APP = None
if not isinstance(QgsApplication.instance(), QgsApplication):
    APP = start_app(options=StartOptions.All)
    initAll()
else:
    APP = QgsApplication.instance()

if False:
    from test_speclib_rasterdataprovider import RasterDataProviderTests
    T = RasterDataProviderTests()
    T.setUpClass()
    T.setUp()
    T.test_VectorLayerRasterDataProvider()
else:
    vl = TestObjects.createVectorLayer()
    vl = TestObjects.createSpectralLibrary(n_empty=3, n_bands=[[25,], [255,]])
    QgsProject.instance().addMapLayer(vl)

    from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider

    registerDataProvider()
    n_bands = [256]
    n_features = 2
    speclib = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
    speclib: QgsVectorLayer

    speclib.startEditing()
    procw = SpectralProcessingWidget()
    procw.setSpeclib(speclib)
    reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
    alg1 = reg.algorithmById('gdal:rearrange_bands')
    alg2 = reg.algorithmById('native:rescaleraster')

    procw.setAlgorithm(alg2)
    procw.show()
    if qgisAppQgisInterface() is None:


        APP.exec_()