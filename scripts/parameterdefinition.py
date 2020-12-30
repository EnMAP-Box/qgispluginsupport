from qgis.core import QgsProcessingParameterDefinition, QgsApplication, QgsProcessingRegistry, QgsProcessingParameterType
from qgis.PyQt.QtCore import QObject

REFS = []

class MyParameter(QgsProcessingParameterDefinition):
    """
    Definition of my parameter
    """
    def __init__(self, name='MyParameter', description='My Parameter', optional:bool=False):
        super().__init__(name, description=description, optional=optional)
        self.mMyValue: str = 'my_value'

        if True: # keep a python reference on the MyParameter instance
            global REFS
            REFS.append([self, super(MyParameter, self)])


    def isDestination(self):
        return False

    def type(self):
        return 'my_type'

    def clone(self):
        p = MyParameter()
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
        return 'My Type'

    def className(self) -> str:
        return 'MyInputType'

    def create(self, name):
        p = MyParameter(name=name)
        return p

    def metadata(self):
        return {}

    def flags(self):
        return QgsProcessingParameterType.ExposeToModeler

    def id(self):
        return 'my_type'

procReg = QgsApplication.instance().processingRegistry()
assert isinstance(procReg, QgsProcessingRegistry)
parameterType = MyParameterType()
procReg.addParameterType(parameterType)