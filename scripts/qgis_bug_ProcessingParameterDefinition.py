from qgis.core import QgsProcessingParameterDefinition, QgsApplication, \
    QgsProcessingRegistry, QgsProcessingParameterType, \
    QgsProcessingParameterBoolean
from qgis.gui import QgsProcessingParameterDefinitionDialog
from qgis.PyQt.QtCore import QObject

REFS = []

MY_TYPE_ID = 'my_type'

class MyParameter(QgsProcessingParameterBoolean):
    """
    Definition of my parameter
    """
    def __init__(self, name='MyParameter', description='My Parameter', optional:bool=False):
        super(MyParameter, self).__init__(name, description=description, optional=optional)
        self.mMyValue: str = 'my_value'
        s = ""
        if False: # keep a python reference on the MyParameter instance
            global REFS
            REFS.append([self,
                         sip.wrapinstance(sip.unwrapinstance(self), MyParameter)])

    def isDestination(self):
        return False

    @staticmethod
    def type():
        return MY_TYPE_ID

    def clone(self):
        p = MyParameter(self.name(), description=self.description())
        p.fromVariantMap(self.toVariantMap())
        return p

    def description(self):
        return 'My Parameter Description'

    def toolTip(self):
        return 'My Parameter Tooltip'

    def toVariantMap(self):
        result = super().toVariantMap()
        result['my_value'] = self.mMyValue
        return result

    def fromVariantMap(self, map:dict):
        super().fromVariantMap(map)
        self.mMyValue = map.get('my_value', '')

        return True


class MyParameterType(QgsProcessingParameterType):
    """
    Describes MyParameter in the Modeler's parameter list
    """
    def __init__(self):
        super().__init__()

    def description(self):
        return 'A single spectral profile or set of similar profiles'

    def name(self):
        return 'MyType'

    def className(self) -> str:
        return 'MyInputType'

    def create(self, name):
        p = MyParameter(name=name)
        global REFS
        REFS.append(p)
        return p

    def metadata(self):
        return {}

    def flags(self):
        return QgsProcessingParameterType.ExposeToModeler

    def id(self):
        return MY_TYPE_ID


from qgis.gui import *
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsDualView, QgsOptionsDialogBase, QgsAttributeForm, QgsGui, \
    QgsSearchWidgetWrapper, QgsMessageBar, QgsProcessingGuiRegistry, QgsProcessingGui, \
    QgsProcessingParameterWidgetContext, QgsProcessingAbstractParameterDefinitionWidget
from qgis.core import QgsVectorLayer, QgsMapLayer, QgsRasterLayer, QgsProject, QgsActionManager, \
    QgsField, QgsApplication, QgsWkbTypes, QgsProcessingRegistry,  \
    QgsProcessingContext, QgsProcessingParameterDefinition, QgsProcessingModelAlgorithm

from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath
import unittest
import random
import math
import xmlrunner
from qps.testing import TestObjects, TestCase, StartOptions
import numpy as np
from qps.speclib.io.envi import *
from qps.speclib.io.asd import *
from qps.speclib.gui import *
from qps.speclib.processing import *
from qps.testing import TestCase
from qps.models import TreeView, TreeNode, TreeModel

class SpectralMathTests(TestCase):

    def test_TestMyParameter(self):
        procReg = QgsApplication.instance().processingRegistry()
        assert isinstance(procReg, QgsProcessingRegistry)

        myType = MyParameterType()
        procReg.addParameterType(myType)

        import processing.modeler.ModelerDialog
        import qgis.utils
        processing.modeler.ModelerDialog.iface = qgis.utils.iface
        from processing.modeler.ModelerDialog import ModelerDialog, createContext

        model: QgsProcessingModelAlgorithm = QgsProcessingModelAlgorithm()
        model.setName('MyModelName')
        model.setGroup('MyModelGroup')
        md = ModelerDialog.create(model)
        self.assertIsInstance(md, ModelerDialog)


        self.showGui(md)

        typeBool = QgsApplication.processingRegistry().parameterType('boolean')
        typeMyType = QgsApplication.processingRegistry().parameterType('my_type')
        for i, myType in enumerate([typeBool, typeMyType]):
            self.assertIsInstance(myType, QgsProcessingParameterType)
            context = createContext()
            widget_context = md.create_widget_context()
            dlg = QgsProcessingParameterDefinitionDialog(type=myType.id(),
                                                         context=context,
                                                         widgetContext=widget_context,
                                                         algorithm=md.model())

            name = f'parameter{i}_type_{myType.name()}'
            parameter = dlg.createParameter(name)

            variant_map = parameter.toVariantMap()
            self.assertIsInstance(variant_map, dict)
            self.assertEqual(variant_map.get('name', None), name)
            s = ""
            #dlg.exec_()


        model: QgsProcessingModelAlgorithm = md
        #md.model().addModelParameter()
        #md.saveModel()
        self.showGui([md])


if __name__ == '__main__':

    procReg = QgsApplication.instance().processingRegistry()
    assert isinstance(procReg, QgsProcessingRegistry)
    parameterType = MyParameterType()
    procReg.addParameterType(parameterType)