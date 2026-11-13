import os.path
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
from processing.gui.AlgorithmExecutor import execute
from qgis.PyQt.QtCore import QMetaType
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
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsApplication, QgsProcessingParameterRasterDestination, QgsProcessingException
from qgis.core import QgsFeature, QgsField
from qgis.core import QgsProcessingAlgorithm, QgsVectorLayer
from qgis.core import QgsProcessingParameterDefinition, QgsProcessingOutputRasterLayer, QgsMapLayerStore, \
    QgsProcessingFeedback, QgsProcessingOutputMultipleLayers
from qgis.core import QgsProcessingUtils, QgsRasterLayer, QgsProcessingParameterMultipleLayers, QgsProcessingContext, \
    QgsMapLayer, QgsProcessingParameterRasterLayer
from qgis.core import QgsProject
from qgis.gui import QgsMessageBar
from qgis.gui import QgsPanelWidget
from qgis.gui import QgsProcessingParametersGenerator

from .spectralprocessingalgorithmmodel import SpectralProcessingAlgorithmModel
from .spectralprocessingcontextgenerator import SpectralProcessingContextGenerator
from .spectralprocessingparameterswidget import SpectralProcessingParametersWidget
from .spectralprocessingrasterdestination import SpectralProcessingRasterDestination
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectrallibraryrasterdataprovider import VectorLayerFieldRasterDataProvider
from ..core.spectralprofile import ProfileEncoding, prepareProfileValueDict, encodeProfileValueDict
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...reimplementation.processingalgorithmdialog import ProcessingAlgorithmDialog
from ...reimplementation.processingalgorithmwidget import ProcessingAlgorithmWidget
from ...utils import write_raster_file, rasterArray, createQgsField


class SpectralProcessingAlgorithmWidget(ProcessingAlgorithmWidget):

    def __init__(self, speclib, *args, algorithm=None, **kwds):
        if not isinstance(speclib, QgsVectorLayer):
            raise TypeError('speclib must be a QgsVectorLayer')

        super().__init__(None, *args, **kwds)

        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        # QgsProcessingContextGenerator.__init__(self)
        self.mWidgetName = 'Spectral Processing Widget'
        self.setWindowTitle(self.mWidgetName)
        icon = QIcon(r':/qps/ui/icons/profile_processing.svg')
        self.setWindowIcon(icon)
        if p := self.parent():
            p.setWindowIcon(icon)

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

        self.mFeedback = self.createFeedback()
        self.mContextGenerator = SpectralProcessingContextGenerator(speclib)

        self._parameters_panel = self.createParametersPanel(
            self.inPlace(), self.mSpeclib, self.messageBar()
        )
        self.setMainWidget(self._parameters_panel)

        if algorithm:
            self.setAlgorithm(algorithm)

    def feedback(self) -> QgsProcessingFeedback:
        return self.mFeedback

    def selectedFeaturesOnly(self) -> bool:
        return self.cbSelectedFeaturesOnly.isEnabled() and self.cbSelectedFeaturesOnly.isChecked()

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
            layout = QHBoxLayout()
            label = QLabel('Select an algorithm')
            layout.addWidget(label)
            w.setLayout(layout)
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

    def setAlgorithm(self, algorithm: QgsProcessingAlgorithm | str | None):
        if isinstance(algorithm, str):
            alg = QgsApplication.processingRegistry().createAlgorithmById(algorithm)
            if alg is None:
                raise ValueError(f'Algorithm {algorithm} not found')
            algorithm = alg

        if not isinstance(algorithm, QgsProcessingAlgorithm):
            # once initialized, we can not set the algorithm to None
            #
            raise ValueError(f'Algorithm {algorithm} is not a QgsProcessingAlgorithm')

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

    def runAlgorithm(self, fail_fast: bool = False):

        # feedback = self.createFeedback()
        feedback = self.feedback()
        processing_context = self.processingContext()
        tmp_folder: str = QgsProcessingUtils.generateTempFilename('')
        processing_context.setTemporaryFolder(tmp_folder)
        parametersWidget: SpectralProcessingParametersWidget = self.mainWidget()

        speclib = self.speclib()
        if not speclib.isEditable():
            mbar = self.messageBar()
            if isinstance(mbar, QgsMessageBar):
                mbar.pushInfo('Layer in edit mode', f'The layer {speclib.name()} in now in edit mode')
            speclib.startEditing()

        if parametersWidget is None:
            return

        parameters, errors = (
            parametersWidget.createAndValidateParameters(QgsProcessingParametersGenerator.Flags())
        )

        algorithm = self.algorithm()
        if not isinstance(algorithm, QgsProcessingAlgorithm):
            feedback.reportError('No algorithm selected.')
            return

        # Prepare Inputs
        if len(errors) > 0:
            err = f'Parameter Errors: {str(errors)}'
            feedback.reportError(err)
            feedback.pushConsoleInfo(f"Parameters:\n{str(parameters)}")
            return

        # set active features to selected feature IDs
        vlf_layers = collect_vector_layer_field_rasters(parameters, algorithm, processing_context)

        if self.selectedFeaturesOnly():
            active_feature_ids = set(speclib.selectedFeatureIds())
        else:
            # Keep every 2nd feature ID
            all_ids = speclib.allFeatureIds()
            active_feature_ids = {fid for i, fid in enumerate(all_ids) if i % 2 == 1}

        vfl_features = dict()
        for lyr in vlf_layers:
            lyr: QgsVectorLayer
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            vfl_features[lyr] = dp.activeFeatures()
            active_feature_ids.intersection_update(dp.activeFeatureIds())

        active_features = list(speclib.getFeatures(sorted(active_feature_ids)))
        active_feature_ids = sorted([f.id() for f in active_features])

        # set active features
        for lyr in vlf_layers:
            lyr: QgsVectorLayer
            dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
            dp.setActiveFeatures(active_features, dp.activeField())

        n_features = len(active_features)
        feedback.pushInfo(f'Save vector field attributes for {n_features} features to temporary file context...')
        tmp_parameter, tmp_context, tmp_project = replace_parameter_layers(
            parameters, algorithm, processing_context, tmp_folder
        )

        # Use the temporary context and parameters from replace_parameter_layers
        # The replace_parameter_layers function has already created temporary TIF files
        # for all VectorLayerFieldRasterDataProvider layers and set them up in tmp_context

        feedback.pushInfo(f'Execute algorithm: {algorithm.id()} ...')
        feedback.pushInfo('Parameters:')
        feedback.pushConsoleInfo(str(tmp_parameter))
        ok, results = execute(algorithm,
                              tmp_parameter,
                              context=tmp_context,
                              feedback=feedback,
                              catch_exceptions=not fail_fast)
        if not ok:
            feedback.reportError(f'Execution failed: {str(results)}')
            return

        # S0 = _read_project_array_data(processing_context.project())
        # S1 = _read_project_array_data(tmp_context.project())
        # S2 = _read_project_array_data(tmp_context.temporaryLayerStore())

        # convert output rasters into vector layer attribute values
        feedback.pushInfo('Save temporary raster file output to vector field attributes')
        ok, outputs, errors = collect_outputs(results, algorithm, tmp_context)
        if ok:
            write_outputs_to_speclib(speclib, outputs, active_features, feedback)


