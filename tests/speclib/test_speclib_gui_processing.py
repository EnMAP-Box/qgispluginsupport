import copy
# noinspection PyPep8Naming
import unittest

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtWidgets import QGridLayout, QWidget
from qgis.core import QgsApplication, QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingFeedback, \
    QgsProcessingOutputRasterLayer, QgsProcessingRegistry, QgsProject, \
    QgsVectorLayer, edit, QgsProcessingException
from qgis.core import (QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterNumber, QgsRasterFileWriter,
                       QgsProcessingParameterRasterDestination)
from qgis.gui import QgsProcessingAlgorithmDialogBase, QgsProcessingContextGenerator, \
    QgsProcessingGui, QgsProcessingParameterWidgetContext
from qps import initAll
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.speclib.core import profile_field_list
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprocessingdialog import SpectralProcessingDialog, \
    SpectralProcessingRasterLayerWidgetWrapper
from qps.testing import ExampleAlgorithmProvider, TestCase, TestObjects, start_app

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
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=3,
                minValue=1
            )
        )
        p = QgsProcessingParameterRasterDestination(
            self.OUTPUT,
            'Output raster layer'
        )

        self.addParameter(p)

        s = ""

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

        if n_bands == input_band_count:
            # No resampling needed
            output_data = input_data
        elif n_bands < input_band_count:
            # Downsample: select evenly spaced bands
            indices = np.linspace(0, input_band_count - 1, n_bands, dtype=int)
            output_data = input_data[indices]
            feedback.pushInfo(f'Downsampling: selected bands at indices {indices.tolist()}')
        else:
            # Upsample: interpolate between bands
            feedback.pushInfo('Upsampling: interpolating between bands...')
            indices_old = np.arange(input_band_count)
            indices_new = np.linspace(0, input_band_count - 1, n_bands)
            output_data = np.zeros((n_bands, rows, cols), dtype=input_data.dtype)

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


