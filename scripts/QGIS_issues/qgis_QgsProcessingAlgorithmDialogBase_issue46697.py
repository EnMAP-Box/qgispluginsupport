from qgis.core import QgsApplication, QgsProcessingRegistry
from qgis.gui import QgsProcessingAlgorithmDialogBase
from qgis.testing.mocked import start_app

APP = start_app()

from processing.core.Processing import Processing
from qgis.analysis import QgsNativeAlgorithms

QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
Processing.initialize()

reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
alg1 = reg.algorithmById('native:rescaleraster')
alg2 = reg.algorithmById('gdal:aspect')

assert alg1.shortHelpString() != ''
assert alg2.shortHelpString() == ''


class ExampleDialog(QgsProcessingAlgorithmDialogBase):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


VisibleHelp = ExampleDialog()

VisibleHelp.setAlgorithm(alg1.create())
VisibleHelp.setWindowTitle(f'{VisibleHelp.windowTitle()} (Visible Help)')

HiddenHelp = ExampleDialog()
HiddenHelp.setAlgorithm(alg1.create())
HiddenHelp.setAlgorithm(alg2.create())  # no short help -> will hide the text browser
HiddenHelp.setAlgorithm(alg1.create())  # text browser remains hidden
HiddenHelp.setWindowTitle(f'{HiddenHelp.windowTitle()} (Hidden Help)')

VisibleHelp.show()
HiddenHelp.show()
APP.exec_()
