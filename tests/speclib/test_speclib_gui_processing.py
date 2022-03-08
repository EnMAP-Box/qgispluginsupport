# noinspection PyPep8Naming
import datetime
import typing
import unittest

import xmlrunner
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsVectorLayer
from qgis.gui import QgsMapCanvas, QgsDualView

from qgis.PyQt.QtWidgets import QGridLayout
from qgis.core import QgsProcessingAlgorithm, QgsProcessingModelChildAlgorithm, QgsProject, QgsProcessingModelOutput, \
    QgsProcessingModelParameter, QgsProcessingModelChildParameterSource, QgsProcessingParameterRasterLayer, \
    QgsProcessingOutputRasterLayer, QgsProcessingFeedback, QgsProcessingContext, QgsProcessingModelAlgorithm, \
    QgsProcessingRegistry, QgsApplication
from qgis.gui import QgsGui, QgsProcessingParameterWidgetContext, QgsProcessingGui, QgsProcessingContextGenerator, \
    QgsProcessingAlgorithmDialogBase
from qgis.gui import QgsProcessingGuiRegistry, QgsProcessingParameterDefinitionDialog
from qps import initAll
from qps.speclib.core import profile_field_list
from qps.speclib.core.spectrallibrary import SpectralLibrary
from qps.speclib.core.spectralprofile import SpectralSetting
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.gui.spectralprocessingdialog import SpectralProcessingDialog, \
    SpectralProcessingRasterLayerWidgetWrapper
from qps.testing import TestCase, ExampleAlgorithmProvider
from qps.testing import TestObjects, StartOptions


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

        return procReg, procGuiReg

    def algorithmProviderTesting(self) -> 'ExampleAlgorithmProvider':
        return QgsApplication.instance().processingRegistry().providerById(ExampleAlgorithmProvider.NAME.lower())

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

    @unittest.skipIf(True, 'Deprecated')
    def test_simple_processing_model(self):

        self.initProcessingRegistry()

        configuration = {}
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        speclib_source = TestObjects.createSpectralLibrary(20, n_bands=[10, 15])

        model = QgsProcessingModelAlgorithm()
        model.setName('ExampleModel')

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg: QgsProcessingAlgorithm = reg.algorithmById(
            'testalgorithmprovider:spectral_python_code_processing')

        self.assertIsInstance(alg, QgsProcessingAlgorithm)

        childAlg = QgsProcessingModelChildAlgorithm(alg.id())
        childAlg.generateChildId(model)
        childAlg.setDescription('MySpectralAlg')

        childId: str = model.addChildAlgorithm(childAlg)

        # Important: addChildAlgorithm creates a copy
        childAlg = model.childAlgorithm(childId)

        input_name = 'input_profiles'
        output_name = 'output_profiles'

        model.addModelParameter(QgsProcessingParameterRasterLayer(input_name, description='Source Speclib'),
                                QgsProcessingModelParameter(input_name))
        childAlg.addParameterSources(
            alg.INPUT, [QgsProcessingModelChildParameterSource.fromModelParameter(input_name)]
        )

        # define algorithm instance outputs for the model,
        # e.g. to be used by other algorithms
        childOutput = QgsProcessingModelOutput(output_name)
        childOutput.setChildOutputName(alg.OUTPUT)
        childAlg.setModelOutputs({output_name: childOutput})

        # define model outputs, e.g. to be used by other users
        model.addOutput(QgsProcessingOutputRasterLayer(output_name))
        model.initAlgorithm(configuration)

        input_names = [d.name() for d in model.parameterDefinitions()]
        output_names = [d.name() for d in model.outputDefinitions()]
        self.assertTrue(input_name in input_names)
        self.assertTrue(output_name in output_names)

        speclibSrc = TestObjects.createSpectralLibrary(10)
        speclibDst = TestObjects.createSpectralLibrary(1)
        parameters = {input_name: speclibSrc,
                      output_name: speclibDst}

        is_valid, msg = model.checkParameterValues(parameters, context)
        self.assertTrue(is_valid, msg=msg)
        can_execute, msg = model.canExecute()
        self.assertTrue(can_execute, msg=msg)
        self.assertTrue(model.prepareAlgorithm(parameters, context, feedback))
        results = model.processAlgorithm(parameters, context, feedback)

        child_alg = model.childAlgorithm(childId)
        child_results = results['CHILD_RESULTS'][childId]
        for output_name, output in child_alg.modelOutputs().items():
            final_key = f'{childId}:{output_name}'
            final_value = child_results[output.childOutputName()]
            s = ""
        s = ""

        # new API
        # context = createContext()
        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(QgsProject.instance())
        from qgis.utils import iface
        if iface is not None:
            widget_context.setMapCanvas(iface.mapCanvas())
            widget_context.setActiveLayer(iface.activeLayer())

        widget_context.setModel(model)

        existing_param = model.parameterDefinitions()[0]
        algorithm = model

        dlg = QgsProcessingParameterDefinitionDialog(type=existing_param.type(),
                                                     context=context,
                                                     widgetContext=widget_context,
                                                     definition=existing_param,
                                                     algorithm=algorithm)
        dlg.setComments('My Comment')
        dlg.setCommentColor(QColor('green'))
        # if edit_comment:
        #    dlg.switchToCommentTab()

        if False and dlg.exec_():
            s = ""
            new_param = dlg.createParameter(existing_param.name())
            comment = dlg.comments()
            comment_color = dlg.commentColor()

    def test_algwidget(self):
        self.initProcessingRegistry()
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

    def test_SpectralProcessingWidget2(self):
        self.initProcessingRegistry()
        from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider
        registerDataProvider()
        n_bands = [256, 13]
        n_features = 20
        speclib = TestObjects.createSpectralLibrary(n=n_features, n_bands=n_bands)
        speclib: QgsVectorLayer

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
            setting = SpectralSetting.fromRasterLayer(file)
            assert setting.xUnit() not in [None, '']

        self.showGui(procw)

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
        self.initProcessingRegistry()

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


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
