import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from qgis.core import QgsProcessing, \
    QgsProcessingFeedback, QgsProcessingContext, QgsVectorLayer, QgsProcessingParameterDefinition, QgsProcessingUtils
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, QgsProcessingParameterExpression,
                       QgsProcessingParameterFileDestination, QgsProcessingParameterField)
from qgis.core import QgsProcessingParameterBoolean
from qgis.core import QgsProcessingParameterString
from ..core import is_profile_field, profile_fields
from ..core.spectralprofile import SpectralProfileFileWriter
from ..io.ecosis import EcoSISSpectralLibraryWriter
from ..io.envi import EnviSpectralLibraryWriter
from ..io.geojson import GeoJSONSpectralLibraryWriter
from ..io.geopackage import GeoPackageSpectralLibraryWriter

WRITERS = {r.id(): r for r in [
    GeoPackageSpectralLibraryWriter,
    EcoSISSpectralLibraryWriter,
    GeoJSONSpectralLibraryWriter,
    EnviSpectralLibraryWriter,
]}


def file_writer(path: Union[str, Path], **kwds) -> Optional[SpectralProfileFileWriter]:
    """
    Tries to find a SpectralProfileFileWriter for the given path and arguments
    :param path:
    :return:
    """
    path = Path(path)
    for writer in WRITERS.values():
        if writer.canWriteFile(path):
            try:
                return writer(path, **kwds)
            except Exception as e:
                s = ""
    return None


class ExportSpectralProfiles(QgsProcessingAlgorithm):
    NAME = 'exportspectralprofiles'
    P_INPUT = 'INPUT'
    P_FIELD = 'FIELD'
    P_PROFILE_NAME = 'PROFILE_NAME'
    P_SELECTED_ONLY = 'SELECTED_ONLY'
    P_WRITER_OPTIONS = 'WRITER_OPTIONS'
    P_FORMAT = 'FORMAT'
    P_OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()

        self.mInputLayer: Optional[QgsVectorLayer] = None
        self.mField: Optional[str] = None
        self.mOutputFile: Optional[Path] = None
        self.mOutputWriter: Optional[SpectralProfileFileWriter] = None

    def name(self) -> str:
        return self.NAME

    def displayName(self) -> str:
        return 'Export spectral profiles'

    def tags(self) -> List[str]:
        return ['spectral libraries', 'ASD', 'spectral evolution', 'ENVI spectral library']

    def shortHelpString(self) -> str:

        D = {
            'ALG_DESC': 'Exports spectral profiles into other file formats',
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
        return ExportSpectralProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any]) -> None:
        p = QgsProcessingParameterVectorLayer(
            self.P_INPUT,
            types=[QgsProcessing.SourceType.TypeVector],
            description='Spectral library',
            defaultValue=configuration.get(self.P_INPUT),
            optional=False)

        p.setHelp('A vector layer with SpectralProfile fields')
        self.addParameter(p)

        p = QgsProcessingParameterBoolean(self.P_SELECTED_ONLY,
                                          description='Selected only',
                                          defaultValue=configuration.get(self.P_SELECTED_ONLY, False))
        p.setHelp('Export only profiles from selected features')

        self.addParameter(p)

        p = QgsProcessingParameterField(self.P_FIELD,
                                        parentLayerParameterName=self.P_INPUT,
                                        description='Profile Field',
                                        defaultValue=configuration.get(self.P_FIELD))

        p.setHelp('The field that contains the spectral profiles to export')
        self.addParameter(p)

        p = QgsProcessingParameterExpression(self.P_PROFILE_NAME,
                                             defaultValue=configuration.get(self.P_PROFILE_NAME,
                                                                            "format('Profile %1', $id)"),
                                             parentLayerParameterName=self.P_INPUT,
                                             description='Profile Name Expression')
        p.setHelp('An expression to generate a name for each profile')
        self.addParameter(p)

        p = QgsProcessingParameterString(self.P_WRITER_OPTIONS,
                                         defaultValue=configuration.get(self.P_WRITER_OPTIONS, None),
                                         description='Writer Options',
                                         optional=True)
        p.setHelp(
            'Additional writer options. Can be defined as JSON dictionary, e.g. <code>{ "key1": "value", "key2", 42}</code>')
        p.setFlags(p.flags() | QgsProcessingParameterDefinition.Flag.FlagAdvanced)

        filters = []
        for k, w in WRITERS.items():
            filters.append(w.filterString())
        p = QgsProcessingParameterFileDestination(
            self.P_OUTPUT,
            description='Output File',
            fileFilter=';;'.join(filters),
        )
        help = 'The file to write spectral profiles to. Supported formats:'
        help += '<ul>'
        for filter in filters:
            help += f'<li>{filter}</li>'
        help += '</ul>'
        p.setHelp(help)
        self.addParameter(p)

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        self.mInputLayer = self.parameterAsVectorLayer(parameters, self.P_INPUT, context=context)

        if not isinstance(self.mInputLayer, QgsVectorLayer):
            feedback.reportError(f'Cannot open {parameters.get(self.P_INPUT)} as vector layer')
            return False

        field = self.parameterAsString(parameters, self.P_FIELD, context=context)
        if field == '':
            field = None

        if isinstance(field, str):
            if field not in self.mInputLayer.fields().names():
                feedback.reportError(f'Field "{field}" not found in {parameters.get(self.P_INPUT)}')
                return False
            field = self.mInputLayer.fields().field(field)
        elif isinstance(field, int):
            field = self.mInputLayer.fields().at(field)

        if field is None:

            for f in profile_fields(self.mInputLayer):
                feedback.pushWarning(f'field undefined. Use 1st profile field: "{f.name()}"')
                field = f
                break

        if not is_profile_field(field):
            feedback.reportError(f'Field "{field.name()}" is not a spectral profile field')
            return False

        self.mField = field.name()

        output_path = self.parameterAsFileOutput(parameters, self.P_OUTPUT, context=context)
        if not (isinstance(output_path, str) and output_path != ''):
            feedback.reportError('Undefined output file')
            return False

        writer_options = self.parameterAsString(parameters, self.P_WRITER_OPTIONS, context=context)
        if writer_options == '':
            writer_options = None
        if isinstance(writer_options, str):
            writer_options = json.loads(writer_options)
        elif writer_options is None:
            writer_options = {}

        if 'crs' not in writer_options:
            writer_options['crs'] = self.mInputLayer.crs()

        writer_options['field'] = self.mField

        writer = file_writer(output_path, **writer_options)
        if not isinstance(writer, SpectralProfileFileWriter):
            feedback.reportError(f'Unsupported output file format: {output_path}')
            return False

        self.mOutputWriter = writer
        self.mOutputFile = Path(output_path)
        return True

    def processAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        # read and
        feedback.pushInfo('Read and group profiles by wavelength setting')

        files = []

        writer = self.mOutputWriter

        selected_only = self.parameterAsBool(parameters, self.P_SELECTED_ONLY, context=context)

        if selected_only:
            features = list(self.mInputLayer.selectedFeatures())
        else:
            features = list(self.mInputLayer.getFeatures())

        files = writer.writeFeatures(self.mOutputFile.as_posix(), features, feedback=feedback)

        return {self.P_OUTPUT: files, }
