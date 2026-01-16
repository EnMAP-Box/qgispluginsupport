import concurrent.futures
import datetime
import os.path
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple

from qgis.core import QgsCoordinateReferenceSystem, QgsEditorWidgetSetup, QgsExpressionContext, \
    QgsExpressionContextScope, QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsMapLayer, QgsProcessing, \
    QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingException, QgsProcessingFeedback, \
    QgsProcessingMultiStepFeedback, QgsProcessingOutputLayerDefinition, QgsProcessingParameterBoolean, \
    QgsProcessingParameterFeatureSink, QgsProcessingParameterMultipleLayers, QgsProcessingUtils, QgsProject, \
    QgsProperty, QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, QgsVectorFileWriter, QgsVectorLayer, \
    QgsWkbTypes, QgsProcessingParameterEnum
from qgis.core import QgsProcessingParameterString, QgsProcessingParameterDefinition
from ..core import profile_field_names
from ..core.spectralprofile import SpectralProfileFileReader
from ..io.asd import ASDBinaryFile
from ..io.ecosis import EcoSISSpectralLibraryReader
from ..io.ecostress import ECOSTRESSSpectralProfileReader
from ..io.envi import EnviSpectralLibraryReader
from ..io.geojson import GeoJSONSpectralLibraryReader
from ..io.geopackage import GeoPackageSpectralLibraryReader
from ..io.spectralevolution import SEDFile
from ..io.svc import SVCSigFile
from ...fieldvalueconverter import GenericFieldValueConverter, GenericPropertyTransformer
from ...utils import file_search, create_picture_viewer_config

READERS = {r.id(): r for r in [
    ASDBinaryFile,
    EcoSISSpectralLibraryReader,
    EnviSpectralLibraryReader,
    GeoJSONSpectralLibraryReader,
    GeoPackageSpectralLibraryReader,
    SEDFile,
    SVCSigFile,
    ECOSTRESSSpectralProfileReader
]}


class SpectralLibraryOutputDefinition(QgsProcessingOutputLayerDefinition):

    def __init__(self, sink, project: QgsProject = None):
        super().__init__(sink, project)

    def useRemapping(self):
        return True


def file_reader(path: Union[str, Path],
                **kwds) -> Optional[SpectralProfileFileReader]:
    """
    Tries to find a SpectralProfileFileReader for the given file.
    :param path:
    :return:
    """
    path = Path(path)
    assert path.is_file()

    for reader in READERS.values():
        if reader.canReadFile(path):
            return reader(path, **kwds)
    return None


def read_profiles(path: Union[str, Path],
                  reader: Union[str, type, SpectralProfileFileReader] = None,
                  **kwds) -> Tuple[List[QgsFeature], Optional[str]]:
    """
    Tries to read spectral profiles from the given path
    :param reader:
    :param dtg_fmt:
    :param path:
    :return: List of QgsFeatures, error
    """

    features = []
    error = None
    path = Path(path)

    try:
        # use new SpectralProfileFileReader API
        if reader is None:
            # derive reader from file name
            reader = file_reader(path, **kwds)
        elif isinstance(reader, type) and issubclass(reader, SpectralProfileFileReader):
            reader = reader(path)
        elif isinstance(reader, str) and reader in READERS.keys():
            reader = READERS[reader](path, **kwds)

        if isinstance(reader, SpectralProfileFileReader):
            features.extend(reader.asFeatures())
        else:
            error = f'Unable to read {path}:\n\t{reader}'
    except Exception as ex:
        error = f'Unable to read {path}:\n\t{ex}'
    return features, error


def read_profile_batch(paths: list) -> Tuple[List[QgsFeature], List[str]]:
    features = []
    errors = []

    for path in paths:
        feat, err = read_profiles(path)
        features.extend(feat)
        if err:
            errors.append(err)
    return features, errors


