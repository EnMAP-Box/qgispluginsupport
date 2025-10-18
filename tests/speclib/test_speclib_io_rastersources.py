# noinspection PyPep8Naming
import pathlib
import unittest

from qgis.core import QgsFeature, QgsProject, QgsWkbTypes
from qgis.core import QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qps import initAll
from qps import registerExpressionFunctions
from qps.layerproperties import AttributeTableWidget
from qps.speclib.core import is_profile_field, is_spectral_library
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportDialog
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.io.rastersources import RasterLayerSpectralLibraryIO, RasterLayerSpectralLibraryImportWidget
from qps.speclib.processing.extractspectralprofiles import ExtractSpectralProfiles
from qps.testing import TestCase, TestObjects, start_app
from qps.utils import rasterArray

start_app()
initAll()


class TestSpeclibIO_Raster(TestCase):

    def registerIO(self):
        ios = [RasterLayerSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_extract_profiles(self):

        alg = ExtractSpectralProfiles()
        alg.initAlgorithm({})

        rl = TestObjects.createRasterLayer(nb=25)
        vl = TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point, )
        context, feedback = self.createProcessingContextFeedback()

        p = QgsProject()
        p.addMapLayers([rl, vl])
        context.setProject(p)

        if False:
            canvas = QgsMapCanvas()

            canvas.setLayers([vl, rl])
            canvas.setDestinationCrs(vl.crs())
            canvas.zoomToFullExtent()
            self.showGui(canvas)

        dir_test = self.createTestOutputDirectory()

        for i, ext in enumerate(['gpkg', 'geojson']):

            path_test = dir_test / f'profiles{i}.{ext}'

            par = {
                alg.P_INPUT_RASTER: rl,
                alg.P_INPUT_VECTOR: vl,
                alg.P_OUTPUT: path_test.as_posix()
            }
            self.assertTrue(alg.prepareAlgorithm(par, context, feedback))
            results = alg.processAlgorithm(par, context, feedback)

            output = results[alg.P_OUTPUT]
            if isinstance(output, str):
                output = QgsVectorLayer(output)
            self.assertIsInstance(output, QgsVectorLayer)

            if True:
                w = AttributeTableWidget(output)
                self.showGui(w)

            self.assertTrue(is_spectral_library(output))
            self.assertTrue(output.featureCount() > 0)
            self.assertTrue(vl.featureCount() > output.featureCount())

        s = ""
        s = ""

    def test_raster_reading(self):
        registerExpressionFunctions()

        io = RasterLayerSpectralLibraryIO()
        w = RasterLayerSpectralLibraryImportWidget()
        fields = w.sourceFields()

        from qpstestdata import enmap, landcover

        array = rasterArray(enmap)

        aggr = 'none'
        for f in io.readRasterVector(enmap, landcover, fields, aggregation=aggr):

            self.assertIsInstance(f, QgsFeature)
            pf = f.fields().field('profiles')
            self.assertTrue(is_profile_field(pf))
            px = f.attribute('px_x')
            py = f.attribute('px_y')
            profileDict = decodeProfileValueDict(f.attribute('profiles'))
            y1 = profileDict['y']
            y2 = array[:, py, px].tolist()
            if aggr == 'none':
                self.assertListEqual(y1, y2)
            s = ""

    def test_raster_input_widget(self):
        layers = [TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.LineString),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point),
                  TestObjects.createRasterLayer()]

        QgsProject.instance().addMapLayers(layers)
        w = RasterLayerSpectralLibraryImportWidget()
        self.showGui(w)
        QgsProject.instance().removeAllMapLayers()

    def test_read_raster(self):
        self.registerIO()

    def test_write_raster(self):
        self.registerIO()

    @unittest.skipIf(TestCase.runsInCI(), 'Test skipped because it opens a blocking dialog')
    def test_dialog(self):
        self.registerIO()
        layers = [TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.LineString),
                  TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point),
                  TestObjects.createRasterLayer()]

        QgsProject.instance().addMapLayers(layers)

        sl = TestObjects.createSpectralLibrary()
        import qpstestdata

        root = pathlib.Path(qpstestdata.__file__).parent

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())
        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
