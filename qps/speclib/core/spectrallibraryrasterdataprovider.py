import math
import re
import typing
import warnings

import numpy as np

from qgis.PyQt import Qt
from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import QModelIndex, QUrl, QUrlQuery, QVariant, QObject, QDateTime, QByteArray
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsRasterInterface, QgsCoordinateReferenceSystem, QgsMapLayerModel, QgsRasterLayer, \
    QgsRasterBandStats, QgsProject, QgsVectorLayerCache, QgsPointXY, QgsRaster, QgsRasterIdentifyResult, \
    QgsColorRampShader
from qgis.core import QgsVectorLayer, QgsFields, QgsRectangle, QgsDataProvider, QgsRasterDataProvider, QgsField, \
    QgsFeature, QgsFeatureRequest, QgsRasterBlockFeedback, QgsRasterBlock, Qgis, QgsProviderMetadata, \
    QgsProviderRegistry, QgsMessageLog
from ..core import profile_fields, is_profile_field
from ..core.spectralprofile import SpectralSetting, groupBySpectralProperties, SpectralProfile, \
    decodeProfileValueDict
from ...utils import QGIS2NUMPY_DATA_TYPES, qgsField, qgisToNumpyDataType, nextColor, numpyToQgisDataType, \
    HashableRectangle


def createRasterLayers(features: typing.Union[QgsVectorLayer, typing.List[QgsFeature]],
                       fields = None) -> typing.List[QgsRasterLayer]:
    """
    Converts a list of QgsFeatures into a set of QgsRasterLayers
    :param features:
    :param fields:
    :return:
    """
    if isinstance(features, QgsVectorLayer):
        features = list(features.getFeatures())

    layers = []
    if len(features) == 0:
        return layers

    all_fields = features[0].fields()
    if fields is None:
        fields = [f for f in all_fields]
    else:
        if isinstance(fields, QgsField):
            fields = [fields]
        elif isinstance(fields, QgsFields):
            fields = [f for f in fields]

    for field in fields:
        assert isinstance(field, QgsField)
        if is_profile_field(field):
            GROUPS = groupBySpectralProperties(features, profile_field=field)

            for setting, profiles in GROUPS.items():
                name = f'{field.name()} ({setting.n_bands()} bands, {setting.xUnit()})'
                lyr = QgsRasterLayer('?', name, VectorLayerFieldRasterDataProvider.providerKey())
                dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
                dp.setActiveFeatures(profiles, field=field)
                layers.append(lyr)
        else:
            name = f'{field.name()} ({field.typeName()})'
            layer = QgsRasterLayer('?', name, VectorLayerFieldRasterDataProvider.providerKey())
            dp: VectorLayerFieldRasterDataProvider = layer.dataProvider()
            dp.setActiveFeatures(features, field=field)
            layers.append(layer)

    return layers


def nn_resample(img, shape):
    def per_axis(in_sz, out_sz):
        ratio = 0.5 * in_sz / out_sz
        return np.round(np.linspace(ratio - 0.5, in_sz - ratio - 0.5, num=out_sz)).astype(int)

    return img[per_axis(img.shape[0], shape[0])[:, None],
               per_axis(img.shape[1], shape[1])]


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

        layer = self.layerFromIndex(index.row() - (1 if self.allowEmptyLayer() else 0))
        if isinstance(layer, QgsRasterLayer) and isinstance(layer.dataProvider(), SpectralLibraryRasterDataProvider):
            return QIcon(r':/qps/ui/icons/profile.svg')
        else:
            return super().data(index, role)


