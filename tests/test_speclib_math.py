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
    QgsProcessingParameterWidgetContext, QgsProcessingAbstractParameterDefinitionWidget
from qgis.core import QgsVectorLayer, QgsMapLayer, QgsRasterLayer, QgsProject, QgsActionManager, \
    QgsField, QgsApplication, QgsWkbTypes, QgsProcessingRegistry, QgsProcessingContext, QgsProcessingParameterDefinition

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

    def test_SpectralAlgorithmInputType(self):


        procReg = QgsApplication.instance().processingRegistry()
        procGuiReg: QgsProcessingGuiRegistry = QgsGui.processingGuiRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)
        parameterType = SpectralAlgorithmInputType()
        self.assertTrue(procReg.addParameterType(parameterType))

        paramFactory = SpectralMathParameterWidgetFactory()
        procGuiReg.addParameterWidgetFactory(paramFactory)

        #provider = SpectralAlgorithmProvider()
        #self.assertTrue(procReg.addProvider(provider))

        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface
        from processing.modeler.ModelerDialog import ModelerDialog
        md = ModelerDialog.create()
        #md.model().addModelParameter()
        #md.saveModel()
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