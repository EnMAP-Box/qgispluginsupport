# noinspection PyPep8Naming
import unittest
import random
import math
import xmlrunner
from qps.testing import TestObjects, TestCase, StartOptions
import numpy as np
from qgis.gui import *
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsDualView, QgsOptionsDialogBase, QgsAttributeForm, QgsGui, \
    QgsSearchWidgetWrapper, QgsMessageBar, QgsProcessingGuiRegistry, QgsProcessingGui, \
    QgsProcessingParameterWidgetContext, QgsProcessingAbstractParameterDefinitionWidget, \
    QgsProcessingModelerParameterWidget

from qgis.core import QgsVectorLayer, QgsMapLayer, QgsRasterLayer, QgsProject, QgsActionManager, \
    QgsField, QgsApplication, QgsWkbTypes, QgsProcessingRegistry, QgsProcessingContext, \
    QgsProcessingParameterDefinition, QgsProcessingModelAlgorithm, QgsProcessingFeedback, \
    QgsProcessingModelChildAlgorithm, QgsProcessingModelChildParameterSource, \
    QgsProcessingAlgorithm, QgsProcessingProvider, QgsProcessingParameterVectorLayer, QgsProcessingModelParameter, \
    QgsProcessingModelOutput, QgsProcessingOutputVectorLayer

from processing.modeler.ModelerDialog import ModelerParametersDialog
from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath

from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *
from qps.speclib.processing import *
from qps.speclib.processingalgorithms import *
from qps.testing import TestCase, TestAlgorithmProvider
from qps.models import TreeView, TreeNode, TreeModel


class SpectralProcessingAlgorithmExample(QgsProcessingAlgorithm):
    NAME = 'spectral_processing_algorithm_example'
    INPUT = 'Input_Profiles'
    OUTPUT = 'Output_Profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mFunction: typing.Callable = None

    def description(self) -> str:
        return 'This is a spectral processing algorithm'

    def initAlgorithm(self, configuration: dict):

        p1 = SpectralProcessingProfiles(self.INPUT, description='Input Profiles')
        self.addParameter(p1, createOutput=False)
        p2 = SpectralProcessingProfilesOutput(self.OUTPUT, description='Output Profiles')
        self.addOutput(p2)

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        input_profiles: typing.List[SpectralProfileBlock] = parameterAsSpectralProfileBlockList(parameters, self.INPUT,
                                                                                                context)
        output_profiles: typing.List[SpectralProfileBlock] = []

        n_block = len(input_profiles)
        for i, profileBlock in enumerate(input_profiles):
            # process block by block

            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i + 1}/{n_block}')

            # do the spectral processing here
            if isinstance(self.mFunction, typing.Callable):
                profileBlock = self.mFunction(profileBlock)
            output_profiles.append(profileBlock)
            feedback.setProgress(100 * i / n_block)

        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_profiles
        return OUTPUTS

    def setProcessingFunction(self, function: typing.Callable):

        assert isinstance(function, typing.Callable)
        self.mFunction = function

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):

        errors = []
        if not self.parameterDefinition(self.INPUT).checkValueIsAcceptable(parameters[self.INPUT], context):
            errors.append(f'Unable to read {self.INPUT}')

        result = len(errors) == 0
        msg = '\n'.join(errors)
        return result, msg

    def createCustomParametersWidget(self) -> QWidget:
        w = QWidget()
        label = QLabel('Placeholder for custom widget')
        l = QHBoxLayout()
        l.addWidget(label)
        w.setLayout(l)
        return w

    def createInstance(self):
        alg = SpectralProcessingAlgorithmExample()
        return alg

    def displayName(self) -> str:

        return 'Spectral Processing Algorithm Example'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'Test Group'

    def helpString(self) -> str:
        return 'Help String'

    def name(self):
        return self.NAME

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        is_valid = True
        for key in [self.INPUT]:
            if not key in parameters.keys():
                feedback.reportError(f'Missing parameter {key}')
                is_valid = False
        return is_valid