class FieldToRasterValueConverter(QObject):
    """
    This class converts QgsFeature values of a field from / to array raster layer values
    """
    LUT_FIELD_TYPES = {
        QVariant.Bool: Qgis.DataType.Byte,
        QVariant.Int: Qgis.DataType.Int32,
        QVariant.UInt: Qgis.DataType.UInt32,
        QVariant.LongLong: Qgis.DataType.Int32,
        QVariant.ULongLong: Qgis.DataType.UInt32,
        QVariant.Double: Qgis.DataType.Float32,
        QVariant.String: Qgis.DataType.Int32,
        QVariant.DateTime: Qgis.DataType.Int32,
        QVariant.Date: Qgis.DataType.Int32,
        QVariant.Time: Qgis.DataType.Int32,
    }

    NO_DATA_CANDIDATES = [-1, -9999]

    @classmethod
    def supportsField(cls, field: QgsField) -> bool:
        return field.type() in FieldToRasterValueConverter.LUT_FIELD_TYPES.keys()

    def __init__(self, field: QgsField, ):
        super().__init__(None)

        assert isinstance(field, QgsField)
        self.mField: QgsField = field
        # there need to be a numeric no-data value
        self.mNoData = -1
        self.mColorTable = list()
        self.mRasterData: np.ndarray = None

    def isValid(self) -> bool:
        return isinstance(self.mRasterData, np.ndarray)

    def updateRasterData(self, features: typing.List[QgsFeature]):

        self.mRasterData = None
        fieldValues = [f.attribute(self.mField.name()) for f in features]
        self.mRasterData, self.mColorTable, self.mNoData = self.toRasterValues(fieldValues)

    def colorInterpretationName(self, bandNo: int):
        return QgsRaster.UndefinedColorInterpretation

    def htmlMetadata(self) -> str:
        return f'Field: {self.field().name()} Type: {self.field().typeName()}'

    def isClassification(self) -> bool:

        return self.field().type() == QVariant.String

    def colorInterpretation(self, bandNo: int) -> int:
        if self.isClassification():
            return QgsRaster.PalettedColor
        else:
            return QgsRaster.GrayIndex

    def colorTable(self, bandNo: int) -> typing.List[QgsColorRampShader.ColorRampItem]:
        return self.mColorTable[:]

    def field(self) -> QgsField:
        return self.mField

    def rasterDataArray(self) -> np.ndarray:
        return self.mRasterData

    def bandCount(self) -> int:
        """
        One field, one raster band
        :return:
        :rtype:
        """
        return 1

    def bandScale(self, bandNo: int) -> float:
        return 1

    def bandOffset(self, bandNo: int) -> float:
        return 0

    def sourceNoDataValue(self, band: int):
        return self.mNoData

    def rasterDataTypeSize(self, band: int):
        s = ""

    def generateBandName(self, band: int):
        digits = int(math.log10(self.bandCount())) + 1
        return '{} Band {}'.format(self.field().name(), str(band).zfill(digits))

    def dataType(self, band: int) -> Qgis.DataType:
        return FieldToRasterValueConverter.LUT_FIELD_TYPES.get(self.mField.type(), Qgis.DataType.UnknownDataType)

    def toRasterValues(self, fieldValues: typing.List) -> typing.Tuple[
        np.ndarray,
        typing.List[QgsColorRampShader.ColorRampItem],
        typing.Any]:
        ns = len(fieldValues)
        nb = self.bandCount()
        field = self.mField
        dtype = qgisToNumpyDataType(self.dataType(1))

        colorTable: typing.List[QgsColorRampShader.ColorRampItem] = []

        noData = None
        numericValues = None

        if field.type() == QVariant.String:
            # convert values class values
            noData = 0
            uniqueValues = set(fieldValues)
            uniqueValues = sorted(uniqueValues, key=lambda v: v not in [None, NULL])

            LUT = {None: noData,
                   NULL: noData
                   }
            color = QColor('black')
            colorTable.append(QgsColorRampShader.ColorRampItem(float(noData), color, 'no data'))
            for v in uniqueValues:
                if v not in LUT.keys():
                    LUT[v] = len(LUT) - 1
                    color = nextColor(color, mode='cat')
                    colorTable.append(QgsColorRampShader.ColorRampItem(
                        float(LUT[v]), color, str(v)))

            numericValues = [LUT[v] for v in fieldValues]

        elif field.type() in [QVariant.Bool,
                              QVariant.Int, QVariant.UInt,
                              QVariant.LongLong, QVariant.ULongLong,
                              QVariant.Double]:

            for c in self.NO_DATA_CANDIDATES:
                if c not in fieldValues:
                    noData = c
                    break

            if noData is None:
                noData = min(fieldValues) - 1

            numericValues = []
            for v in fieldValues:
                if v in [None, NULL]:
                    numericValues.append(noData)
                else:
                    numericValues.append(v)
        elif field.type() == QVariant.DateTime:
            numericValues = []
            noData = -9999
            for v in fieldValues:
                if isinstance(v, QDateTime):
                    numericValues.append(v.toSecsSinceEpoch())
                else:
                    numericValues.append(noData)

        if noData is not None and numericValues is not None:
            array = np.asarray(numericValues, dtype=dtype)
            array = array.reshape((nb, 1, ns))
        else:
            # fallback: empty image
            noData = -9999
            array = noData * np.ones((nb, 1, ns))

        assert array.ndim == 3
        return array, colorTable, noData

    @classmethod
    def toFieldValues(cls, field: QgsField, rasterValues: np.ndarray) -> typing.List:
        raise NotImplementedError


