import typing

from PyQt5.QtWidgets import QFormLayout
from qgis._core import QgsVectorLayer, QgsExpressionContext, QgsFields, QgsProcessingFeedback, QgsFeature

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

    def filter(self) -> str:
        return "Geopacakge (*.gpkg);;SpatialLite (*.sqlite)"

    def setSpeclib(self, speclib: QgsVectorLayer):
        pass


class GeoPackageSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(GeoPackageSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None

    def formatName(self) -> str:
        return GeoPackageSpectralLibraryIO.formatName()

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

