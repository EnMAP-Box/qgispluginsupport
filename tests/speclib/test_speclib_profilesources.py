# noinspection PyPep8Naming
import datetime
import random
import unittest
from typing import Iterator, List, Tuple

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QPushButton, QSplitter, QVBoxLayout, QWidget
from qgis.core import edit, Qgis, QgsExpressionContext, QgsFeature, QgsField, QgsGeometry, QgsMapToPixel, QgsPoint, \
    QgsPointXY, QgsProject, QgsRaster, QgsRasterDataProvider, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsDualView, QgsMapCanvas
from qps import initAll
from qps.maptools import CursorLocationMapTool
from qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import isProfileValueDict, SpectralProfileBlock, SpectralSetting
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprofilesources import MapCanvasLayerProfileSource, ProfileSamplingMode, \
    SamplingBlockDescription, SpectralFeatureGeneratorNode, SpectralProfileBridge, SpectralProfileBridgeTreeView, \
    SpectralProfileBridgeViewDelegate, SpectralProfileGeneratorNode, SpectralProfileSource, SpectralProfileSourceModel, \
    SpectralProfileSourcePanel, SpectralProfileSourceProxyModel, StandardFieldGeneratorNode, StandardLayerProfileSource
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import parseWavelength, rasterArray, SpatialExtent, SpatialPoint
from qpstestdata import enmap

start_app()
initAll()


