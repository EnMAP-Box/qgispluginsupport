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
    QgsProcessingAlgorithm, QgsProcessingProvider

from processing.modeler.ModelerDialog import ModelerParametersDialog
from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath

from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *
from qps.speclib.processing import *
from qps.speclib.processingalgorithms import SpectralProfileWriter, SpectralProfileReader
from qps.testing import TestCase, TestAlgorithmProvider
from qps.models import TreeView, TreeNode, TreeModel


class SpectralProcessingAlgorithmExample(QgsProcessingAlgorithm):
    NAME = 'SpectralProcessingAlgorithmExample'
    INPUT = 'Input Profiles'
    OUTPUT = 'Output Profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mFunction: typing.Callable = None

    def description(self) -> str:
        return 'This is a spectral processing algorithm'

    def initAlgorithm(self, configuration: dict):

        p1 = SpectralAlgorithmInput(self.INPUT, description='Input Profiles')
        self.addParameter(p1, createOutput=False)

        o1 = SpectralAlgorithmOutputDestination(self.OUTPUT, description='Modified profiles')
        self.addParameter(o1)

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        input_profiles: SpectralAlgorithmInput = parameters[self.INPUT]
        output_profiles: SpectralAlgorithmOutput = self.outputDefinition(self.OUTPUT)


        for i, profileBlock in enumerate(input_profiles.profileBlocks()):
            # process block by block

            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i+1}/{input_profiles.n_blocks()}')

            # do the spectral processing here

            if isinstance(self.mFunction, typing.Callable):
                profileBlock = self.mFunction(profileBlock)
            output_profiles.addProfileBlock(profileBlock)
            feedback.setProgress(100 * i / input_profiles.n_blocks())

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
        result = True
        msg = ''
        # check parameters

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

        return True

class SpectraProcessingExamples(TestCase):
    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:
        super(SpectraProcessingExamples, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        from qps import initResources
        initResources()
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)
        cls.mTestProvider = TestAlgorithmProvider()
        procReg.addProvider(cls.mTestProvider)

        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        paramFactory = SpectralProcessingParameterWidgetFactory()
        procGuiReg.addParameterWidgetFactory(paramFactory)

        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface

    def testProvider(self) -> QgsProcessingProvider:
        return self.mTestProvider

    def test_use_spectral_algorithm(self):
        alg = SpectralProcessingAlgorithmExample()

        configuration = {}
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        def onFeedbackProgress(v:float):
            print(f'Progress {v}')
        feedback.progressChanged.connect(onFeedbackProgress)


        self.assertTrue(len(alg.parameterDefinitions()) == 0)
        self.assertTrue(len(alg.outputDefinitions()) == 0)

        alg.initAlgorithm(configuration)

        self.assertTrue(any([d for d in alg.parameterDefinitions()
                             if isinstance(d, SpectralAlgorithmInput)]))

        self.assertTrue(any([d for d in alg.outputDefinitions()
                             if isinstance(d, SpectralAlgorithmOutput)]))

        speclib = TestObjects.createSpectralLibrary(10, n_bands=[6, 7, 10, 25])
        self.assertTrue(len(speclib) == 10*4)

        input = SpectralAlgorithmInput()
        input.setFromSpectralLibrary(speclib)

        output = SpectralAlgorithmOutput(alg.OUTPUT)

        parameters = {alg.INPUT: input,
                      alg.OUTPUT: output}

        self.assertTrue(
            alg.prepareAlgorithm(parameters, context, feedback)
        )

        results = alg.processAlgorithm(parameters, context, feedback)

        output = results[alg.OUTPUT]
        self.assertIsInstance(output, SpectralAlgorithmOutput)


    def test_read_and_write(self):

        configuration = {}
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        algReader = SpectralProfileReader()
        algWriter = SpectralProfileWriter()
        algReader.initAlgorithm(configuration)
        algWriter.initAlgorithm(configuration)

        param = {

        }
        algReader.prepareAlgorithm()



        # write outputs

        s = ""


    def test_register_spectral_algorithm(self):

        alg = SpectralProcessingAlgorithmExample()
        self.testProvider().algs.append(alg)
        self.testProvider().refreshAlgorithms()

        self.assertTrue(alg in self.testProvider().algorithms())

        from qps.speclib.processing import spectral_algorithms
        self.assertTrue(alg in spectral_algorithms())

        # open modeler and see if the algorithm appears there
        from processing.modeler.ModelerDialog import ModelerDialog
        d = ModelerDialog()
        self.showGui(d)

    def text_use_simple_model(self):

        # todo: show how to create a simple linear model
        pass


class SpectralProcessingTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:

        super(SpectralProcessingTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        from qps import initResources
        initResources()

    def initProcessingRegistry(self) -> typing.Tuple[QgsProcessingRegistry, QgsProcessingGuiRegistry]:
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        paramFactory = SpectralProcessingParameterWidgetFactory()
        procGuiReg.addParameterWidgetFactory(paramFactory)

        parameterType = SpectralAlgorithmInputType()
        self.assertTrue(procReg.addParameterType(parameterType))

        provider = TestAlgorithmProvider()
        self.assertTrue(procReg.addProvider(provider))

        self.mFac = paramFactory
        self.mPRov = provider

        return procReg, procGuiReg

    def test_SpectralAlgorithmInputType(self):

        self.initProcessingRegistry()

        salgs = spectral_algorithms()
        assert len(salgs) > 0


        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface
        from processing.modeler.ModelerDialog import ModelerDialog
        from processing.modeler.ModelerParametersDialog import ModelerParametersPanelWidget

        model: QgsProcessingModelAlgorithm = QgsProcessingModelAlgorithm()
        model.setName('MyModelName')
        model.setGroup('MyModelGroup')
        alg = salgs[0]
        #w = ModelerParametersPanelWidget(alg, model, None, None, None, None)
        #self.showGui(w)
        dlg = ModelerParametersDialog(alg, model)
        #dlg.exec_()
        calg1: QgsProcessingModelChildAlgorithm = dlg.createAlgorithm()


        calg2: QgsProcessingModelChildAlgorithm = dlg.createAlgorithm()
        model.addChildAlgorithm(calg1)
        model.addChildAlgorithm(calg2)
        for output in calg2.algorithm().outputDefinitions():
            output: SpectralAlgorithmOutput

        compatibleParameterTypes = [SpectralAlgorithmInput.TYPE]
        compatibleOuptutTypes = [SpectralAlgorithmInput.TYPE]
        compatibleDataTypes = []
        result1 = model.availableSourcesForChild(calg1.childId(), compatibleParameterTypes, compatibleOuptutTypes, compatibleDataTypes)

        for source in result1:
            isChildOutput = source.source() == QgsProcessingModelChildParameterSource.ChildOutput
            if not isChildOutput:
                s = ""
            assert source.outputChildId() in model.childAlgorithms()
            alg = model.childAlgorithm(source.outputChildId())
            assert alg.algorithm()
            s = ""
        p = QWidget()
        parameter = calg1.algorithm().parameterDefinitions()[0]
        context = QgsProcessingContext()
        w = QgsProcessingModelerParameterWidget(model, calg1.childId(), parameter, context, p)

        #w.populateSources(compatibleParameterTypes, compatibleOuptutTypes, compatibleDataTypes)
        #w.setSourceType(QgsProcessingModelChildParameterSource.ChildOutput)
        self.showGui([p,w])
        alg.algorithm()
        result2 = model.availableSourcesForChild(calg2.childId(), compatibleParameterTypes, compatibleOuptutTypes, compatibleDataTypes)
        s = ""
        """
        mModel->availableSourcesForChild( mChildId, compatibleParameterTypes, compatibleOutputTypes, compatibleDataTypes );
        #widget = QgsGui.processingGuiRegistry().createModelerParameterWidget(model,
                                                                             calg2.childId,
                                                                             output,
                                                                             self.context)
        #widget.setDialog(self.dialog)
        """
        calg1.algorithm().destinationParameterDefinitions()


        outputs = {}

        res, errors = model.validateChildAlgorithm(id)
        self.assertTrue(res)

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)
        parameters = {}


        #res = model.run(parameters, context, feedback)
        

        md = ModelerDialog.create(model)
        self.assertIsInstance(md, ModelerDialog)
        self.showGui([md])

        #parent = QWidget()
        #context = QgsProcessingContext()
        #widgetContext = QgsProcessingParameterWidgetContext()

        #definitionWidget: QgsProcessingAbstractParameterDefinitionWidget \
        #    = procGuiReg.createParameterDefinitionWidget(paramFactory.parameterType(), context, widgetContext)
        #self.assertIsInstance(definitionWidget, QgsProcessingAbstractParameterDefinitionWidget)
        #self.showGui(definitionWidget)
        #parameter = definitionWidget.createParameter('testname', 'test descripton', QgsProcessingParameterDefinition)
        #self.assertTrue(parameter, SpectralAlgorithmInput)
        #wrapper = procGuiReg.createParameterWidgetWrapper(parameter, QgsProcessingGui.Standard)
        #wrapper = procGuiReg.createParameterWidgetWrapper(parameter, QgsProcessingGui.Batch)
        #wrapper = procGuiReg.createParameterWidgetWrapper(parameter, QgsProcessingGui.Modeler)



    def test_gui(self):
        self.initProcessingRegistry()
        sl = TestObjects.createSpectralLibrary(10)
        w = SpectralLibraryWidget(speclib=sl)
        self.showGui(w)
        s = ""
        pass

    def test_SimpleModel(self):
        reg, guiReg = self.initProcessingRegistry()
        reg: QgsProcessingRegistry
        guiReg: QgsProcessingGuiRegistry

        m = ProcessingModelAlgorithmChain()
        self.assertIsInstance(m, QAbstractListModel)

        algs = spectral_algorithms()

        w = QTableView()
        w.setModel(m)
        w.show()
        last = None
        for a in algs:
            m.addAlgorithm(a)
            #m.addAlgorithm(a.id())
            last = a


        pm = m.processingModel()

        self.showGui(w)

    def test_SpectralProcessingWidget(self):
        self.initProcessingRegistry()
        w = SpectralProcessingWidget()

        self.showGui(w)

    def test_ModelBuilder(self):
        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface
        self.initProcessingRegistry()
        procReg = QgsApplication.instance().processingRegistry()
        for p in procReg.parameterTypes():
            if p.id() == '':
                s = ""

        from processing.modeler.ModelerDialog import ModelerDialog
        pathModel = pathlib.Path(__file__).parent / 'testmodel.model3'
        d = ModelerDialog()
        d.loadModel(pathModel.as_posix())

        model = d.model()

        model.availableSourcesForChild
        self.showGui(d)
        s = ""


    def test_SpectralProcessingAlgorithmTreeView(self):

        self.initProcessingRegistry()
        tv = SpectralProcessingAlgorithmTreeView()
        m = SpectralProcessingAlgorithmModel(tv)
        tv.setModel(m)

        self.showGui(tv)
