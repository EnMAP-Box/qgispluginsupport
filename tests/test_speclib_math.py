# noinspection PyPep8Naming
import unittest
import random
import math
import xmlrunner
from qps.testing import TestObjects, TestCase, StartOptions
import numpy as np
from qgis.gui import QgsMapCanvas, QgsDualView, QgsOptionsDialogBase, QgsAttributeForm, QgsGui, \
    QgsSearchWidgetWrapper, QgsMessageBar
from qgis.core import QgsVectorLayer, QgsMapLayer, QgsRasterLayer, QgsProject, QgsActionManager, \
    QgsField, QgsApplication, QgsWkbTypes
from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath

from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *
from qps.speclib.math import *
from qps.testing import TestCase
from qps.models import TreeView, TreeNode, TreeModel

class SpectralMathTests(TestCase):



    def test_functiontableview(self):

        tv = SpectralMathFunctionTableView()
        m = SpectralMathFunctionModel()
        tv.setModel(m)

        self.assertTrue(len(m) == 0)
        func = GenericSpectralMathFunction()
        self.assertIsInstance(func, SpectralMathFunction)
        m.addFunction(func)

        self.assertTrue(len(m) == 1)

        self.showGui(tv)

    def test_spectralMathFunctionRegistry(self):

        reg = SpectralMathFunctionRegistry()
        f1 = GenericSpectralMathFunction()
        f2 = XUnitConversion()

        self.assertTrue(reg.registerFunction(f1))
        self.assertFalse(reg.registerFunction(f1))
        self.assertFalse(reg.registerFunction(GenericSpectralMathFunction()))
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
        f1 = GenericSpectralMathFunction()
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
            self.assertIsInstance(f1, SpectralMathFunction)
            self.assertIsInstance(f2, SpectralMathFunction)
            self.assertEqual(f1.id(), f2.id())

        self.assertIsInstance(w, QWidget)
        self.showGui(w)