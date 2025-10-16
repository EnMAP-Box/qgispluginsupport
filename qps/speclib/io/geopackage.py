import os
import pathlib
from pathlib import Path
from typing import Any, List, Union, Optional

from qgis.core import (QgsCoordinateReferenceSystem,
                       QgsMapLayer,
                       QgsCoordinateTransformContext, QgsExpressionContext, QgsFeature,
                       QgsFields, QgsProcessingFeedback, QgsVectorFileWriter, QgsVectorLayer)
from ..core.spectrallibraryio import SpectralLibraryExportWidget, SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import SpectralProfileFileReader, SpectralProfileFileWriter
from ...fieldvalueconverter import GenericFieldValueConverter


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
        return "Geopackage (*.gpkg)"

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
        return "Geopackage (*.gpkg)"

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
                       path: Union[str, pathlib.Path],
                       profiles: Any,
                       exportSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[str]:

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
        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        profiles, srcFields, crs, wkbType = cls.extractWriterInfos(profiles, exportSettings)
        if len(profiles) == 0:
            return []

        newLayerName = exportSettings.get('layer_name', '')
        if newLayerName == '':
            newLayerName = os.path.basename(newLayerName)

        ogrDataSourceOptions = []
        ogrLayerOptions = [
            f'IDENTIFIER={newLayerName}',
            f'DESCRIPTION={newLayerName}']

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.datasourceOptions = ogrDataSourceOptions
        options.layerOptions = ogrLayerOptions
        options.fileEncoding = 'UTF-8'
        options.skipAttributeCreation = False
        options.driverName = 'GPKG'

        transformationContext = QgsCoordinateTransformContext()

        dstFields = GenericFieldValueConverter.compatibleTargetFields(srcFields, options.driverName)
        converter = GenericFieldValueConverter(srcFields, dstFields)
        options.fieldValueConverter = converter

        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path,
                                                                 dstFields,
                                                                 # fields,
                                                                 wkbType,
                                                                 crs,
                                                                 transformationContext,
                                                                 options)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            raise Exception(f'Error when creating {path}: {writer.errorMessage()}')

        if not writer.addFeatures(profiles):
            if writer.hasError() != QgsVectorFileWriter.NoError:
                raise Exception(f'Error when creating feature: {writer.errorMessage()}')

        del writer

        cls.copyEditorWidgetSetup(path, srcFields)

        return [path]

    @classmethod
    def importProfiles(cls,
                       path: str,
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:
        lyr = QgsVectorLayer(path)
        # load editor widget information on spectral profile fields
        lyr.loadDefaultStyle()
        return list(lyr.getFeatures())


class GeoPackageSpectralLibraryWriter(SpectralProfileFileWriter):

    def __init__(self, *args, crs: QgsCoordinateReferenceSystem, **kwds):
        super().__init__(*args, **kwds)
        self.mCrs: QgsCoordinateReferenceSystem = crs

    @classmethod
    def id(cls) -> str:
        return 'GeoPackage'

    @classmethod
    def filterString(cls) -> str:
        return 'Geopackage (*.gpkg)'

    def writeFeatures(self,
                      features: List[QgsFeature],
                      field: str,
                      path: str,
                      feedback: Optional[QgsProcessingFeedback] = None,
                      ) -> List[Path]:

        if feedback is None:
            feedback = QgsProcessingFeedback()

        if len(features) == 0:
            feedback.pushInfo('No features to write')
            return []

        f0 = features[0]

        srcFields = f0.fields()
        wkbType = f0.geometry().wkbType()

        layerName = Path(path).stem
        ogrDataSourceOptions = []
        ogrLayerOptions = [
            f'IDENTIFIER={layerName}',
            f'DESCRIPTION={layerName}']

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.datasourceOptions = ogrDataSourceOptions
        options.layerOptions = ogrLayerOptions
        options.fileEncoding = 'UTF-8'
        options.skipAttributeCreation = False
        options.driverName = 'GPKG'

        transformationContext = QgsCoordinateTransformContext()

        dstFields = GenericFieldValueConverter.compatibleTargetFields(srcFields, options.driverName)
        converter = GenericFieldValueConverter(srcFields, dstFields)
        options.fieldValueConverter = converter

        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path,
                                                                 dstFields,
                                                                 # fields,
                                                                 wkbType,
                                                                 self.mCrs,
                                                                 transformationContext,
                                                                 options)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            feedback.reportError(f'Error when creating {path}: {writer.errorMessage()}')
            return []

        if not writer.addFeatures(features):
            if writer.hasError() != QgsVectorFileWriter.NoError:
                feedback.reportError(f'Error when creating feature: {writer.errorMessage()}')
                return []
        del writer

        lyr = QgsVectorLayer(path)
        if lyr.isValid():
            for dstField in dstFields:
                i = lyr.fields().lookupField(dstField.name())
                if i >= 0:
                    lyr.setEditorWidgetSetup(i, dstField.editorWidgetSetup())
            msg, success = lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            if not success:
                feedback.reportError(msg)

        return [Path(path)]


class GeoPackageSpectralLibraryReader(SpectralProfileFileReader):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def id(cls) -> str:
        return 'GeoPackage'

    @classmethod
    def canReadFile(cls, path: Union[str, pathlib.Path]) -> bool:
        return pathlib.Path(path).suffix == '.gpkg'

    def asFeatures(self) -> List[QgsFeature]:
        lyr = QgsVectorLayer(self.path().as_posix())
        lyr.loadDefaultStyle()
        return list(lyr.getFeatures())
