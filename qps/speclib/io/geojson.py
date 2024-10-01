import os
from pathlib import Path
from typing import Any, List, Union

import numpy as np

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsExpressionContext, \
    QgsExpressionContextScope, QgsFeature, QgsField, QgsFields, QgsProcessingFeedback, QgsProject, QgsProperty, \
    QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, QgsVectorFileWriter, QgsVectorLayer
from ..core import is_profile_field
from ..core.spectrallibraryio import SpectralLibraryExportWidget, SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict
from ...qgisenums import QMETATYPE_QSTRING


class GeoJsonSpectralLibraryExportWidget(SpectralLibraryExportWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def formatName(self) -> str:
        return GeoJsonSpectralLibraryIO.formatName()

    def supportsMultipleSpectralSettings(self) -> bool:
        return True

    def supportsMultipleProfileFields(self) -> bool:
        return True

    def supportsLayerName(self) -> bool:
        return True

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(GeoJsonSpectralLibraryIO)

    def filter(self) -> str:
        return "GeoJSON (*.geojson)"

    def exportSettings(self, settings: dict) -> dict:
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            settings['crs'] = speclib.crs()
            settings['wkbType'] = speclib.wkbType()
        return settings


class GeoJsonSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(GeoJsonSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(GeoJsonSpectralLibraryIO)

    def filter(self) -> str:
        return "GeoJSON (*.geojson)"

    def setSource(self, source: str):
        lyr = QgsVectorLayer(source)
        if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
            lyr.loadDefaultStyle()
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
        context.setFields(self.sourceFields())
        if isinstance(self.mSource, QgsVectorLayer) and self.mSource.featureCount() > 0:
            for f in self.mSource.getFeatures():
                if isinstance(f, QgsFeature):
                    context.setFeature(f)
                    break
        return context


class GeoJsonFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):

    def __init__(self, fields: QgsFields):
        super(GeoJsonFieldValueConverter, self).__init__()
        self.mFields: QgsFields = QgsFields(fields)

        # define converter functions
        self.mFieldDefinitions = dict()
        self.mFieldConverters = dict()

        for field in self.mFields:
            name = field.name()
            idx = self.mFields.lookupField(name)
            if field.type() != QMETATYPE_QSTRING and is_profile_field(field):
                converted_field = QgsField(name=name, type=QMETATYPE_QSTRING, typeName='string', len=-1)
                self.mFieldDefinitions[name] = converted_field
                self.mFieldConverters[idx] = lambda v, f=converted_field: self.convertProfileField(v, f)

            else:
                self.mFieldDefinitions[name] = QgsField(super().fieldDefinition(field))
                self.mFieldConverters[idx] = lambda v: v

    def convertProfileField(self, value, field: QgsField) -> str:
        d = decodeProfileValueDict(value, numpy_arrays=True)
        d['y'] = d['y'].astype(np.float32)
        text = encodeProfileValueDict(d, field)
        return text

    def clone(self) -> QgsVectorFileWriter.FieldValueConverter:
        return GeoJsonFieldValueConverter(self.mFields)

    def convert(self, fieldIdxInLayer: int, value: Any) -> Any:
        return self.mFieldConverters[fieldIdxInLayer](value)

    def fieldDefinition(self, field: QgsField) -> QgsField:
        return QgsField(self.mFieldDefinitions[field.name()])

    def convertedFields(self) -> QgsFields:
        fields = QgsFields()
        for f in self.mFields:
            fields.append(self.fieldDefinition(f))
        return fields


class GeoJsonSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'GeoJSON'

    @classmethod
    def createExportWidget(cls) -> SpectralLibraryExportWidget:
        return GeoJsonSpectralLibraryExportWidget()

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return GeoJsonSpectralLibraryImportWidget()

    @classmethod
    def exportProfiles(cls,
                       path: Union[str, Path],
                       profiles,
                       exportSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback(), **kwargs) -> List[str]:

        profiles, fields, crs, wkbType = cls.extractWriterInfos(profiles, exportSettings)
        if len(profiles) == 0:
            return []

        transformContext = QgsProject.instance().transformContext()
        crsJson = QgsCoordinateReferenceSystem('EPSG:4326')

        newLayerName = exportSettings.get('layer_name', '')

        path: Path = Path(path)

        if newLayerName == '':
            newLayerName = os.path.basename(newLayerName)

        datasourceOptions = exportSettings.get('datasourceOptions', dict())
        assert isinstance(datasourceOptions, dict)
        rfc7946: bool = exportSettings.get('rfc7946', True) is True

        datasourceOptions = exportSettings.get('datasourceOptions',
                                               [])  # 'ATTRIBUTES_SKIP=NO', 'DATE_AS_STRING=YES', 'ARRAY_AS_STRING=YES']

        layerOptions = exportSettings.get('layerOptions', [f'DESCRIPTION={newLayerName}'])
        layerOptions.insert(0, f'RFC7946={"YES" if rfc7946 else "NO"}')

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.datasourceOptions = datasourceOptions
        options.layerOptions = layerOptions
        options.fileEncoding = exportSettings.get('fileEncoding', 'UTF-8')
        options.skipAttributeCreation = False
        options.driverName = 'GeoJSON'

        converter = GeoJsonFieldValueConverter(fields)
        options.fieldValueConverter = converter
        convertedFields = converter.convertedFields()

        writer_crs: QgsCoordinateReferenceSystem = crsJson if rfc7946 else crs
        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path.as_posix(),
                                                                 convertedFields,
                                                                 wkbType,
                                                                 writer_crs,
                                                                 transformContext,
                                                                 options)
        # we might need to transform the coordinates to JSON EPSG:4326
        mappingDefinition = QgsRemappingSinkDefinition()
        mappingDefinition.setSourceCrs(crs)
        mappingDefinition.setDestinationCrs(writer_crs)
        mappingDefinition.setDestinationFields(fields)
        mappingDefinition.setDestinationWkbType(wkbType)

        for field in fields:
            field: QgsField
            mappingDefinition.addMappedField(field.name(), QgsProperty.fromField(field.name()))

        expressionContext = QgsExpressionContext()
        expressionContext.setFields(fields)
        expressionContext.setFeedback(feedback)

        scope = QgsExpressionContextScope()
        scope.setFields(fields)
        expressionContext.appendScope(scope)
        transformationContext = QgsCoordinateTransformContext()

        featureSink = QgsRemappingProxyFeatureSink(mappingDefinition, writer)
        featureSink.setExpressionContext(expressionContext)
        featureSink.setTransformContext(transformationContext)

        if writer.hasError() != QgsVectorFileWriter.NoError:
            raise Exception(f'Error when creating {path}: {writer.errorMessage()}')

        featureSink.flushBuffer()

        if not featureSink.addFeatures(profiles):
            errSink = featureSink.lastError()
            if writer.errorCode() != QgsVectorFileWriter.NoError:
                raise Exception(f'Error when creating feature: {writer.errorMessage()}')

        del writer

        # set profile column styles etc.
        cls.copyEditorWidgetSetup(path.as_posix(), fields)

        return [path.as_posix()]

    @classmethod
    def importProfiles(cls,
                       path: str,
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:
        lyr = QgsVectorLayer(Path(path).as_posix())
        lyr.loadDefaultStyle()
        return list(lyr.getFeatures())
