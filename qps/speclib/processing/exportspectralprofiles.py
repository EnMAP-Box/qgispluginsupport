import os.path
from typing import Dict, Any, List

from qgis.core import QgsProcessing, \
    QgsProcessingFeedback, QgsProcessingContext, QgsVectorLayer
from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, QgsProcessingParameterFileDestination
from ..core import profile_fields, profile_field_names
from ..core.spectrallibraryio import SpectralLibraryIO


class ExportSpectralProfiles(QgsProcessingAlgorithm):
    NAME = 'exportspectralprofiles'
    P_INPUT = 'INPUT'
    P_FORMAT = 'FORMAT'
    P_OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()

        self.mFormatNames = []
        self.mFormatFilters = []
        self.mFormatIOs = []

        self.mInputLayer: QgsVectorLayer = None
        self.mOutputFile: str = None
        self.mOutputIO: SpectralLibraryIO = None

    def name(self) -> str:
        return self.NAME

    def displayName(self) -> str:
        return 'Import Spectral Profiles into a vector layer'

    def tags(self) -> List[str]:
        return ['spectral libraries', 'ASD', 'spectral evolution', 'ENVI spectral library']

    def shortHelpString(self) -> str:
        info = """Exports spectral profiles."""
        return info

    def group(self) -> str:
        return 'Spectral Library'

    def groupId(self) -> str:
        return 'spectrallibrary'

    def createInstance(self) -> 'QgsProcessingAlgorithm':
        return ExportSpectralProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any]) -> None:
        p = QgsProcessingParameterVectorLayer(
            self.P_INPUT,
            types=[QgsProcessing.TypeVector],
            description='Spectral library',
            optional=False)

        p.setHelp('Can be any vector layer with SpectralProfile fields')
        self.addParameter(p)

        for io in SpectralLibraryIO.spectralLibraryIOs(write=True):
            w = io.createExportWidget()
            for f in w.filter().split(';;'):
                self.mFormatNames.append(w.formatName())
                self.mFormatIOs.append(io)
                self.mFormatFilters.append(f)

        p = QgsProcessingParameterFileDestination(
            self.P_OUTPUT,
            description='Output File',
            fileFilter=';;'.join(self.mFormatFilters),
        )
        p.setHelp('Output file type')
        self.addParameter(p)

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        self.mInputLayer = self.parameterAsVectorLayer(parameters, self.P_INPUT, context=context)
        self.mOutputFile = self.parameterAsFileOutput(parameters, self.P_OUTPUT, context=context)
        errors = []
        if not isinstance(self.mInputLayer, QgsVectorLayer):
            errors.append(f'Cannot open "{self.P_INPUT}" as vector layer: {parameters.get(self.P_INPUT)}')
        else:
            if not len(profile_fields(self.mInputLayer)) > 0:
                errors.append(f'No profile fields found in "{self.P_INPUT}" {parameters.get(self.P_INPUT)}')

        if not isinstance(self.mOutputFile, str):
            errors.append('Undefined output file')
        else:
            ext = os.path.splitext(self.mOutputFile)[1]
            for i, filter in enumerate(self.mFormatFilters):
                if ext in filter:
                    self.mOutputIO = self.mFormatIOs[i]
                    break
            if not isinstance(self.mOutputIO, SpectralLibraryIO):
                errors.append(f'Unsupported file format: "{ext}" ({self.mOutputFile})')

        if len(errors) > 0:

            feedback.reportError('\n'.join(errors))
            return False
        else:
            return True

    def processAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        exportSettings = dict()

        if self.mOutputIO.createExportWidget().supportsMultipleProfileFields():
            writtenFiles = self.mOutputIO.exportProfiles(
                self.mOutputFile,
                self.mInputLayer.getFeatures(),
                exportSettings=exportSettings,
                feedback=feedback)
        else:
            writtenFiles = []
            pfieldnames = profile_field_names(self.mInputLayer)

            outfile = self.mOutputFile
            bn, ext = os.path.splitext(outfile)
            for i, pfield in enumerate(pfieldnames):

                if i > 0:
                    outfile = f'{bn}.{pfield}{ext}'
                exportSettings['profile_field'] = pfield
                wfiles = self.mOutputIO.exportProfiles(
                    outfile,
                    self.mInputLayer.getFeatures(),
                    exportSettings=exportSettings,
                    feedback=feedback)

                writtenFiles.extend(wfiles)
                s = ""

        results = {self.P_OUTPUT: writtenFiles[0],
                   self.P_OUTPUT + 'S': writtenFiles}

        return results
