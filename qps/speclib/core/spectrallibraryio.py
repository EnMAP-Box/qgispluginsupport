from typing import Any, List, Tuple

from qgis.PyQt.QtCore import QObject
from qgis.core import QgsExpressionContext, QgsFeature, QgsFeatureSink, QgsField, QgsFields, QgsProperty, \
    QgsRemappingProxyFeatureSink, \
    QgsRemappingSinkDefinition, QgsVectorLayer
from . import profile_field_names
from ...fieldvalueconverter import GenericPropertyTransformer

IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS = 'required_source_fields'


class SpectralLibraryImportFeatureSink(QgsRemappingProxyFeatureSink):

    def __init__(self,
                 sinkDefinition: QgsRemappingSinkDefinition,
                 speclib: QgsFeatureSink,
                 dstFields: QgsFields = None):

        # take care of required conversions
        fieldMap = sinkDefinition.fieldMap()
        fieldMap2 = dict()
        transformers = []

        if dstFields is None and isinstance(speclib, QgsVectorLayer):
            dstFields = speclib.fields()
        assert isinstance(dstFields, QgsFields), 'Destination Fields (dstFields) not specified'

        for k, srcProp in fieldMap.items():
            srcProp: QgsProperty
            dstField: QgsField = dstFields.field(k)
            transformer = GenericPropertyTransformer(dstField)
            srcProp.setTransformer(transformer)
            transformers.append(transformer)
            # if is_profile_field(dstField) and not isinstance(srcProp.transformer(), QgsPropertyTransformer):
            #    transformer = SpectralProfilePropertyTransformer(dstField)
            #    srcProp.setTransformer(transformer)
            #    transformers.append(transformer)
            fieldMap2[k] = srcProp
        sinkDefinition.setFieldMap(fieldMap2)
        super().__init__(sinkDefinition, speclib)
        self.mSpeclib = speclib
        self.mProfileFieldNames = profile_field_names(self.mSpeclib)
        self.mContext: QgsExpressionContext = None
        self.mFieldMap = sinkDefinition.fieldMap()
        self.mTransformers = transformers

    def setExpressionContext(self, context: QgsExpressionContext) -> None:
        super().setExpressionContext(context)
        self.mContext = context

    def remapFeature(self, feature: QgsFeature) -> List[QgsFeature]:
        s = ""
        try:
            features = super().remapFeature(feature)
        except Exception as ex:
            s = ""
        return features


class ProfileProperty(QgsProperty, QObject):

    def __init__(self, targetField: QgsField, *args, **kwds):
        QObject.__init__(self)
        self.mField = targetField

    def value(self, *args, **kwds) -> Tuple[Any, bool]:
        v = super().value(*args, **kwds)

        s = ""
        return v

    def __repr__(self):
        return f'ProfileProperty {id(self)}'