def temp_tiff_filename(path: str, context: QgsProcessingContext):
    """
    Returns a temporary file name for a raster file.
    :param path: path to the raster file
    :param context: processing context
    :return: temporary file name
    """
    bn, ext = os.path.splitext(path)
    return QgsProcessingUtils.generateTempFilename(f'{bn}.tif', context)


def gdal_readable_layer(layer: Any, context: QgsProcessingContext) -> QgsMapLayer | None:
    """
    Converts a QgsRasterLayer into a format that can be read by GDAL, by saving the data into a temporary file.
    Other QgsMapLayer types are returned as is.
    Returns None for other inputs or QgsMapLayers which are invalid.
    :param layer: any QgsMapLayer
    :param context: processing context
    :return: QgsMapLayer or None
    """
    if isinstance(layer, str):
        layer = context.getMapLayer(layer)
    if not (isinstance(layer, QgsMapLayer) and layer.isValid()):
        return None

    if isinstance(layer, QgsRasterLayer):
        if layer.dataProvider().name() != 'gdal':

            # create a raster that can be read from GDAL
            new_path = temp_tiff_filename(f'{layer.id()}.tif', context)
            success, errors = write_raster_file(layer, new_path, context)
            if not success:
                raise AssertionError(f'Error writing {new_path}')
            else:
                layer_new = QgsRasterLayer(new_path, layer.name())
                return layer_new

    return layer


def _read_project_array_data(p) -> dict:
    layers = []
    if isinstance(p, QgsProject):
        layers = [lyr for lyr in p.mapLayers().values() if isinstance(lyr, QgsRasterLayer)]
    elif isinstance(p, QgsMapLayerStore):
        layers = [lyr for lyr in p.mapLayers().values() if isinstance(lyr, QgsRasterLayer)]
    results = dict()
    for lyr in layers:
        results[lyr.id()] = rasterArray(lyr)
    return results


