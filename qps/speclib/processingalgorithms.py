import typing

from qgis.core import \
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, \
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingFeatureSource, QgsProcessingParameterField

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget, QLabel, QHBoxLayout

from .processing import \
    SpectralAlgorithmInput, SpectralAlgorithmOutput, SpectralAlgorithmOutputDestination,\
    SpectralProfileBlock

class SpectralProfileReader(QgsProcessingAlgorithm):
    """
    Reads spectral profile block from SpectralLibraries / Vectorlayers with BLOB columns
    """
    INPUT = 'input_speclib'
    INPUT_FIELD = 'input_field'
    OUTPUT = 'output_profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Reads spectral profiles'

    def initAlgorithm(self, configuration: dict):

        p1 = QgsProcessingParameterVectorLayer(self.INPUT)
        self.addParameter(p1)
        p2 = QgsProcessingParameterField(self.INPUT_FIELD,
                                         parentLayerParameterName=self.INPUT,
                                         allowMultiple=False)
        self.addParameter(p2)

        o1 = SpectralAlgorithmOutput(self.OUTPUT)
        self.addOutput(o1)
        pass

    def asPythonCommand(self) -> str:
        pass

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

    def createInstance(self):
        alg = SpectralProfileReader()
        return alg

    def displayName(self) -> str:
        return 'Spectral Profile Reader'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Loader Help String'

    def name(self):
        return 'SpectralProfileReader'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        speclib = self.parameterAsVectorLayer(parameters, context)

        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class SpectralProfileWriter(QgsProcessingAlgorithm):
    INPUT = 'input_profiles'
    OUTPUT = 'output_speclib'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Writes spectral profiles'

    def initAlgorithm(self, configuration: dict):

        p1 = SpectralAlgorithmInput(self.INPUT)
        self.addParameter(p1)

        o1 = SpectralAlgorithmOutput(self.OUTPUT)
        self.addOutput(o1)
        self.mParameters.append([p1, o1])

    def asPythonCommand(self) -> str:
        pass

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

    def createInstance(self):
        alg = SpectralProfileReader()
        return alg

    def displayName(self) -> str:
        return 'SpectralProfileReader'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Loader Help String'

    def name(self):
        return 'Spectral Profile Loader'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        speclib = self.parameterAsVectorLayer(parameters, context)

        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class DummyAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'Input Profiles'
    OUTPUT = 'Output Profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mFunction: typing.Callable = None

    def description(self) -> str:
        return 'Dummy Algorithm Description'

    def initAlgorithm(self, configuration: dict):


        p1 = SpectralAlgorithmInput(self.INPUT, description='Input Profiles')
        self.addParameter(p1, createOutput=False)

        o1 = SpectralAlgorithmOutputDestination(self.OUTPUT, description='Modified profiles')
        self.addParameter(o1)
        pass

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        input_profiles: SpectralAlgorithmInput = self.parameterDefinition(self.INPUT)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles.profileBlocks():
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)

            if isinstance(self.mFunction, typing.Callable):
                profileBlock = self.mFunction(profileBlock)

            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS

    def setProcessingFunction(self, function: typing.Callable):

        assert isinstance(function, typing.Callable)
        self.mFunction = function

    def asPythonCommand(self) -> str:
        pass

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
        label = QLabel('Placeholder custom widget')
        l = QHBoxLayout()
        l.addWidget(label)
        w.setLayout(l)
        return w

    def createExpressionContext(self,
                                parameter: dict,
                                context: QgsProcessingContext,
                                source: QgsProcessingFeatureSource,
                                ):

        return None

    def createInstance(self):

        alg = DummyAlgorithm()
        return alg

    def displayName(self) -> str:

        return 'Dummy Profile Algorithm'

    def flags(self):

        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):

        return 'qps'

    def helpString(self) -> str:
        return 'Dummy Alg Help String'

    def name(self):
        return 'Dummy Alg Name'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        return True

