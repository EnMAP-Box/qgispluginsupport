# noinspection PyPep8Naming
import random
import unittest
import datetime

import xmlrunner

from qgis.gui import QgsProcessingGuiRegistry, QgsProcessingParameterDefinitionDialog

from qgis.core import QgsProcessingProvider

from qps import initResources, initAll
from qps.maptools import CursorLocationMapTool
from qps.speclib.core import profile_field_lookup
from qps.speclib.gui.spectralprofilesources import SpectralProfileSourcePanel
from qps.testing import TestObjects, StartOptions
from qps.speclib.gui.spectrallibrarywidget import *
from qps.speclib.processing import *
from qps.speclib.processingalgorithms import *
from qps.testing import TestCase, TestAlgorithmProvider
import numpy as np
from qps.speclib.gui.spectralprofilesources import *

class SpectralProcessingTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:
        from qps import QPS_RESOURCE_FILE
        from qps.resources import findQGISResourceFiles
        resources.extend(findQGISResourceFiles())
        resources.append(QPS_RESOURCE_FILE)
        super(SpectralProcessingTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        initAll()

    def initProcessingRegistry(self) -> typing.Tuple[QgsProcessingRegistry, QgsProcessingGuiRegistry]:
        procReg = QgsApplication.instance().processingRegistry()
        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        provider_names = [p.name() for p in procReg.providers()]
        if TestAlgorithmProvider.NAME not in provider_names:
            procGuiReg.addParameterWidgetFactory(SpectralProcessingAlgorithmInputWidgetFactory())
            procGuiReg.addParameterWidgetFactory(SpectralProcessingProfilesOutputWidgetFactory())
            self._profile_type = SpectralProcessingProfileType()
            self.assertTrue(procReg.addParameterType(self._profile_type))

            provider = TestAlgorithmProvider()
            self.assertTrue(procReg.addProvider(provider))
            provider._algs.extend([
                SpectralProfileReader(),
                SpectralProfileWriter(),
                SpectralXUnitConversion(),
                SpectralPythonCodeProcessingAlgorithm()
            ])
            provider.refreshAlgorithms()
            self.mPRov = provider
        return procReg, procGuiReg

    def test_dualview(self):

        n_features = 5000
        # sl = TestObjects.createVectorLayer(n_features=n_features)
        sl: SpectralLibrary = TestObjects.createSpectralLibrary(n_features, n_bands=[177])
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


    def test_SpectralProfileSourcePanel(self):

        sources, spectralLibraryWidget = self.createTestObjects()
        canvas = QgsMapCanvas()
        canvas.setLayers(sources)
        canvas.setDestinationCrs(sources[0].crs())
        canvas.zoomToFullExtent()
        mt = CursorLocationMapTool(canvas, True)
        canvas.setMapTool(mt)
        center = SpatialPoint.fromMapCanvasCenter(canvas)

        panel = SpectralProfileSourcePanel()
        # panel.mBridge.addSources(sources)
        # panel.mBridge.addSpectralLibraryWidgets(widgets)
        panel.createRelation()
        panel.createRelation()

        # add sources
        panel.addSources(sources)

        # add widgets
        panel.addSpectralLibraryWidgets(spectralLibraryWidget)

        slw = SpectralLibraryWidget()
        panel.addSpectralLibraryWidgets(slw)

        g = panel.createRelation()
        self.assertIsInstance(g, SpectralFeatureGeneratorNode)
        n = g.spectralProfileGeneratorNodes()[0]
        self.assertIsInstance(n, SpectralProfileGeneratorNode)
        lyrA = sources[0]
        n.setSource(lyrA)
        mode = n.setSampling(KernelProfileSamplingMode())
        self.assertIsInstance(mode, KernelProfileSamplingMode)
        size = mode.kernelSize()
        g.spectralProfileGeneratorNodes()

        # panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)

        # remove sources
        panel.removeSources(sources)

        # remove widgets
        panel.removeSpectralLibraryWidgets(spectralLibraryWidget)

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

        # re-add destinations
        panel.addSpectralLibraryWidgets([slw1, slw2])

        # re-add sources
        panel.addSources([src1, src2])

        modes = SpectralProfileSamplingModeModel.registeredModes()

        for pgnode in fgnode1.spectralProfileGeneratorNodes():
            pgnode.setSource(src1)
            self.assertIsInstance(pgnode.sampling(), SingleProfileSamplingMode)
            pgnode.setSampling(modes[0])

        for pgnode in fgnode2.spectralProfileGeneratorNodes():
            pgnode.setSource(src2)
            pgnode.setSampling(modes[1])

        RESULTS = panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)
        sl = slw1.speclib()
        self.assertTrue(sl.featureCount() == 1)
        self.assertTrue(sl.id() in RESULTS.keys())

        btnAdd = QPushButton('Random click')
        def onClicked():

            ext = SpatialExtent.fromMapCanvas(canvas)
            x = random.uniform(ext.xMinimum(), ext.xMaximum())
            y = random.uniform(ext.yMinimum(), ext.yMaximum())
            pt = SpatialPoint(ext.crs(), x, y)
            panel.loadCurrentMapSpectra(pt, mapCanvas=canvas, runAsync=False)

        mt.sigLocationRequest.connect(lambda crs, pt: panel.loadCurrentMapSpectra(SpatialPoint(crs, pt)))
        btnAdd.clicked.connect(onClicked)
        hl = QHBoxLayout()
        hl.addWidget(btnAdd)
        vl = QVBoxLayout()
        vl.addLayout(hl)
        vl.addWidget(panel)
        w = QWidget()
        w.setLayout(vl)
        self.showGui([w, slw1, slw2, canvas])

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

                # simulate reading of requested inputBlock
                self.assertEqual(lyr, description.layer())
                array = rasterLayerArray(lyr, description.rect())

                self.assertEqual(array.shape, (lyr.bandCount(), y, x))

                wl, wlu = parseWavelength(lyr)
                spectral_setting = SpectralSetting(wl, xUnit=wlu)
                inputBlock = SpectralProfileBlock(array, spectral_setting)

                outputBlock = mode.profiles(inputBlock, description)
                self.assertIsInstance(outputBlock, SpectralProfileBlock)
                if aggregation == KernelProfileSamplingMode.NO_AGGREGATION:
                   self.assertTrue(outputBlock.n_profiles() == x*y)
                else:
                   self.assertTrue(outputBlock.n_profiles() == 1)

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
            positions = mode.samplingBlockDescription(lyr, center)
            self.assertIsInstance(positions, list)


            p = center
            bbox = QgsRectangle(center, center)
            bbox.setXMaximum(bbox.xMinimum() + 100)
            bbox.setYMinimum(bbox.yMinimum() - 100)

            r1 = lyr.dataProvider().identify(p, QgsRaster.IdentifyFormatValue)
            r2 = lyr.dataProvider().identify(p, QgsRaster.IdentifyFormatValue, boundingBox=bbox)

            r3 = lyr.dataProvider().identify(p, QgsRaster.IdentifyFormatHtml)

            for pos in positions:
                self.assertIsInstance(pos, QgsPointXY)


        cb = QComboBox()
        cb.setModel(model)
        self.showGui(cb)

    def createTestObjects(self) -> typing.Tuple[
        typing.List[QgsRasterLayer], typing.List[SpectralLibraryWidget]
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

    def test_SpectralFeatureGenerator(self):
        layers, widgets = self.initProcessingRegistry()

        model = SpectralProfileBridge()
        model.addSources(layers)
        model.createFeatureGenerator()
        # model.createFeatureGenerator()
        model.addSpectralLibraryWidgets(widgets)

        proxyModel = SpectralProfileSourceProxyModel()
        proxyModel.setSourceModel(model)

        tv = SpectralProfileBridgeTreeView()
        tv.setModel(proxyModel)

        delegate = SpectralProfileBridgeViewDelegate()
        delegate.setItemDelegates(tv)
        delegate.setBridge(model)
        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
