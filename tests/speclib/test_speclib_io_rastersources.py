# noinspection PyPep8Naming
import unittest

from qgis.core import QgsProject, QgsWkbTypes
from qgis.core import QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qps import initAll
from qps.layerproperties import AttributeTableWidget
from qps.speclib.core import is_spectral_library
from qps.speclib.processing.extractspectralprofiles import ExtractSpectralProfiles
from qps.testing import TestCase, TestObjects, start_app

start_app()
initAll()


class TestSpeclibIO_Raster(TestCase):

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

            results, success = alg.run(par, context, feedback)

            self.assertTrue(success)

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


if __name__ == '__main__':
    unittest.main(buffer=False)
