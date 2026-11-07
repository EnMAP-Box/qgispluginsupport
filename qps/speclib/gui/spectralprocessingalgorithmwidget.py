from typing import List, Dict, Any, Tuple

from PyQt6.QtWidgets import QDialog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
)
from qgis._core import QgsProcessingUtils, QgsRasterLayer, QgsProcessingParameterMultipleLayers, QgsProcessingContext, \
    QgsMapLayer, QgsProcessingParameterRasterLayer
from qgis._gui import QgsProcessingParametersGenerator
from qgis.core import QgsProcessingAlgorithm, QgsVectorLayer
from qgis.gui import QgsPanelWidget

from core.spectrallibraryrasterdataprovider import VectorLayerFieldRasterDataProvider
from .spectralprocessingalgorithmmodel import SpectralProcessingAlgorithmModel
from .spectralprocessingcontextgenerator import SpectralProcessingContextGenerator
from .spectralprocessingparameterswidget import SpectralProcessingParametersWidget
from ...reimplementation.processingalgorithmdialog import ProcessingAlgorithmDialog
from ...reimplementation.processingalgorithmwidget import ProcessingAlgorithmWidget


class SpectralProcessingAlgorithmWidget(ProcessingAlgorithmWidget):

    def __init__(self, speclib, *args, algorithm=None, **kwds):
        if not isinstance(speclib, QgsVectorLayer):
            raise TypeError('speclib must be a QgsVectorLayer')

        super().__init__(None, *args, **kwds)

        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        # QgsProcessingContextGenerator.__init__(self)
        self.mWidgetName = 'Spectral Processing Widget'
        self.setWindowTitle(self.mWidgetName)
        self.setWindowIcon(QIcon(r':/qps/ui/icons/profile_processing.svg'))
        self.btnAlgorithm: QPushButton = QPushButton('Algorithm')
        self.btnAlgorithm.setIcon(QIcon(':/images/themes/default/processingAlgorithm.svg'))
        self.btnAlgorithm.clicked.connect(self.setAlgorithmFromDialog)

        self.mTemporaryRaster: List[str] = []
        self.tbAlgorithmName: QLineEdit = QLineEdit()
        self.tbAlgorithmName.setPlaceholderText('Select a raster processing algorithm / model')
        self.tbAlgorithmName.setReadOnly(True)
        self.tbAlgorithmName.setAutoFillBackground(True)
        self.tbAlgorithmName.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))

        self.cbSelectedFeaturesOnly = QCheckBox('Only process selected features')

        self.mTopGrid = QGridLayout()
        self.mTopGrid.addWidget(self.btnAlgorithm, 0, 0)
        self.mTopGrid.addWidget(self.tbAlgorithmName, 0, 1)
        self.mTopGrid.addWidget(self.cbSelectedFeaturesOnly, 1, 0, 1, 2)

        # self.btnAlgorithm.clicked.connect(self.actionSetAlgorithm.trigger)
        self.layout().insertLayout(0, self.mTopGrid)
        self.mProcessingAlgorithmModel: SpectralProcessingAlgorithmModel = SpectralProcessingAlgorithmModel()

        self.mSpeclib = speclib

        self.mContextGenerator = SpectralProcessingContextGenerator(speclib)

        self._parameters_panel = self.createParametersPanel(
            self.inPlace(), self.mSpeclib, self.messageBar()
        )
        self.setMainWidget(self._parameters_panel)

        if isinstance(algorithm, QgsProcessingAlgorithm):
            self.setAlgorithm(algorithm)

    def createParametersPanel(self, inPlaceMode, activeLayer, messageBar):
        a = self.algorithm()
        if isinstance(a, QgsProcessingAlgorithm) and isinstance(self.speclib(), QgsVectorLayer):
            widget = SpectralProcessingParametersWidget(
                a, inPlaceMode, activeLayer, messageBar, speclib=self.speclib())
            widget.registerProcessingContextGenerator(self.mContextGenerator)
            widget.registerWidgetContextGenerator(self.mContextGenerator)
            widget.registerProcessingParametersGenerator(self.mContextGenerator)
            widget.initWidgets()
            return widget
        else:
            w = QgsPanelWidget()
            l = QHBoxLayout()
            label = QLabel('Select an algorithm')
            l.addWidget(label)
            w.setLayout(l)
            return w

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def setAlgorithmFromDialog(self):

        d = ProcessingAlgorithmDialog(parent=self)
        d.setAlgorithmModel(self.mProcessingAlgorithmModel)

        if d.exec() == QDialog.DialogCode.Accepted:
            alg = d.algorithm()
            if isinstance(alg, QgsProcessingAlgorithm):
                self.setAlgorithm(alg)

    def setAlgorithm(self, algorithm: QgsProcessingAlgorithm | None):
        if algorithm != self.algorithm():
            super().setAlgorithm(algorithm)
            self._parameters_panel = self.createParametersPanel(
                self.inPlace(), self.mSpeclib, self.messageBar()
            )
            self.setMainWidget(self._parameters_panel)

            self.updateGui()

    def updateGui(self):
        """
        Updates GUI widgets
        """
        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            n = sl.selectedFeatureCount()
            self.cbSelectedFeaturesOnly.setEnabled(n > 0)
            self.cbSelectedFeaturesOnly.setText(f'Only process {n} selected features')

        self.tbAlgorithmName: QLineEdit

        alg: QgsProcessingAlgorithm = self.algorithm()
        hasAlg = isinstance(alg, QgsProcessingAlgorithm)
        if hasAlg:
            self.tbAlgorithmName.setStyleSheet('')
            css = ''
            # info = f'<b>{alg.displayName()}</b> "{alg.id()}"'
            info = f'{alg.displayName()} "{alg.id()}"'
            tooltip = f'Algorithm Name: {alg.name()}<br>Algorithm ID: {alg.id()}'
        else:
            css = 'color:"red";'
            info = tooltip = self.tbAlgorithmName.placeholderText()
        self.tbAlgorithmName.setStyleSheet(css)
        self.tbAlgorithmName.setText(info)
        self.tbAlgorithmName.setToolTip(tooltip)
        self.setWindowTitle(self.mWidgetName)

    def processingContext(self):
        return self.mContextGenerator.processingContext()

    def widgetContext(self):
        return self.mContextGenerator.createWidgetContext()

    def runAlgorithm(self):

        feedback = self.createFeedback()

        processing_context = self.processingContext()
        tmp_folder: str = QgsProcessingUtils.generateTempFilename('')
        processing_context.setTemporaryFolder(tmp_folder)

        parameters = {}
        validation_result = []
        if self.mainWidget() is not None:
            parameters, validation_result = (
                self.mainWidget().createAndValidateParameters(QgsProcessingParametersGenerator.Flags())
            )
        else:
            return

        algorithm = self.algorithm()
        if not isinstance(algorithm, QgsProcessingAlgorithm):
            return

        # 1. check parameters for QgsRasterLayers that use a VectorLayerFieldRasterDataProvider.
        #    Convert these into temporary local files that can be used with gdal algorithms
        # 2. replace the VectorLayerFieldRasterDataProvider layer with layer that use the temporary local files
        #    keep in mind for these parameters the VectorLayerFieldRasterDataProvider's activeFeatureIDs()
        #    so that we can later on refer each pixel index to a feature id
        # 3. run the algorithm with modified parameters. report to feedback and collect all results / outputs
        # 4. collect results and convert its outputs as followed
        #    If output raster have the same number of pixels as the input rasters:
        #    - raster files with one band into int / float fields
        #    - raster files with > 1 bands into spectral profile fields
        #    otherwise do not use them

        vectorfieldrasterlayers = collect_vectorlayerfieldrasters(parameters, algorithm, processing_context)

        affected_features = set()


