# noinspection PyPep8Naming
import datetime
import random
import unittest
from typing import Tuple, List

from PyQt5.QtCore import QSize
from qgis.PyQt.QtWidgets import QComboBox, QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QGridLayout
from qgis._core import QgsExpressionContext, QgsPoint, QgsPointXY, QgsMapToPixel
from qgis.core import QgsRasterDataProvider, QgsVectorLayer, QgsFeature, QgsWkbTypes
from qgis.core import QgsRasterLayer, QgsProject
from qgis.gui import QgsMapCanvas, QgsDualView
from qps.maptools import CursorLocationMapTool
from qps.speclib.core import is_profile_field
from qps.speclib.core.spectralprofile import SpectralProfileBlock, SpectralSetting, isProfileValueDict
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprofilesources import SpectralProfileSourcePanel, SpectralProfileSourceProxyModel, \
    SpectralProfileBridgeTreeView, SpectralProfileBridgeViewDelegate, KernelProfileSamplingMode, \
    SingleProfileSamplingMode, SpectralProfileSamplingModeModel, SpectralProfileSamplingMode, \
    SamplingBlockDescription, \
    SpectralProfileBridge, MapCanvasLayerProfileSource, SpectralFeatureGeneratorNode, SpectralProfileGeneratorNode, \
    SpectralProfileSourceModel, StandardLayerProfileSource
from qps.testing import TestCaseBase, start_app
from qps.testing import TestObjects
from qps.utils import SpatialPoint, spatialPoint2px, parseWavelength, rasterArray, SpatialExtent

start_app()


