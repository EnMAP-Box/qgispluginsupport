import datetime
import os.path
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple

from qgis.core import QgsCoordinateReferenceSystem, QgsEditorWidgetSetup, QgsExpressionContext, \
    QgsExpressionContextScope, QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsMapLayer, QgsProcessing, \
    QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingException, QgsProcessingFeedback, \
    QgsProcessingMultiStepFeedback, QgsProcessingOutputLayerDefinition, QgsProcessingParameterBoolean, \
    QgsProcessingParameterFeatureSink, QgsProcessingParameterMultipleLayers, QgsProcessingUtils, QgsProject, \
    QgsProperty, QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, QgsVectorFileWriter, QgsVectorLayer, \
    QgsWkbTypes
from ..core import profile_field_names
from ..core.spectralprofile import SpectralProfileFileReader
from ..io.asd import RX_ASDFILE, ASDBinaryFile
from ..io.ecosis import EcoSISSpectralLibraryIO
from ..io.envi import EnviSpectralLibraryIO
from ..io.envi import canRead as canReadESL
from ..io.spectralevolution import SEDFile, rx_sed_file
from ..io.svc import SVCSigFile, rx_sig_file
from ...fieldvalueconverter import GenericFieldValueConverter, GenericPropertyTransformer
from ...utils import file_search, create_picture_viewer_config


class SpectralLibraryOutputDefinition(QgsProcessingOutputLayerDefinition):

    def __init__(self, sink, project: QgsProject = None):
        super().__init__(sink, project)

    def useRemapping(self):
        return True


def file_reader(path: Union[str, Path]) -> Optional[SpectralProfileFileReader]:
    """
    Return a SpectralProfileFileReader to read profiles in the given file
    :param path:
    :return:
    """
    path = Path(path)
    assert path.is_file()
    if rx_sig_file.search(path.name):
        return SVCSigFile(path)
    elif RX_ASDFILE.search(path.name):
        return ASDBinaryFile(path)
    elif rx_sed_file.search(path.name):
        return SEDFile(path)
    return None


def read_profiles(path: Union[str, Path]) -> Tuple[List[QgsFeature], Optional[str]]:
    """
    Tries to read spectral profiles from the given path
    :param path:
    :return: List of QgsFeatures, error
    """

    features = []
    error = None
    path = Path(path)

    try:
        reader = file_reader(path)
        if isinstance(reader, SpectralProfileFileReader):
            features.append(reader.asFeature())
        elif canReadESL(path):
            features.extend(EnviSpectralLibraryIO.importProfiles(path))
        elif path.name.endswith('.csv'):
            # try ecosis
            features.extend(EcoSISSpectralLibraryIO.importProfiles(path))

    except Exception as ex:
        error = f'Unable to read {path}:\n\t{ex}'
    return features, error