class SpectralProcessingTests(TestCase):

    def test_dualview(self):

        n_features = 5000
        # sl = TestObjects.createVectorLayer(n_features=n_features)
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary(n_features, n_bands=[177])
        self.assertEqual(sl.featureCount(), n_features)
        c = QgsMapCanvas()
        if True:
            dv = QgsDualView()
            dv.init(sl, c, loadFeatures=True)
        sl.startEditing()
        fids = sl.allFeatureIds()
        sl.selectByIds(fids[-2500:])
        n_to_del = len(sl.selectedFeatureIds())
        t0 = datetime.datetime.now()
        context = QgsVectorLayer.DeleteContext(cascade=True, project=QgsProject.instance())
        sl.beginEditCommand('Delete features')
        success, n_del = sl.deleteSelectedFeatures(context)
        sl.endEditCommand()
        assert success
        print(f'Required {datetime.datetime.now() - t0} to delete {n_del} features')
        # self.showGui(dv)

    def test_borderPixel(self):
        from qpstestdata import enmap
        lyr: QgsRasterLayer = QgsRasterLayer(enmap.as_posix())
        lyr.setName('EnMAP')
        ext = lyr.extent()

        dp: QgsRasterDataProvider = lyr.dataProvider()
        nb, ns, nl = lyr.bandCount(), lyr.height(), lyr.width()
        pxx, pxy = lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY()

        out_of_image = [
            SpatialPoint(lyr.crs(), ext.xMinimum() - 0.0001 * pxx, ext.yMaximum()),
            SpatialPoint(lyr.crs(), ext.xMaximum() + 0.0001 * pxx, ext.yMaximum())
        ]

        source = StandardLayerProfileSource(lyr)

        k_mode = ProfileSamplingMode()
        k_mode.setKernelSize(3, 3)
        k_mode.setAggregation(ProfileSamplingMode.NO_AGGREGATION)

        for pt in out_of_image:
            self.assertFalse(lyr.extent().contains(pt))
            size = k_mode.kernelSize()
            x, y = size.width(), size.height()
            profiles = source.collectProfiles(pt, QSize(x, y))
            self.assertTrue(len(profiles) > 0)
            self.assertTrue(len(profiles) < x * y)

            s = ""

        sl = TestObjects.createSpectralLibrary()
        slw = SpectralLibraryWidget(speclib=sl)
        panel = SpectralProfileSourcePanel()
        panel.addSources(lyr)
        panel.addSpectralLibraryWidgets(slw)
        gnode = panel.createRelation()
        gnode.setSpeclib(sl)
        for n in gnode.spectralProfileGeneratorNodes():
            n.setProfileSource(lyr)

        canvas = QgsMapCanvas()
        canvas.setLayers([sl, lyr])
        canvas.zoomToFullExtent()
        mt = CursorLocationMapTool(canvas, showCrosshair=True)
        mt.sigLocationRequest.connect(lambda crs, pt: panel.loadCurrentMapSpectra(SpatialPoint(crs, pt)))
        canvas.setMapTool(mt)

        self.showGui([canvas, panel, slw])

        QgsProject.instance().removeAllMapLayers()

    def test_SpectralProfileSources(self):

        lyr1 = TestObjects.createRasterLayer()
        lyr2 = TestObjects.createRasterLayer()

        canvas = QgsMapCanvas()
        layers = [lyr1, lyr2]
        QgsProject.instance().addMapLayers(layers)
        canvas.setLayers(layers)
        canvas.zoomToFullExtent()
        sources = [
            StandardLayerProfileSource(lyr1),
            MapCanvasLayerProfileSource(canvas)]

        point = SpatialPoint.fromMapLayerCenter(lyr1)

        def check_profile_results(results):
            self.assertIsInstance(results, List)
            for (d, c) in results:
                self.assertIsInstance(d, dict)
                self.assertTrue(isProfileValueDict(d))
                self.assertIsInstance(c, QgsExpressionContext)

        for s in sources:
            s: SpectralProfileSource
            print(f'Test {s.__class__.__name__}')
            self.assertIsInstance(s, SpectralProfileSource)
            self.assertIsInstance(s.name(), str)
            self.assertIsInstance(s.toolTip(), str)

            profiles1a = s.collectProfiles(point)
            profiles1b = s.collectProfiles(point, kernel_size=QSize(1, 1))

            check_profile_results(profiles1a)
            check_profile_results(profiles1b)
            self.assertDictEqual(profiles1a[0][0], profiles1b[0][0])
            self.assertDictEqual(profiles1a[0][1].variablesToMap(), profiles1b[0][1].variablesToMap())

            profiles2 = s.collectProfiles(point, kernel_size=QSize(2, 2))
            profiles3 = s.collectProfiles(point, kernel_size=QSize(3, 3))
            check_profile_results(profiles2)
            check_profile_results(profiles3)

            profiles4 = s.collectProfiles(point, random_other_args='foobar')
            check_profile_results(profiles4)
        QgsProject.instance().removeAllMapLayers()

    def test_nodeValidation(self):

        class TestValNode(StandardFieldGeneratorNode):

            def __init__(self, *args, **kwds):
                super().__init__(*args, **kwds)

                self.mErrors = []

            def validate(self) -> Iterator[str]:
                for err in super().validate():
                    yield err
                for err in self.mErrors:
                    yield err

        n1 = TestValNode('n1')
        n2 = TestValNode('n2')
        n2.setCheckable(True)
        n3a = TestValNode('n3a')
        n3b = TestValNode('n3b')
        n3a.setCheckable(True)
        n3b.setCheckable(False)

        n2.appendChildNodes([n3a, n3b])
        n1.appendChildNodes([n2])

        for n in [n1, n2, n3a, n3b]:
            n.setCheckState(Qt.Checked)

        self.assertListEqual(list(n3a.errors()),
                             ['n3a: Field is undefined.',
                              'n3a: Value is undefined. Needs a value/expression or uncheck the field.'])
        self.assertListEqual(list(n3b.errors()),
                             ['n3b: Field is undefined.',
                              'n3b: Value is undefined. Needs a value/expression or uncheck the field.'])
        for e in n2.errors(recursive=True):
            print(e)
        self.assertListEqual(list(n2.errors(recursive=True)),
                             ['n2: Field is undefined.',
                              'n2: Value is undefined. Needs a value/expression or uncheck the field.',
                              'n2:n3a: Field is undefined.',
                              'n2:n3a: Value is undefined. Needs a value/expression or uncheck the field.',
                              'n2:n3b: Field is undefined.',
                              'n2:n3b: Value is undefined. Needs a value/expression or uncheck the field.']
                             )

    def test_SpectralProfileSourcePanel_gui(self):
        from qps import registerEditorWidgets, initResources
        initResources()
        registerEditorWidgets()

        sources, (slw1, slw2) = self.createTestObjects()
        sources.append(TestObjects.createMultiMaskExample(nb=10, ns=30, nl=50))
        canvas = QgsMapCanvas()
        canvas.setLayers(sources)
        canvas.setDestinationCrs(sources[0].crs())
        canvas.zoomToFullExtent()
        canvas.setExtent(sources[0].extent())
        mt = CursorLocationMapTool(canvas, True)
        canvas.setMapTool(mt)
        mt.sigLocationRequest.connect(lambda crs, pt: panel.loadCurrentMapSpectra(SpatialPoint(crs, pt)))

        center = SpatialPoint.fromMapCanvasCenter(canvas)

        panel = SpectralProfileSourcePanel()
        panel.mBridge.addSources(sources)
        panel.mBridge.addSpectralLibraryWidgets([slw1, slw2])
        panel.createRelation()
        panel.createRelation()

        hl = QHBoxLayout()
        # hl.addWidget(btnAdd)
        vl = QVBoxLayout()
        vl.addLayout(hl)
        vl.addWidget(panel)
        w = QWidget()
        w.setLayout(vl)

        splitV = QSplitter()
        splitV.setOrientation(Qt.Vertical)
        splitV.addWidget(slw1)
        splitV.addWidget(slw2)

        splitH = QSplitter()
        splitH.addWidget(canvas)
        splitH.addWidget(splitV)
        splitH.addWidget(w)

        speclibs = [sl for sl in panel.spectralProfileBridge().destinations()]
        canvas.setLayers(speclibs + canvas.layers())
        self.showGui(splitH)

        QgsProject.instance().removeAllMapLayers()

    def test_SpectralProfileSourcePanel(self):

        from qps import registerEditorWidgets, initResources
        initResources()
        registerEditorWidgets()

        sources, spectralLibraryWidgets = self.createTestObjects()
        sources.append(TestObjects.createMultiMaskExample(nb=10, ns=30, nl=50))
        canvas = QgsMapCanvas()
        canvas.setLayers(sources)
        canvas.setDestinationCrs(sources[0].crs())
        canvas.zoomToFullExtent()
        canvas.setExtent(sources[0].extent())
        mt = CursorLocationMapTool(canvas, True)
        canvas.setMapTool(mt)

        center = SpatialPoint.fromMapCanvasCenter(canvas)

        panel = SpectralProfileSourcePanel()
        # panel.mBridge.addSources(sources)
        # panel.mBridge.addSpectralLibraryWidgets(widgets)
        panel.createRelation()
        panel.createRelation()

        # add sources
        panel.addSources(MapCanvasLayerProfileSource())
        panel.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_LAST_LAYER))
        panel.addSources(sources)

        # add widgets
        panel.addSpectralLibraryWidgets(spectralLibraryWidgets)
        speclib = TestObjects.createSpectralLibrary()
        speclib.setName('NewLib')

        slw = SpectralLibraryWidget(speclib=speclib)

        panel.addSpectralLibraryWidgets(slw)

        g = panel.createRelation()
        self.assertIsInstance(g, SpectralFeatureGeneratorNode)
        # self.assertEqual(g.name(), speclib.name())

        n = g.spectralProfileGeneratorNodes()[0]
        self.assertIsInstance(n, SpectralProfileGeneratorNode)
        lyrA = sources[0]
        n.setProfileSource(lyrA)
        mode = n.setSampling(ProfileSamplingMode())
        self.assertIsInstance(mode, ProfileSamplingMode)
        size = mode.kernelSize()
        g.spectralProfileGeneratorNodes()

        # panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)

        # remove sources
        panel.removeSources(sources)

        # remove widgets
        panel.removeSpectralLibraryWidgets(spectralLibraryWidgets)

        slw.close()

        (src1, src2), (slw1, slw2) = self.createTestObjects()
        sl1 = slw1.plotModel().visualizations()[0].layer()

        with edit(sl1):
            assert SpectralLibraryUtils.addSpectralProfileField(sl1, 'profile_new')

        # re-add generators
        fgnode1 = panel.createRelation()
        fgnode2 = panel.createRelation()
        self.assertIsInstance(fgnode1, SpectralFeatureGeneratorNode)
        self.assertIsInstance(fgnode2, SpectralFeatureGeneratorNode)
        fgnode1.setSpeclib(sl1)
        fgnode2.setSpeclib(sl1)

        # clear test speclibs
        for slw in [slw1, slw2]:

            for sl in slw.plotModel().spectralLibraries():
                with edit(sl):
                    sl.selectAll()
                    sl.deleteSelectedFeatures()

        sl1 = slw1.plotModel().spectralLibraries()[0]
        with edit(sl1):
            assert SpectralLibraryUtils.addSpectralProfileField(sl1, 'profile2')

        speclib_sources = slw1.spectralLibraries()
        QgsProject.instance().addMapLayers(speclib_sources, False)
        maskLayer = TestObjects.createMultiMaskExample(nb=25, ns=50, nl=50)

        if False:
            map_sources = [src1, src2]
        else:
            map_sources = [maskLayer]

        QgsProject.instance().addMapLayers(map_sources, False)
        canvas.setLayers(map_sources)
        canvas.zoomToFullExtent()
        # re-add destinations
        panel.addSpectralLibraryWidgets([slw1, slw2])

        # re-add sources
        panel.addSources(map_sources)

        modes = [ProfileSamplingMode(),
                 ProfileSamplingMode()]
        modes[1].setKernelSize(3, 3)
        modes[1].setAggregation(ProfileSamplingMode.NO_AGGREGATION)

        for o, pgnode in enumerate(fgnode1.spectralProfileGeneratorNodes()):
            pgnode.setProfileSource(map_sources[0])
            self.assertIsInstance(pgnode.sampling(), ProfileSamplingMode)
            pgnode.setSampling(modes[0])
            pgnode.setScaling(o * 10, 1)

        for n in fgnode1.fieldNodes():
            n.setCheckState(Qt.Checked)

        n = fgnode1.fieldNode('color')
        n.setValue("'yellow'")

        for v in ['px_x', 'px_y', 'geo_x', 'geo_y']:
            n = fgnode1.fieldNode(v)
            n.setExpression(f'@{v}')

        for pgnode in fgnode2.spectralProfileGeneratorNodes():
            pgnode.setProfileSource(map_sources[-1])
            pgnode.setSampling(modes[1])

        panel.mBridge
        RESULTS = panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)

        if False:
            self.assertEqual(sl2.featureCount(), 9)
            self.assertTrue(sl1.id() in RESULTS.keys())
            self.assertTrue(sl2.id() in RESULTS.keys())
        for speclib_ids, features in RESULTS.items():
            for feature in features:
                self.assertIsInstance(feature, QgsFeature)
                self.assertTrue(feature.geometry().type() == QgsWkbTypes.PointGeometry)

        btnAdd = QPushButton('Random click')

        def onClicked():
            ext = SpatialExtent.fromMapCanvas(canvas)
            x = random.uniform(ext.xMinimum(), ext.xMaximum())
            y = random.uniform(ext.yMinimum(), ext.yMaximum())
            pt = SpatialPoint(ext.crs(), x, y)
            panel.loadCurrentMapSpectra(pt, mapCanvas=canvas, runAsync=False)

        def onDestroyed():
            print('destroyed layer')

        def onClosing():
            print('Closing layer')

        for lyr in panel.mBridge.destinations():
            lyr.destroyed.connect(onDestroyed)
            lyr.willBeDeleted.connect(onClosing)

        mt.sigLocationRequest.connect(lambda crs, pt, c=canvas:
                                      panel.loadCurrentMapSpectra(SpatialPoint(crs, pt), mapCanvas=canvas))
        btnAdd.clicked.connect(onClicked)
        hl = QHBoxLayout()
        hl.addWidget(btnAdd)
        vl = QVBoxLayout()
        vl.addLayout(hl)
        vl.addWidget(panel)
        w = QWidget()
        w.setLayout(vl)

        splitV = QSplitter()
        splitV.setOrientation(Qt.Vertical)
        splitV.addWidget(slw1)
        splitV.addWidget(slw2)

        splitH = QSplitter()
        splitH.addWidget(canvas)
        splitH.addWidget(splitV)
        splitH.addWidget(w)

        speclibs = [sl for sl in panel.spectralProfileBridge().destinations()]
        canvas.setLayers(speclibs + canvas.layers())
        self.showGui(splitH)
        QgsProject.instance().removeAllMapLayers()

    def validate_profile_data(self, profileData, lyr: QgsRasterLayer, ptR: QgsPointXY):

        array = rasterArray(lyr)
        dp: QgsRasterDataProvider = lyr.dataProvider()
        for (d, context) in profileData:
            self.assertTrue(isProfileValueDict(d))
            self.assertIsInstance(context, QgsExpressionContext)
            pt = context.geometry()
            self.assertTrue(pt, QgsPoint)
            ptXY: QgsPointXY = pt.asPoint()
            ext = lyr.extent()
            self.assertTrue(ext.xMinimum() <= ptXY.x() <= ext.xMaximum())
            self.assertTrue(ext.yMinimum() <= ptXY.y() <= ext.yMaximum())
            self.assertTrue(ext.contains(ptXY),
                            msg=f'Layer extent {ext} \n does not contain context point\n {pt}')
            m2p = QgsMapToPixel(lyr.rasterUnitsPerPixelX(),
                                lyr.extent().center().x(),
                                lyr.extent().center().y(),
                                lyr.width(),
                                lyr.height(),
                                0)
            pxR = m2p.transform(ptXY)
            px_xR, px_yR = int(pxR.x()), int(pxR.y())

            px_x = context.variable('px_x')
            px_y = context.variable('px_y')

            self.assertEqual(px_xR, px_x)
            self.assertEqual(px_yR, px_y)

            if Qgis.versionInt() < 33000:
                results = dp.identify(ptXY, QgsRaster.IdentifyFormat.IdentifyFormatValue)
            else:
                results = dp.identify(ptXY, Qgis.RasterIdentifyFormat.Value)

            yValues = d['y']
            yValuesR = [results.results()[b] for b in range(1, lyr.bandCount() + 1)]

            if yValues != yValuesR:
                s = ""
            self.assertListEqual(yValues, yValuesR)

    def test_SpectralProfileSourceModel(self):

        lyr1 = TestObjects.createRasterLayer(nb=2, ns=5, nl=5)
        lyr2 = TestObjects.createRasterLayer(nb=25, ns=5, nl=5)
        pt1 = SpatialPoint.fromPixelPosition(lyr1, 0.5, 0.5)
        pt2 = SpatialPoint.fromPixelPosition(lyr1, 1.5, 1.5)

        for pt in [pt1, pt2]:
            self.assertTrue(lyr1.extent().contains(pt))

        model = SpectralProfileSourceModel()
        self.assertTrue(len(model) == 0)

        src1 = StandardLayerProfileSource(lyr1)
        src2 = StandardLayerProfileSource(lyr2)
        canvas = QgsMapCanvas()
        canvas.setLayers([lyr2])
        canvas.zoomToFullExtent()
        src3 = MapCanvasLayerProfileSource(canvas)
        src4 = MapCanvasLayerProfileSource(canvas)
        model.addSources([src1, src1, src2, src3, src4])
        self.assertEqual(len(model), 3)

        sources = model[:]
        self.assertListEqual(sources, [src1, src2, src3])
        for src in sources:
            for pt in [pt1, pt2]:
                self.assertIsInstance(src, SpectralProfileSource)
                profileData3 = src.collectProfiles(pt, QSize(5, 2))
                profileData1 = src.collectProfiles(pt)
                self.assertTrue(len(profileData1) == 1)

                profileData2 = src.collectProfiles(pt, QSize(3, 3))

                if isinstance(src, StandardLayerProfileSource):
                    lyr: QgsRasterLayer = src.mLayer
                    self.validate_profile_data(profileData1, lyr, pt)
                    self.validate_profile_data(profileData2, lyr, pt)
                    self.validate_profile_data(profileData3, lyr, pt)
                    s = ""

        sources = model[:]
        sources = sources + sources[0:]
        model.removeSources(sources)

        self.assertTrue(len(model) == 0)

    def test_kernelSampling(self):

        aggregations = [ProfileSamplingMode.NO_AGGREGATION,
                        ProfileSamplingMode.AGGREGATE_MEAN,
                        ProfileSamplingMode.AGGREGATE_MEDIAN,
                        ProfileSamplingMode.AGGREGATE_MIN,
                        ProfileSamplingMode.AGGREGATE_MAX]
        kernels = [('3x3'),
                   # ('4x4'),
                   ('5x5')]

        lyr = QgsRasterLayer(enmap.as_posix())
        center = SpatialPoint.fromMapLayerCenter(lyr)

        source = StandardLayerProfileSource(lyr)

        mode = ProfileSamplingMode()
        for aggregation in aggregations:
            for kernel in kernels:
                mode.setKernelSize(kernel)
                mode.setAggregation(aggregation)
                size = mode.kernelSize()

                x, y = size.width(), size.height()
                self.assertEqual(kernel, f'{x}x{y}')
                mode.setKernelSize(QSize(x, y))
                x2, y2 = mode.kernelSizeXY()
                self.assertEqual(QSize(x, y), QSize(x2, y2))

                self.assertEqual(aggregation, mode.aggregation())

                profiles = source.collectProfiles(center, mode.kernelSize())

                self.assertEqual(len(profiles), x * y)

                profiles_aggr = mode.profiles(center, profiles)

                if aggregation == ProfileSamplingMode.NO_AGGREGATION:
                    self.assertEqual(len(profiles), len(profiles_aggr))
                else:
                    self.assertEqual(len(profiles_aggr), 1)
                for t in profiles:
                    self.assertIsInstance(t, tuple)
                    self.assertEqual(len(t), 2)
                    p, c = t
                    self.assertIsInstance(p, dict)
                    self.assertIsInstance(c, QgsExpressionContext)
                    self.assertIsInstance(c.geometry(), QgsGeometry)
                    if Qgis.versionInt() < 33000:
                        self.assertEqual(c.geometry().type(), QgsWkbTypes.PointGeometry)
                    else:
                        self.assertEqual(c.geometry().type(), Qgis.GeometryType.Point)

    def simulate_block_reading(self,
                               description: SamplingBlockDescription,
                               lyr: QgsRasterLayer) -> SpectralProfileBlock:

        # simulate reading of requested inputBlock
        self.assertEqual(lyr, description.layer())
        array = rasterArray(lyr, description.rect())
        self.assertEqual(array.shape, (lyr.bandCount(), description.rect().height(), description.rect().width()))
        wl, wlu = parseWavelength(lyr)
        spectral_setting = SpectralSetting(wl, xUnit=wlu)
        inputBlock = SpectralProfileBlock(array, spectral_setting)
        return inputBlock

    def test_MapCanvasLayerProfileSource(self):

        source1 = MapCanvasLayerProfileSource()
        source2 = MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_LAST_LAYER)
        source3 = MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_ALL_LAYERS)
        self.assertEqual(source1.mMode, MapCanvasLayerProfileSource.MODE_FIRST_LAYER)
        self.assertEqual(source2.mMode, MapCanvasLayerProfileSource.MODE_LAST_LAYER)
        self.assertEqual(source3.mMode, MapCanvasLayerProfileSource.MODE_ALL_LAYERS)

        canvas = QgsMapCanvas()
        lyr1 = TestObjects.createRasterLayer()
        lyr2 = TestObjects.createRasterLayer()
        canvas.setLayers([lyr1, lyr2])
        canvas.zoomToFullExtent()

        pt = SpatialPoint.fromMapCanvasCenter(canvas)

        profiles1 = source1.collectProfiles(pt, canvas=canvas)
        profiles2 = source2.collectProfiles(pt, canvas=canvas)
        profiles3 = source3.collectProfiles(pt, canvas=canvas)
        self.assertEqual(len(profiles1), 1)
        self.assertEqual(len(profiles2), 1)
        self.assertEqual(len(profiles3), 2)

        for profiles in [profiles1, profiles2, profiles3]:
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertIsInstance(p, Tuple)
                self.assertTrue(len(p) == 2)
                d, c = p
                self.assertTrue(isProfileValueDict(d))
                self.assertIsInstance(c, QgsExpressionContext)

    def createTestObjects(self) -> Tuple[
        List[QgsRasterLayer], List[SpectralLibraryWidget]
    ]:
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]

        from qpstestdata import enmap, hymap
        lyr1 = QgsRasterLayer(enmap.as_posix(), 'EnMAP')
        lyr2 = QgsRasterLayer(hymap.as_posix(), 'HyMAP')
        # lyr2 = QgsRasterLayer(hymap.as_posix(), 'Sentinel-2')

        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)
        sl.setName('Speclib 1')
        RENAME = {'profiles': 'ASD',
                  'profiles1': 'Sentinel2'}
        with edit(sl):
            for oldName, newName in RENAME.items():
                idx = sl.fields().lookupField(oldName)
                sl.renameAttribute(idx, newName)
            sl.addAttribute(QgsField('px_x', QMETATYPE_INT))
            sl.addAttribute(QgsField('px_y', QMETATYPE_INT))
            sl.addAttribute(QgsField('geo_x', QMETATYPE_DOUBLE))
            sl.addAttribute(QgsField('geo_y', QMETATYPE_DOUBLE))
            sl.addAttribute(QgsField('text', QMETATYPE_QSTRING))
            sl.addAttribute(QgsField('color', QMETATYPE_QSTRING))

        sl.commitChanges()

        slw1 = SpectralLibraryWidget(speclib=sl)
        slw2 = SpectralLibraryWidget(speclib=sl)

        widgets = [slw1, slw2]
        sources = [lyr1, lyr2]

        return sources, widgets

    def test_FieldNodes(self):

        n1 = StandardFieldGeneratorNode()
        n1.setName('n1')
        n1.setCheckState(Qt.Unchecked)
        self.assertFalse(n1.hasErrors())
        n1.setCheckState(Qt.Checked)
        errors = list(n1.errors(recursive=True))

        self.assertTrue(n1.hasErrors())
        self.assertTrue(len(errors) > 0)
        field = QgsField('n1field', QMETATYPE_QSTRING)
        n1.setField(field)
        n1.setExpression("'foobar'")
        errors2 = list(n1.errors(recursive=True))
        self.assertFalse(n1.hasErrors())

        n2 = SpectralProfileGeneratorNode()
        n2.setName('n2')
        errors = list(n2.errors(recursive=True))
        self.assertTrue(n2.hasErrors())

        lyr = TestObjects.createRasterLayer()
        profileSource = StandardLayerProfileSource(lyr)
        n2.setProfileSource(profileSource)
        n2.setField(field)
        errors = list(n2.errors(recursive=True))
        self.assertFalse(n2.hasErrors())

    def test_SpectralFeatureGenerator(self):

        sources, widgets = self.createTestObjects()

        model = SpectralProfileBridge()
        model.addSources(MapCanvasLayerProfileSource())
        model.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_LAST_LAYER))
        model.addSources(sources)
        node = model.createFeatureGenerator()
        # model.createFeatureGenerator()
        model.addSpectralLibraryWidgets(widgets)

        proxyModel = SpectralProfileSourceProxyModel()
        proxyModel.setSourceModel(model)

        tv = SpectralProfileBridgeTreeView()
        tv.setModel(proxyModel)

        delegate = SpectralProfileBridgeViewDelegate(tv)
        delegate.setItemDelegates(tv)
        delegate.setBridge(model)
        self.showGui(tv)

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
