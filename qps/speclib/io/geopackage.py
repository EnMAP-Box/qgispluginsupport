import os
import pathlib
from typing import Any, List, Union

import numpy as np
from osgeo.gdalconst import DMD_CREATIONFIELDDATASUBTYPES
from osgeo.ogr import Driver, GetDriverByName
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsExpressionContext, QgsFeature, \
    QgsField, QgsFields, QgsProcessingFeedback, QgsVectorFileWriter, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant

from ..core import is_profile_field
from ..core.spectrallibraryio import SpectralLibraryExportWidget, SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict
from ...qgisenums import QMETATYPE_QSTRING


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


class GeoPackageFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):

    def __init__(self, fields: QgsFields):
        super(GeoPackageFieldValueConverter, self).__init__()
        self.mFields: QgsFields = QgsFields(fields)

        # define converter functions
        self.mFieldDefinitions = dict()
        self.mFieldConverters = dict()

        # can it write JSON fields?
        drv: Driver = GetDriverByName('GPKG')
        supported_subtypes = drv.GetMetadataItem(DMD_CREATIONFIELDDATASUBTYPES)
        can_write_json = 'JSON' in supported_subtypes

        for field in self.mFields:
            name = field.name()
            idx = self.mFields.lookupField(name)
            if is_profile_field(field) and field.type() == QVariant.Map and not can_write_json:
                convertedField = QgsField(name=name, type=QMETATYPE_QSTRING, len=-1)
                self.mFieldDefinitions[name] = convertedField
                self.mFieldConverters[idx] = lambda v, f=convertedField: self.convertProfileField(v, f)
            else:
                self.mFieldDefinitions[name] = QgsField(super().fieldDefinition(field))
                self.mFieldConverters[idx] = lambda v: v

    def convertProfileField(self, value, field: QgsField) -> str:
        d = decodeProfileValueDict(value, numpy_arrays=True)
        d['y'] = d['y'].astype(np.float32)
        text = encodeProfileValueDict(d, field)
        return text

    def clone(self) -> QgsVectorFileWriter.FieldValueConverter:
        return GeoPackageFieldValueConverter(self.mFields)

    def convert(self, fieldIdxInLayer: int, value: Any) -> Any:
        return self.mFieldConverters[fieldIdxInLayer](value)

    def fieldDefinition(self, field: QgsField) -> QgsField:
        return QgsField(self.mFieldDefinitions[field.name()])

    def convertedFields(self) -> QgsFields:
        fields = QgsFields()
        for f in self.mFields:
            fields.append(self.fieldDefinition(f))
        return fields


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

        profiles, fields, crs, wkbType = cls.extractWriterInfos(profiles, exportSettings)
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

        converter = GeoPackageFieldValueConverter(fields)
        options.fieldValueConverter = converter
        convertedFields = converter.convertedFields()

        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path,
                                                                 convertedFields,
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

        cls.copyEditorWidgetSetup(path, fields)

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