class ImportSpectralProfiles(QgsProcessingAlgorithm):
    NAME = 'importspectralprofiles'
    P_INPUT = 'INPUT'
    P_INPUT_TYPE = 'INPUT_TYPE'

    P_RECURSIVE = 'RECURSIVE'
    P_OUTPUT = 'OUTPUT'
    P_USE_RELPATH = 'RELPATH'
    P_DATETIMEFORMAT = 'DATETIMEFORMAT'

    def __init__(self):
        super().__init__()

        self._results: Dict = dict()
        self._input_files: List[Path] = []
        self._use_rel_path: bool = False
        self._dtg_fmt: Optional[str] = None
        self._output_file: Optional[str] = None
        self._profile_field_names: List[str] = []
        self._dstFields: Optional[QgsFields] = None
        self._input_readers = ['All']

    def name(self) -> str:
        return self.NAME

    def displayName(self) -> str:
        return 'Import spectral profiles'

    def tags(self) -> List[str]:
        return ['spectral libraries', 'ASD', 'spectral evolution', 'ENVI spectral library']

    def shortHelpString(self) -> str:

        D = {
            'ALG_DESC': 'Imports spectral profiles from various file formats into a new vector layer.',
            'ALG_CREATOR': 'benjamin.jakimow@geo.hu-berlin.de',
        }
        for p in self.parameterDefinitions():
            p: QgsProcessingParameterDefinition
            infos = [f'<i>Identifier <code>{p.name()}</code></i>']
            if i := p.help():
                infos.append(i)
            infos = [i for i in infos if i != '']
            D[p.name()] = '<br>'.join(infos)

        html = QgsProcessingUtils.formatHelpMapAsHtml(D, self)
        return html

    def group(self) -> str:
        return 'Spectral Library'

    def groupId(self) -> str:
        return 'spectrallibrary'

    def createInstance(self) -> 'QgsProcessingAlgorithm':
        return ImportSpectralProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any]) -> None:

        for k in sorted(READERS.keys()):
            if k not in self._input_readers:
                self._input_readers.append(k)

        p = QgsProcessingParameterMultipleLayers(
            self.P_INPUT,
            description='Input Sources',
            layerType=QgsProcessing.SourceType.TypeFile,
            optional=False,
            defaultValue=configuration.get(self.P_INPUT))

        p.setLayerType(QgsProcessing.SourceType.TypeFile)

        p.setHelp('Files or folders to read spectral profiles from')
        self.addParameter(p)

        p = QgsProcessingParameterEnum(
            self.P_INPUT_TYPE,
            description='Input file type',
            options=self._input_readers,
            defaultValue=configuration.get(self.P_INPUT_TYPE, self._input_readers[0]),
            usesStaticStrings=True,
            allowMultiple=False,
        )

        infos = ['Define the reader for the input files:']
        infos.append('<ul>')
        infos.append('<li><code>All</code>: Try to find the input format automatically. May be slow.</li>')
        for k, v in READERS.items():
            infos.append(f'<li><code>{k}</code>: {v.shortHelp()}</li>')
        infos.append('</ul>')
        p.setHelp('\n'.join(infos))
        self.addParameter(p)

        p = QgsProcessingParameterBoolean(
            self.P_RECURSIVE,
            description='Recursive search',
            optional=True,
            defaultValue=configuration.get(self.P_RECURSIVE, False))
        p.setHelp('Search recursively in sub-folders')
        self.addParameter(p)

        p = QgsProcessingParameterBoolean(
            self.P_USE_RELPATH,
            description='Relative paths',
            optional=True,
            defaultValue=configuration.get(self.P_USE_RELPATH, False))
        p.setHelp('Write filepaths relative to output spectral library.')
        self.addParameter(p)

        p = QgsProcessingParameterString(self.P_DATETIMEFORMAT,
                                         defaultValue=configuration.get(self.P_DATETIMEFORMAT, None),
                                         description='Date-time format code',
                                         optional=True)

        p.setHelp('Allows to set the date-time format code to read localized / none-ISO time stamps.'
                  'For example, "%d.%m.%Y %H:%M:%S" to read "27.05.2025 09:39:32". '
                  '<br>See <a href="https://docs.python.org/3/library/datetime.html#format-codes">'
                  'https://docs.python.org/3/library/datetime.html#format-codes</a> for details.')
        p.setFlags(p.flags() | QgsProcessingParameterDefinition.Flag.FlagAdvanced)
        self.addParameter(p)

        p = QgsProcessingParameterFeatureSink(
            self.P_OUTPUT,
            defaultValue=configuration.get(self.P_OUTPUT, QgsProcessing.TEMPORARY_OUTPUT),
            description='Spectral library',
            optional=True)
        p.setHelp('Vector layer with one or more fields that contain spectral profiles')
        self.addParameter(p)

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
                feedback.pushInfo(f'Search for files in : {p}')
                rx = re.compile(r'.*\.(sed|sig|asd|\d+|txt|csv)$')
                for f in file_search(p, rx, recursive=recursive):
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
        self._dtg_fmt = self.parameterAsString(parameters, self.P_DATETIMEFORMAT, context)
        if self._dtg_fmt == '':
            self._dtg_fmt = None
        return len(errors) == 0

    def processAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        wkbType = None
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        all_fields = QgsFields()

        reader_key = parameters.get(self.P_INPUT_TYPE)
        if not isinstance(reader_key, str):
            reader_key = self.parameterAsEnum(parameters, self.P_INPUT_TYPE, context)

        reader_options = {}

        if isinstance(reader_key, int):
            reader_key = self._input_readers[reader_key]

        if reader_key not in self._input_readers:
            feedback.reportError(f'Unknown reader: {reader_key}')

        if self._dtg_fmt:
            reader_options['dtg_fmt'] = self._dtg_fmt

        if reader_key == 'All':
            feedback.pushInfo('Reader not specified. Try to find the input format automatically. May be slow.')
            reader = None
        else:
            reader = READERS.get(reader_key, None)

        PROFILES: Dict[Tuple, List[QgsFeature]] = dict()
        n_files = len(self._input_files)

        multiFeedback = QgsProcessingMultiStepFeedback(2, feedback)

        multiFeedback.setCurrentStep(0)
        feedback.setProgressText(f'Read {n_files} files ...')
        t0 = datetime.datetime.now()

        def measureTime():
            nonlocal t0
            dt = datetime.datetime.now() - t0
            t0 = datetime.datetime.now()
            return dt

        if False:
            max_workers = min(os.cpu_count() or 1, 8)
            pt = datetime.datetime.now()
            batch_size = n_files // max_workers
            batch_size = 10
            batches = [self._input_files[i:i + batch_size] for i in range(0, n_files, batch_size)]
            # Maximal 8 Threads
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_uri = {
                    executor.submit(read_profile_batch, batch): batch for batch in batches
                }

                completed = 0
                for future in concurrent.futures.as_completed(future_to_uri):
                    # uri = future_to_uri[future]
                    features, error = future.result()

                    if error:
                        multiFeedback.reportError(error)

                    if len(features) > 0:
                        fields: QgsFields = features[0].fields()
                        key = tuple(fields.names())
                        PROFILES[key] = PROFILES.get(key, []) + features
                        for f in fields:
                            if f.name() not in all_fields.names():
                                all_fields.append(QgsField(f))

                    completed += 1
                    # print(f'Completed: {completed}')

                if (datetime.datetime.now() - pt).total_seconds() > 3:
                    multiFeedback.setProgress(completed / n_files * 100)
                    pt = datetime.datetime.now()
        else:
            for i, uri in enumerate(self._input_files):
                profiles, error = read_profiles(uri, reader=reader, dtg_fmt=self._dtg_fmt)
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
                if i % 10 == 0:
                    multiFeedback.setProgress((i + 1) / n_files * 100)
                    pt = datetime.datetime.now()

        multiFeedback.pushInfo(f'Reading done {measureTime()}')
        if len(PROFILES) == 0:
            multiFeedback.pushWarning('No profiles found')

        for features in PROFILES.values():
            for feature in features:
                if feature.hasGeometry():
                    wkbType = feature.geometry().wkbType()
                    break
            if wkbType:
                break

        if wkbType is None:
            wkbType = QgsWkbTypes.Type.NoGeometry

        output_path = parameters.get(self.P_OUTPUT, self.parameterDefinition(self.P_OUTPUT).defaultValue())

        if isinstance(output_path, QgsProcessingOutputLayerDefinition):
            output_path = output_path.toVariant()['sink']['val']

        if output_path == QgsProcessing.TEMPORARY_OUTPUT:
            output_path = 'dummy.gpkg'

        if output_path.startswith('memory:'):
            driver = 'memory'
        else:
            driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(output_path)[1])
        dst_fields = GenericFieldValueConverter.compatibleTargetFields(all_fields, driver)

        # outputPar = QgsProcessingOutputLayerDefinition(parameters.get(self.P_OUTPUT), context.project())
        # remapping = QgsRemappingSinkDefinition()

        assert len(all_fields) == len(dst_fields)

        # outputPar.setRemappingDefinition(remapping)

        if self._use_rel_path:
            multiFeedback.pushInfo('Try to convert absolute paths to relative paths')
            path_sink = Path(self.parameterAsFile(parameters, self.P_OUTPUT, context))
            for srcFieldNames, features in PROFILES.items():
                for field in srcFieldNames:
                    if field in [SpectralProfileFileReader.KEY_Picture,
                                 SpectralProfileFileReader.KEY_Path]:
                        for p in features:
                            path_abs = p.attribute(field)
                            if path_abs not in [None, '']:
                                path_abs = Path(path_abs)
                                try:
                                    path_rel = os.path.relpath(path_abs, path_sink)
                                except ValueError:
                                    path_rel = path_abs
                                p.setAttribute(field, path_rel)

        n_total = 0
        for features in PROFILES.values():
            n_total += len(features)
        multiFeedback.setCurrentStep(1)
        multiFeedback.pushInfo(f'Write {n_total} features')

        sink, destId = self.parameterAsSink(parameters,
                                            self.P_OUTPUT,
                                            context, dst_fields,
                                            wkbType,
                                            crs)

        if not isinstance(sink, QgsFeatureSink):
            raise QgsProcessingException(f'Unable to create output file: {parameters.get(self.P_OUTPUT)}')

        for i, (srcFieldNames, features) in enumerate(PROFILES.items()):

            srcFields = features[0].fields()

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

            if not remappingSink.addFeatures(features):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, ''))

            if (datetime.datetime.now() - pt).total_seconds() > 3:
                multiFeedback.setProgress((i + 1) / n_total * 100)
                pt = datetime.datetime.now()

        del sink
        multiFeedback.pushInfo(f'Writing done {measureTime()}')
        self._profile_field_names = profile_field_names(all_fields)
        results = {self.P_OUTPUT: destId}
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
            feedback.pushInfo(f'Created {vl.publicSource(True)}\nPost-processing finished.')
        else:
            feedback.pushWarning(f'Unable to reload {vl} as vectorlayer and set profile fields')

        feedback.setProgress(100)

        return {self.P_OUTPUT: vl}