class SpectralProfileValueConverter(FieldToRasterValueConverter):

    @classmethod
    def supportsField(cls, field: QgsField) -> bool:
        return is_profile_field(field)

    def __init__(self, field: QgsField):
        assert is_profile_field(field)
        super(SpectralProfileValueConverter, self).__init__(field)
        self.mSpectralSetting: SpectralSetting = None

    def colorInterpretation(self, bandNo: int) -> int:
        return QgsRaster.MultiBandColor

    def activeSpectralSetting(self) -> SpectralSetting:
        return self.mSpectralSetting

    def bandCount(self) -> int:
        if isinstance(self.mSpectralSetting, SpectralSetting):
            return self.mSpectralSetting.n_bands()
        else:
            return 0

    def dataType(self, band: int) -> Qgis.DataType:
        if isinstance(self.mRasterData, np.ndarray):
            return numpyToQgisDataType(self.mRasterData.dtype)

        else:
            return Qgis.DataType.UnknownDataType

    def toRasterValues(self, fieldValues: typing.List) -> typing.Tuple[
        np.ndarray,
        typing.List[QgsColorRampShader.ColorRampItem],
        typing.Any]:

        # get spectral setting
        self.mSpectralSetting = None

        ns = len(fieldValues)
        nb = 0
        profileData: typing.List = []
        profileIndices: typing.List[int] = []

        for i, v in enumerate(fieldValues):
            if isinstance(v, QByteArray):
                d = decodeProfileValueDict(v)
                try:
                    s = SpectralSetting.fromDictionary(d)
                except Exception as ex:
                    s = ""
                if isinstance(s, SpectralSetting):
                    if self.mSpectralSetting is None:
                        self.mSpectralSetting = s
                        nb = s.n_bands()
                    if s == self.mSpectralSetting:
                        profileData.append(d['y'])
                        profileIndices.append(i)

        profileIndices = np.asarray(profileIndices)
        profileData2 = np.asarray(profileData)
        # p1 = profileData[0]
        profileData = np.asarray(profileData).transpose().reshape(nb, 1, len(profileIndices))

        uniqueValues = np.unique(profileData)

        noData = None
        no_data_candidates = self.NO_DATA_CANDIDATES[:]
        if len(profileData) > 0:
            no_data_candidates.append(profileData.min() - 1)
        for c in no_data_candidates:
            if c not in uniqueValues:
                noData = c
                break

        rasterData = np.ones((nb, 1, ns), dtype=profileData.dtype) * noData
        if len(profileIndices) > 0:
            rasterData[:, :, profileIndices] = profileData
        return rasterData, [], noData

        s = ""


