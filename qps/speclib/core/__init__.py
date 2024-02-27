from typing import Union, List, Dict

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsFields


def create_profile_field(*args, **kwds) -> QgsField:
    from .spectrallibrary import SpectralLibraryUtils
    return SpectralLibraryUtils.createProfileField(*args, **kwds)


def can_store_spectral_profiles(field: QgsField) -> bool:
    """
    Returns True if the QgsField can be used to store spectral profiles
    """
    """
    json JSON=8 subType=10 len=0   = JSON type, as by OGR
    blob Binary=12 subType=0 len=0 = BLOB
    text String=10 subType=0 len=0 = unlimited string / varchar
    text10 String=10 subType=0 len=10 length-limited string, not supported!
    """
    if not (isinstance(field, QgsField) and field.length() in [0, -1]):
        return False
    b = field.type() in [QVariant.ByteArray,
                         QVariant.String,
                         QVariant.Map  # JSON
                         ]

    return b


def is_profile_field(field: QgsField) -> bool:
    """
    Checks if a field is a valid spectra profile field, i.e.
    is of type binary and has the editor widget setup set to EDITOR_WIDGET_REGISTRY_KEY
    :param field: QgsField
    :return: bool
    """
    from .spectrallibrary import SpectralLibraryUtils
    return SpectralLibraryUtils.isProfileField(field)


def make_profile_field(field: QgsField) -> True:
    from .spectrallibrary import SpectralLibraryUtils
    return SpectralLibraryUtils.makeToProfileField(field)


def contains_profile_field(object: Union[QgsVectorLayer, QgsFeature, QgsFields]) -> bool:
    """
    Returns True if the input contains a QgsField of type binary / string and editorWidget SpectralProfile
    :param object:
    :return: bool
    """
    fields = None
    if isinstance(object, (QgsVectorLayer, QgsFeature)):
        fields = object.fields()
    elif isinstance(object, QgsFields):
        fields = object
    if isinstance(fields, QgsFields):
        for field in fields:
            if is_profile_field(field):
                return True
    return False


def is_spectral_library(layer: QgsVectorLayer) -> bool:
    """
    Returns True if a vector layer contains at least one spectral profile field
    :param layer: QgsVectorLayer
    :return: bool
    """
    return contains_profile_field(layer)


def is_spectral_feature(feature: QgsFeature) -> bool:
    """
    Returns True if a QgsFeatures contains at least oe spectral profile field
    :param feature:
    :return:
    """
    return contains_profile_field(feature)


def profile_fields(fields: Union[QgsFeature, QgsVectorLayer, QgsFields]) -> QgsFields:
    """
    Returns the spectral profile fields
    :param fields: fields to check
    :return: QgsFields
    """
    pfields = QgsFields()

    if isinstance(fields, QgsFeature):
        fields = fields.fields()
    elif isinstance(fields, QgsVectorLayer):
        fields = fields.fields()
    elif isinstance(fields, list):
        fds = QgsFields()
        for f in fields:
            assert isinstance(f, QgsField)
            fds.append(f)
        fields = fds
    elif isinstance(fields, QgsFields):
        pass
    if not isinstance(fields, QgsFields):
        return pfields

    for i in range(fields.count()):
        f = fields.at(i)
        if is_profile_field(f):
            pfields.append(f)
    return pfields


def profile_field_list(spectralLibrary: Union[QgsFeature, QgsVectorLayer, QgsFields]) -> List[QgsField]:
    """
    Returns the fields that contains values of SpectralProfiles
    :param spectralLibrary:
    :return:
    """
    pfields = profile_fields(spectralLibrary)
    return [pfields.at(i) for i in range(pfields.count())]


def profile_field_lookup(spectralLibrary: Union[QgsFeature, QgsVectorLayer]) -> \
        Dict[Union[int, str], QgsField]:
    """
    Returns a dictionary to lookup spectral profile fields by name or field index
    :param spectralLibrary: QgsVectorLayer
    :return: dict
    """
    fields = profile_field_list(spectralLibrary)
    D = {f.name(): f for f in fields}
    for f in fields:
        D[spectralLibrary.fields().lookupField(f.name())] = f
    return D


def profile_field_indices(spectralLibrary: Union[QgsFeature, QgsVectorLayer]) -> List[int]:
    """
    Returns the indices of spectral profile fields
    :param spectralLibrary: QgsVectorLayer
    :return: [list of int]
    """
    return [spectralLibrary.fields().lookupField(f.name()) for f in profile_field_list(spectralLibrary)]


def profile_field_names(spectralLibrary: Union[QgsFeature, QgsVectorLayer]) -> List[str]:
    """
    Returns the names of spectral profile fields
    :param spectralLibrary: QgsVectorLayer
    :return: [list of str]
    """
    return [f.name() for f in profile_field_list(spectralLibrary)]


def first_profile_field_index(source: Union[QgsFields, QgsFeature, QgsVectorLayer]) -> int:
    """
    Returns the 1st QByteArray field that can be used to store Spectral Profile data
    :param source:
    :return:
    """
    if isinstance(source, QgsVectorLayer):
        for f in profile_field_list(source):
            return source.fields().lookupField(f.name())
    elif isinstance(source, QgsFeature):
        return first_profile_field_index(source.fields())
    elif isinstance(source, QgsFields):
        for f in source:
            if f.type() == QVariant.ByteArray:
                return source.lookupField(f.name())
    return -1


def field_index(source: Union[QgsFields, QgsFeature, QgsVectorLayer],
                field: Union[str, int, QgsField]) -> int:
    """
    Returns the field index as int, or -1, if not found
    :param source:
    :param field:
    :return:
    """
    if isinstance(field, int):
        return field

    idx = -1
    if isinstance(source, (QgsVectorLayer, QgsFeature)):
        fields = source.fields()
    assert isinstance(fields, QgsFields)
    if isinstance(field, QgsField):
        idx = fields.lookupField(field.name())
    elif isinstance(field, str):
        idx = fields.lookupField(field)

    return idx
