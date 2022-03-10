import os
import typing

from qgis.core import Qgis
from qgis.core import QgsProject, QgsWkbTypes
from qgis.core import QgsVectorLayer, QgsExpressionContext, QgsFields, QgsProcessingFeedback, QgsFeature, \
    QgsCoordinateReferenceSystem
from qgis.core import QgsVectorLayerExporter
from ..core.spectrallibraryio import SpectralLibraryImportWidget, SpectralLibraryIO, \
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
        return SpectralLibraryIO.spectralLibraryIOInstances(GeoPackageSpectralLibraryIO)

    def filter(self) -> str:
        return "Geopackage (*.gpkg);;SpatialLite (*.sqlite)"

    def exportSettings(self, settings: dict) -> dict:
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            settings['crs'] = speclib.crs()
            settings['wkbType'] = speclib.wkbType()
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
        if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
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
        # writer: QgsVectorFileWriter = None
        # saveVectorOptions = QgsVectorFileWriter.SaveVectorOptions()
        # saveVectorOptions.feedback = feedback
        # saveVectorOptions.driverName = 'GPKG'
        # saveVectorOptions.symbologyExport = QgsVectorFileWriter.SymbolLayerSymbology
        # saveVectorOptions.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        # saveVectorOptions.layerOptions = ['OVERWRITE=YES', 'TRUNCATE_FIELDS=YES']
        newLayerName = exportSettings.get('layer_name', '')
        if newLayerName == '':
            newLayerName = os.path.basename(newLayerName)

        options = exportSettings.get('options', dict())
        options['driverName'] = 'GPKG'

        assert isinstance(options, dict)
        wkbType = exportSettings.get('wkbType', QgsWkbTypes.NoGeometry)
        crs = QgsCoordinateReferenceSystem(exportSettings.get('crs', QgsCoordinateReferenceSystem()))

        # writer: QgsVectorFileWriter = None
        writer: QgsVectorLayerExporter = None
        transformContext = QgsProject.instance().transformContext()

        fields: QgsFields = None

        if Qgis.versionInt() < 32000:
            successCode = QgsVectorLayerExporter.NoError
        else:
            successCode = Qgis.VectorExportResult.Success

        for i, profile in enumerate(profiles):
            if i == 0:
                # init file writer based on 1st feature fields
                fields = profile.fields()
                writer = QgsVectorLayerExporter(path, 'ogr', profile.fields(), wkbType, crs,
                                                options=options,
                                                overwrite=True)

                if writer.errorCode() != successCode:
                    raise Exception(f'Error when creating {path}: {writer.errorMessage()}')

            if not writer.addFeature(profile):
                if writer.errorCode() != successCode:
                    raise Exception(f'Error when creating feature: {writer.errorMessage()}')

        if True:
            # set profile columns
            lyr = QgsVectorLayer(path)

            if lyr.isValid():
                for name in fields.names():
                    i = lyr.fields().lookupField(name)
                    if i >= 0:
                        lyr.setEditorWidgetSetup(i, fields.field(name).editorWidgetSetup())
                msg, success = lyr.saveDefaultStyle()
                print(msg)

        return [path]

    @classmethod
    def importProfiles(cls,
                       path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        lyr = QgsVectorLayer(path)
        # todo: add filters
        return lyr.getFeatures()