class SpectraProcessingExamples(TestCase):
    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:
        super(SpectraProcessingExamples, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        from qps import initResources
        initResources()
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)
        cls.mTestProvider = TestAlgorithmProvider()
        cls.mTestProvider._algs = [
            SpectralProfileReader(),
            # SpectralProcessingAlgorithmExample(),
            SpectralProfileWriter()
        ]
        # cls.mTestProvider.algorithms()
        procReg.addProvider(cls.mTestProvider)

        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        procGuiReg.addParameterWidgetFactory(SpectralProcessingAlgorithmInputWidgetFactory())
        procGuiReg.addParameterWidgetFactory(SpectralProcessingProfilesOutputWidgetFactory())

        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface

    def testProvider(self) -> QgsProcessingProvider:
        return self.mTestProvider

    def test_example_spectral_algorithms(self):
        configuration = {}

        def onFeedbackProgress(v: float):
            print(f'Progress {v}')

        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(onFeedbackProgress)

        # use an exemplary SpectralProcessingAlgorithm
        alg = SpectralProcessingAlgorithmExample()
        alg.initAlgorithm(configuration)

        # There is no `SpectralProcessingAlgorithm`, but a QgsProcessingAlgorithm
        # is a SpectralProcessingAlgorithm, if:
        self.assertTrue(is_spectral_processing_algorithm(alg))

        # which means it defines SpectralProcessingProfiles(s) as input
        self.assertTrue(any([d for d in alg.parameterDefinitions()
                             if isinstance(d, SpectralProcessingProfiles)]))

        # and SpectralProcessingProfilesOutput(s)
        self.assertTrue(any([d for d in alg.outputDefinitions()
                             if isinstance(d, SpectralProcessingProfilesOutput)]))

        # SpectralAlgorithmInputs(QgsProcessingParameterDefinition) and
        # SpectralAlgorithmOutputs(QgsProcessingOutputDefinitions) are used to
        # transfer processing results between SpectralProfileAlgorithms

        # internally, they use SpectralProfileBlocks to described
        # and transfer profile data of same spectral setting:

        # create a SpectralLibrary of profiles with a different number of bands:
        speclib: SpectralLibrary = TestObjects.createSpectralLibrary(10, n_bands=[6, 7, 10, 25])

        # use the spectral library as input

        parameters = {alg.INPUT: speclib}
        self.assertTrue(alg.checkParameterValues(parameters, context))
        results = alg.processAlgorithm(parameters, context, feedback)
        self.assertIsInstance(results, dict)
        profile_blocks = results.get(SpectralProcessingAlgorithmExample.OUTPUT, None)
        self.assertIsInstance(profile_blocks, list)

        # as the spectral library contains profiles with 6, 7, 10 or 25 bands,
        # they are grouped into 4 SpectralProfileBlocks
        self.assertTrue(len(profile_blocks) == 4)
        for b, block in enumerate(profile_blocks):
            self.assertIsInstance(block, SpectralProfileBlock)

            # the spectral settings describes what all block profiles have in common:
            # (i)   number of bands,
            # (ii)  xUnit, like 'nm' for nanometers or 'date' for temporal profiles
            # (iii) yUnit, like 'reflectance' or 'ndvi' (usually this is not defined explicitly)
            # tbd: could be extended e.g. with a description of scaling, offset, band band list, ...

            setting = block.spectralSetting()
            self.assertIsInstance(setting, SpectralSetting)
            print(f'Block {b + 1}:\n\t{setting}\n\t{block.n_profiles()} profiles')

            # profile values are available as numpy array
            data = block.data()
            self.assertIsInstance(data, np.ndarray)
            self.assertTrue(data.shape[0] == setting.n_bands())
            self.assertTrue(data.shape[0] == block.n_bands())

            # for better use in image-operating algorithms, the data array
            # is an 'image-like' 3D array, with
            self.assertTrue(data.shape[0] == block.n_bands())
            self.assertTrue(data.shape[1] * data.shape[2] == block.n_profiles())


    def test_example_spectral_processing_model(self):
        """
        This example shows how to create a processing model that:
        1. reads profiles from a speclib
        2. processes profiles
        3. writes the processed profile into a Speclib
        """

        configuration = {}
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        speclib_source = TestObjects.createSpectralLibrary(20, n_bands=[10, 15])
        speclib_target = TestObjects.createSpectralLibrary()

        model = QgsProcessingModelAlgorithm()
        model.setName('ExampleModel')

        def createChildAlgorithm(algorithm_id: str, description='') -> QgsProcessingModelChildAlgorithm:
            alg = QgsProcessingModelChildAlgorithm(algorithm_id)
            alg.generateChildId(model)
            alg.setDescription(description)
            return alg

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg = SpectralProcessingAlgorithmExample()
        self.testProvider().addAlgorithm(alg)

        self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralProcessingAlgorithmExample)

        # get the QgsProcessingAlgorithms we like to connect in the model
        # 1. read spectral profiles from any QgsVectorLayer.
        #    The spectral_profile_reader can use standard QGIS input object, i.e. vector layer and vector fields
        #    Its output is a list of SpectralProfileBlocks
        algR = reg.algorithmById('testalgorithmprovider:spectral_profile_reader')

        # 2. read and process SpectralProfileBlocls
        algP = reg.algorithmById('testalgorithmprovider:spectral_processing_algorithm_example')

        # 3. write SpectralProfileBlocks to standard QGIS output object, i.e. a BLOB field of a QgsVectorLayer
        algW = reg.algorithmById('testalgorithmprovider:spectral_profile_writer')

        for a in [algP, algR, algW]:
            self.assertIsInstance(a, QgsProcessingAlgorithm)

        # create child algorithms, i.e. instances of QgsProcessingAlgorithms
        idR: str = model.addChildAlgorithm(createChildAlgorithm(algR.id(), 'Read'))
        idP1: str = model.addChildAlgorithm(createChildAlgorithm(algP.id(), 'Process Step 1'))
        idP2: str = model.addChildAlgorithm(createChildAlgorithm(algP.id(), 'Process Step 2'))
        idW: str = model.addChildAlgorithm(createChildAlgorithm(algW.id(), 'Write'))

        # set model input / output
        model.addModelParameter(QgsProcessingParameterVectorLayer('speclib_source', description='Source Speclib'),
                                QgsProcessingModelParameter('speclib_source'))
        model.addModelParameter(QgsProcessingParameterVectorLayer('speclib_target', description='Target Speclib'),
                                QgsProcessingModelParameter('speclib_target'))

        # connect child inputs and outputs
        calgR = model.childAlgorithm(idR)
        calgR.addParameterSources(
            SpectralProfileReader.INPUT,
            [QgsProcessingModelChildParameterSource.fromModelParameter('speclib_source')]
        )
        calgR.addParameterSources(
            SpectralProfileReader.INPUT_FIELD,
            [QgsProcessingModelChildParameterSource.fromStaticValue('values')]
        )

        calgP1 = model.childAlgorithm(idP1)
        calgP1.addParameterSources(
            SpectralProcessingAlgorithmExample.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(idR, SpectralProfileReader.OUTPUT)]
        )

        calgP2 = model.childAlgorithm(idP2)
        calgP2.addParameterSources(
            SpectralProcessingAlgorithmExample.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(idP1, SpectralProcessingAlgorithmExample.OUTPUT)]
        )

        calgW = model.childAlgorithm(idW)
        calgW.addParameterSources(
            SpectralProfileWriter.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(idP2, SpectralProcessingAlgorithmExample.OUTPUT)]
        )
        calgW.addParameterSources(
            SpectralProfileWriter.OUTPUT,
            [QgsProcessingModelChildParameterSource.fromModelParameter('speclib_target')]
        )

        outputs = {SpectralProcessingAlgorithmExample.OUTPUT: QgsProcessingModelOutput('output_spectra')}
        calgP2.setModelOutputs(outputs)
        # define outputs
        s = ""

        # set the positions for parameters and algorithms in the model canvas:
        x = 150
        y = 50
        dx = 100
        dy = 75
        components = model.parameterComponents()
        for n, p in components.items():
            p.setPosition(QPointF(x, y))
            x += dx
        model.setParameterComponents(components)

        y = 50
        x = 400
        for calg in [calgR, calgP1, calgP2, calgW]:
            calg: QgsProcessingModelChildAlgorithm
            calg.setPosition(QPointF(x, y))
            y += dy

        # outputID = calgW.modelOutput('speclib_target').childId()
        parameters = {'speclib_source': speclib_source,
                      'speclib_target': speclib_target}

        model.initAlgorithm(configuration)
        # self.assertTrue(model.prepareAlgorithm(parameters, context, feedback))

        n0 = len(parameters['speclib_target'])
        results, success = model.run(parameters, context, feedback)
        self.assertTrue(success)
        self.assertIsInstance(results, dict)
        self.assertTrue(len(parameters['speclib_target']) == n0 + len(speclib_source))

        from processing.modeler.ModelerDialog import ModelerDialog
        d = ModelerDialog(model=model)

        # note: this will work only if environmental variable CI=False
        self.showGui(d)

    def test_example_register_spectral_algorithms(self):
        alg = SpectralProcessingAlgorithmExample()
        # ._algs.append(alg)
        # self.testProvider().refreshAlgorithms()
        self.testProvider().addAlgorithm(alg)

        self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralProcessingAlgorithmExample)

        from qps.speclib.processing import spectral_algorithms

        self.assertTrue(alg.name() in [a.name() for a in spectral_algorithms()])

        # open modeler and see if the algorithm appears there

        from processing.modeler.ModelerDialog import ModelerDialog
        d = ModelerDialog()

        # note: this will work only if environmental variable CI=False
        self.showGui(d)


class SpectralProcessingTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:

        super(SpectralProcessingTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        from qps import initResources
        initResources()

    def initProcessingRegistry(self) -> typing.Tuple[QgsProcessingRegistry, QgsProcessingGuiRegistry]:
        procReg = QgsApplication.instance().processingRegistry()
        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        provider_names = [p.name() for p in procReg.providers()]
        if TestAlgorithmProvider.NAME not in provider_names:
            procGuiReg.addParameterWidgetFactory(SpectralProcessingAlgorithmInputWidgetFactory())
            procGuiReg.addParameterWidgetFactory(SpectralProcessingProfilesOutputWidgetFactory())

            self.assertTrue(procReg.addParameterType(SpectralProcessingProfileType()))

            provider = TestAlgorithmProvider()
            self.assertTrue(procReg.addProvider(provider))
            provider._algs.extend([
                SpectralProfileReader(),
                SpectralProfileWriter(),
                SpectralProcessingAlgorithmExample()
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

    def test_SpectralLibraryWidget(self):
        self.initProcessingRegistry()
        n_profiles_per_n_bands = 1000
        n_bands = [6, 30, 177]
        if False:
            # speed-test for deleting features
            slibs = [TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands) for _ in range(4)]

            c = QgsMapCanvas()
            for i, sl in enumerate(slibs):

                sl.startEditing()
                sl.beginEditCommand('Delete features')
                fids = sl.allFeatureIds()
                sl.selectByIds(fids[1500:])
                if i == 1:
                    w = QgsDualView()
                    w.init(sl, c)
                    w.show()
                elif i == 2:
                    w = AttributeTableWidget(sl)
                    w.show()
                elif i == 3:
                    w = SpectralLibraryWidget(speclib=sl)
                    w.show()
                t0 = datetime.datetime.now()
                sl.deleteSelectedFeatures()
                sl.endEditCommand()
                dt = datetime.datetime.now() - t0
                print(f'Speclib {i}: {dt}')
            s = ""

        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)
        w = SpectralLibraryWidget(speclib=sl)
        self.showGui(w)
        s = ""
        pass

    def test_SpectralProfileReader(self):
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)
        configuration = {}
        alg = SpectralProfileReader()

        speclib: SpectralLibrary = TestObjects.createSpectralLibrary(10, n_bands=10, wlu='nm')
        speclib.startEditing()
        speclib.addSpeclib(TestObjects.createSpectralLibrary(10, n_bands=10, wlu='micrometers'))
        speclib.commitChanges()

        parameters = {alg.INPUT: speclib,
                      alg.INPUT_FIELD: 'values'}
        alg.initAlgorithm(configuration)
        alg.prepareAlgorithm(parameters, context, feedback)
        results = alg.processAlgorithm(parameters, context, feedback)

        self.assertTrue(alg.OUTPUT in results.keys())
        self.assertIsInstance(results[alg.OUTPUT], list)
        n = 0
        for block in results[alg.OUTPUT]:
            self.assertIsInstance(block, SpectralProfileBlock)
            n += block.n_profiles()
        self.assertEqual(n, len(speclib))

    def test_SpectralXUnitConversion(self):

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)
        configuration = {}

        speclib: SpectralLibrary = TestObjects.createSpectralLibrary(10, n_bands=10, wlu='nm')
        speclib.startEditing()
        speclib.addSpeclib(TestObjects.createSpectralLibrary(10, n_bands=10, wlu='micrometers'))
        speclib.commitChanges()

        blocks = speclib.profileBlocks()

        alg = SpectralXUnitConversion()
        alg.initAlgorithm(configuration)

        target_unit = 'mm'
        parameters = {alg.INPUT: blocks,
                      alg.TARGET_XUNIT: target_unit}

        alg.prepareAlgorithm(parameters, context, feedback)
        outputs = alg.processAlgorithm(parameters, context, feedback)
        for block in outputs[alg.OUTPUT]:
            self.assertIsInstance(block, SpectralProfileBlock)
            self.assertTrue(block.spectralSetting().xUnit() == target_unit)
            print(block.spectralSetting().x())

    def test_SimpleModel(self):
        reg, guiReg = self.initProcessingRegistry()
        reg: QgsProcessingRegistry
        guiReg: QgsProcessingGuiRegistry

        m = SpectralProcessingAlgorithmChainModel()
        self.assertIsInstance(m, QAbstractListModel)

        algs = spectral_algorithms()

        w = QTableView()
        w.setModel(m)
        w.show()
        last = None
        for a in algs:
            m.addAlgorithm(a)
            # m.addAlgorithm(a.id())
            last = a

        pm = m.processingModel()

        self.showGui(w)

    def test_SpectralProcessingWidget(self):
        self.initProcessingRegistry()
        w = SpectralProcessingWidget()

        self.showGui(w)

    def test_SpectralProcessingAlgorithmTreeView(self):

        self.initProcessingRegistry()
        tv = SpectralProcessingAlgorithmTreeView()
        m = SpectralProcessingAlgorithmModel(tv)
        tv.setModel(m)

        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
