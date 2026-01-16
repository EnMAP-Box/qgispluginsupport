from pathlib import Path
from typing import Any, List, Union, Optional

import numpy as np

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
                       QgsExpressionContext,
                       QgsExpressionContextScope, QgsFeature, QgsMapLayer,
                       QgsField, QgsFields, QgsProcessingFeedback, QgsProject, QgsProperty,
                       QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition,
                       QgsVectorFileWriter, QgsVectorLayer)
from qgis.core import QgsFeatureIterator
from ..core import is_profile_field
from ..core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, SpectralProfileFileReader, \
    SpectralProfileFileWriter
from ...qgisenums import QMETATYPE_QSTRING


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


class GeoJSONSpectralLibraryWriter(SpectralProfileFileWriter):

    def __init__(self, *args,
                 crs: QgsCoordinateReferenceSystem = None,
                 rfc7946: bool = True, **kwds):
        super().__init__(*args, **kwds)

        if crs is None:
            crs = QgsCoordinateReferenceSystem('EPSG:4326')
        self.mCrs = crs
        self.mRFC7946 = rfc7946

    @classmethod
    def id(cls) -> str:
        return 'GeoJSON'

    @classmethod
    def filterString(cls) -> bool:
        return "GeoJSON (*.geojson)"

    def writeFeatures(self,
                      path: Union[str, Path],
                      features: List[QgsFeature],
                      feedback: Optional[QgsProcessingFeedback] = None) -> List[Path]:

        path = Path(path)

        if feedback is None:
            feedback = QgsProcessingFeedback()

        if isinstance(features, QgsFeatureIterator):
            features = list(features)

        if len(features) == 0:
            feedback.pushInfo('No features to write')
            return []

        if isinstance(features, QgsFeatureIterator):
            features = list(features)

        f0 = features[0]

        srcFields = f0.fields()
        wkbType = f0.geometry().wkbType()

        layerName = Path(path).stem

        transformContext = QgsProject.instance().transformContext()
        crsJson = QgsCoordinateReferenceSystem('EPSG:4326')

        path: Path = Path(path)

        datasourceOptions = []

        layerOptions = [f'DESCRIPTION={layerName}']
        layerOptions.insert(0, f'RFC7946={"YES" if self.mRFC7946 else "NO"}')

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.datasourceOptions = datasourceOptions
        options.layerOptions = layerOptions
        options.fileEncoding = 'UTF-8'
        options.skipAttributeCreation = False
        options.driverName = 'GeoJSON'

        converter = GeoJsonFieldValueConverter(srcFields)
        options.fieldValueConverter = converter
        dstFields = converter.convertedFields()

        writer_crs: QgsCoordinateReferenceSystem = crsJson if self.mRFC7946 else self.mCrs
        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path.as_posix(),
                                                                 dstFields,
                                                                 wkbType,
                                                                 writer_crs,
                                                                 transformContext,
                                                                 options)
        # we might need to transform the coordinates to JSON EPSG:4326
        mappingDefinition = QgsRemappingSinkDefinition()
        mappingDefinition.setSourceCrs(self.mCrs)
        mappingDefinition.setDestinationCrs(writer_crs)
        mappingDefinition.setDestinationFields(dstFields)
        mappingDefinition.setDestinationWkbType(wkbType)

        for field in srcFields:
            field: QgsField
            mappingDefinition.addMappedField(field.name(), QgsProperty.fromField(field.name()))

        expressionContext = QgsExpressionContext()
        expressionContext.setFields(srcFields)
        expressionContext.setFeedback(feedback)

        scope = QgsExpressionContextScope()
        scope.setFields(srcFields)
        expressionContext.appendScope(scope)
        transformationContext = QgsCoordinateTransformContext()

        featureSink = QgsRemappingProxyFeatureSink(mappingDefinition, writer)
        featureSink.setExpressionContext(expressionContext)
        featureSink.setTransformContext(transformationContext)

        if writer.hasError() != QgsVectorFileWriter.WriterError.NoError:
            feedback.reportError(f'Error when creating {path}: {writer.errorMessage()}')
            return []

        featureSink.flushBuffer()

        if not featureSink.addFeatures(features):
            feedback.reportError(f'Error when creating feature: {writer.errorMessage()}')
            return []

        del writer

        lyr = QgsVectorLayer(path.as_posix())
        if lyr.isValid():
            for dstField in dstFields:
                i = lyr.fields().lookupField(dstField.name())
                if i >= 0:
                    lyr.setEditorWidgetSetup(i, dstField.editorWidgetSetup())
            msg, success = lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            if not success:
                feedback.reportError(msg)

        return [path]


class GeoJSONSpectralLibraryReader(SpectralProfileFileReader):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def id(cls) -> str:
        return 'GeoJSON'

    @classmethod
    def canReadFile(cls, path: Union[str, Path]) -> bool:
        return Path(path).suffix == '.geojson'

    def asFeatures(self) -> List[QgsFeature]:
        lyr = QgsVectorLayer(self.path().as_posix())
        lyr.loadDefaultStyle()
        return list(lyr.getFeatures())
