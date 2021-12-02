import typing
import pathlib

import numpy as np
from qgis.core import QgsVectorLayer, QgsFields, QgsRectangle, QgsDataProvider, QgsRasterDataProvider, QgsField, \
    QgsDataSourceUri, QgsFeature, QgsFeatureRequest, QgsRasterBlockFeedback, QgsRasterBlock, Qgis, QgsProviderMetadata, \
    QgsProviderRegistry, QgsMessageLog

from qps.speclib.core import profile_fields, is_profile_field, profile_field_indices
from qps.speclib.core.spectralprofile import SpectralSetting, groupBySpectralProperties, SpectralProfile
from qps.utils import QGIS2NUMPY_DATA_TYPES


def featuresToArrays(speclib: QgsVectorLayer,
                     spectral_profile_fields: typing.List[QgsField],
                     fids: typing.List[int] = None) -> \
        typing.Dict[typing.Tuple[SpectralSetting, ...],
                    typing.Tuple[np.ndarray, typing.List[np.ndarray]]]:
    assert isinstance(speclib, QgsVectorLayer)
    if spectral_profile_fields is None:
        spectral_profile_fields = profile_fields(speclib)

    assert len(spectral_profile_fields) > 0
    pfields = profile_fields(speclib)
    assert len(pfields) > 0
    pfield_indices: typing.List[int] = list()
    for field in spectral_profile_fields:
        assert field in pfields
        pfield_indices.append(speclib.fields().lookupField(field.name()))

    request = QgsFeatureRequest()
    if fids:
        request.setFilterFids(fids)
    expression = ''
    for i, field in enumerate(spectral_profile_fields):
        if i > 0:
            expression += ' AND '
        expression += f'"{field.name()}" is not NULL'

    request.setFilterExpression(expression)

    PROFILES = dict()

    for feature in speclib.getFeatures(request):
        profile = SpectralProfile.fromQgsFeature(feature, profile_field=pfield_indices[0])
        settings: typing.List[SpectralSetting] = list()
        for f in pfield_indices:
            settings.append(profile.spectralSettings(f))
        settings = tuple(settings)
        PROFILE_LIST = PROFILES.get(settings, [])
        PROFILE_LIST.append(profile)
        PROFILES[settings] = PROFILE_LIST

    ARRAYS: typing.Dict[typing.Tuple[SpectralSetting, ...],
                        typing.Tuple[np.ndarray, typing.List[np.ndarray]]] = dict()
    for settings, profiles in PROFILES.items():

        ns = len(profiles)
        fids = np.empty((ns,), dtype=int)
        arrays: typing.List[np.ndarray] = list()

        for i, setting in enumerate(settings):
            nb = setting.n_bands()
            array = np.empty((nb, ns), dtype=float)
            arrays.append(array)
        for p, profile in enumerate(profiles):
            profile: SpectralProfile
            fids[p] = profile.id()
            for i, setting in enumerate(settings):
                array = arrays[i]
                array[:, p] = profile.yValues(pfield_indices[i])
        ARRAYS[settings] = (fids, arrays)
    return ARRAYS


def speclibToRaster(speclib: QgsVectorLayer,
                    directory: pathlib.Path,
                    profile_field: typing.Union[str, int, QgsField] = None,
                    prefix: str = 'speclib2raster') -> typing.List[pathlib.Path]:
    directory = pathlib.Path(directory)
    assert directory.is_dir()
    assert isinstance(speclib, QgsVectorLayer)
    ARRAYS = featuresToArrays(speclib.getFeatures(), profile_field)


