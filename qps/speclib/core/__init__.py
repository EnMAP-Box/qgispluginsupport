import typing

from PyQt5.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsFields

from qps.speclib import EDITOR_WIDGET_REGISTRY_KEY


def profile_fields(spectralLibrary: typing.Union[QgsFeature, QgsVectorLayer]) -> typing.List[QgsField]:
    """
    Returns the fields that contains values of SpectralProfiles
    :param spectralLibrary:
    :return:
    """
    fields = [f for f in spectralLibrary.fields() if
              f.type() == QVariant.ByteArray]
    if isinstance(spectralLibrary, QgsVectorLayer):
        fields = [f for f in fields if f.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY]
    return fields


def profile_field_indices(spectralLibrary: typing.Union[QgsFeature, QgsVectorLayer]) -> typing.List[int]:
    return [spectralLibrary.fields().lookupField(f.name()) for f in profile_fields(spectralLibrary)]

def profile_field_names(spectralLibrary: typing.Union[QgsFeature, QgsVectorLayer]) -> typing.List[str]:
    return [f.name() for f in profile_fields(spectralLibrary)]


def first_profile_field_index(source: typing.Union[QgsFields, QgsFeature, QgsVectorLayer]) -> int:
    """
    Returns the 1st QByteArray field that can be used to store Spectral Profile data
    :param source:
    :return:
    """
    if isinstance(source, QgsVectorLayer):
        for f in profile_fields(source):
            return source.fields().lookupField(f.name())
    elif isinstance(source, QgsFeature):
        return first_profile_field_index(source.fields())
    elif isinstance(source, QgsFields):
        for f in source:
            if f.type() == QVariant.ByteArray:
                return source.lookupField(f.name())
    return -1


def field_index(source: typing.Union[QgsFields, QgsFeature, QgsVectorLayer], field: typing.Union[str, int, QgsField]) -> int:
    """
    Returns the field index as int
    :param source:
    :param field:
    :return:
    """
    if isinstance(field, int):
        return field
    else:
        if isinstance(source, (QgsVectorLayer, QgsFeature)):
            fields = source.fields()
        assert isinstance(fields, QgsFields)
        if isinstance(field, QgsField):
            return fields.lookupField(field.name())
        elif isinstance(field, str):
            return fields.lookupField(field)

    raise NotImplementedError()