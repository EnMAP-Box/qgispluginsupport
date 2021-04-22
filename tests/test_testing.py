# coding=utf-8
"""Resources test.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'

import xmlrunner
from qgis._core import QgsProcessingProvider, QgsProcessingModelAlgorithm, QgsProcessingFeedback, QgsProcessingContext, \
    QgsProcessingAlgorithm

from qgis.core import QgsProject, QgsApplication, QgsVectorLayer, QgsCoordinateReferenceSystem, \
    QgsProcessingRegistry, QgsLayerTree, QgsLayerTreeModel
from qgis.gui import QgsLayerTreeView,  QgisInterface, QgsGui
import unittest
import qps.testing
from osgeo import gdal
import numpy as np

from qps.speclib.core.spectralprofile import SpectralProfileBlock


class testClassTesting(unittest.TestCase):

    def test_init(self):
        import qps.testing
        self.assertTrue(qps.testing != None)

        qgis_app = qps.testing.start_app(options=qps.testing.StartOptions.All)

        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)

        self.assertTrue(len(qgis_app.processingRegistry().providers()) > 0)

        self.assertIsInstance(qgis_app.processingRegistry(), QgsProcessingRegistry)
        self.assertTrue(len(qgis_app.processingRegistry().algorithms()) > 0)

        self.assertIsInstance(QgsGui.instance(), QgsGui)
        self.assertTrue(len(QgsGui.instance().editorWidgetRegistry().factories()) > 0,
                        msg='Standard QgsEditorWidgetWrapper not initialized')

        # test iface
        import qgis.utils
        iface = qgis.utils.iface

        self.assertIsInstance(iface, QgisInterface)
        self.assertIsInstance(iface, qps.testing.QgisMockup)

        lyr1 = qps.testing.TestObjects.createVectorLayer()
        lyr2 = qps.testing.TestObjects.createVectorLayer()

        self.assertIsInstance(iface.layerTreeView(), QgsLayerTreeView)
        self.assertIsInstance(iface.layerTreeView().layerTreeModel(), QgsLayerTreeModel)
        root = iface.layerTreeView().layerTreeModel().rootGroup()
        self.assertIsInstance(root, QgsLayerTree)
        self.assertEqual(len(root.findLayers()), 0)

        # QgsProject.instance().layersAdded.connect(lambda : print('ADDED'))
        # QgsProject.instance().legendLayersAdded.connect(lambda: print('ADDED LEGEND'))

        QgsProject.instance().addMapLayer(lyr1, False)
        QgsProject.instance().addMapLayer(lyr2, True)

        QgsApplication.processEvents()

        self.assertTrue(lyr1.id() not in root.findLayerIds())
        self.assertTrue(lyr2.id() in root.findLayerIds())

        app = QgsApplication.instance()
        ENV = app.systemEnvVars()
        for k in sorted(ENV.keys()):
            print('{}={}'.format(k, ENV[k]))

        qgis_app.quit()

    def test_init_minimal(self):
        qgis_app = qps.testing.start_app(options=qps.testing.StartOptions.Minimized)

        self.assertIsInstance(qgis_app, QgsApplication)
        self.assertIsInstance(qgis_app.libexecPath(), str)
        qgis_app.quit()




class test_TestObject(qps.testing.TestCase):

    def test_spectralProfiles(self):
        from qps.testing import TestObjects

        profiles = list(TestObjects.spectralProfiles(10))
        self.assertIsInstance(profiles, list)
        self.assertTrue(len(profiles) == 10)

    def test_VectorLayers(self):
        from qps.testing import TestObjects
        from osgeo import ogr

        ds = TestObjects.createVectorDataSet(wkb=ogr.wkbPoint)
        self.assertIsInstance(ds, ogr.DataSource)
        self.assertTrue(ds.GetLayerCount() == 1)
        lyr = ds.GetLayer(0)
        self.assertIsInstance(lyr, ogr.Layer)
        self.assertEqual(lyr.GetGeomType(), ogr.wkbPoint)
        self.assertTrue(lyr.GetFeatureCount() > 0)

        ds = TestObjects.createVectorDataSet(wkb=ogr.wkbLineString)
        self.assertIsInstance(ds, ogr.DataSource)
        self.assertTrue(ds.GetLayerCount() == 1)
        lyr = ds.GetLayer(0)
        self.assertIsInstance(lyr, ogr.Layer)

        self.assertTrue(lyr.GetFeatureCount() > 0)
        self.assertEqual(lyr.GetGeomType(), ogr.wkbLineString)

        lyr = TestObjects.createVectorLayer()
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        self.assertIsInstance(lyr.crs(), QgsCoordinateReferenceSystem)
        self.assertTrue(lyr.crs().isValid())

    def test_processingProvider(self):
        from qps.testing import TestObjects
        prov = TestObjects.createProcessingProvider()
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        self.assertIsInstance(prov, QgsProcessingProvider)
        self.assertTrue(reg.providerById(prov.id()) == prov)

        prov2 = TestObjects.createProcessingProvider()
        self.assertEqual(prov, prov2)

    def test_spectralProcessingAlgorithms(self):

        from qps.testing import TestObjects, SpectralProcessingAlgorithmExample
        from qps.speclib.processing import is_spectral_processing_algorithm

        alg: SpectralProcessingAlgorithmExample = TestObjects.createSpectralProcessingAlgorithm()
        self.assertIsInstance(alg, QgsProcessingAlgorithm)
        self.assertIsInstance(alg, SpectralProcessingAlgorithmExample)
        self.assertTrue(is_spectral_processing_algorithm(alg))

        speclib = TestObjects.createSpectralLibrary()
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)

        parameters = {alg.INPUT: speclib}
        success, msg = alg.checkParameterValues(parameters, context)
        self.assertTrue(success, msg=msg)
        self.assertTrue(alg.prepareAlgorithm(parameters, context, feedback))

        results, success = alg.run(parameters, context, feedback)
        self.assertTrue(success)
        self.assertTrue(alg.OUTPUT in results.keys())
        self.assertIsInstance(results[alg.OUTPUT], list)
        for block in results[alg.OUTPUT]:
            assert isinstance(block, SpectralProfileBlock)

    def test_spectralProcessingModel(self):

        from qps.testing import TestObjects
        from qps.speclib.processing import is_spectral_processing_model
        model = TestObjects.createSpectralProcessingModel()
        self.assertIsInstance(model, QgsProcessingModelAlgorithm)
        self.assertTrue(is_spectral_processing_model(model))

        speclib = TestObjects.createSpectralLibrary()

        # outputID = calgW.modelOutput('speclib_target').childId()
        parameters = {'input_profiles': speclib}
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)
        success, msg = model.checkParameterValues(parameters, context)
        self.assertTrue(success, msg=msg)
        self.assertTrue(model.prepareAlgorithm(parameters, context, feedback))
        results, success = model.run(parameters, context, feedback)
        self.assertTrue(success)

        results = model.processAlgorithm(parameters, context, feedback)
        self.assertIsInstance(results, dict)

        from qps.speclib.processing import outputParameterResult
        for p in model.outputDefinitions():
            result1 = outputParameterResult(results, p)
            result2 = outputParameterResult(results, p.name())
            self.assertEqual(result1, result2)
            self.assertIsInstance(result1, list)
            for b in result1:
                self.assertIsInstance(b, SpectralProfileBlock)

        self.assertTrue(success)


    def test_coredata(self):
        from qps.testing import TestObjects
        import numpy as np
        array, wl, wlu, gt, wkt = TestObjects.coreData()
        self.assertIsInstance(array, np.ndarray)
        self.assertIsInstance(wl, np.ndarray)
        self.assertTrue(len(wl) > 0)
        self.assertIsInstance(wlu, str)
        self.assertTrue(len(gt) == 6)
        self.assertIsInstance(wkt, str)

    def test_RasterData(self):
        from qps.testing import TestObjects

        cl = TestObjects.createRasterDataset(10, 20, nc=7)
        self.assertIsInstance(cl, gdal.Dataset)
        self.assertEqual(cl.RasterCount, 1)
        self.assertEqual(cl.RasterXSize, 10)
        self.assertEqual(cl.RasterYSize, 20)

        classNames = cl.GetRasterBand(1).GetCategoryNames()
        self.assertEqual(len(classNames), 7)

        ns = 250
        nl = 100
        nb = 10
        ds = TestObjects.createRasterDataset(ns, nl, nb=nb, eType=gdal.GDT_Float32)
        self.assertIsInstance(ds, gdal.Dataset)
        from qps.utils import parseWavelength
        wl, wlu = parseWavelength(ds)
        self.assertIsInstance(wl, np.ndarray)
        self.assertIsInstance(wlu, str)

        self.assertEqual(ds.RasterCount, nb)
        self.assertEqual(ds.RasterXSize, ns)
        self.assertEqual(ds.RasterYSize, nl)
        self.assertEqual(ds.GetRasterBand(1).DataType, gdal.GDT_Float32)

        dsSrc = TestObjects.createRasterDataset(100, 100, 1)
        woptions = gdal.WarpOptions(dstSRS='EPSG:4326')
        pathDst = '/vsimem/warpDest.tif'
        dsDst = gdal.Warp(pathDst, dsSrc, options=woptions)
        self.assertIsInstance(dsDst, gdal.Dataset)

    def test_Speclibs(self):
        from qps.testing import TestObjects
        from qps.speclib.core.spectrallibrary import SpectralLibrary
        slib = TestObjects.createSpectralLibrary(7)
        self.assertIsInstance(slib, SpectralLibrary)
        self.assertTrue(len(slib) == 7)


if __name__ == "__main__":

    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
