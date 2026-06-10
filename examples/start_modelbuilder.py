from processing.modeler.ModelerDialog import ModelerDialog
from qgis.core import QgsApplication, QgsProcessingRegistry, QgsProcessingAlgorithm, \
    QgsProcessingParameterNumber, QgsProcessingParameterRasterDestination, \
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingParameterFile
from qps.testing import start_app, ExampleAlgorithmProvider

app: QgsApplication = start_app()


class MyParameter(QgsProcessingParameterFile):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class TestProcessingAlgorithm(QgsProcessingAlgorithm):

    def __init__(self):
        super(TestProcessingAlgorithm, self).__init__()

    def createInstance(self):
        return TestProcessingAlgorithm()

    def name(self):
        return 'exmaplealg'

    def displayName(self):
        return 'Example Algorithm'

    def groupId(self):
        return 'exampleapp'

    def group(self):
        return 'TEST APPS'

    def initAlgorithm(self, configuration=None):
        self.addParameter(MyParameter('pathInput', 'The Input Dataset'))
        self.addParameter(
            QgsProcessingParameterNumber('value', 'The value', QgsProcessingParameterNumber.Double, 1, False,
                                         0.00, 999999.99))
        self.addParameter(QgsProcessingParameterRasterDestination('pathOutput', 'The Output Dataset'))

    def processAlgorithm(self, parameters: dict, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        outputs = {}
        return outputs


myProvider = ExampleAlgorithmProvider()
myProvider._algs.append(TestProcessingAlgorithm())
myProvider.loadAlgorithms()

registry: QgsProcessingRegistry = app.processingRegistry()
registry.addProvider(myProvider)

D = ModelerDialog()
D.show()

app.exec()
