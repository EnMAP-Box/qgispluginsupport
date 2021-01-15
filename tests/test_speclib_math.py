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
from qps.speclib.math import *
from qps.testing import TestCase
from qps.models import TreeView, TreeNode, TreeModel

class SpectralMathTests(TestCase):

    @classmethod
    def setUpClass(cls, cleanup=True, options=StartOptions.All, resources=[]) -> None:

        super(SpectralMathTests, cls).setUpClass(cleanup=cleanup, options=options, resources=resources)


    def initProcessingRegistry(self):
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        paramFactory = SpectralMathParameterWidgetFactory()
        procGuiReg.addParameterWidgetFactory(paramFactory)

        parameterType = SpectralAlgorithmInputType()
        self.assertTrue(procReg.addParameterType(parameterType))


        provider = SpectralAlgorithmProvider()
        self.assertTrue(procReg.addProvider(provider))

        self.mFac = paramFactory
        self.mPRov = provider

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





        s = ""
        pass
    def test_SimpleModel(self):

        m = SimpleSpectralMathModel()

        self.assertIsInstance(m, QgsProcessingModelAlgorithm)

        m

    def test_AlgoritmWidget(self):
        self.initProcessingRegistry()

        wrapper = QgsGui.processingGuiRegistry().createModelerParameterWidget(dialog.model,
                                                                              dialog.childId,
                                                                              param,
                                                                              dialog.context)

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

    def test_loadinqgis(self):

        s = ""

    def test_functiontableview(self):

        tv = SpectralMathFunctionTableView()
        m = SpectralMathFunctionModel()
        tv.setModel(m)

        self.assertTrue(len(m) == 0)
        func = GenericSpectralAlgorithm()
        self.assertIsInstance(func, SpectralAlgorithm)
        m.addFunction(func)

        self.assertTrue(len(m) == 1)

        self.showGui(tv)

    def test_spectralMathFunctionRegistry(self):

        reg = SpectralMathFunctionRegistry()
        f1 = GenericSpectralAlgorithm()
        f2 = XUnitConversion()

        self.assertTrue(reg.registerFunction(f1))
        self.assertFalse(reg.registerFunction(f1))
        self.assertFalse(reg.registerFunction(GenericSpectralAlgorithm()))
        self.assertTrue(reg.registerFunction(f2))
        self.assertTrue(len(reg) == 2)
        self.assertTrue(reg.unregisterFunction(f2))
        self.assertTrue(len(reg) == 1)
        self.assertFalse(reg.unregisterFunction(f2))

        reg.registerFunction(f2, group='Group')

        tv = TreeView()
        tv.setModel(reg)

        self.showGui(tv)



    def test_spectralMathWidget(self):

        w = SpectralMathWidget()
        f1 = GenericSpectralAlgorithm()
        f2 = XUnitConversion()

        model = w.functionModel()
        model.addFunctions([f1, f2])
        model.removeFunctions([f2, f1])
        model.addFunctions([f2, f1])

        doc = QDomDocument()
        node = doc.createElement('functions')
        model.writeXml(node, doc)

        model2 = SpectralMathFunctionModel.readXml(node)
        self.assertIsInstance(model2, SpectralMathFunctionModel)
        self.assertTrue(len(model) == len(model2))
        for f1, f2 in zip(model, model2):
            self.assertIsInstance(f1, SpectralAlgorithm)
            self.assertIsInstance(f2, SpectralAlgorithm)
            self.assertEqual(f1.id(), f2.id())

        self.assertIsInstance(w, QWidget)
        self.showGui(w)