class SpectralProcessingTests(TestCase):

    def algorithmProviderTesting(self) -> 'ExampleAlgorithmProvider':
        return QgsApplication.instance().processingRegistry().providerById(ExampleAlgorithmProvider.NAME.lower())

    def test_example_algo(self):

        alg = ExampleRasterProcessing()
        # alg.initAlgorithm({})
        ext_ref = QgsRasterFileWriter.supportedFormatExtensions()

        # ext0 = alg.parameterDefinitions()[-1].supportedOutputRasterLayerExtensions()
        def ext(a: QgsProcessingAlgorithm):
            p = a.parameterDefinition('OUTPUT')
            if p:
                return p.supportedOutputRasterLayerExtensions()
            return None

        a1 = alg.createInstance()
        a2 = alg.create({})
        e0 = ext(alg)
        e1 = ext(a1)
        e2 = ext(a2)
        a2.initAlgorithm({})
        e2b = ext(a2)

        aid = alg.id()

        # self.assertTrue(len(ext(alg)) > 0)

        provider = ExampleAlgorithmProvider.instance()
        provider.addAlgorithm(alg)
        e0b = ext(alg)

        a3 = provider.algorithm(aid)
        e3 = ext(a3)
        a3.initAlgorithm({})
        e3b = ext(a3)
        s = ""

    def test_resampling(self):

        provider = ExampleAlgorithmProvider.instance()
        a = ExampleRasterProcessing()
        provider.addAlgorithm(a)

        algorithmId = [a.id() for a in provider.algorithms()
                       if a.id().endswith('examplerasterprocessing')][0]
        s = ""

        speclib = TestObjects.createSpectralLibrary(2)

        TestObjects.processingAlgorithm()

        with edit(speclib):
            slw = SpectralLibraryWidget(speclib=speclib)
            spd = SpectralProcessingDialog(speclib=speclib, algorithmId=algorithmId)
            spd.runAlgorithm(fail_fast=True)
            # slw.showSpectralProcessingWidget(algorithmId=algorithmId)
            # wrapper = spd.processingModelWrapper()
            s = ""
            feedback = spd.processingFeedback()

            self.showGui([spd, slw])

        # preg.removeProvider(provider)
        QgsProject.instance().removeAllMapLayers()

    def test_logging(self):
        logs = {'setProgressText': 'A progress text',
                'setProgress': 75,
                'pushInfo': 'A pushInfo',
                'reportError': 'An error info',
                'pushDebugInfo': 'A debug info',
                'pushConsoleInfo': 'A console info',
                'pushCommandInfo': 'A command info'
                }
        provider = ExampleAlgorithmProvider.instance()
        provider.addAlgorithm(AlgorithmLogging(logs))
        algorithmId = provider.algorithms()[0].id()
        s = ""

        speclib = TestObjects.createSpectralLibrary(2)

        TestObjects.processingAlgorithm()

        with edit(speclib):
            slw = SpectralLibraryWidget(speclib=speclib)
            spd = SpectralProcessingDialog(speclib=speclib, algorithmId=algorithmId)
            spd.runAlgorithm(fail_fast=True)
            # slw.showSpectralProcessingWidget(algorithmId=algorithmId)
            # wrapper = spd.processingModelWrapper()
            s = ""
            feedback = spd.processingFeedback()
            html = feedback.htmlLog()
            for funcName, value in logs.items():
                value = str(value)
                self.assertTrue(value in html)
            self.showGui([spd, slw])

        # preg.removeProvider(provider)
        QgsProject.instance().removeAllMapLayers()

    def test_algwidget(self):

        from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider
        registerDataProvider()
        n_bands = [256]
        n_features = 20
        speclib = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
        speclib: QgsVectorLayer

        speclib.startEditing()
        procw = SpectralProcessingDialog(speclib=speclib)
        # procw.setSpeclib(speclib)
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg1 = reg.algorithmById('gdal:rearrange_bands')
        alg2 = reg.algorithmById('native:rescaleraster')

        procw.setAlgorithm(alg2)
        self.showGui(procw)

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog')
    def test_SpectralProcessingWidget2(self):

        from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider
        registerDataProvider()
        n_bands = [256, 13]
        n_features = 20
        speclib = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
        speclib: QgsVectorLayer

        slw = SpectralLibraryWidget(speclib=speclib)
        pFields = profile_field_list(speclib)

        speclib.startEditing()
        procw = SpectralProcessingDialog()
        procw.setSpeclib(speclib)
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg1 = reg.algorithmById('gdal:rearrange_bands')
        alg2 = reg.algorithmById('native:rescaleraster')
        procw.setAlgorithm(alg2)
        wrapper = procw.processingModelWrapper()
        cbInputField = wrapper.parameterWidget('INPUT')
        cbInputField.setCurrentIndex(1)
        currentInputFieldName = cbInputField.currentText()

        cb2 = wrapper.outputWidget('OUTPUT')
        cb2.setCurrentText('newfield')

        procw.runAlgorithm(fail_fast=True)
        tempFiles = procw.temporaryRaster()
        for file in tempFiles:
            prop = QgsRasterLayerSpectralProperties.fromRasterLayer(file)

            wl = prop.wavelengths()
            wlu = prop.wavelengthUnits()

            ds = gdal.Open(file)
            nb = ds.RasterCount
            self.assertEqual(nb, len(wl))
            self.assertEqual(nb, len(wlu))

        self.assertTrue(True)
        self.showGui([slw, procw])

        QgsProject.instance().removeAllMapLayers()

    def test_SpectralProcessingRasterLayerWidgetWrapper(self):

        parameters = [
            QgsProcessingParameterRasterLayer('rasterlayer'),

        ]

        gridLayout = QGridLayout()

        layers = [TestObjects.createRasterLayer(),
                  TestObjects.createRasterLayer(),
                  TestObjects.createVectorLayer()]

        class ContextGenerator(QgsProcessingContextGenerator):

            def __init__(self, context):
                super().__init__()
                self.processing_context = context

            def processingContext(self):
                return self.processing_context

        project = QgsProject()
        project.addMapLayers(layers)
        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(project)
        processing_context = QgsProcessingContext()
        context_generator = ContextGenerator(processing_context)
        parameters_generator = None

        def onValueChanged(*args):
            print(args)

        wrappers = dict()
        widgets = []
        for i, param in enumerate(parameters):
            wrapper = SpectralProcessingRasterLayerWidgetWrapper(param, QgsProcessingGui.Standard)
            wrapper.setWidgetContext(widget_context)
            wrapper.registerProcessingContextGenerator(context_generator)
            wrapper.registerProcessingParametersGenerator(parameters_generator)
            wrapper.widgetValueHasChanged.connect(onValueChanged)
            # store wrapper instance
            wrappers[param.name()] = wrapper
            label = wrapper.createWrappedLabel()
            # self.addParameterLabel(param, label)
            widget = wrapper.createWrappedWidget(processing_context)
            widgets.append((label, widget))
            gridLayout.addWidget(label, i, 0)
            gridLayout.addWidget(widget, i, 1)

        w = QWidget()
        w.setLayout(gridLayout)
        self.showGui(w)

    @unittest.skipIf(TestCase.runsInCI(), 'Sandbox only')
    def test_dialog(self):
        class D(QgsProcessingAlgorithmDialogBase):
            def __init__(self, *args, **kwds):
                super().__init__(*args, **kwds)

        d = D()
        d.exec_()

    def test_SpectralLibraryWidget(self):

        from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider
        registerDataProvider()
        n_bands = [[256, 2500],
                   [123, 42]]
        n_features = 10
        speclib = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
        speclib: QgsVectorLayer
        # speclib.selectByIds([1, 2, 3, 4])
        # speclib.startEditing()
        slw = SpectralLibraryWidget(speclib=speclib)
        self.showGui(slw)
        slw.project().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
