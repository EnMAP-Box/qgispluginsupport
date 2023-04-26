import pathlib
from os import scandir
from typing import List, Dict, Any

from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterMultipleLayers, QgsProcessing, \
    QgsProcessingParameterFeatureSink, QgsProcessingContext, \
    QgsProcessingFeedback, QgsFields, QgsWkbTypes, QgsCoordinateReferenceSystem, QgsFeatureSink, QgsProcessingException, \
    QgsProcessingUtils, QgsVectorLayer, QgsEditorWidgetSetup, QgsMapLayer, QgsRemappingSinkDefinition, QgsFeature, \
    QgsProperty, QgsExpressionContextScope, QgsExpressionContext

from .. import EDITOR_WIDGET_REGISTRY_KEY
from ..core import profile_field_names
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportFeatureSink


class ImportSpectralProfiles(QgsProcessingAlgorithm):
    NAME = 'importspectralprofiles'
    P_INPUT = 'INPUT'
    P_OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()

        self._results: Dict = dict()
        self._input_files: List[pathlib.Path] = []
        self._profile_field_names: List[str] = []

    def name(self) -> str:
        return self.NAME

    def displayName(self) -> str:
        return 'Import Spectral Profiles into a vector layer'

    def tags(self) -> List[str]:
        return ['spectral libraries', 'ASD', 'spectral evolution', 'ENVI spectral library']

    def shortHelpString(self) -> str:

        return """This algorithm imports spectral profiles from file formats like ENVI spectral libraries
        or ASD binary files.
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

        self.addParameter(QgsProcessingParameterFeatureSink(self.P_OUTPUT, 'Spectral Library'))

    def prepareAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        input_sources = self.parameterAsFileList(parameters, self.P_INPUT, context)
        errors = []

        input_files = []
        for f in input_sources:
            p = pathlib.Path(f)
            if p.is_dir():
                for e in scandir(p):
                    if e.is_file():
                        input_files.append(pathlib.Path(e.path))
            elif p.is_file():
                input_files.append(p)

            else:
                errors.append(f'Not file/folder: {f}')

        if len(input_files) == 0:
            errors.append('Missing input files')

        if len(errors) > 0:
            feedback.reportError('\n'.join(errors))

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

        # : todo: optimize loading by file-extension sorting
        for uri in self._input_files:
            profiles = SpectralLibraryIO.readProfilesFromUri(uri)
            if len(profiles) > 0:
                fields: QgsFields = profiles[0].fields()
                key = tuple(fields.names())
                PROFILES[key] = PROFILES.get(key, []) + profiles
                all_fields.extend(fields)
                all_fields.extend(profiles[0].fields())

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

        sink, destId = self.parameterAsSink(parameters,
                                            self.P_OUTPUT,
                                            context, all_fields,
                                            wkbType,
                                            crs)
        sink: QgsFeatureSink

        for srcFieldNames, profiles in PROFILES.items():

            srcFields = profiles[0].fields()

            propertyMap = dict()
            for dstField in all_fields.names():
                if dstField in srcFieldNames:
                    propertyMap[dstField] = QgsProperty.fromField(dstField)

            srcCrs = QgsCoordinateReferenceSystem('EPSG:4826')
            sinkDefinition = QgsRemappingSinkDefinition()
            sinkDefinition.setDestinationFields(all_fields)
            sinkDefinition.setSourceCrs(srcCrs)
            sinkDefinition.setDestinationCrs(crs)
            sinkDefinition.setDestinationWkbType(wkbType)
            sinkDefinition.setFieldMap(propertyMap)

            # define a QgsExpressionContext that
            # is used by the SpectralLibraryImportFeatureSink to convert
            # value from the IO context to the output sink context
            expContext = QgsExpressionContext()
            expContext.setFields(srcFields)
            expContext.setFeedback(feedback)

            scope = QgsExpressionContextScope()
            scope.setFields(srcFields)
            expContext.appendScope(scope)

            featureSink = SpectralLibraryImportFeatureSink(sinkDefinition, sink, dstFields=all_fields)
            featureSink.setExpressionContext(expContext)

            if not featureSink.addFeatures(profiles):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, ''))

        del sink

        self._profile_field_names = profile_field_names(all_fields)
        results[self.P_OUTPUT] = destId
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
                for fieldName in self._profile_field_names:
                    idx = vl.fields().lookupField(fieldName)
                    if idx > -1:
                        setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
                        vl.setEditorWidgetSetup(idx, setup)
                vl.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            else:
                feedback.pushWarning(f'Unable to reload {lyr_id} as vectorlayer and set profile fields')
        return {self.P_OUTPUT: vl}