def replace_parameter_layers(
    parameters: Dict[str, Any],
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext,
    tmp_folder: str,
) -> Tuple[Dict[str, Any], QgsProcessingContext, QgsProject]:
    """
    Replaces all QgsRasterLayers that use a VectorLayerFieldRasterDataProvider with a new QgsRasterLayer that
    has been stored in a local temp directory and accesses gdal-readable TIF files.
    :param parameters:
    :param alg:
    :param context:
    :param tmp_folder:
    :return: tuple of (new_parameters, new_context, new_project)
    """

    new_project = QgsProject()
    new_context = QgsProcessingContext()
    new_context.setFeedback(context.feedback())
    new_context.setTransformContext(context.transformContext())
    new_context.setTemporaryFolder(tmp_folder)
    new_context.setProject(new_project)
    new_parameters = dict()

    _all_layers = []
    for p_name, p_value in parameters.items():
        p_name: str
        new_value = p_value
        p_def: QgsProcessingParameterDefinition = alg.parameterDefinition(p_name)
        if isinstance(p_def, QgsProcessingParameterMultipleLayers):
            new_layers = []
            for layer_id in p_value:
                layer_id: str
                lyr = context.getMapLayer(layer_id)
                lyr_new = gdal_readable_layer(lyr, context)

                if isinstance(lyr_new, QgsMapLayer) and lyr_new.isValid():
                    new_layers.append(lyr_new)

            new_project.addMapLayers(new_layers)
            new_value = new_layers
            _all_layers.extend(new_layers)

        elif isinstance(p_def, QgsProcessingParameterRasterLayer):
            lyr_new = gdal_readable_layer(p_value, context)

            if isinstance(lyr_new, QgsMapLayer):
                new_project.addMapLayer(lyr_new)
                new_value = lyr_new.id()
                _all_layers.append(lyr_new)
        elif isinstance(p_def, QgsProcessingParameterRasterDestination):
            new_value = temp_tiff_filename(p_value, context)
        elif isinstance(p_def, QgsProcessingParameterDefinition):
            if p_def.type() == 'alignrasterlayers' and isinstance(p_value, list):
                new_values = []
                for d in p_value:
                    if isinstance(d, dict):
                        d2 = d.copy()

                        inputFile = gdal_readable_layer(d.get('inputFile'), context)
                        if isinstance(inputFile, QgsMapLayer):
                            d2['inputFile'] = inputFile
                            _all_layers.append(inputFile)

                        outputFile = d.get('outputFile')
                        if isinstance(outputFile, str):
                            d2['outputFile'] = temp_tiff_filename(outputFile, context)

                        new_values.append(d2)
                    else:
                        raise RuntimeError(f"Invalid value for parameter '{p_name}': {p_value}")
                new_value = new_values

        new_parameters[p_name] = new_value
    return new_parameters, new_context, new_project


def layer_to_fieldname(layer: QgsMapLayer) -> str:
    field_name = SpectralProcessingRasterDestination.pathToFieldName(layer.name())
    if field_name == '':
        field_name = SpectralProcessingRasterDestination.pathToFieldName(layer.source())
    return field_name


def write_outputs_to_speclib(
    speclib: QgsVectorLayer,
    outputs: List[dict],
    active_features: List[QgsFeature],
    feedback: QgsProcessingFeedback,
) -> bool:
    if not speclib.isEditable():
        raise QgsProcessingException(f'vector layer is not in editable: "{speclib.name()}"')

    nf = len(active_features)

    NEW_VALUES = {}
    for output in outputs:
        output: SpectralProcessingOutput

        nb, nl, ns = output.data.shape
        # sprop = output.spectral_properties

        is_profile_field = nb > 1
        if ns != nf:
            feedback.reportError(f'Output {output.parameter} has {ns} bands, expected {nf}')
            return False

        fidx = speclib.fields().indexFromName(output.fieldname)
        if fidx == -1:
            field = None
            if is_profile_field:
                field: QgsField = SpectralLibraryUtils.createProfileField(output.fieldname)
                if not speclib.dataProvider().supportedType(field):
                    field = SpectralLibraryUtils.createProfileField(output.fieldname,
                                                                    encoding=ProfileEncoding.Text)
            else:
                field = createQgsField(output.fieldname, output.data[0, 0, 0])
                if not speclib.dataProvider().supportedType(field):
                    field = QgsField(
                        name=output.fieldname,
                        type=QMetaType.Type.Double
                    )

            if isinstance(field, QgsField):
                speclib.beginEditCommand(f'Add field {field.name()}')
                if not SpectralLibraryUtils.addAttribute(speclib, field):
                    feedback.reportError(f'Failed to add field {output.fieldname} to spectral library')
                    speclib.endEditCommand()
                    return False
                speclib.endEditCommand()
        fidx = speclib.fields().indexFromName(output.fieldname)
        field = speclib.fields()[fidx]

        for i, feature in enumerate(active_features):
            attribute_map = NEW_VALUES.get(feature.id(), dict())

            if is_profile_field:
                pdict = prepareProfileValueDict(
                    y=output.data[:, 0, i],
                    x=output.spectral_properties.wavelengths(),
                    xUnit=output.spectral_properties.wavelengthUnits()[0],
                    bbl=output.spectral_properties.badBands()
                )
                value = encodeProfileValueDict(pdict, field)
            else:
                value = output.data[0, 0, i].tolist()
            attribute_map[fidx] = value

            NEW_VALUES[feature.id()] = attribute_map

    # write data
    speclib.beginEditCommand("Write data to speclib")
    for fid, attribute_map in NEW_VALUES.items():
        if not (speclib.changeAttributeValues(fid, attribute_map)):
            msg = f'Failed to update attribute values for feature ID: {fid}'
            feedback.reportError(msg)
            speclib.endEditCommand()
            return False

    speclib.endEditCommand()

    return True


