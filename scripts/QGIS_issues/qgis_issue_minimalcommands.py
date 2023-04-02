from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterString, QgsProcessingContext
from qgis.testing import TestCase, start_app

start_app()

LONG_TEXT = """A very long and\nmultiline text."""


class ExampleAlgorithm(QgsProcessingAlgorithm):

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return 'examplealg'

    def displayName(self) -> str:
        return 'Example algorithm with default values'

    def shortHelpString(self) -> str:
        return self.displayName()

    def initAlgorithm(self, configuration: dict) -> None:
        self.addParameter(
            QgsProcessingParameterString('Par1', defaultValue=LONG_TEXT)
        )


class AlgorithmTest(TestCase):

    def test_parameterization_strings(self):
        alg = ExampleAlgorithm()
        configuration = {}
        alg.initAlgorithm(configuration)

        context = QgsProcessingContext()

        parameters = dict(Par1='Short Text')
        pythonCmd = alg.asPythonCommand(parameters, context)
        self.assertEqual(pythonCmd, "processing.run(\"examplealg\", {'Par1':'Short Text'})")

        cliCmd, success = alg.asQgisProcessCommand(parameters, context)
        self.assertEqual(cliCmd, "qgis_process run examplealg --Par1='Short Text'")
        self.assertTrue(success)

        # test with default parameters
        parameters = dict()
        pythonCmd = alg.asPythonCommand(parameters, context)
        self.assertEqual(pythonCmd, "processing.run(\"examplealg\", {})")

        cliCmd, success = alg.asQgisProcessCommand(parameters, context)
        self.assertEqual(cliCmd, "qgis_process run examplealg")
        self.assertTrue(success)
