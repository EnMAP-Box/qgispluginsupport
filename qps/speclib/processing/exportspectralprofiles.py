from typing import Dict, Any, List

from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, QgsProcessingParameterFileDestination

from qps.speclib.core.spectrallibraryio import SpectralLibraryIO


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
        return ExportSpectralProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any]) -> None:

        self.addParameter(QgsProcessingParameterVectorLayer(
            self.P_INPUT,
            description='A spectral library, i.e. a vector layer with SpectralProfile fields)',
            optional=False)
        )

        for io in SpectralLibraryIO.spectralLibraryIOs(write=True):
            w = io.createExportWidget()
            for f in w.filter().split(';;'):
                self.mFormatNames.append(w.formatName())
                self.mFormatIOs.append(io)
                self.mFormatFilters.append(f)

        self.addParameter(QgsProcessingParameterFileDestination(
            self.P_OUTPUT,
            description='The format specific file output',
            fileFilter=self.mFormatFilters,
        ))
