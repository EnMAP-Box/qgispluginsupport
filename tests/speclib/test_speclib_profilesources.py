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

    def test_SpectralProfileSources(self):
        # self.initProcessingRegistry()
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]

        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)

        RENAME = {'profiles': 'ASD', 'profiles1': 'Sentinel2'}
        sl.startEditing()
        for oldName, newName in RENAME.items():
            idx = sl.fields().lookupField(oldName)
            sl.renameAttribute(idx, newName)
            s = ""
        sl.commitChanges()
        SLW = SpectralLibraryWidget(speclib=sl)

        raster_sources = [TestObjects.createRasterLayer(nb=5),
                          TestObjects.createRasterLayer(nb=10)]

        panel = SpectralProfileSourcePanel()
        panel.bridge().addSource(raster_sources)
        self.showGui([SLW, panel])
        s = ""
        pass

    def test_SpectralFeatureGenerator(self):
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]

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

        model = SpectralProfileBridgeV2()
        model.createFeatureGenerator()
        # model.createFeatureGenerator()
        model.addSpectralLibraryWidget(slw1)
        model.addSpectralLibraryWidget(slw2)

        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(model)

        tv = TreeView()
        tv.setModel(proxyModel)

        delegate = SpectralProfileBridgeViewDelegateV2()
        delegate.setItemDelegates(tv)
        delegate.setBridge(model)
        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
