# noinspection PyPep8Naming
import os
import unittest
import datetime

import xmlrunner
from PyQt5.QtCore import QVariant
from qgis._core import QgsProcessingAlgorithm, QgsProcessingModelChildAlgorithm, QgsProject, QgsProcessingModelOutput, \
    QgsField, QgsProcessingModelParameter, QgsProcessingModelChildParameterSource, QgsProcessingParameterRasterLayer, \
    QgsProcessingOutputRasterLayer, QgsProcessingFeedback, QgsProcessingContext, QgsProcessingModelAlgorithm, \
    QgsProcessingRegistry, QgsApplication
from qgis._gui import QgsGui, QgsProcessingParameterWidgetContext

from qgis.gui import QgsProcessingGuiRegistry, QgsProcessingParameterDefinitionDialog

from qgis.core import QgsProcessingProvider

from qps import initResources, initAll
from qps.speclib.core import profile_field_lookup
from qps.testing import TestObjects, StartOptions
from qps.speclib.gui.spectrallibrarywidget import *
from qps.speclib.gui.spectralprocessingwidget import SpectralProcessingWidget, SpectralProcessingAlgorithmTreeView, SpectralProcessingAlgorithmModel
from qps.testing import TestCase, TestAlgorithmProvider
import numpy as np

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

    def algorithmProviderTesting(self) -> 'TestAlgorithmProvider':
        return QgsApplication.instance().processingRegistry().providerById(TestAlgorithmProvider.NAME.lower())

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
        n_profiles_per_n_bands = 5
        n_bands = [177, 6]
        SpectralLibraryWidget._SHOW_MODEL = True

        sl = TestObjects.createSpectralLibrary(n_profiles_per_n_bands, n_bands=n_bands)
        RENAME = {'profiles': 'ASD', 'profiles1': 'Ref'}
        sl.startEditing()
        for oldName, newName in RENAME.items():
            idx = sl.fields().lookupField(oldName)
            sl.renameAttribute(idx, newName)
            s = ""
        # sl.addAttribute(QgsField(name='notes', type=QVariant.String)),
        sl.addAttribute(QgsField(name='date', type=QVariant.Date)),
        sl.commitChanges()
        SLW = SpectralLibraryWidget(speclib=sl)

        SLW2 = SpectralLibraryWidget(speclib=TestObjects.createSpectralLibrary(20))


        # create a new model
        spm = TestObjects.createSpectralProcessingModel()

        procReg = QgsApplication.instance().processingRegistry()
        provider = procReg.providerById('project')
        from processing.modeler.ProjectProvider import ProjectProvider
        self.assertIsInstance(provider, ProjectProvider)
        provider.add_model(spm)
        
        PC: SpectralProfilePlotControlModel = SLW.plotControl()

        # set spectral model to 1st item
        PC.setData(PC.index(0, PC.PIX_MODEL), spm, role=Qt.EditRole)
        # from qps.resources import ResourceBrowser
        # rb = ResourceBrowser()
        self.showGui([SLW, SLW2])
        s = ""
        pass


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

    def test_SpectralProcessingWidget(self):
        self.initProcessingRegistry()
        speclib = TestObjects.createSpectralLibrary()
        w = SpectralProcessingWidget()
        w.setSpeclib(speclib)

        self.assertTrue(w.model() is None)

        # model = TestObjects.createRasterProcessingModel()
        reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        alg = reg.algorithmById('gdal:rearrange_bands')
        w.loadModel(alg)

        from qgis.PyQt.QtWidgets import QMainWindow
        M = QMainWindow()
        M.setCentralWidget(w)
        toolbar = QToolBar()
        for a in w.findChildren(QAction):
            toolbar.addAction(a)
        M.addToolBar(toolbar)
        # save and load models
        test_dir = self.createTestOutputDirectory() / 'spectral_processing'
        os.makedirs(test_dir, exist_ok=True)
        path = test_dir / 'mymodel.model3'


        self.showGui(M)

    def test_SpectralProcessingAlgorithmTreeView(self):

        self.initProcessingRegistry()
        tv = SpectralProcessingAlgorithmTreeView()
        m = SpectralProcessingAlgorithmModel(tv)
        tv.setModel(m)

        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
