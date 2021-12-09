import typing
import pathlib

import numpy as np
from PyQt5.QtCore import QModelIndex
from PyQt5.QtGui import QIcon
from qgis._core import QgsRasterInterface, QgsCoordinateReferenceSystem, QgsMapLayerModel, QgsRasterLayer, \
    QgsRasterBandStats

from qgis.PyQt import Qt
from qgis.core import QgsVectorLayer, QgsFields, QgsRectangle, QgsDataProvider, QgsRasterDataProvider, QgsField, \
    QgsDataSourceUri, QgsFeature, QgsFeatureRequest, QgsRasterBlockFeedback, QgsRasterBlock, Qgis, QgsProviderMetadata, \
    QgsProviderRegistry, QgsMessageLog

from qps.speclib.core import profile_fields, is_profile_field, profile_field_indices
from qps.speclib.core.spectralprofile import SpectralSetting, groupBySpectralProperties, SpectralProfile
from qps.utils import QGIS2NUMPY_DATA_TYPES


def featuresToArrays(speclib: QgsVectorLayer,
                     spectral_profile_fields: typing.List[QgsField],
                     fids: typing.List[int] = None,
                     allow_empty_profiles: bool = False,
                     ) -> \
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
            if allow_empty_profiles:
                expression += ' OR '
            else:
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
            if isinstance(setting, SpectralSetting):
                nb = setting.n_bands()
                array = np.empty((nb, ns), dtype=float)
            else:
                array = None
            arrays.append(array)

        for p, profile in enumerate(profiles):
            profile: SpectralProfile
            fids[p] = profile.id()
            for i, setting in enumerate(settings):
                array = arrays[i]
                if isinstance(array, np.ndarray):
                    array[:, p] = profile.yValues(pfield_indices[i])
        ARRAYS[settings] = (fids, arrays)
    return ARRAYS


