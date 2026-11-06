import copy
import unittest

import numpy as np
from osgeo import gdal
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import (
    QgsApplication, QgsProcessingAlgorithm, QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputRasterLayer, QgsProcessingException,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterNumber, QgsProcessingParameterRasterDestination,
)

from qps import initAll
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.reimplementation.processingalgorithmdialog import ProcessingAlgorithmDialog
from qps.speclib.gui.spectralprocessingalgorithmmodel import SpectralProcessingAlgorithmModel
from qps.testing import ExampleAlgorithmProvider, TestCase, start_app

start_app()
initAll()


class ExampleRasterProcessing(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    N_BANDS = 'N_BANDS'

    def __init__(self):
        super().__init__()

    def createInstance(self):
        return ExampleRasterProcessing()

    def name(self):
        return 'examplerasterprocessing'

    def displayName(self):
        return 'Example Raster Processing'

    def groupId(self):
        return 'exampleapp'

    def group(self):
        return 'Example Applications'

    def shortHelpString(self):
        return 'Processes a raster layer and outputs a new raster with n bands'

    def initAlgorithm(self, configuration=None):

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT,
                'Input raster layer',
                optional=False
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.N_BANDS,
                'Number of output bands',
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=3,
                minValue=1
            )
        )
        p = QgsProcessingParameterRasterDestination(
            self.OUTPUT,
            'Output raster layer'
        )

        self.addParameter(p)

    def processAlgorithm(self, parameters, context, feedback):

        # Get input parameters
        input_layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        n_bands = self.parameterAsInt(parameters, self.N_BANDS, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        if not input_layer or not input_layer.isValid():
            raise QgsProcessingException('Invalid input raster layer')

        if n_bands < 1:
            raise QgsProcessingException('Number of bands must be at least 1')

        feedback.pushInfo(f'Processing raster: {input_layer.name()}')
        feedback.pushInfo(f'Input bands: {input_layer.bandCount()}')
        feedback.pushInfo(f'Output bands: {n_bands}')

        # Open input with GDAL
        spectral_settings_in = QgsRasterLayerSpectralProperties.fromRasterLayer(input_layer)
        input_ds = gdal.Open(input_layer.source())
        if not input_ds:
            raise QgsProcessingException('Could not open input raster with GDAL')

        input_band_count = input_ds.RasterCount
        rows = input_ds.RasterYSize
        cols = input_ds.RasterXSize

        feedback.setProgress(10)

        # Read input data
        feedback.pushInfo('Reading input bands...')
        input_data = []
        for i in range(1, input_band_count + 1):
            if feedback.isCanceled():
                return {}

            band = input_ds.GetRasterBand(i)
            data = band.ReadAsArray()
            input_data.append(data)

            progress = 10 + int(30 * i / input_band_count)
            feedback.setProgress(progress)

        input_data = np.array(input_data)

        # Process: resample to n bands
        feedback.setProgress(40)
        feedback.pushInfo(f'Resampling from {input_band_count} to {n_bands} bands...')
        wl_in = spectral_settings_in.wavelengths()
        wl_out = []
        if n_bands == input_band_count:
            # No resampling needed
            output_data = input_data
            if np.any(wl_in):
                wl_out = wl_in
        elif n_bands < input_band_count:
            # Downsample: select evenly spaced bands
            indices = np.linspace(0, input_band_count - 1, n_bands, dtype=int)
            if np.any(wl_in):
                wl_out = [wl_in[i] for i in indices]

            output_data = input_data[indices]
            feedback.pushInfo(f'Downsampling: selected bands at indices {indices.tolist()}')
        else:
            # Upsample: interpolate between bands
            feedback.pushInfo('Upsampling: interpolating between bands...')
            indices_old = np.arange(input_band_count)
            indices_new = np.linspace(0, input_band_count - 1, n_bands)
            output_data = np.zeros((n_bands, rows, cols), dtype=input_data.dtype)

            if np.any(wl_in):
                wl_out = np.interp(indices_new, indices_old, wl_in)

            for row in range(rows):
                if feedback.isCanceled():
                    return {}

                for col in range(cols):
                    output_data[:, row, col] = np.interp(
                        indices_new,
                        indices_old,
                        input_data[:, row, col]
                    )

                if row % 100 == 0:
                    progress = 40 + int(50 * row / rows)
                    feedback.setProgress(progress)

        feedback.setProgress(90)
        feedback.pushInfo('Writing output raster...')

        # Create output raster
        driver = gdal.GetDriverByName('GTiff')
        data_type = input_ds.GetRasterBand(1).DataType
        output_ds = driver.Create(output_path, cols, rows, n_bands, data_type)

        if not output_ds:
            raise QgsProcessingException('Could not create output raster')

        # Copy geotransform and projection
        output_ds.SetGeoTransform(input_ds.GetGeoTransform())
        output_ds.SetProjection(input_ds.GetProjection())

        # Write bands
        for i in range(n_bands):
            band = output_ds.GetRasterBand(i + 1)
            band.WriteArray(output_data[i])
            band.FlushCache()

            if i < len(wl_out):
                wl_ = wl_out[i]
                if wl_:
                    band.SetMetadataItem('CENTRAL_WAVELENGTH_UM', str(wl_), 'IMAGERY')
            # Set nodata value if available
            input_band = input_ds.GetRasterBand(1)
            nodata = input_band.GetNoDataValue()
            if nodata is not None:
                band.SetNoDataValue(nodata)

        # Clean up
        input_ds = None
        output_ds = None

        feedback.setProgress(100)
        feedback.pushInfo('Processing complete!')

        return {self.OUTPUT: output_path}


class AlgorithmLogging(QgsProcessingAlgorithm):

    def __init__(self, logs: dict, name='exampleLoginAlg'):
        super(AlgorithmLogging, self).__init__()
        self._name = name
        self._log = logs

    def createInstance(self):
        return AlgorithmLogging(copy.deepcopy(self._log), name=self.name())

    def name(self):
        return self._name

    def displayName(self):
        return 'Example Algorithm with log'

    def groupId(self):
        return 'exampleapp'

    def group(self):
        return 'TEST APPS'

    def initAlgorithm(self, configuration=None):
        # no inputs, but outputs
        self.addOutput(QgsProcessingOutputRasterLayer('outputProfile',
                                                      'An output raster layer'))

    def processAlgorithm(self, parameters: dict, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        outputs = {}
        for funcName, msg in self._log.items():
            feedback.pushInfo(f'Test "{funcName}"<-"{msg}"')
            func = getattr(feedback, funcName)
            func(msg)
            outputs[funcName] = msg

        outputs['outputProfile'] = 'foobar.tif'
        return outputs


class SpectralProcessingGuiTests(TestCase):

    def algorithmProviderTesting(self) -> 'ExampleAlgorithmProvider':
        return QgsApplication.instance().processingRegistry().providerById(ExampleAlgorithmProvider.NAME.lower())

    def test_ProcessingAlgorithmDialog(self):
        model = SpectralProcessingAlgorithmModel()
        d = ProcessingAlgorithmDialog()
        d.setAlgorithmModel(model)

        if d.exec() == QDialog.DialogCode.Accepted:
            self.assertIsInstance(d.algorithm(), QgsProcessingAlgorithm)
        if d.exec() == QDialog.DialogCode.Accepted:
            self.assertIsInstance(d.algorithm(), QgsProcessingAlgorithm)

        self.showGui(d)

        self.assertIsInstance(d, ProcessingAlgorithmDialog)


if __name__ == '__main__':
    unittest.main(buffer=False)
