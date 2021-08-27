# noinspection PyPep8Naming
import unittest
import datetime

import xmlrunner

from qgis.gui import QgsProcessingGuiRegistry, QgsProcessingParameterDefinitionDialog

from qgis.core import QgsProcessingProvider

from qps import initResources, initAll
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

        sources, widgets = self.createTestObjects()
        canvas = QgsMapCanvas()
        center = SpatialPoint.fromMapCanvasCenter(canvas)

        panel = SpectralProfileSourcePanel()
        # panel.mBridge.addSources(sources)
        # panel.mBridge.addSpectralLibraryWidgets(widgets)
        panel.createRelation()
        panel.createRelation()

        # add sources
        panel.mBridge.addSources(sources)

        # add widgets
        panel.mBridge.addSpectralLibraryWidgets(widgets)

        panel.loadCurrentMapSpectra(center, mapCanvas=canvas, runAsync=False)

        # remove sources
        for s in sources:
            panel.mBridge.removeSource(s)

        # remove widgets
        for w in widgets:
            panel.mBridge.removeDestination(w)

        self.showGui(panel)

        a = np.ndarray

        c = a != 2
        b = a != a



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
            positions = mode.profilePositions(lyr, center)
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