class SpectralLibraryRasterDataProvider(QgsRasterDataProvider):
    """
    An
    """

    def __init__(self, *args, speclib=None, fids: typing.List[int]=None, **kwds):

        super().__init__(*args, **kwds)

        self.mSpeclib: QgsVectorLayer = None
        self.mProfileFields: QgsFields = QgsFields()
        self.mARRAYS: typing.Dict[typing.Tuple[SpectralSetting, ...],
                      typing.Tuple[np.ndarray, typing.List[np.ndarray]]] = None
        self.mActiveProfileSettings: typing.Tuple[SpectralSetting, ...] = None
        self.mActiveProfileField: QgsField = None

        if speclib:
            self.initData(speclib, fids)

    def name(self):
        return 'Name'

    @classmethod
    def providerKey(cls) -> str:
        return 'speclibraster'

    @classmethod
    def description(self) -> str:
        return 'SpectralLibraryRasterDataProvider'

    @classmethod
    def createProvider(cls, uri, providerOptions, flags=None):
        # compatibility with Qgis < 3.16, ReadFlags only available since 3.16
        flags = QgsDataProvider.ReadFlags()
        provider = SpectralLibraryRasterDataProvider(uri, providerOptions, flags)
        return provider

    def isValid(self) -> bool:
        return self.mARRAYS is not None

    def _field_and_settings(self,
                            field: QgsField = None,
                            settings: typing.Tuple[SpectralSetting, ...] = None) -> \
            typing.Tuple[QgsField, typing.Tuple[SpectralSetting, ...]]:
        if field is None:
            field = self.activeProfileField()
        if settings is None:
            settings = self.activeProfileSettings()
        return field, settings

    def profileFields(self) -> QgsFields:
        return self.mProfileFields

    def profileSetting(self,
                       field: QgsField = None,
                       settings: typing.Tuple[SpectralSetting, ...] = None) -> SpectralSetting:
        field, settings = self._field_and_settings(field, settings)
        return settings[self.mProfileFields.indexOf(field.name())]

    def profileArray(self,
                     field: QgsField = None,
                     settings: typing.Tuple[SpectralSetting, ...] = None) -> np.ndarray:
        field, settings = self._field_and_settings(field, settings)
        fid, arrays = self.mARRAYS[settings]
        return arrays[self.mProfileFields.indexOf(field.name())]

    def profileFIDs(self,
                    settings: typing.Tuple[SpectralSetting, ...] = None) -> np.ndarray:
        if settings is None:
            settings = self.activeProfileSettings()
        fids, arrays = self.mARRAYS[settings]
        return fids

    def setActiveProfileField(self, field: QgsField):
        assert field in self.mProfileFields
        self.mActiveProfileField = field

    def activeProfileField(self) -> QgsField:
        return self.mActiveProfileField

    def setActiveProfileSettings(self, settings: typing.Tuple[SpectralSetting, ...]):
        assert settings in self.mARRAYS.keys()
        self.mActiveProfileSettings = settings

    def activeProfileSettings(self) -> typing.Tuple[SpectralSetting, ...]:
        return self.mActiveProfileSettings

    def xSize(self) -> int:
        return len(self.profileFIDs())

    def ySize(self) -> int:
        if len(self.mARRAYS) > 0:
            return 1
        else:
            return 0

    def dataType(self, bandNo: int) -> Qgis.DataType:
        array = self.profileArray()
        t = Qgis.DataType.UnknownDataType
        for qgis_type, dtype in QGIS2NUMPY_DATA_TYPES.items():
            if dtype == array.dtype:
                t = qgis_type
                break
        return t

    def block(self,
              bandNo: int,
              boundingBox: QgsRectangle,
              width: int,
              height: int,
              feedback: QgsRasterBlockFeedback = None) -> QgsRasterBlock:
        band_data = self.profileArray()[bandNo-1, :]

        block = QgsRasterBlock(self.dataType(bandNo), width, height)

        return block

    def bandCount(self) -> int:
        return self.profileSetting().n_bands()

    def profileSettingsList(self) -> typing.List[typing.Tuple[SpectralSetting, ...]]:
        return self.mARRAYS.keys()

    def initData(self, speclib: QgsVectorLayer, fids: typing.List[int] = None):
        self.mSpeclib = speclib
        self.mProfileFields = profile_fields(speclib)
        self.mARRAYS = featuresToArrays(speclib, self.mProfileFields, fids=fids)

    def linkProvider(self, provider):
        assert isinstance(provider, SpectralLibraryRasterDataProvider)
        self.mSpeclib = provider.mSpeclib
        self.mProfileFields = provider.mProfileFields
        self.mARRAYS = provider.mARRAYS

    def clone(self) -> 'SpectralLibraryRasterDataProvider':
        dp = SpectralLibraryRasterDataProvider(None)
        dp.mARRAYS = self.mARRAYS
        dp.mProfileFields = self.mProfileFields
        dp.mActiveProfileSettings = self.mActiveProfileSettings
        dp.mSpeclib = self.mSpeclib

        return dp

    def uri(self) -> QgsDataSourceUri:
        return self.speclib().source()

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def fields(self) -> QgsFields:
        return self.mProfileFields

    def extent(self) -> QgsRectangle:
        pass


def myfunc(*args, **kwds):
    return ''


def registerDataProvider():

    metadata = QgsProviderMetadata(
        SpectralLibraryRasterDataProvider.providerKey(),
        SpectralLibraryRasterDataProvider.description(),
        SpectralLibraryRasterDataProvider.createProvider
    )
    registry = QgsProviderRegistry.instance()
    registry.registerProvider(metadata)
    QgsMessageLog.logMessage('SpectralLibraryRasterDataProvider registered')