class SpectralLibraryRasterLayerModel(QgsMapLayerModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        if role != Qt.DecorationRole:
            return super().data(index, role)

        isEmpty = index.row() == 0 and self.allowEmptyLayer()
        additionalIndex = index.row() - (1 if self.allowEmptyLayer() else 0) - self.rowCount()

        if isEmpty or additionalIndex >= 0:
            return None

        layer = self.layerFromIndex(index.row() - ( 1 if self.allowEmptyLayer() else 0 ) )
        if isinstance(layer, QgsRasterLayer) and isinstance(layer.dataProvider(), SpectralLibraryRasterDataProvider):
            return QIcon(r':/qps/ui/icons/profile.svg')
        else:
            return super().data(index, role)



class SpectralLibraryRasterDataProvider(QgsRasterDataProvider):
    """
    An
    """

    def __init__(self, *args, speclib=None, fids: typing.List[int]=None, **kwds):

        super().__init__(*args, **kwds)

        self.mSpeclib: QgsVectorLayer = None
        self.mProfileFields: QgsFields = QgsFields()
        self.mARRAYS: typing.Dict[typing.Tuple[SpectralSetting, ...],
                      typing.Tuple[np.ndarray, typing.List[np.ndarray]]] = dict()
        self.mActiveProfileSettings: typing.Tuple[SpectralSetting, ...] = None
        self.mActiveProfileField: QgsField = None

        if speclib:
            self.initData(speclib, fids)


    def createFieldLayer(self,
                         field: QgsField,
                         settings: typing.Tuple[SpectralSetting, ...]) -> QgsRasterLayer:
        i = self.profileFields().indexOf(field.name())
        assert i >= 0

        layer = QgsRasterLayer(self.speclib().source(),
                               f'<no name>',
                               SpectralLibraryRasterDataProvider.providerKey())
        assert layer.isValid()
        dp: SpectralLibraryRasterDataProvider = layer.dataProvider()
        dp.linkProvider(self)
        dp.setActiveProfileField(field)
        dp.setActiveProfileSettings(settings)

        activeFieldSetting = dp.activeProfileFieldSetting()
        name = f'{field.name()} ({activeFieldSetting.n_bands()} bands, {activeFieldSetting.xUnit()})'
        layer.setName(name)
        return layer

    def createFieldLayers(self,
                          fields: QgsFields = None,
                          profileSettingsList: typing.List[typing.Tuple[SpectralSetting, ...]] = None,
                          one_setting_per_field: bool = True) -> typing.List[QgsRasterLayer]:

        FIELD_LAYERS = []
        FIELD_NAMES = set()

        if not isinstance(fields, QgsFields):
            fields = self.profileFields()
        else:
            for f in fields:
                assert f in self.profileFields()

        if profileSettingsList is None:
            profileSettingsList = self.profileSettingsList()
        else:
            for settings in profileSettingsList:
                assert settings in self.profileSettingsList()

        for settings in profileSettingsList:
            for i, setting in enumerate(settings):
                if isinstance(setting, SpectralSetting):
                    field = fields.at(i)
                    if one_setting_per_field and field.name() in FIELD_NAMES:
                        continue
                    FIELD_LAYERS.append(self.createFieldLayer(field, settings))
        return FIELD_LAYERS

    def capabilities(self):
        caps = QgsRasterInterface.Size | QgsRasterInterface.Identify | QgsRasterInterface.IdentifyValue
        return QgsRasterDataProvider.ProviderCapabilities(caps)

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

    def dataSourceUri(self, expandAuthConfig=False):
        s = ""

    def crs(self) -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem()

    def isValid(self) -> bool:
        return True
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
        if not (isinstance(field, QgsField) and len(settings) > 0):
            return None
        return settings[self.mProfileFields.indexOf(field.name())]

    def profileArray(self,
                     field: QgsField = None,
                     settings: typing.Tuple[SpectralSetting, ...] = None) -> np.ndarray:
        field, settings = self._field_and_settings(field, settings)
        if not isinstance(field, QgsField):
            return np.empty((0,), dtype=int)
        fid, arrays = self.mARRAYS[settings]
        return arrays[self.mProfileFields.indexOf(field.name())]

    def profileFIDs(self,
                    settings: typing.Tuple[SpectralSetting, ...] = None) -> np.ndarray:
        if settings is None:
            settings = self.activeProfileSettings()
        fids, arrays = self.mARRAYS.get(settings, (np.empty((0,), dtype=int), []))
        return fids

    def setActiveProfileField(self, field: QgsField):
        assert field in self.mProfileFields
        self.mActiveProfileField = field

    def activeProfileField(self) -> QgsField:
        return self.mActiveProfileField

    def activeProfileFieldSetting(self) -> SpectralSetting:
        i = self.profileFields().indexOf(self.activeProfileField().name())
        return self.activeProfileSettings()[i]

    def activeProfileFIDs(self) -> typing.List[int]:
        return self.profileFIDs(self.activeProfileSettings())

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

    def sourceDataType(self, bandNo):
        return self.dataType(bandNo)

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
        band_data: np.ndarray = self.profileArray()[bandNo-1, :]

        data_subset = band_data
        dt = self.dataType(bandNo)
        block = QgsRasterBlock(dt, width, height)
        block.setData(band_data.tobytes())
        return block

    def bandStatistics(self,
                       bandNo: int,
                       stats: QgsRasterBandStats.Stats = QgsRasterBandStats.Stats.All,
                       extent: QgsRectangle = QgsRectangle(),
                       sampleSize: int = 0,
                       feedback: QgsRasterBlockFeedback = None) -> QgsRasterBandStats:

        if extent is None:
            extent = QgsRectangle()
        else:
            extent = QgsRectangle(extent)

        stats = QgsRasterBandStats()
        band_data: np.ndarray = self.profileArray()[bandNo-1, :]

        stats.sum = band_data.sum()
        stats.minimumValue = band_data.min()
        stats.maximumValue = band_data.max()
        stats.mean = band_data.mean()
        stats.extent = extent
        return stats

    def generateBandName(self, band_no: int):
        setting = self.profileSetting()

        if isinstance(setting, SpectralSetting) and band_no > 0  and band_no <= setting.n_bands():
            wl = setting.x()[band_no-1]
            wlu = setting.xUnit()
            return f'Band {band_no} {wl} {wlu}'

        return ''

    def bandCount(self) -> int:
        setting = self.profileSetting()
        if not isinstance(setting, SpectralSetting):
            return 0
        else:
            return self.profileSetting().n_bands()

    def profileSettingsList(self) -> typing.List[typing.Tuple[SpectralSetting, ...]]:
        return list(self.mARRAYS.keys())

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

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def fields(self) -> QgsFields:
        return self.mProfileFields

    def extent(self) -> QgsRectangle:

        rect = QgsRectangle()
        rect.setXMaximum(self.xSize())
        rect.setYMaximum(self.ySize())
        return rect


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