class ImportSpectralProfiles(QgsProcessingAlgorithm):
    NAME = 'importspectralprofiles'
    P_INPUT = 'INPUT'
    P_RECURSIVE = 'RECURSIVE'
    P_OUTPUT = 'OUTPUT'
    P_USE_RELPATH = 'RELPATH'

    def __init__(self):
        super().__init__()

        self._results: Dict = dict()
        self._input_files: List[Path] = []
        self._use_rel_path: bool = False
        self._output_file: Optional[str] = None
        self._profile_field_names: List[str] = []
        self._dstFields: Optional[QgsFields] = None

    def name(self) -> str:
        return self.NAME

    def displayName(self) -> str:
        return 'Import Spectral Profiles into a vector layer'

    def tags(self) -> List[str]:
        return ['spectral libraries', 'ASD', 'spectral evolution', 'ENVI spectral library']

    def shortHelpString(self) -> str:

        return """Imports spectral profiles from file formats like ENVI spectral libraries,
        ASD (<code>.asd</code>), Spectral Evolution (<code>.sed</code>) or Spectral Vista Coorporation (SVC, <code>.sig</code>) Spectrometers.
        """

    def group(self) -> str:
        return 'Spectral Library'

    def groupId(self) -> str:
        return 'spectrallibrary'

    def createInstance(self) -> 'QgsProcessingAlgorithm':
        return ImportSpectralProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any]) -> None:

        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.P_INPUT,
            description='Files to read spectral profiles from',
            layerType=QgsProcessing.SourceType.TypeFile,
            optional=False)
        )

        self.addParameter(QgsProcessingParameterBoolean(
            self.P_RECURSIVE,
            description='Recursive search for profile files',
            optional=True,
            defaultValue=False),
        )

        self.addParameter(QgsProcessingParameterBoolean(
            self.P_USE_RELPATH,
            description='Write pathes relative to spectral library',
            optional=True,
            defaultValue=False),
        )

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.P_OUTPUT,
            description='Spectral library',
            optional=True))

    def prepareAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        input_sources = self.parameterAsFileList(parameters, self.P_INPUT, context)
        errors = []

        recursive: bool = self.parameterAsBool(parameters, self.P_RECURSIVE, context)
        input_files = []
        for f in input_sources:
            p = Path(f)
            if p.is_dir():
                for f in file_search(p, '*.*', recursive=recursive):
                    if os.path.isfile(f):
                        input_files.append(Path(f))
            elif p.is_file():
                input_files.append(p)

            else:
                errors.append(f'Not file/folder: {f}')

        if len(input_files) == 0:
            errors.append('Missing input files')

        if len(errors) > 0:
            feedback.reportError('\n'.join(errors))

        self._use_rel_path = self.parameterAsBoolean(parameters, self.P_USE_RELPATH, context)
        self._input_files = input_files
        return len(errors) == 0

    def processAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        results = dict()

        wkbType = None
        crs = QgsCoordinateReferenceSystem('EPSG:4326')

        all_fields = QgsFields()

        # collect profiles, ordered by field definition
        PROFILES: Dict[str, List[QgsFeature]] = dict()

        multiFeedback = QgsProcessingMultiStepFeedback(2, feedback)
        multiFeedback.setCurrentStep(1)
        n_files = len(self._input_files)

        pt = datetime.datetime.now()

        for i, uri in enumerate(self._input_files):
            profiles, error = read_profiles(uri)
            if error:
                feedback.reportError(error)
            # profiles = SpectralLibraryIO.readProfilesFromUri(uri, feedback=multiFeedback)
            if len(profiles) > 0:
                fields: QgsFields = profiles[0].fields()
                key = tuple(fields.names())
                PROFILES[key] = PROFILES.get(key, []) + profiles
                for f in fields:
                    if f.name() not in all_fields.names():
                        all_fields.append(QgsField(f))
                # all_fields.extend(fields)
                # all_fields.extend(profiles[0].fields())
            if (datetime.datetime.now() - pt).total_seconds() > 3:
                multiFeedback.setProgress((i + 1) / n_files * 100)
                pt = datetime.datetime.now()

        # get wktType
        if wkbType is None:
            for k, profiles in PROFILES.items():
                if wkbType:
                    break
                for p in profiles:
                    if p.hasGeometry():
                        wkbType = p.geometry().wkbType()
                        break
        if wkbType is None:
            wkbType = QgsWkbTypes.Type.NoGeometry

        dst_fields = QgsFields()
        # Describe output fields.
        # If destination provide does not support field type
        # try to get a suitable conversion, e.g. QMap / JSON -> str
        #
        value_output = parameters.get(self.P_OUTPUT)
        if isinstance(value_output, str):
            driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(value_output)[1])
            dst_fields = GenericFieldValueConverter.compatibleTargetFields(all_fields, driver)
        else:
            dst_fields = QgsFields(all_fields)

        # outputPar = QgsProcessingOutputLayerDefinition(parameters.get(self.P_OUTPUT), context.project())
        # remapping = QgsRemappingSinkDefinition()

        assert len(all_fields) == len(dst_fields)

        # outputPar.setRemappingDefinition(remapping)

        if len(PROFILES) == 0:
            feedback.pushWarning('No profiles found')

        if self._use_rel_path:
            path_sink = Path(self.parameterAsFile(parameters, self.P_OUTPUT, context))
            for srcFieldNames, profiles in PROFILES.items():
                for field in srcFieldNames:
                    if field in [SpectralProfileFileReader.KEY_Picture,
                                 SpectralProfileFileReader.KEY_Path]:
                        for p in profiles:
                            path_abs = p.attribute(field)
                            if path_abs not in [None, '']:
                                path_abs = Path(path_abs)
                                path_rel = os.path.relpath(path_abs, path_sink)
                                p.setAttribute(field, path_rel)

        sink, destId = self.parameterAsSink(parameters,
                                            self.P_OUTPUT,
                                            context, dst_fields,
                                            wkbType,
                                            crs)

        sink: QgsFeatureSink

        multiFeedback.setCurrentStep(2)
        n_total = len(profiles)

        for i, (srcFieldNames, profiles) in enumerate(PROFILES.items()):

            srcFields = profiles[0].fields()

            remappingFieldMap = dict()
            transformers = []
            for dstField in dst_fields:
                assert isinstance(dstField, QgsField)
                if dstField.name() in srcFieldNames:
                    srcFieldName = dstField.name()
                    transformer = GenericPropertyTransformer(dstField)
                    transformers.append(transformer)
                    property = QgsProperty.fromField(srcFieldName)
                    property.setTransformer(transformer)
                    remappingFieldMap[dstField.name()] = property

            srcCrs = QgsCoordinateReferenceSystem('EPSG:4326')

            remappingDefinition = QgsRemappingSinkDefinition()
            remappingDefinition.setDestinationFields(dst_fields)
            remappingDefinition.setSourceCrs(srcCrs)
            remappingDefinition.setDestinationCrs(crs)
            remappingDefinition.setDestinationWkbType(wkbType)
            remappingDefinition.setFieldMap(remappingFieldMap)

            # define a QgsExpressionContext that
            # is used by the SpectralLibraryImportFeatureSink to convert
            # values from the IO context to the output sink context
            expContext = QgsExpressionContext()
            expContext.setFields(srcFields)
            expContext.setFeedback(feedback)

            scope = QgsExpressionContextScope()
            scope.setFields(srcFields)
            expContext.appendScope(scope)

            # featureSink = SpectralLibraryImportFeatureSink(sinkDefinition, sink, dst_fields)
            remappingSink = QgsRemappingProxyFeatureSink(remappingDefinition, sink)
            remappingSink.setExpressionContext(expContext)

            if not remappingSink.addFeatures(profiles):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, ''))

            if (datetime.datetime.now() - pt).total_seconds() > 3:
                multiFeedback.setProgress((i + 1) / n_total * 100)
                pt = datetime.datetime.now()

        del sink

        self._profile_field_names = profile_field_names(all_fields)
        results[self.P_OUTPUT] = destId
        self._dstFields = dst_fields
        self._results = results
        return results

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        vl = self._results.get(self.P_OUTPUT)
        if isinstance(vl, str):
            lyr_id = vl
            vl = QgsProcessingUtils.mapLayerFromString(vl, context,
                                                       allowLoadingNewLayers=True,
                                                       typeHint=QgsProcessingUtils.LayerHint.Vector)
            if isinstance(vl, QgsVectorLayer) and vl.isValid():
                for f in self._dstFields:
                    idx = vl.fields().lookupField(f.name())
                    if idx > -1:
                        if f.name() == SpectralProfileFileReader.KEY_Picture:
                            config = create_picture_viewer_config(self._use_rel_path, 300)
                            setup = QgsEditorWidgetSetup('ExternalResource', config)

                        else:
                            setupOld = f.editorWidgetSetup()
                            setup = QgsEditorWidgetSetup(setupOld.type(), setupOld.config())

                        if isinstance(setup, QgsEditorWidgetSetup):
                            vl.setEditorWidgetSetup(idx, setup)
                    else:
                        s = ""
                        # setup = QgsEditorWidgetSetup()
                # for fieldName in self._profile_field_names:
                #    idx = vl.fields().lookupField(fieldName)
                #    if idx > -1:
                #        setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
                #        vl.setEditorWidgetSetup(idx, setup)
                vl.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            else:
                feedback.pushWarning(f'Unable to reload {lyr_id} as vectorlayer and set profile fields')
        return {self.P_OUTPUT: vl}