class SpectralProcessingTests(TestCaseBase):

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
        lyr: QgsRasterLayer = QgsRasterLayer(enmap)
        lyr.setName('EnMAP')
        ext = lyr.extent()

        dp: QgsRasterDataProvider = lyr.dataProvider()
        nb, ns, nl = lyr.bandCount(), lyr.height(), lyr.width()
        pxx, pxy = lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY()

        out_of_image = [
            SpatialPoint(lyr.crs(), ext.xMinimum() - 0.0001 * pxx, ext.yMaximum()),
            SpatialPoint(lyr.crs(), ext.xMaximum() + 0.0001 * pxx, ext.yMaximum())
        ]

        SpectralProfileSamplingModeModel.registerMode(SingleProfileSamplingMode())
        SpectralProfileSamplingModeModel.registerMode(KernelProfileSamplingMode())

        sp_mode = SingleProfileSamplingMode()
        k_mode = KernelProfileSamplingMode()
        k_mode.setKernelSize(3, 3)
        k_mode.setAggregation(KernelProfileSamplingMode.NO_AGGREGATION)

        for pt in out_of_image:
            self.assertFalse(lyr.extent().contains(pt))
            pos = spatialPoint2px(lyr, pt)
            blockInfo = sp_mode.samplingBlockDescription(lyr, pt)
            self.assertTrue(blockInfo is None)

            blockInfo = k_mode.samplingBlockDescription(lyr, pt)
            self.assertIsInstance(blockInfo, SamplingBlockDescription)
            outputProfileBlock = self.simulate_block_reading(blockInfo, lyr)

        slw = SpectralLibraryWidget()
        panel = SpectralProfileSourcePanel()
        panel.addSources(lyr)
        panel.addSpectralLibraryWidgets(slw)
        gnode = panel.createRelation()
        gnode.setSpeclibWidget(slw)
        for n in gnode.spectralProfileGeneratorNodes():
            n.setProfileSource(lyr)

        canvas = QgsMapCanvas()
        canvas.setLayers([slw.speclib(), lyr])
        canvas.zoomToFullExtent()
        mt = CursorLocationMapTool(canvas, showCrosshair=True)
        mt.sigLocationRequest.connect(lambda crs, pt: panel.loadCurrentMapSpectra(SpatialPoint(crs, pt)))
        canvas.setMapTool(mt)

        self.showGui([canvas, panel, slw])

    def test_SpectralProfileSourcePanel(self):

        sources, spectralLibraryWidget = self.createTestObjects()
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
        panel.addSpectralLibraryWidgets(spectralLibraryWidget)

        slw = SpectralLibraryWidget()
        panel.addSpectralLibraryWidgets(slw)

        g = panel.createRelation()
        self.assertIsInstance(g, SpectralFeatureGeneratorNode)
        self.assertEqual(g.name(), g.speclib().name())

        g.speclib().setName('NewName')
        self.assertEqual(g.name(), g.speclib().name())

        n = g.spectralProfileGeneratorNodes()[0]
        self.assertIsInstance(n, SpectralProfileGeneratorNode)
        lyrA = sources[0]
        n.setProfileSource(lyrA)
        mode = n.setSampling(KernelProfileSamplingMode())
        self.assertIsInstance(mode, KernelProfileSamplingMode)
        size = mode.kernelSize()
        g.spectralProfileGeneratorNodes()

        # panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)

        # remove sources
        panel.removeSources(sources)

        # remove widgets
        panel.removeSpectralLibraryWidgets(spectralLibraryWidget)

        slw.close()

        (src1, src2), (slw1, slw2) = self.createTestObjects()

        # re-add generators
        fgnode1 = panel.createRelation()
        fgnode2 = panel.createRelation()
        for n in [fgnode1, fgnode2]:
            self.assertIsInstance(n, SpectralFeatureGeneratorNode)
        fgnode1.setSpeclibWidget(slw1)
        fgnode2.setSpeclibWidget(slw2)

        # clear test speclibs
        for slw in [slw1, slw2]:
            slw.speclib().startEditing()
            slw.speclib().selectAll()
            slw.speclib().deleteSelectedFeatures()
            slw.speclib().commitChanges()

        speclib_sources = [slw1.speclib(), slw2.speclib()]
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

        modes = SpectralProfileSamplingModeModel.registeredModes()

        for o, pgnode in enumerate(fgnode1.spectralProfileGeneratorNodes()):
            pgnode.setProfileSource(map_sources[0])
            self.assertIsInstance(pgnode.sampling(), SingleProfileSamplingMode)
            pgnode.setSampling(modes[0])
            pgnode.setScaling(o * 10, 1)

        for pgnode in fgnode2.spectralProfileGeneratorNodes():
            pgnode.setProfileSource(map_sources[-1])
            pgnode.setSampling(modes[1])

        RESULTS = panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)
        sl = slw1.speclib()
        self.assertTrue(sl.featureCount() == 1)
        self.assertTrue(sl.id() in RESULTS.keys())
        for speclib_ids, profiles in RESULTS.items():
            for profile in profiles:
                self.assertIsInstance(profile, QgsFeature)
                self.assertTrue(profile.geometry().type() == QgsWkbTypes.PointGeometry)

        btnAdd = QPushButton('Random click')

        def onClicked():
            ext = SpatialExtent.fromMapCanvas(canvas)
            x = random.uniform(ext.xMinimum(), ext.xMaximum())
            y = random.uniform(ext.yMinimum(), ext.yMaximum())
            pt = SpatialPoint(ext.crs(), x, y)
            panel.loadCurrentMapSpectra(pt, mapCanvas=canvas, runAsync=False)

        def onDestroyed():
            print('destroyed sli')

        def onClosing():
            print('Closing sli')

        for sli in panel.mBridge.destinations():
            sli.destroyed.connect(onDestroyed)
            sli.sigWindowIsClosing.connect(onClosing)

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

        grid = QGridLayout()
        grid.addWidget(canvas, 0, 0)
        grid.addWidget(w, 1, 0)
        grid.addWidget(slw1, 0, 1)
        grid.addWidget(slw2, 1, 1)
        w2 = QWidget()
        w2.setLayout(grid)
        self.showGui(w2)
        QgsProject.instance().removeAllMapLayers()

    def validate_profile_data(self, profileData, lyr: QgsRasterLayer, ptR: QgsPointXY):

        array = rasterArray(lyr)

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
            pxR = m2p.transform(ptR)
            px_xR, px_yR = int(pxR.x()), int(pxR.y())

            px_x = context.variable('px_x')
            px_y = context.variable('px_y')

            self.assertEqual(px_xR, px_x)
            self.assertEqual(px_yR, px_y)

            yValues = d['y']
            yValuesR = array[:, px_y, px_x].tolist()

            if yValues != yValuesR:
                s = ""
            self.assertListEqual(yValues, yValuesR)

    def test_spectral_profile_source_model(self):

        lyr1 = TestObjects.createRasterLayer(nb=2, ns=5, nl=5)
        lyr2 = TestObjects.createRasterLayer(nb=25, ns=5, nl=5)
        pt1 = SpatialPoint.fromPixelPosition(lyr1, 0.5, 0.5)
        pt2 = SpatialPoint.fromPixelPosition(lyr1, 1.5, 1.5)

        model = SpectralProfileSourceModel()
        self.assertTrue(len(model) == 0)

        src1 = StandardLayerProfileSource(lyr1)
        src2 = StandardLayerProfileSource(lyr2)

        model.addSources([src1, src1, src2])
        self.assertEqual(len(model), 2)

        sources = model[:]
        self.assertListEqual(sources, [src1, src2])
        for src in model:
            for pt in [pt1, pt2]:
                self.assertIsInstance(src, StandardLayerProfileSource)
                src: StandardLayerProfileSource

                lyr: QgsRasterLayer = src.mLayer

                profileData1 = src.collectProfiles(pt)
                self.assertTrue(len(profileData1) == 1)
                self.validate_profile_data(profileData1, lyr, pt)

                profileData2 = src.collectProfiles(pt, QSize(3, 3))
                self.validate_profile_data(profileData2, lyr, pt)

                profileData3 = src.collectProfiles(pt, QSize(5, 2))
                self.validate_profile_data(profileData3, lyr, pt)

    def test_kernelSampling(self):

        mode = KernelProfileSamplingMode()

        aggregations = [KernelProfileSamplingMode.NO_AGGREGATION,
                        KernelProfileSamplingMode.AGGREGATE_MEAN,
                        KernelProfileSamplingMode.AGGREGATE_MEDIAN,
                        KernelProfileSamplingMode.AGGREGATE_MIN,
                        KernelProfileSamplingMode.AGGREGATE_MAX]
        kernels = ['3x3', '4x4', '5x5']
        from qpstestdata import enmap
        lyr = QgsRasterLayer(enmap)
        center = lyr.extent().center()

        for aggregation in aggregations:
            for kernel in kernels:
                mode.setKernelSize(kernel)
                mode.setAggregation(aggregation)

                x, y = mode.kernelSize()
                self.assertEqual(kernel, f'{x}x{y}')
                self.assertEqual(aggregation, mode.aggregation())

                description = mode.samplingBlockDescription(lyr, center)
                self.assertIsInstance(description, SamplingBlockDescription)
                w, h = description.rect().width(), description.rect().height()
                self.assertEqual((x, y), (w, h)), f'Sampling block size is {w}x{h} instead {kernel}'

                inputBlock = self.simulate_block_reading(description, lyr)

                outputBlock = mode.profiles(inputBlock, description)
                self.assertIsInstance(outputBlock, SpectralProfileBlock)
                if aggregation == KernelProfileSamplingMode.NO_AGGREGATION:
                    self.assertTrue(outputBlock.n_profiles() == x * y)
                else:
                    self.assertTrue(outputBlock.n_profiles() == 1)

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
        source2 = MapCanvasLayerProfileSource(MapCanvasLayerProfileSource.MODE_LAST_LAYER)
        self.assertEqual(source1.mMode, MapCanvasLayerProfileSource.MODE_FIRST_LAYER)
        self.assertEqual(source2.mMode, MapCanvasLayerProfileSource.MODE_LAST_LAYER)

        self.assertEqual(source1.toolTip(), MapCanvasLayerProfileSource.MODE_TOOLTIP[source1.mMode])
        self.assertEqual(source2.toolTip(), MapCanvasLayerProfileSource.MODE_TOOLTIP[source2.mMode])

        canvas = QgsMapCanvas()
        lyr1 = TestObjects.createRasterLayer()
        lyr2 = TestObjects.createRasterLayer()
        canvas.setLayers([lyr1, lyr2])
        canvas.zoomToFullExtent()

        self.assertEqual(lyr1, source1.rasterLayer(canvas, canvas.center()))
        self.assertEqual(lyr2, source2.rasterLayer(canvas, canvas.center()))

    def test_ProfileSamplingModel(self):

        from qpstestdata import enmap

        lyr = QgsRasterLayer(enmap)
        center = SpatialPoint.fromMapLayerCenter(lyr)

        modes = [SingleProfileSamplingMode,
                 KernelProfileSamplingMode]
        for m in modes:
            SpectralProfileSamplingModeModel.registerMode(m())
        model = SpectralProfileSamplingModeModel()

        for mode in model:
            print(f'Test: {mode.__class__.__name__}')
            assert isinstance(mode, SpectralProfileSamplingMode)
            blockDescription = mode.samplingBlockDescription(lyr, center)
            self.assertIsInstance(blockDescription, SamplingBlockDescription)

            inputBlock = self.simulate_block_reading(blockDescription, lyr)
            self.assertIsInstance(inputBlock, SpectralProfileBlock)
            outputBlock = mode.profiles(inputBlock, blockDescription)
            self.assertIsInstance(outputBlock, SpectralProfileBlock)

        cb = QComboBox()
        cb.setModel(model)
        self.showGui(cb)

    def createTestObjects(self) -> Tuple[
        List[QgsRasterLayer], List[SpectralLibraryWidget]
    ]:
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]

        from qpstestdata import enmap, hymap
        lyr1 = QgsRasterLayer(enmap, 'EnMAP')
        lyr2 = QgsRasterLayer(hymap, 'HyMAP')
        lyr2 = QgsRasterLayer(hymap, 'Sentinel-2')

        modes = [SingleProfileSamplingMode,
                 KernelProfileSamplingMode]
        for m in modes:
            SpectralProfileSamplingModeModel.registerMode(m())

        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)
        sl.setName('Speclib 1')
        RENAME = {'profiles': 'ASD', 'profiles1': 'Sentinel2'}
        sl.startEditing()
        for oldName, newName in RENAME.items():
            idx = sl.fields().lookupField(oldName)
            sl.renameAttribute(idx, newName)
            s = ""
        sl.commitChanges()

        slw1 = SpectralLibraryWidget(speclib=sl)
        slw2 = SpectralLibraryWidget()
        slw2.speclib().setName('Speclib 2')

        widgets = [slw1, slw2]
        sources = [lyr1, lyr2]

        return sources, widgets

    def test_SpectralProfileBridge(self):

        sources, widgets = self.createTestObjects()
        lyr1 = sources[0]
        point = SpatialPoint(lyr1.crs(), lyr1.extent().center())
        model = SpectralProfileBridge()
        model.addSources(MapCanvasLayerProfileSource())
        model.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_LAST_LAYER))
        model.addSources(sources)
        g = model.createFeatureGenerator()
        # model.createFeatureGenerator()
        model.addSpectralLibraryWidgets(widgets)
        results = model.loadProfilesV2(point)
        s = ""

    def test_SpectralFeatureGenerator(self):

        sources, widgets = self.createTestObjects()

        model = SpectralProfileBridge()
        model.addSources(MapCanvasLayerProfileSource())
        model.addSources(MapCanvasLayerProfileSource(mode=MapCanvasLayerProfileSource.MODE_LAST_LAYER))
        model.addSources(sources)
        model.createFeatureGenerator()
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


if __name__ == '__main__':
    unittest.main(buffer=False)