class VectorLayerFieldRasterDataProvider(QgsRasterDataProvider):
    """
    A QgsRasterDataProvider to access the field values in a QgsVectorLayer like a raster layer
    """
    PARENT = QObject()

    FIELD_CONVERTER = [FieldToRasterValueConverter, SpectralProfileValueConverter]

    def __init__(self,
                 uri: str,
                 providerOptions: QgsDataProvider.ProviderOptions = QgsDataProvider.ProviderOptions(),
                 flags: typing.Union[QgsDataProvider.ReadFlags, QgsDataProvider.ReadFlag] = QgsDataProvider.ReadFlags(),
                 ):

        super().__init__(uri, providerOptions=providerOptions, flags=flags)
        self.mProviderOptions = providerOptions
        self.mFlags = flags
        self.mField: QgsField = None
        self.mFieldConverter: FieldToRasterValueConverter = None
        self.mFeatures: typing.List[QgsFeature] = []
        self.mStatsCache = dict()
        self.mYOffset: int = 0
        self.mYOffsetManual: bool = False
        self.initWithDataSourceUri(self.dataSourceUri())

    def activeFeatures(self) -> typing.List[QgsFeature]:
        return self.mFeatures

    def initWithDataSourceUri(self, uri: str) -> None:

        url: QUrl = QUrl(uri)
        query: QUrlQuery = QUrlQuery(url)

        layerID: str = None
        layer: QgsVectorLayer = None
        cacheSize: int = 2048

        if query.hasQueryItem('lid'):
            layerID = query.queryItemValue('lid')
        elif query.hasQueryItem('layerid'):
            layerID = query.queryItemValue('layerid')
        if layerID:
            layerID = re.sub(r'[{}]', '', layerID)
            layer = QgsProject.instance().mapLayer(layerID)

        if isinstance(layer, QgsVectorLayer):
            if query.hasQueryItem('cachesize'):
                cs = int(query.queryItemValue('cachesize'))
                assert cs > 0, 'cachesize needs to be > 0'
                cacheSize = cs

            if layer.featureCount() > 0:
                self.setActiveFeatures(layer.getFeatures())

                if query.hasQueryItem('field'):
                    self.setActiveField(query.queryItemValue('field'))
                else:
                    self.setActiveField(self.fields()[0])

    def fields(self) -> QgsFields:
        if len(self.mFeatures) > 0:
            return self.mFeatures[0].fields()
        else:
            return QgsFields()

    def generateBandName(self, bandNumber: int) -> str:
        if self.hasFieldConverter():
            return self.fieldConverter().generateBandName(bandNumber)
        else:
            return f'{self.activeField().name()} Band {bandNumber} '

    def block(self,
              bandNo: int,
              boundingBox: QgsRectangle,
              width: int,
              height: int,
              feedback: typing.Optional[QgsRasterBlockFeedback] = None) -> QgsRasterBlock:

        # print(f'# block: {bandNo}: {boundingBox} : {width} : {height}', flush=True)

        dt = self.dataType(bandNo)
        block = QgsRasterBlock(dt, width, height)

        mExtent = self.extent()
        if not mExtent.intersects(boundingBox):
            block.setIsNoData()
            return block

        if not mExtent.contains(boundingBox):
            subRect = QgsRasterBlock.subRect(boundingBox, width, height, mExtent)
            block.setIsNoDataExcept(subRect)

        self._readBlock(bandNo, boundingBox, width, height, block, feedback)

        return block

    def _readBlock(self, bandNo: int, reqExtent: QgsRectangle,
                   bufferWidthPix: int, bufferHeightPix: int, block: QgsRasterBlock,
                   feedback: QgsRasterBlockFeedback) -> bool:
        fullExtent = self.extent()
        intersectExtent = reqExtent.intersect(fullExtent)
        if intersectExtent.isEmpty():
            print('# draw request outside view extent', flush=True)
            return False

        converter = self.fieldConverter()
        if isinstance(converter, FieldToRasterValueConverter):
            x0, x1 = round(intersectExtent.xMinimum()), round(intersectExtent.xMaximum())
            # y0, y1 = round(intersectExtent.yMinimum()), round(intersectExtent.yMaximum())
            # import scipy.interpolate as interp
            band_slice = converter.rasterDataArray()[bandNo - 1, 0:1, int(x0):int(x1)]

            band_data = nn_resample(band_slice, (bufferHeightPix, bufferWidthPix))

            # print(f'# Extents:\nF={fullExtent}\nR={reqExtent}\nI={intersectExtent}\n w={bufferWidthPix} h={bufferHeightPix}')

            # print(f'# band_data: {band_data.shape} {band_data.min()} to {band_data.max()}')
            block.setData(band_data.tobytes())

        return True

    def fieldValues(self) -> list:
        return [f.attribute(self.activeField().name()) for f in self.activeFeatures()]

    def hasStatistics(self,
                      bandNo: int,
                      stats: int = ...,
                      extent: QgsRectangle = ...,
                      sampleSize: int = ...,
                      feedback: typing.Optional['QgsRasterBlockFeedback'] = ...) -> bool:
        return True
        statsKey = self._statsKey(bandNo, stats, extent, sampleSize)
        return statsKey in self.mStatsCache.keys()

    def _statsKey(self, bandNo, stats, extent, sampleSize):
        return (bandNo, stats, HashableRectangle(extent))

    def bandStatistics(self,
                       bandNo: int,
                       stats: int = ...,
                       extent: QgsRectangle = ...,
                       sampleSize: int = ...,
                       feedback: typing.Optional['QgsRasterBlockFeedback'] = ...) -> 'QgsRasterBandStats':

        statsKey = self._statsKey(bandNo, stats, extent, sampleSize)
        if statsKey in self.mStatsCache.keys():
            return self.mStatsCache[statsKey]
        print(f'# statistics')
        if extent is None:
            extent = QgsRectangle()
        else:
            extent = QgsRectangle(extent)

        stats = QgsRasterBandStats()
        if self.hasFieldConverter():
            band_data: np.ndarray = self.fieldConverter().rasterDataArray()[bandNo - 1, :, :]

            stats.sum = np.nansum(band_data)
            stats.minimumValue = np.nanmin(band_data)
            stats.maximumValue = np.nanmax(band_data)
            stats.mean = np.nanmean(band_data)
            stats.extent = extent
            stats.elementCount = len(band_data)
            stats.height = band_data.shape[-2]
            stats.width = band_data.shape[-1]

            # set statsGathered! if not, the default renderer won't consider the value range
            stats.statsGathered = True
            self.mStatsCache[statsKey] = stats
        return stats

    def hasFieldConverter(self) -> bool:
        return isinstance(self.mFieldConverter, FieldToRasterValueConverter)

    def bandScale(self, bandNo: int) -> float:
        if self.hasFieldConverter():
            return self.fieldConverter().bandScale(bandNo)
        else:
            return 1

    def bandOffset(self, bandNo: int) -> float:
        if self.hasFieldConverter():
            return self.fieldConverter().bandOffset(bandNo)
        else:
            return 0

    def setActiveField(self, field: typing.Union[str, int, QgsField]):
        lastField: QgsField = self.activeField()

        activeField = qgsField(self.fields(), field)

        assert isinstance(activeField, QgsField), f'Field not found/supported: {field}'

        if activeField != self.mField or not \
                (isinstance(self.fieldConverter(), FieldToRasterValueConverter)
                 and self.fieldConverter().supportsField(activeField)):
            self.mFieldConverter = None
            for c in VectorLayerFieldRasterDataProvider.FIELD_CONVERTER:
                if c.supportsField(activeField):
                    self.mField = activeField
                    self.setFieldConverter(c(activeField))
                    break

        if not isinstance(self.fieldConverter(), FieldToRasterValueConverter):
            warnings.warn(f'Did not found converter for field "{field}"')
            self.mField = activeField
            self.mFieldConverter = FieldToRasterValueConverter(self.mField)

        if lastField != self.mField:
            self.fieldConverter().updateRasterData(self.activeFeatures())

        # set the extent Y offset
        if not self.mYOffsetManual:
            fields = self.fields()
            if fields.count() > 0:
                self.mYOffset = fields.lookupField(self.mField.name())

        self.mStatsCache.clear()

    def setExtentYOffset(self, offset: int):
        assert offset >= 0
        self.mYOffset = offset
        self.mYOffsetManual = True

    def activeField(self) -> QgsField:
        return self.mField

    def setActiveFeatures(self, features: typing.List[QgsFeature], field: QgsField = None):
        if not isinstance(features, list):
            features = list(features)
        assert isinstance(features, list)
        self.mFeatures.clear()
        self.mFeatures.extend(features)

        if isinstance(field, QgsField):
            self.setActiveField(field)

        if self.fieldConverter():
            self.fieldConverter().updateRasterData(self.activeFeatures())

        self.mStatsCache.clear()
        self.fullExtentCalculated.emit()
        self.dataChanged.emit()

    def activeFeatureIds(self) -> typing.List[int]:
        return [f.id() for f in self.mFeatures]

    def setFieldConverter(self, converter: FieldToRasterValueConverter):
        assert isinstance(self.activeField(), QgsField)
        assert isinstance(converter, FieldToRasterValueConverter)
        assert converter.supportsField(self.activeField())
        self.mFieldConverter = converter

    def fieldConverter(self) -> FieldToRasterValueConverter:
        return self.mFieldConverter

    def enableProviderResampling(self, enable: bool) -> bool:
        return True

    def extent(self) -> QgsRectangle:
        rect = QgsRectangle()
        rect.setXMinimum(0)
        rect.setYMinimum(self.mYOffset)
        rect.setXMaximum(self.xSize())
        rect.setYMaximum(self.mYOffset + self.ySize())
        return rect

    def sourceDataType(self, bandNo: int) -> Qgis.DataType:
        return self.dataType(bandNo)

    def sourceHasNoDataValue(self, bandNo):
        return True

    def sourceNoDataValue(self, bandNo):
        if self.hasFieldConverter():
            return self.fieldConverter().sourceNoDataValue(bandNo)
        else:
            return FieldToRasterValueConverter.NO_DATA_CANDIDATES[0]

    def dataType(self, bandNo: int) -> Qgis.DataType:

        if self.hasFieldConverter():
            return self.fieldConverter().dataType(bandNo)
        else:
            return Qgis.DataType.UnknownDataType

    def bandCount(self) -> int:
        if self.hasFieldConverter():
            return self.mFieldConverter.bandCount()
        else:
            return 0

    def xSize(self) -> int:
        return len(self.mFeatures)

    def ySize(self) -> int:
        if len(self.mFeatures) > 0:
            return 1
        else:
            return 0

    def capabilities(self):
        caps = QgsRasterInterface.Size | QgsRasterInterface.IdentifyValue | QgsRasterInterface.Identify
        # QgsRasterInterface.IdentifyHtml | QgsRasterInterface.IdentifyText
        return QgsRasterDataProvider.ProviderCapabilities(caps)

    def htmlMetadata(self) -> str:
        md = ' Dummy '
        md += self.fieldConverter().htmlMetadata()
        return md

    def name(self):
        return 'Name2'

    @classmethod
    def providerKey(cls) -> str:
        return 'vectorlayerfieldraster'

    @classmethod
    def description(self) -> str:
        return 'VectorLayerFieldRasterDataProvider'

    @classmethod
    def createProvider(cls, uri, providerOptions, flags=None):
        # compatibility with Qgis < 3.16, ReadFlags only available since 3.16
        flags = QgsDataProvider.ReadFlags()
        provider = VectorLayerFieldRasterDataProvider(uri, providerOptions, flags)
        return provider

    def colorInterpretation(self, bandNo: int) -> int:
        if self.hasFieldConverter():
            return self.fieldConverter().colorInterpretation(bandNo)
        else:
            return QgsRaster.GrayIndex

    def colorTable(self, bandNo: int) -> typing.List[QgsColorRampShader.ColorRampItem]:
        return self.fieldConverter().colorTable(bandNo)

    def clone(self) -> 'VectorLayerFieldRasterDataProvider':
        dp = VectorLayerFieldRasterDataProvider(None)
        dp.setDataSourceUri(self.dataSourceUri(expandAuthConfig=True))
        # share vector layer cache

        dp.setActiveFeatures(self.activeFeatures())
        dp.setActiveField(self.activeField())
        dp.setParent(VectorLayerFieldRasterDataProvider.PARENT)
        # print(f'#CLONE  {self.extent()}  ->  {dp.extent()}')
        # self._refs_.append(dp)
        return dp

    def crs(self) -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem()

    def isValid(self) -> bool:
        return True
        return isinstance(self.mVectorLayerCache, QgsVectorLayerCache) and \
               isinstance(self.mFieldConverter, FieldToRasterValueConverter)

    def identify(self, point: QgsPointXY, format: QgsRaster.IdentifyFormat,
                 boundingBox: QgsRectangle = ..., width: int = ..., height: int = ...,
                 dpi: int = ...) -> QgsRasterIdentifyResult:

        results = dict()

        x = int(point.x())
        array = self.fieldConverter().rasterDataArray()

        r = None
        if format == QgsRaster.IdentifyFormatValue:

            if 0 <= x < array.shape[-1]:
                for b in range(self.bandCount()):
                    results[b + 1] = float(array[b, 0, x])
        elif format in [QgsRaster.IdentifyFormatHtml, QgsRaster.IdentifyFormatText]:
            results[0] = 'Dummy HTML / Text'

        info = f'# identify results ({len(results)}):'
        for k, v in results.items():
            info += f'\n\t {k}:{v}'
        print(info)
        r = QgsRasterIdentifyResult(format, results)
        return r


class SpectralLibraryRasterDataProvider(QgsRasterDataProvider):
    """
    An
    """

    def __init__(self, *args, speclib=None, fids: typing.List[int] = None, **kwds):

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
        band_data: np.ndarray = self.profileArray()[bandNo - 1, :]

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
        band_data: np.ndarray = self.profileArray()[bandNo - 1, :]

        stats.sum = band_data.sum()
        stats.minimumValue = band_data.min()
        stats.maximumValue = band_data.max()
        stats.mean = band_data.mean()
        stats.extent = extent
        return stats

    def generateBandName(self, band_no: int):
        setting = self.profileSetting()

        if isinstance(setting, SpectralSetting) and band_no > 0 and band_no <= setting.n_bands():
            wl = setting.x()[band_no - 1]
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

    metadata = QgsProviderMetadata(
        VectorLayerFieldRasterDataProvider.providerKey(),
        VectorLayerFieldRasterDataProvider.description(),
        VectorLayerFieldRasterDataProvider.createProvider
    )
    registry.registerProvider(metadata)
    QgsMessageLog.logMessage('VectorLayerRasterDataProvider registered')
