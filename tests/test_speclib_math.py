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


class SpectralMathTests(TestCase):


    def test_functiontableview(self):

        tv = SpectralMathFunctionTableView()
        m = SpectralMathFunctionModel()
        tv.setModel(m)

        self.assertTrue(len(m) == 0)
        func = GenericSpectralMathFunction()
        self.assertIsInstance(func, AbstractSpectralMathFunction)
        m.addFunction(func)

        self.assertTrue(len(m) == 1)

        self.showGui(tv)

    def test_spectralMathWidget(self):

        w = SpectralMathWidget()
        w.mFunctionModel.addFunction(GenericSpectralMathFunction())
        self.assertIsInstance(w, QWidget)
        self.showGui(w)