class SpectralProcessingOutput(object):

    @classmethod
    def fromLayer(cls, parameter: str, layer: QgsMapLayer):

        field_name = layer_to_fieldname(layer)
        if not isinstance(layer, QgsRasterLayer):
            return None

        data = rasterArray(layer)
        if not isinstance(data, np.ndarray):
            return None
        output = SpectralProcessingOutput(parameter, field_name, data)
        output.spectral_properties = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)
        return output

    def __init__(self, parameter: str, fieldname: str, data: np.ndarray):
        self.parameter = parameter
        self.fieldname = fieldname
        self.data = data
        self.spectral_properties: QgsRasterLayerSpectralProperties | None = None


def collect_outputs(
    results: dict,
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext
) -> Tuple[bool, List[SpectralProcessingOutput], List[str]]:
    feedback = context.feedback()
    if not isinstance(feedback, QgsProcessingFeedback):
        feedback = QgsProcessingFeedback()

    outputs: List[SpectralProcessingOutput] = list()
    errors = list()

    for p_def in alg.outputDefinitions():
        p_value = results.get(p_def.name())

        try:
            if isinstance(p_def, QgsProcessingOutputRasterLayer):
                lyr = raster_from_context(p_value, context)
                if not isinstance(lyr, QgsRasterLayer):
                    msg = f'Unable to read output for "{p_def.name()}": {p_value}'
                    feedback.reportError(msg)
                    continue

                if output := SpectralProcessingOutput.fromLayer(p_def.name(), lyr):
                    outputs.append(output)

            elif isinstance(p_def, QgsProcessingOutputMultipleLayers):
                if isinstance(p_value, list):
                    for output_name in p_value:
                        lyr = raster_from_context(output_name, context)
                        if not isinstance(lyr, QgsRasterLayer):
                            msg = f'Unable to read output for "{p_def.name()}": {p_value}'
                            feedback.reportError(msg)
                            continue
                        if output := SpectralProcessingOutput.fromLayer(p_def.name(), lyr):
                            outputs.append(output)

        except Exception as ex:
            msg = f'Unable to read output for "{p_def.name()}": {ex}'
            errors.append(msg)
            feedback.reportError(msg)
            continue

    return len(errors) == 0, outputs, errors


def raster_from_context(
    p_value: Any | None,
    context: QgsProcessingContext
) -> QgsRasterLayer | None:
    lyr = None
    if isinstance(p_value, QgsRasterLayer):
        lyr = p_value
    else:
        lyr = context.getMapLayer(p_value)

    if lyr is None:
        lyr = context.temporaryLayerStore().mapLayer(p_value)
    if lyr is None and isinstance(p_value, str):
        name = None
        p = Path(p_value)
        if p.is_file():
            name = p.stem
        lyr = QgsRasterLayer(p_value, baseName=name)
    return lyr


def collect_vector_layer_field_rasters(
    parameters: Dict[str, Any],
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext,
) -> List[QgsRasterLayer]:
    """
    :param parameters:
    :param alg:
    :param context:
    :return:
    """
    # collect vector field raster layers
    vfr_layers: List[QgsRasterLayer] = []

    def is_vf_layer(input: Any, context: QgsProcessingContext) -> QgsRasterLayer | None:
        if isinstance(input, str):
            input = context.getMapLayer(input)

        if isinstance(input, QgsRasterLayer
                      ) and input.isValid() and isinstance(
            input.dataProvider(), VectorLayerFieldRasterDataProvider
        ):
            return input
        else:
            return None

    for parameter_name, v in parameters.items():
        parameter_name: str
        param = alg.parameterDefinition(parameter_name)
        if isinstance(param, QgsProcessingParameterMultipleLayers):
            for layer_id in v:
                layer_id: str
                if vfl := is_vf_layer(layer_id, context):
                    if vfl not in vfr_layers:
                        vfr_layers.append(vfl)

        elif isinstance(param, QgsProcessingParameterRasterLayer):
            if vfl := is_vf_layer(v, context):
                if vfl not in vfr_layers:
                    vfr_layers.append(vfl)

    return vfr_layers