def collect_vectorlayerfieldrasters_feature_ids(rasters: List[QgsRasterLayer]) -> List[int]:
    """
    Returns the feature IDs that are used as inputs for the virtual raster layers
    :return:
    """
    all_fids = set()
    for lyr in rasters:
        s = ""


def collect_vectorlayerfieldrasters(
    parameters: Dict[str, Any],
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext,
) -> dict[str, Tuple[str, QgsRasterLayer]]:
    # collect vector field raster layers
    vector_field_layers: Dict[str, Tuple[str, QgsRasterLayer]] = {}
    required_layer = {}

    def is_match(input: Any) -> bool:
        return (
            isinstance(input, QgsRasterLayer)
            and input.isValid()
            and isinstance(input.dataProvider(), VectorLayerFieldRasterDataProvider)
        )

    for k, v in parameters.items():
        k: str
        param = alg.parameterDefinition(k)
        if isinstance(param, QgsProcessingParameterMultipleLayers):
            for layer_id in v:
                layer_id: str
                lyr = context.getMapLayer(layer_id)
                if is_match(lyr):
                    lyr: QgsRasterLayer
                    vector_field_layers[k] = (layer_id, lyr)
                if isinstance(lyr, QgsMapLayer):
                    required_layer[layer_id] = lyr

        elif isinstance(param, QgsProcessingParameterRasterLayer):
            if is_match(v):
                v: QgsRasterLayer
                vector_field_layers[k] = (v.id(), v)

    return vector_field_layers
