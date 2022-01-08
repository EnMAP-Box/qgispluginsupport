import site
import pathlib
import importlib

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import QgsMapLayerModel, QgsApplication, QgsRasterDataProvider, Qgis

from qgis.gui import QgsMapToolIdentify

import qps
from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas
from qgis.core import QgsProject, QgsRasterLayer, QgsContrastEnhancement
from qps.speclib.core.spectralprofile import groupBySpectralProperties

if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

TESTS = REPO / 'tests' / 'speclib'
site.addsitedir(TESTS)

from qps.speclib.core import spectrallibraryrasterdataprovider, profile_fields

importlib.reload(spectrallibraryrasterdataprovider)
from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider, VectorLayerFieldRasterDataProvider
from qps.testing import TestObjects, start_app
from qps.utils import qgisAppQgisInterface
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget

APP = None
if not isinstance(QgsApplication.instance(), QgsApplication):
    APP = start_app()
else:
    APP = QgsApplication.instance()

qps.initAll()

if False:
    from test_speclib_rasterdataprovider import RasterDataProviderTests

    T = RasterDataProviderTests()
    T.setUpClass()
    T.setUp()
    T.test_VectorLayerRasterDataProvider()
else:
    vl = TestObjects.createVectorLayer()
    vl = TestObjects.createSpectralLibrary(n_empty=3, n_bands=[[25, ], [255, ]])
    QgsProject.instance().addMapLayer(vl)

    p_field = profile_fields(vl)

    fids = vl.allFeatureIds()
    layers = []
    dpList = []
    registerDataProvider()
    features = list(vl.getFeatures())
    for field in vl.fields():
        name = f'Test {field.name()}:{field.typeName()}'
        print(name)
        src = f'?lid={{{vl.id()}}}&field={field.name()}'
        # src = ''
        layer = QgsRasterLayer(src, name, VectorLayerFieldRasterDataProvider.providerKey())
        dp: VectorLayerFieldRasterDataProvider = layer.dataProvider()
        assert isinstance(dp, VectorLayerFieldRasterDataProvider)
        dp.setActiveFeatures(features)
        assert dp.activeField().name() == field.name()

        # required
        layer.setExtent(dp.extent())
        # ce = QgsContrastEnhancement(layer.renderer().contrastEnhancement())
        # layer.setContrastEnhancement(ce.contrastEnhancementAlgorithm())

        print(layer.name())
        assert dp.extent() == layer.extent()
        if not field.type() == QVariant.ByteArray:
            continue
            pass
        dpList.append(dp)
        layers.append(layer)

        # break

        nb = dp.bandCount()
        for b in range(1, nb + 1):
            bandName = dp.generateBandName(b)

            displayName = dp.displayBandName(b)
            dt = dp.sourceDataType(b)
            src_nodata = dp.sourceNoDataValue(b)

            usr_nodata = dp.userNoDataValues(b)
            dtype = dp.dataType(b)
            assert isinstance(dtype, Qgis.DataType)
            assert dtype != Qgis.DataType.UnknownDataType

    QgsProject.instance().addMapLayers(layers, True)

    for lyr in layers:
        assert isinstance(lyr, QgsRasterLayer)
        dp = lyr.dataProvider()
        assert isinstance(dp, QgsRasterDataProvider)

    slw = SpectralLibraryWidget(speclib=vl)


    def onIdentifyResults(results):
        print(results, flush=True)


    if qgisAppQgisInterface() is None:
        c = QgsMapCanvas()
        c.setLayers(layers)
        c.zoomToFullExtent()
        mt = QgsMapToolIdentify(c)

        mt.changedRasterResults.connect(onIdentifyResults)
        c.setMapTool(mt)
        c.show()
        slw.show()
        APP.exec_()
