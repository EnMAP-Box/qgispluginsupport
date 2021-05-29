# noinspection PyPep8Naming
import unittest
import datetime

import xmlrunner

from qgis.gui import QgsProcessingGuiRegistry, QgsProcessingParameterDefinitionDialog

from qgis.core import QgsProcessingProvider

from qps import initResources, initAll
from qps.speclib.core import profile_field_lookup
from qps.testing import TestObjects, StartOptions
from qps.speclib.gui.spectrallibrarywidget import *
from qps.speclib.processing import *
from qps.speclib.processingalgorithms import *
from qps.testing import TestCase, TestAlgorithmProvider
import numpy as np

class SpectralProcessingExamples(TestCase):
    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:
        super(SpectralProcessingExamples, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)
        initResources()
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)
        cls.mTestProvider = TestAlgorithmProvider()
        cls.mTestProvider._algs = [
            SpectralProfileReader(),
            SpectralPythonCodeProcessingAlgorithm(),
            SpectralXUnitConversion(),
            SpectralProfileWriter()
        ]
        # cls.mTestProvider.algorithms()
        procReg.addProvider(cls.mTestProvider)

        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        procGuiReg.addParameterWidgetFactory(SpectralProcessingAlgorithmInputWidgetFactory())
        procGuiReg.addParameterWidgetFactory(SpectralProcessingProfilesOutputWidgetFactory())
        cls._profile_type = SpectralProcessingProfileType()
        assert procReg.addParameterType(cls._profile_type)

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
        alg = SpectralPythonCodeProcessingAlgorithm()
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

        # create a SpectralLibrary of profiles with a different number of bands per features:
        speclib: SpectralLibrary = TestObjects.createSpectralLibrary(10, n_bands=[6, 10])
        speclib.startEditing()
        speclib.addSpeclib(TestObjects.createSpectralLibrary(10, n_bands=[5, 17]))
        speclib.commitChanges()
        # use the spectral library as input

        parameters = {alg.INPUT: speclib}
        self.assertTrue(alg.checkParameterValues(parameters, context))

        results = alg.processAlgorithm(parameters, context, feedback)
        self.assertIsInstance(results, dict)

        # Spectral Processing algorithms return a list of SpectralProfileBlocks as output
        profile_blocks = results.get(SpectralPythonCodeProcessingAlgorithm.OUTPUT, None)
        self.assertIsInstance(profile_blocks, list)

        # the spectral library contains profiles with (field 1) 6 and 5 bands and (field 2) 10 and 17 bands,
        # they are grouped into 4 SpectralProfileBlocks
        self.assertTrue(len(profile_blocks) == 2)

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
        3. writes processed profiles into a Speclib
        """

        configuration = {}
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        speclib_source = TestObjects.createSpectralLibrary(20, n_bands=[10, 15])
        speclib_target = TestObjects.createSpectralLibrary()

        model = QgsProcessingModelAlgorithm()
        model.setName('ExampleModel')


        def createChildAlgorithm(algorithm_id: str, description='') -> QgsProcessingModelChildAlgorithm:
            """
            Helper function to create a QgsProcessingModelChildAlgorithm
            :param algorithm_id: algorithm id, as available in the QgsProcessingRegistry
            :param description:
            :return: QgsProcessingModelChildAlgorithm
            """
            alg = QgsApplication.instance().processingRegistry().algorithmById(algorithm_id)
            assert isinstance(alg, QgsProcessingAlgorithm), f'{algorithm_id} not registered in QgsProcessingRegistry'
            child_alg = QgsProcessingModelChildAlgorithm(algorithm_id)
            child_alg.generateChildId(model)
            child_alg.setDescription(description)
            return child_alg

        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg = SpectralPythonCodeProcessingAlgorithm()
        self.testProvider().addAlgorithm(alg)

        self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralPythonCodeProcessingAlgorithm)

        # get the QgsProcessingAlgorithms we like to connect in the model
        # 1. read spectral profiles from any QgsVectorLayer.
        #    The spectral_profile_reader can use standard QGIS input object, i.e. vector layer and vector fields
        #    Its output is a list of SpectralProfileBlocks

        # create child algorithms. Each represents an instances of a QgsProcessingAlgorithms
        cidR: str = model.addChildAlgorithm(createChildAlgorithm('testalgorithmprovider:spectral_profile_reader',
                                                                 'Read'))
        cidP1: str = model.addChildAlgorithm(createChildAlgorithm('testalgorithmprovider:spectral_python_code_processing',
                                                                  'Process Step 1'))
        cidP2: str = model.addChildAlgorithm(createChildAlgorithm('testalgorithmprovider:spectral_python_code_processing',
                                                                  'Process Step 2'))
        cidW: str = model.addChildAlgorithm(createChildAlgorithm('testalgorithmprovider:spectral_profile_writer',
                                                                 'Write'))

        # set model inputs and outputs
        mip_name_src = 'speclib_source'
        mip_name_dst = 'speclib_target'

        # define model inputs
        model.addModelParameter(QgsProcessingParameterVectorLayer(mip_name_src, description='Source Speclib'),
                                QgsProcessingModelParameter(mip_name_src))
        model.addModelParameter(QgsProcessingParameterVectorLayer(mip_name_dst, description='Target Speclib'),
                                QgsProcessingModelParameter(mip_name_dst))


        # connect child inputs with model inputs or child outputs
        # 1. Read profiles from the input source
        calgR: QgsProcessingModelChildAlgorithm = model.childAlgorithm(cidR)
        calgR.addParameterSources(
            SpectralProfileReader.INPUT,
            [QgsProcessingModelChildParameterSource.fromModelParameter(mip_name_src)]
        )

        # 2. Processing Step 1: process profiles returned by the SpectralProfileReader
        calgP1: QgsProcessingModelChildAlgorithm = model.childAlgorithm(cidP1)
        calgP1.addParameterSources(
            SpectralPythonCodeProcessingAlgorithm.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(cidR, SpectralProfileReader.OUTPUT)]
        )

        # 3. Processing Step 2: process profiles returned by Processing Step 1
        calgP2: QgsProcessingModelChildAlgorithm = model.childAlgorithm(cidP2)
        calgP2.addParameterSources(
            SpectralPythonCodeProcessingAlgorithm.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(cidP1, SpectralPythonCodeProcessingAlgorithm.OUTPUT)]
        )

        # 4. Write processed profiles from Step 2 to model destination
        calgW = model.childAlgorithm(cidW)
        calgW.addParameterSources(
            SpectralProfileWriter.INPUT,
            [QgsProcessingModelChildParameterSource.fromChildOutput(cidP2, SpectralPythonCodeProcessingAlgorithm.OUTPUT)]
        )

        calgW.addParameterSources(
            SpectralProfileWriter.OUTPUT,
            [QgsProcessingModelChildParameterSource.fromStaticValue('TEMP.gpkg')]
        )

        # define model outputs
        mop_name_dst = 'speclib_output'

        model.addOutput(QgsProcessingOutputVectorLayer(mop_name_dst))
        m_output_dst = QgsProcessingModelOutput(mop_name_dst)
        m_output_dst.setChildOutputName(SpectralProfileWriter.OUTPUT)
        m_output_dst.setChildId(calgW.childId())
        calgW.setModelOutputs({mop_name_dst: m_output_dst})




        s = ""
        # Define which of the processing step results should be used as model output
        # use sinks of last algorithm as model outputs

        model.initAlgorithm(configuration)
        structureModelGraphicItems(model)

        # outputID = calgW.modelOutput('speclib_target').childId()
        parameters = {mip_name_src: speclib_source,
                      mip_name_dst: speclib_target
                      }

        success, msg = model.checkParameterValues(parameters, context)
        self.assertTrue(success, msg=msg)
        self.assertTrue(model.prepareAlgorithm(parameters, context, feedback), msg=feedback.textLog())
        # model.preprocessParameters(parameters)
        n0 = len(parameters[mip_name_src])
        model_results, success = model.run(parameters, context, feedback)
        self.assertTrue(success, msg=feedback.textLog())
        self.assertIsInstance(model_results, dict)
        model_result = outputParameterResult(model_results, mop_name_dst)


        from processing.modeler.ModelerDialog import ModelerDialog
        d = ModelerDialog(model=model)

        # note: this will work only if environmental variable CI=False
        self.showGui(d)

    def test_example_register_spectral_algorithms(self):
        alg = SpectralPythonCodeProcessingAlgorithm()
        # ._algs.append(alg)
        # self.testProvider().refreshAlgorithms()
        self.testProvider().addAlgorithm(alg)

        self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralPythonCodeProcessingAlgorithm)

        self.assertTrue(alg.name() in [a.name() for a in spectral_algorithms()])

        # open modeler and see if the algorithm appears there

        from processing.modeler.ModelerDialog import ModelerDialog
        d = ModelerDialog()

        # note: this will work only if environmental variable CI=False
        self.showGui(d)

    def test_SpectralLibraryWidget(self):

        n_profiles_per_n_bands = 50
        n_bands = [6, 30, 177]
        alg = SpectralPythonCodeProcessingAlgorithm()
        self.testProvider().addAlgorithm(alg)
        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)
        w = SpectralLibraryWidget(speclib=sl)

        self.showGui(w)
        s = ""
        pass


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

    def test_SpectralProcessingModelList(self):

        m1 = self.create_spectral_processing_model('Model1')
        m2 = self.create_spectral_processing_model('Model2')

        model = SpectralProcessingModelList()
        self.assertTrue(model.rowCount() == 0)

        model.addModel(m1)
        model.addModel(m1)
        model.addModel(m2)

        self.assertTrue(len(model) == 2)
        self.assertTrue(model.rowCount() == 2)
        self.assertEqual(m2, model[1])
        idx = model.index(1, 0)

        self.assertTrue(model.data(idx, Qt.DisplayRole) == m2.id())
        self.assertEqual(m2, model.data(idx, Qt.UserRole))
        self.assertEqual(m2.id(), model.data(idx, Qt.DisplayRole))

        model.removeModel(m1)

        self.assertTrue(len(model) == 1)
        self.assertFalse(m1 in model)
        self.assertTrue(m2 in model)

    def test_SpectralLibraryWidget(self):
        self.initProcessingRegistry()
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]

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
        RENAME = {'profiles': 'ASD', 'profiles1': 'Sentinel2'}
        sl.startEditing()
        for oldName, newName in RENAME.items():
            idx = sl.fields().lookupField(oldName)
            sl.renameAttribute(idx, newName)
            s = ""
        sl.commitChanges()
        SLW = SpectralLibraryWidget(speclib=sl)

        # create a new model
        spm = TestObjects.createSpectralProcessingModel()

        PC: SpectralProfilePlotControl = SLW.plotControl()
        PC.addModel(spm)

        # set spectral mode to 1st item
        PC.setData(PC.index(0, PC.CIX_MODEL), spm, role=Qt.EditRole)
        # from qps.resources import ResourceBrowser
        # rb = ResourceBrowser()
        self.showGui(SLW)
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
                      alg.INPUT_FIELD: None # automatically selected the 1st profile field
                      }
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

    def test_SpectralProfileWriter(self):
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        context.setFeedback(feedback)
        configuration = {}
        alg: SpectralProfileWriter = SpectralProfileWriter()
        alg.initAlgorithm(configuration)
        dummy = SpectralProfileBlock.dummy(n=5)

        # 1. write into new spectral library

        parameters = {alg.INPUT: dummy,
                      alg.OUTPUT: 'TEMP',
                      }

        self.assertTrue(alg.prepareAlgorithm(parameters, context, feedback), msg=feedback.textLog())
        results = alg.processAlgorithm(parameters, context, feedback)
        speclib1 = results.get(alg.OUTPUT, None)
        self.assertIsInstance(speclib1, SpectralLibrary)
        self.assertEqual(dummy.n_profiles(), len(speclib1))

        for i, profile in enumerate(speclib1):
            yValueDummy = dummy.data()[:, :, i].flatten().tolist()
            yValueProfile = profile.yValues()
            self.assertListEqual(yValueDummy, yValueProfile)
            self.assertEqual(profile.xValues(), list(dummy.spectralSetting().x()))
            self.assertEqual(profile.xUnit(), dummy.spectralSetting().xUnit())

        # 2. write to existing spectral library, new profile files
        dummy2 = SpectralProfileBlock.dummy(n=10)
        parameters = {alg.INPUT: dummy2,
                      alg.MODE: 'Match',
                      alg.OUTPUT_FIELD: 'profiles2',
                      alg.OUTPUT: speclib1,
                      }
        self.assertTrue(alg.prepareAlgorithm(parameters, context, feedback), msg=feedback.textLog())
        results = alg.processAlgorithm(parameters, context, feedback)
        self.assertEqual(speclib1, results.get(alg.OUTPUT, None))
        self.assertTrue(speclib1.featureCount() == 10)

        LUT = profile_field_lookup(speclib1)
        self.assertTrue('profiles2' in LUT.keys())
        self.assertTrue(len(speclib1) == dummy2.n_profiles())
        for i, profile in enumerate(speclib1):
            profile: SpectralProfile
            profile.setCurrentProfileField('profiles2')
            yValueDummy = dummy2.data()[:, :, i].flatten().tolist()
            yValueProfile = profile.yValues()
            self.assertListEqual(yValueDummy, yValueProfile)

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

    def create_spectral_processing_model(self, name='') -> QgsProcessingModelAlgorithm:
        self.initProcessingRegistry()
        m = SpectralProcessingModelCreatorTableModel()
        m.setModelName(name)
        m.addAlgorithm(SpectralXUnitConversion())

        model = m.createModel()
        assert is_spectral_processing_model(model)
        return model

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
        alg: SpectralPythonCodeProcessingAlgorithm = reg.algorithmById(
            'testalgorithmprovider:spectral_python_code_processing')

        self.assertIsInstance(alg, QgsProcessingAlgorithm)
        self.assertTrue(is_spectral_processing_algorithm(alg, SpectralProfileIOFlag.All))

        childAlg = QgsProcessingModelChildAlgorithm(alg.id())
        childAlg.generateChildId(model)
        childAlg.setDescription('MySpectralAlg')

        childId: str = model.addChildAlgorithm(childAlg)

        # Important: addChildAlgorithm creates a copy
        childAlg = model.childAlgorithm(childId)

        input_name = 'input_profiles'
        output_name = 'output_profiles'

        model.addModelParameter(SpectralProcessingProfiles(input_name, description='Source Speclib'),
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
        model.addOutput(SpectralProcessingProfilesOutput(output_name))
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

        if False:
            dialog = ModelerParametersDialog(childAlg.algorithm(),
                                             model,
                                             algName=childId,
                                             configuration=configuration)
        else:
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

    def test_SpectralProcessingModelCreatorTableView(self):
        reg, guiReg = self.initProcessingRegistry()
        reg: QgsProcessingRegistry
        guiReg: QgsProcessingGuiRegistry

        algs = [a for a in spectral_algorithms() if is_spectral_processing_algorithm(a, SpectralProfileIOFlag.All)]
        self.assertTrue(len(algs) > 0)
        m = SpectralProcessingModelCreatorTableModel()
        self.assertIsInstance(m, QAbstractListModel)
        tv = SpectralProcessingModelCreatorTableView()
        tv.setModel(m)
        tv.show()
        for i, a in enumerate(algs):
            m.addAlgorithm(a, name=f'AlgA{i + 1}')
        for a in algs:
            m.addAlgorithm(a.id(), name=f'AlgB{i + 1}')

        n = len(m)
        self.assertTrue(n == len(algs) * 2)

        tv.selectRow(1)
        selectedWrapper = tv.currentIndex().data(Qt.UserRole)
        self.assertIsInstance(selectedWrapper, SpectralProcessingModelCreatorAlgorithmWrapper, selectedWrapper)
        self.assertTrue(selectedWrapper.name == 'AlgA2')
        m.removeAlgorithms(selectedWrapper)
        self.assertTrue(len(m) == n - 1)
        self.showGui(tv)

        model = m.createModel()
        self.assertTrue(is_spectral_processing_model(model))

        configuration = {}
        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        parameters = {}
        for p in model.parameterDefinitions():
            if isinstance(p, SpectralProcessingProfiles):
                parameters[p.name()] = TestObjects.createSpectralLibrary()

        self.assertTrue(model.prepareAlgorithm(parameters, context, feedback))
        results = model.processAlgorithm(parameters, context, feedback)
        for o in model.outputDefinitions():
            values = outputParameterResult(results, o.name())
            if isinstance(o, SpectralProcessingProfilesOutput):
                self.assertIsInstance(values, list)
                for block in values:
                    self.assertIsInstance(block, SpectralProfileBlock)

        self.showGui(tv)

    def test_SpectralProcessingWidget(self):
        self.initProcessingRegistry()
        w = SpectralProcessingWidget()

        id = 'testalgorithmprovider:spectral_processing_algorithm_example'
        # id2 = 'testalgorithmprovider:'

        for a in spectral_algorithms():
            if is_spectral_processing_algorithm(a, SpectralProfileIOFlag.Inputs | SpectralProfileIOFlag.Outputs):
                w.mProcessingModelTableModel.addAlgorithm(a)
                w.mProcessingModelTableModel.addAlgorithm(a.id())
        # for i in range(w.mProcessingModelTableModel.rowCount()):
        #    w.mTableView.selectRow(i)
        from qgis.PyQt.QtWidgets import QMainWindow
        M = QMainWindow()
        M.setCentralWidget(w)
        toolbar = QToolBar()
        for a in w.findChildren(QAction):
            toolbar.addAction(a)
        M.addToolBar(toolbar)
        success, error = w.verifyModel()

        self.assertTrue(success, msg=error)
        model = w.model()
        self.assertTrue(is_spectral_processing_model(model))

        # save and load models
        test_dir = self.createTestOutputDirectory() / 'spectral_processing'
        os.makedirs(test_dir, exist_ok=True)
        path = test_dir / 'mymodel.model3'
        wrappers_before = [w for w in w.mProcessingModelTableModel if w.is_active]
        w.saveModel(path)
        w.clearModel()
        self.assertTrue(len(w.mProcessingModelTableModel) == 0)
        w.loadModel(path)
        wrappers_after = [w for w in w.mProcessingModelTableModel if w.is_active]
        self.assertTrue(len(wrappers_after) == len(wrappers_before))
        # for w_b, w_a in zip(wrappers_before, wrappers_after):
        #    self.assertEqual(w_b.name, w_a.name)

        w.loadModel(model)

        self.showGui(M)

    def test_processing_algorithms(self):
        self.initProcessingRegistry()

        alg = SpectralPythonCodeProcessingAlgorithm()
        alg.initAlgorithm({})
        self.assertTrue(is_spectral_processing_algorithm(alg))

        for a in createSpectralAlgorithms():
            self.assertIsInstance(a, QgsProcessingAlgorithm)
            a.initAlgorithm({})
            has_inputs = is_spectral_processing_algorithm(a, SpectralProfileIOFlag.Inputs)
            has_outputs = is_spectral_processing_algorithm(a, SpectralProfileIOFlag.Outputs)
            self.assertTrue(has_inputs or has_outputs)

    def test_SpectralProcessingAlgorithmTreeView(self):

        self.initProcessingRegistry()
        tv = SpectralProcessingAlgorithmTreeView()
        m = SpectralProcessingAlgorithmModel(tv)
        tv.setModel(m)

        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
