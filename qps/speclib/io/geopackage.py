import typing

from PyQt5.QtWidgets import QFormLayout
from qgis._core import QgsVectorLayer, QgsExpressionContext, QgsFields, QgsProcessingFeedback, QgsFeature, \
    QgsVectorFileWriter, QgsCoordinateTransformContext, QgsCoordinateReferenceSystem

from qgis._gui import QgsFieldMappingWidget
from qps.speclib.core.spectrallibraryio import SpectralLibraryImportWidget, SpectralLibraryIO, \
    SpectralLibraryExportWidget


class GeoPackageSpectralLibraryExportWidget(SpectralLibraryExportWidget):

    def __init__(self, *args, **kwds):
        super(GeoPackageSpectralLibraryExportWidget, self).__init__(*args, **kwds)

    def formatName(self) -> str:
        return GeoPackageSpectralLibraryIO.formatName()

    def supportsMultipleSpectralSettings(self) -> bool:
        return True

    def supportsMultipleProfileFields(self) -> bool:
        return True

    def supportsLayerName(self) -> bool:
        return True

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return GeoPackageSpectralLibraryIO

    def filter(self) -> str:
        return "Geopackage (*.gpkg);;SpatialLite (*.sqlite)"

    def exportSettings(self, settings: dict) -> dict:
        settings['crs'] = self.speclib().crs()
        settings['wkbType'] = self.speclib().wkbType()
        return settings


class GeoPackageSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(GeoPackageSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(GeoPackageSpectralLibraryIO)

    def filter(self) -> str:
        return "Geopackage (*.gpkg);;SpatialLite (*.sqlite)"

    def setSource(self, source: str):
        lyr = QgsVectorLayer(source)
        if isinstance(lyr, QgsVectorLayer):
            self.mSource = lyr
        self.sigSourceChanged.emit()

    def sourceFields(self) -> QgsFields:
        if isinstance(self.mSource, QgsVectorLayer):
            return self.mSource.fields()
        else:
            return QgsFields()

    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        if isinstance(self.mSource, QgsVectorLayer):
            return self.mSource.crs()
        else:
            return None

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()

        return context

    @staticmethod
    def importProfiles(path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        lyr = QgsVectorLayer(path)
        return lyr.getFeatures()


class GeoPackageSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'Geopackage'

    @classmethod
    def createExportWidget(cls) -> SpectralLibraryExportWidget:
        return GeoPackageSpectralLibraryExportWidget()

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return GeoPackageSpectralLibraryImportWidget()


    @classmethod
    def exportProfiles(cls,
                       path: str,
                       exportSettings: dict,
                       profiles: typing.Iterable[QgsFeature],
                       feedback: QgsProcessingFeedback) -> typing.List[str]:


        """
        :param fileName: file name to write to
        :param fields: fields to write
        :param geometryType: geometry type of output file
        :param srs: spatial reference system of output file
        :param transformContext: coordinate transform context
        :param options: save options
        """
        write: QgsVectorFileWriter = None
        saveVectorOptions = QgsVectorFileWriter.SaveVectorOptions()
        saveVectorOptions.feedback = feedback
        saveVectorOptions.driverName = 'GPKG'

        transformContext = QgsCoordinateTransformContext()
        for i, profile in enumerate(profiles):
            if i == 0:
                # init file writer based on 1st feature fields
                writer = QgsVectorFileWriter.create(
                    fileName=path,
                    fields=profile.fields(),
                    geometryType=exportSettings['wkbType'],
                    srs=exportSettings['crs'],
                    transformContext=transformContext,
                    options=saveVectorOptions,
                    #sinkFlags=None,
                    newLayer=None,
                    newFilename=None
                )

            writer.addFeature(profile)

        return [path]

    @classmethod
    def importProfiles(cls,
                       path: str,
                       fields: QgsFields,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        pass