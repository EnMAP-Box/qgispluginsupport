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
    QgsProcessingModelChildAlgorithm, QgsProcessingModelChildParameterSource

from processing.modeler.ModelerDialog import ModelerParametersDialog
from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath

from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *
from qps.speclib.processing import *
from qps.testing import TestCase
from qps.models import TreeView, TreeNode, TreeModel

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

        provider = SpectralAlgorithmProvider()
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


        m = SimpleProcessingModelAlgorithmChain()
        self.assertIsInstance(m, QAbstractListModel)

        algs = spectral_algorithms()

        w = QTableView()
        w.setModel(m)
        for a in algs:
            m.addAlgorithm(a)
            m.addAlgorithm(a.id())


        self.showGui(w)

    def test_AlgorithmWidget(self):
        self.initProcessingRegistry()

        wrapper = QgsGui.processingGuiRegistry().createModelerParameterWidget(dialog.model,
                                                                              dialog.childId,
                                                                              param,
                                                                              dialog.context)

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
