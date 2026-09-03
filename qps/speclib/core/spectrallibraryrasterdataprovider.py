import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable, Set
from urllib.parse import urlencode

import numpy as np
from qgis.PyQt.QtCore import NULL, QByteArray, QDateTime, QObject, QUrl, QUrlQuery, QMetaType
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsDataProvider, QgsFeature, \
    QgsFeatureRequest, QgsField, QgsFields, QgsPointXY, QgsProject, \
    QgsRaster, QgsRasterBandStats, QgsRasterBlock, QgsRasterBlockFeedback, \
    QgsRasterDataProvider, QgsRasterIdentifyResult, QgsRasterLayer, QgsRectangle, QgsVectorLayer, \
    QgsProviderMetadata, QgsProviderRegistry, QgsMessageLog

from .spectralprofile import groupBySpectralProperties, spectralSettingsDict
from ..core import is_profile_field, profile_fields
from ..core.spectralprofile import decodeProfileValueDict  # , groupBySpectralProperties_depr, SpectralSetting
from ...utils import HashableRectangle, nextColor, numpyToQgisDataType, qgsField, QGIS2NUMPY_DATA_TYPES

_DEF_CRS = None


def defaultCrs() -> QgsCoordinateReferenceSystem:
    global _DEF_CRS
    if _DEF_CRS is None:
        _DEF_CRS = QgsCoordinateReferenceSystem('EPSG:32631')
    return _DEF_CRS


def create_uri(vl: QgsVectorLayer, field: QgsField) -> str:
    params = {'lid': vl.id(), 'field': field.name(), 'src': vl.source()}
    uri = 'vectorlayerfieldraster://?' + urlencode(params)
    return uri


def createRasterLayers(
    vl: QgsVectorLayer,
    selected_only: bool = False,
    fields=None
) -> List[QgsRasterLayer]:
def createRasterLayers(
    features: Union[QgsVectorLayer, List[QgsFeature]],
    fields: Union[str, List[str], List[QgsField], QgsField, QgsFields] = None
) -> List[QgsRasterLayer]:
    """
    Returns a list of in-memory QgsRasterLayers that represent the values inside a QgsVectorLayer.
    :param features:
    :param fields:
    :return:
    """
    request = QgsFeatureRequest()
    request.setSubsetOfAttributes([])
    if not selected_only:
        features = list(vl.getFeatures())
    else:
        features = list(vl.getSelectedFeatures())

    layers = []
    if len(features) == 0:
        return layers

    all_fields = features[0].fields()
    all_field_names = all_fields.names()
    if fields is None:
        requested_field_names = all_field_names
    elif isinstance(fields, str):
        requested_field_names = [fields]
    elif isinstance(fields, QgsFields):
        requested_field_names = fields.names()
    elif isinstance(fields, QgsField):
        requested_field_names = [fields.name()]
    elif isinstance(fields, Iterable):
        requested_field_names = [f.name() if isinstance(f, QgsField) else str(f) for f in fields]
    else:
        raise ValueError(f'fields: "{fields}" is not supported')

    for f in requested_field_names:
        if f not in all_field_names:
            raise AssertionError(f'"{f}" is not a valid field name')

    for field_name in requested_field_names:
        field = all_fields[field_name]

        if is_profile_field(field):
            GROUPS = groupBySpectralProperties(features, field=field)

            for setting_json, profile_features in GROUPS.items():
                settings = json.loads(setting_json)
                nb = settings['band_count']
                xUnit = settings.get('xUnit', '')

                name = f'{nb} bands'
                if xUnit:
                    name += f', {xUnit}'
                name = f'{field.name()} ({name})'

                uri = create_uri(vl, field)
                layer = QgsRasterLayer('?', name, VectorLayerFieldRasterDataProvider.providerKey())
                dp: VectorLayerFieldRasterDataProvider = layer.dataProvider()
                dp.setActiveFeatures(profile_features, field=field.name())
                if not (layer.isValid()):
                    raise AssertionError(f'Layer invalid: {layer}\n{layer.error().message()}')

                layers.append(layer)
        else:
            name = f'{field.name()} ({field.typeName()})'
            uri = create_uri(vl, field)
            layer = QgsRasterLayer(uri, name, VectorLayerFieldRasterDataProvider.providerKey())
            dp: VectorLayerFieldRasterDataProvider = layer.dataProvider()
            dp.setActiveFeatures(features, field=field.name())
            layers.append(layer)

    return layers


def nn_resample(img, shape):
    def per_axis(in_sz, out_sz):
        ratio = 0.5 * in_sz / out_sz
        return np.round(np.linspace(ratio - 0.5, in_sz - ratio - 0.5, num=out_sz)).astype(int)

    return img[per_axis(img.shape[0], shape[0])[:, None], per_axis(img.shape[1], shape[1])]


def natural_sort_key(s):
    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    return [convert(c) for c in re.split(r'(\d+)', str(s) if s is not None else '')]


def featuresToArrays(speclib: QgsVectorLayer,
                     fields=None,
                     fids: List[int] = None,
                     bbl: bool = False,
                     fwhm: bool = False,
                     ) -> Dict[str, Dict[str, np.ndarray]]:
    """
    Reads spectral profiles from a vector layer and returns them as
    3D raster arrays, grouped by similar spectral and field properties

    :param speclib: QgsVectorLayer with one or more spectral profile fields
    :param fids: the feature ids to get data from. If None (default), all features are used.
    :param fwhm: False, set True differentiate returned data by FWHM too
    :param bbl: False, set True differentiate returned data by BBL too
    :return: dict with a string keys containing all metadata, and a numpy array containing the profile data
    """
    if not (isinstance(speclib, QgsVectorLayer)):
        raise AssertionError

    if fields is None:
        fields = profile_fields(speclib)
    elif isinstance(fields, (QgsFeature, QgsVectorLayer, QgsFields)):
        fields = profile_fields(fields)
    elif isinstance(fields, int):
        fields = [speclib.fields().at(fields)]
    elif not isinstance(fields, list):
        fields = fields
    else:
        raise NotImplementedError()

    _fields = []
    for f in fields:
        fld = None
        if isinstance(f, int):
            fld = speclib.fields().at(f)
        elif isinstance(f, str):
            fld = speclib.fields().byName(f)
        elif isinstance(f, QgsField):
            fld = speclib.fields().field(f.name())

        if is_profile_field(fld):
            _fields.append(fld)

    field2idx = {f.name(): speclib.fields().indexOf(f.name()) for f in _fields}

    request = QgsFeatureRequest()
    if fids:
        request.setFilterFids(fids)

    PROFILE_DATA = {}

    for feature in speclib.getFeatures(request):
        feature: QgsFeature
        fid = feature.id()
        for field_name, idx in field2idx.items():
            data = decodeProfileValueDict(feature.attribute(idx))
            if data != {}:
                y = data['y']
                key = spectralSettingsDict(data)
                key['field_name'] = field_name
                key = json.dumps(key, ensure_ascii=False)
                pdata = PROFILE_DATA.get(key, {'profiles': [], 'fids': []})
                pdata['profiles'].append(y)
                pdata['fids'].append(fid)
                PROFILE_DATA[key] = pdata
    for k, data in PROFILE_DATA.items():
        # convert profiles and fids to numpy arrays
        s = json.loads(k)
        nb = s['band_count']
        nl = 1
        ns = len(data['profiles'])
        array = np.asarray(data['profiles'])
        array = array.T.reshape(nb, nl, ns)
        data['profiles'] = array
        data['fids'] = np.asarray(data['fids'])

    return PROFILE_DATA


# class SpectralLibraryRasterLayerModel(QgsMapLayerModel):
#
#     def __init__(self, *args, **kwds):
#         super().__init__(*args, **kwds)
#
#     def data(self, index: QModelIndex, role: int = ...) -> Any:
#         if not index.isValid():
#             return None
#
#         if role != Qt.ItemDataRole.DecorationRole:
#             return super().data(index, role)
#
#         isEmpty = index.row() == 0 and self.allowEmptyLayer()
#         additionalIndex = index.row() - (1 if self.allowEmptyLayer() else 0) - self.rowCount()
#
#         if isEmpty or additionalIndex >= 0:
#             return None
#
#         layer = self.layerFromIndex(index.row() - (1 if self.allowEmptyLayer() else 0))
#         if isinstance(layer, QgsRasterLayer) and isinstance(layer.dataProvider(), SpectralLibraryRasterDataProvider):
#             return QIcon(r':/qps/ui/icons/profile.svg')
#         else:
#             return super().data(index, role)

#
# class FieldToRasterValueConverter(QObject):
#     """
#     This class converts QgsFeature values of a field from / to 3D-array raster layer values
#     """
#     LUT_FIELD_TYPES = {
#         QMetaType.Type.Bool: Qgis.DataType.Byte,
#         QMetaType.Type.Int: Qgis.DataType.Int32,
#         QMetaType.Type.UInt: Qgis.DataType.UInt32,
#         QMetaType.Type.LongLong: Qgis.DataType.Int32,
#         QMetaType.Type.ULong: Qgis.DataType.UInt32,
#         QMetaType.Type.Double: Qgis.DataType.Float32,
#         QMetaType.Type.QString: Qgis.DataType.Int32,
#         QMetaType.Type.QDateTime: Qgis.DataType.Int32,
#         QMetaType.Type.QDate: Qgis.DataType.Int32,
#         QMetaType.Type.QTime: Qgis.DataType.Int32,
#     }
#
#     NO_DATA_CANDIDATES = [-1, -9999]
#
#     dataChanged = pyqtSignal()
#
#     @classmethod
#     def supportsField(cls, field: QgsField) -> bool:
#         return field.type() in FieldToRasterValueConverter.LUT_FIELD_TYPES.keys()
#
#     def __init__(self):
#         super().__init__(None)
#
#         self.mField: QgsField = None
#         # there need to be a numeric no-data value
#         self.mNoData = -1
#         self.mColorTable = list()
#         self.mRasterData: Optional[np.ndarray] = None
#         self.mFeatureIndices: List[int] = []
#
#     def isValid(self) -> bool:
#         return isinstance(self.mRasterData, np.ndarray)
#
#     def spectralSetting(self) -> dict:
#         """
#         Returns a dict that describes the wavelength information related to the raster data
#         """
#         s = {'band_count': self.bandCount(),
#              'xUnit': BAND_INDEX,
#              'field_name': self.field().name()}
#         return s
#         # return SpectralSetting(list(range(self.bandCount())), xUnit=BAND_INDEX, field_name=self.field().name())
#
#     def updateRasterData(self, features: List[QgsFeature]):
#
#         self.mRasterData = None
#         fieldValues = [f.attribute(self.mField.name()) for f in features]
#         self.mFeatureIndices.clear()
#         self.mFeatureIndices.extend([f.id() for f in features])
#         self.mRasterData, self.mColorTable, self.mNoData = self.toRasterValues(fieldValues)
#
#         self.dataChanged.emit()
#
#     def colorInterpretationName(self, bandNo: int):
#         if Qgis.versionInt() >= 32900:
#             return Qgis.RasterColorInterpretation.Undefined
#         else:
#             return QgsRaster.ColorInterpretation.UndefinedColorInterpretation
#
#     def htmlMetadata(self) -> str:
#         return f'Field: {self.field().name()} Type: {self.field().typeName()}'
#
#     def isClassification(self) -> bool:
#
#         if isinstance(self.mField, QgsField):
#             return self.mField.type() == QMetaType.Type.QString and not is_profile_field(self.mField)
#         else:
#             return False
#
#     def colorInterpretation(self, bandNo: int) -> int:
#
#         if self.isClassification():
#             return QgsRaster.DrawingStyle.PalettedColor
#         else:
#             return QgsRaster.ColorInterpretation.GrayIndex
#
#     def colorTable(self, bandNo: int) -> List[QgsColorRampShader.ColorRampItem]:
#         return self.mColorTable[:]
#
#     def field(self) -> QgsField:
#         return self.mField
#
#     def rasterDataArray(self) -> np.ndarray:
#         return self.mRasterData
#
#     def bandCount(self) -> int:
#         """
#         One field, one raster band
#         :return:
#         :rtype:
#         """
#         if isinstance(self.mRasterData, np.ndarray):
#             return self.mRasterData.shape[0]
#         else:
#             return 0
#
#     def width(self):
#         if isinstance(self.mRasterData, np.ndarray):
#             return self.mRasterData.shape[2]
#         else:
#             return 0
#
#     def height(self):
#         if isinstance(self.mRasterData, np.ndarray):
#             return self.mRasterData.shape[1]
#         else:
#             return 0
#
#     def bandScale(self, bandNo: int) -> float:
#         return 1
#
#     def bandOffset(self, bandNo: int) -> float:
#         return 0
#
#     def sourceNoDataValue(self, band: int):
#         return self.mNoData
#
#     def rasterDataTypeSize(self, band: int):
#         pass
#
#     def generateBandName(self, band: int):
#         digits = int(math.log10(self.bandCount())) + 1
#         return '{} Band {}'.format(self.field().name(), str(band).zfill(digits))
#
#     def dataType(
#         self, band: int
#     ) -> Qgis.DataType:
#         return FieldToRasterValueConverter.LUT_FIELD_TYPES.get(
#             self.mField.type(), Qgis.DataType.UnknownDataType
#         )
#
#     def toRasterValues(
#         self, fieldValues: List
#     ) -> Tuple[np.ndarray, List[QgsColorRampShader.ColorRampItem], Any]:
#         """
#         Converts a list of field values to a list of raster values
#         :param fieldValues:
#         :return:
#         """
#
#         field = self.mField
#         ns = len(fieldValues)
#         colorTable: List[QgsColorRampShader.ColorRampItem] = []
#
#         noData = None
#         numericValues = None
#
#         if field.type() == QMetaType.Type.QString:
#             # convert text values to raster class values
#             noData = 0
#             uniqueValues = set(fieldValues)
#             uniqueValues = sorted(uniqueValues, key=lambda v: (v not in [None, NULL],
#                                                                natural_sort_key(v) if v not in [None, NULL] else ''))
#
#             LUT = {None: noData,
#                    NULL: noData
#                    }
#             color = QColor('black')
#             colorTable.append(QgsColorRampShader.ColorRampItem(float(noData), color, 'no data'))
#             for v in uniqueValues:
#                 if v not in LUT.keys():
#                     LUT[v] = len(LUT) - 1
#                     color = nextColor(color, mode='cat')
#                     colorTable.append(QgsColorRampShader.ColorRampItem(
#                         float(LUT[v]), color, str(v)))
#
#             numericValues = [LUT[v] for v in fieldValues]
#
#         elif field.type() in [QMetaType.Type.Bool,
#                               QMetaType.Type.Int, QMetaType.Type.UInt,
#                               QMetaType.Type.LongLong, QMetaType.Type.ULongLong,
#                               QMetaType.Type.Double, QMetaType.Type.Double]:
#             # convert int/bool/floats to 1-D raster class valuess
#             for c in self.NO_DATA_CANDIDATES:
#                 if c not in fieldValues:
#                     noData = c
#                     break
#
#             if noData is None:
#                 noData = min(fieldValues) - 1
#                 while noData in fieldValues:
#                     noData -= 1
#
#             numericValues = []
#             for v in fieldValues:
#                 if v in [None, NULL]:
#                     numericValues.append(noData)
#                 else:
#                     numericValues.append(v)
#         elif field.type() == QMetaType.Type.QDateTime:
#             # convert datetime values to raster class values
#             numericValues = []
#             noData = -9999
#             for v in fieldValues:
#                 if isinstance(v, QDateTime):
#                     numericValues.append(v.toSecsSinceEpoch())
#                 else:
#                     numericValues.append(noData)
#
#         if noData is not None and numericValues is not None:
#             array = np.asarray(numericValues)
#             array = array.reshape((1, 1, ns))
#         else:
#             # fallback: empty image
#             noData = -9999
#             array = noData * np.ones((1, 1, ns))
#
#         if not (array.ndim == 3):
#             raise AssertionError
#         return array, colorTable, noData
#
#     @classmethod
#     def toFieldValues(cls, field: QgsField, rasterValues: np.ndarray) -> List:
#         raise NotImplementedError

#
# class SpectralProfileValueConverter(FieldToRasterValueConverter):
#
#     @classmethod
#     def supportsField(cls, field: QgsField) -> bool:
#         return is_profile_field(field)
#
#     def __init__(self, field: QgsField):
#         if not (is_profile_field(field)):
#             raise AssertionError
#         super(SpectralProfileValueConverter, self).__init__(field)
#         self.mSpectralSetting: dict = dict()
#
#     def colorInterpretation(self, bandNo: int) -> int:
#         if Qgis.versionInt() >= 32900:
#             return Qgis.RasterColorInterpretation.GrayIndex
#         else:
#             return QgsRaster.DrawingStyle.MultiBandColor
#
#     def _profileToSpectralSetting(self, profile: dict) -> dict:
#         """
#
#         :param profile:
#         :return:
#         """
#         s = dict()
#         for k in ['x', 'xUnit', 'fwhm', 'bbl']:
#             if k in profile:
#                 s[k] = profile[k]
#         return s
#
#     def spectralSetting(self) -> dict:
#         return self.mSpectralSetting
#
#     def bandCount(self) -> int:
#         return self.mSpectralSetting.get('band_count', 1)
#
#     def dataType(self, band: int) -> Qgis.DataType:
#         if isinstance(self.mRasterData, np.ndarray):
#             dt = numpyToQgisDataType(self.mRasterData.dtype)
#             # if dt == Qgis.DataType.Float64:
#             #    dt = Qgis.DataType.Float32
#             return dt
#         else:
#             return Qgis.DataType.UnknownDataType
#
#     def toRasterValues(self, fieldValues: List) -> Tuple[np.ndarray, List[QgsColorRampShader.ColorRampItem], Any]:
#
#         # get spectral setting
#         self.mSpectralSetting.clear()
#
#         ns = len(fieldValues)
#         nb = 0
#         profileData: List = []
#         profileIndices: List[int] = []
#
#         for i, v in enumerate(fieldValues):
#             if isinstance(v, (QByteArray, str, dict)):
#
#                 try:
#                     d = decodeProfileValueDict(v)
#                     s = spectralSettingsDict(d)
#                     s['field_name'] = self.field().name()
#                 except Exception:
#                     s = None
#
#                 if isinstance(s, dict):
#                     self.mSpectralSetting.update(s)
#                     nb = s['band_count']
#                     if s == self.mSpectralSetting:
#                         profileData.append(d['y'])
#                         profileIndices.append(i)
#
#         profileIndices = np.asarray(profileIndices)
#
#         profileData = np.asarray(profileData).transpose().reshape(nb, 1, len(profileIndices))
#
#         uniqueValues = np.unique(profileData)
#
#         noData = None
#         no_data_candidates = self.NO_DATA_CANDIDATES[:]
#         if len(profileData) > 0:
#             no_data_candidates.append(profileData.min() - 1)
#         for c in no_data_candidates:
#             if c not in uniqueValues:
#                 noData = c
#                 break
#
#         if profileData.dtype == np.int64:
#             profileData = profileData.astype(np.int32)
#
#         rasterData = np.ones((nb, 1, ns), dtype=profileData.dtype) * noData
#         if len(profileIndices) > 0:
#             rasterData[:, :, profileIndices] = profileData
#         return rasterData, [], noData


class VectorLayerFieldRasterDataProvider(QgsRasterDataProvider):
    """
    A QgsRasterDataProvider to access the field values in a QgsVectorLayer like a raster layer
    """
    PARENT = QObject()

    def __init__(
        self,
        uri: str,
        providerOptions: QgsDataProvider.ProviderOptions = QgsDataProvider.ProviderOptions(),
        flags: Union[QgsDataProvider.ReadFlags, QgsDataProvider.ReadFlag] = QgsDataProvider.ReadFlags(),
    ):

        super().__init__(uri, providerOptions=providerOptions, flags=flags)
        self.mProviderOptions = providerOptions
        self.mFlags = flags
        self.mField: Optional[QgsField] = None
        # self.mFieldConverter: FieldToRasterValueConverter = FieldToRasterValueConverter()
        self.mFeatures: List[QgsFeature] = []
        self.mFeatureSourceID: str = ''
        self.mStatsCache = dict()
        self.mYOffset: int = 0
        self.mYOffsetManual: bool = False

        self.mNoDataValue = -1
        self.mColorTable = list()
        self.mRasterData: Optional[np.ndarray] = None
        self.mRasterMetadata = dict()
        self.mRasterDataQgisType: Qgis.DataType = Qgis.DataType.UnknownDataType

        if uri:
            self._init_from_uri(uri)

    def featureSourceId(self) -> str:
        return self.mFeatureSourceID

    def source(self) -> str:
        source = super().source()
        return source

    def dataSourceUri(self, *args, **kwargs) -> str:
        source = super().dataSourceUri(*args, **kwargs)
        return source

    def activeFeatures(self) -> List[QgsFeature]:
        return self.mFeatures

    def activeFeatureIDs(self) -> List[int]:
        return [feature.id() for feature in self.mFeatures]

    def _init_from_uri(self, uri: str) -> None:

        url: QUrl = QUrl(uri)
        query: QUrlQuery = QUrlQuery(url)

        layerID: Optional[str] = None
        layerSrc: Optional[str] = None

        field = None
        vl = None
        # cacheSize: int = 2048

        if query.hasQueryItem('lid'):
            layerID = query.queryItemValue('lid')
        elif query.hasQueryItem('layerid'):
            layerID = query.queryItemValue('layerid')
        if layerID:
            layerID = re.sub(r'[{}]', '', layerID)
            vl = QgsProject.instance().mapLayer(layerID)
        elif layerSrc:
            vl = QgsVectorLayer(layerSrc)

        if query.hasQueryItem('field'):
            field = query.queryItemValue('field')
        elif self.fields().count() > 0:
            field = self.fields()[0].name()

        if isinstance(vl, QgsVectorLayer) and field and field in vl.fields().names():
            self._init_from_vector_layer(vl, field)

    def _init_from_vector_layer(self, vl: QgsVectorLayer, field: str):
        self.mFeatureSourceID = vl.id()
        self.setActiveFeatures(vl.getFeatures(), field)

    def fields(self) -> QgsFields:
        if len(self.mFeatures) > 0:
            return self.mFeatures[0].fields()
        else:
            return QgsFields()

    def generateBandName(self, bandNumber: int) -> str:
        #         digits = int(math.log10(self.bandCount())) + 1
        #         return '{} Band {}'.format(self.field().name(), str(band).zfill(digits))

        #         if isinstance(setting, SpectralSetting) and band_no > 0 and band_no <= setting.n_bands():
        #             wl = setting.x()[band_no - 1]
        #             wlu = setting.xUnit()
        #             return f'Band {band_no} {wl} {wlu}'

        digits = int(math.log10(self.bandCount())) + 1
        bn = str(bandNumber).zfill(digits)

        info = f'{self.activeField()} Band {bn}'
        if yValues := self.mRasterMetadata.get('y', None):
            if 0 < bandNumber <= len(yValues):
                info += f' {yValues[bandNumber - 1]}'
        return info

    def block(self,
              bandNo: int,
              boundingBox: QgsRectangle,
              width: int,
              height: int,
              feedback: Optional[QgsRasterBlockFeedback] = None) -> QgsRasterBlock:

        # print(f'# block: {bandNo}: {boundingBox} : {width} : {height}', flush=True)

        dt = self.dataType(bandNo)
        target_type = QGIS2NUMPY_DATA_TYPES[dt]
        block = QgsRasterBlock(dt, width, height)

        mExtent = self.extent()
        if not mExtent.intersects(boundingBox):
            block.setIsNoData()
            return block

        if not mExtent.contains(boundingBox):
            subRect = QgsRasterBlock.subRect(boundingBox, width, height, mExtent)
            block.setIsNoDataExcept(subRect)

        # self._readBlock(bandNo, boundingBox, width, height, block, feedback)

        fullExtent = self.extent()
        intersectExtent = boundingBox.intersect(fullExtent)
        if intersectExtent.isEmpty():
            # print('# draw request outside view extent', flush=True)
            block.setIsNoData()
            return block

        if isinstance(self.mRasterData, np.ndarray) and 0 < bandNo <= self.mRasterData.shape[0]:
            x0, x1 = round(intersectExtent.xMinimum()), round(intersectExtent.xMaximum())
            band_slice = self.mRasterData[bandNo - 1, 0:1, int(x0):int(x1)]
            band_data = nn_resample(band_slice, (height, width))
            band_data = band_data.astype(target_type)
            block.setData(band_data.tobytes())

            # if not block.value(0, 0) == band_data[0, 0]:
            #     raise ValueError('Block value does not match band data')

        return block

    def fieldValues(self) -> list:
        return [f.attribute(self.activeField()) for f in self.activeFeatures()]

    def spectralSetting(self) -> dict:
        warnings.warn(DeprecationWarning('spectralSetting() is deprecated, use rasterMetaData() instead'))
        return self.rasterMetaData()

    def rasterMetaData(self) -> Dict[str, Any]:
        """Contains additional information which is not covered by standard QgsRasterDataProvider attributes"""
        return self.mRasterMetadata

    def hasStatistics(
        self,
        bandNo: int,
        stats: int = ...,
        extent: QgsRectangle = ...,
        sampleSize: int = ...,
        feedback: Optional['QgsRasterBlockFeedback'] = ...
    ) -> bool:
        return True
        # statsKey = self._statsKey(bandNo, stats, extent, sampleSize)
        # return statsKey in self.mStatsCache.keys()

    def _statsKey(self, bandNo, stats, extent, sampleSize):
        return (bandNo, stats, HashableRectangle(extent))

    def bandStatistics(
        self,
        bandNo: int,
        stats: Qgis.RasterBandStatistic,
        extent: Optional[QgsRectangle] = None,
        sampleSize: int = 0,
        feedback: Optional[QgsRasterBlockFeedback] = None
    ) -> QgsRasterBandStats:

        if extent is None:
            extent = QgsRectangle()
        else:
            extent = QgsRectangle(extent)

        statsKey = self._statsKey(bandNo, stats, extent, sampleSize)
        if statsKey in self.mStatsCache.keys():
            return self.mStatsCache[statsKey]

        results = QgsRasterBandStats()
        if isinstance(self.mRasterData, np.ndarray) and 0 <= bandNo < self.mRasterData.shape[0]:
            band_data: np.ndarray = self.mRasterData[bandNo - 1, :, :]
            nl, ns = band_data.shape
            if nl > 0 and ns > 0:
                results.sum = np.nansum(band_data)
                results.minimumValue = np.nanmin(band_data)
                results.maximumValue = np.nanmax(band_data)
                results.mean = np.nanmean(band_data)
            results.extent = extent
            results.elementCount = nl * ns
            results.height = band_data.shape[-2]
            results.width = band_data.shape[-1]

            RC = Qgis.RasterBandStatistic
            statsGathered = (
                RC.Sum | RC.Mean | RC.Min | RC.Max  # noqa: W503
            )

            results.statsGathered = Qgis.RasterBandStatistics(statsGathered)

            self.mStatsCache[statsKey] = results
        return results

    def bandScale(self, bandNo: int) -> float:
        return 1

    def bandOffset(self, bandNo: int) -> float:
        return 0

    def setExtentYOffset(self, offset: int):
        if not (offset >= 0):
            raise AssertionError
        self.mYOffset = offset
        self.mYOffsetManual = True

    def activeField(self) -> str:
        if self.mField:
            return self.mField.name()
        else:
            return ''

    def setActiveFeatures(
        self,
        features: Iterable[QgsFeature],
        field: str
    ):
        self.mRasterMetadata.clear()
        self.mRasterData = None
        self.mStatsCache.clear()
        self.mField = None
        self.mFeatures.clear()

        if not isinstance(features, list):
            features = list(features)

        if len(features) == 0:
            return

        fields = features[0].fields()
        activeField = qgsField(fields, field)
        if not (isinstance(activeField, QgsField)):
            raise AssertionError(f'Field not found/supported: {field}')

        self.mField = activeField

        # set the extent Y offset
        if not self.mYOffsetManual:
            if fields.count() > 0:
                self.mYOffset = fields.lookupField(activeField.name())

        # convert feature data into fast-accessible numpy data
        if not isinstance(features, list):
            features = list(features)
        if not (isinstance(features, list)):
            raise AssertionError

        self.mFeatures.extend(features)

        fieldValues = [f.attribute(self.mField.name()) for f in features]

        self._read_raster_values(fieldValues, activeField)

        self.fullExtentCalculated.emit()
        self.dataChanged.emit()

    def _read_raster_values(
        self,
        field_values: List[Any],
        field: QgsField
    ) -> Tuple[np.ndarray, list, float, dict]:
        """
        Converts the field values into values that can be exposed as raster data.
        :param field_values:
        :param field:
        :return:
        """
        ns = len(field_values)

        raster_data = None
        raster_nodata = -9999
        raster_metadata = dict()
        raster_color_table: List[QgsColorRampShader.ColorRampItem] = []

        if is_profile_field(field):
            profile_data = []
            spectral_settings = None
            for v in field_values:
                if isinstance(v, (QByteArray, str, dict)):
                    try:
                        d = decodeProfileValueDict(v)
                        if spectral_settings is None:
                            spectral_settings = spectralSettingsDict(d)
                        profile_data.append(d)
                    except Exception:
                        profile_data.append({})

            if spectral_settings is None:
                nb = 0

            else:
                nb = spectral_settings.get("band_count", 0)
                raster_metadata.update(spectral_settings)

            profile_data = [p.get('y', []) for p in profile_data]
            profile_data = [p if len(p) == nb else None for p in profile_data]

            is_data = []

            valid_values = []
            for i, d in enumerate(profile_data):
                if d:
                    is_data.append(i)
                    valid_values.append(d)

            is_data = np.asarray(is_data)

            valid_values = np.asarray(valid_values).transpose().reshape(nb, 1, len(valid_values))
            class_names = np.unique(valid_values)
            no_data_candidates = [-1, -9999] + [valid_values.min() - 1]
            for c in no_data_candidates:
                if c not in class_names:
                    raster_nodata = c
                    break

            raster_data = np.ones((nb, 1, ns), dtype=valid_values.dtype) * raster_nodata
            raster_data[:, :, is_data] = valid_values

            if not raster_data.shape == (nb, 1, ns):
                raise ValueError(
                    f"Unexpected raster data shape: {raster_data.shape} instead of {(nb, 1, ns)}"
                )

        else:
            nb = 1
            raster_nodata = None
            numeric_values = []

            # string type? convert to categorical raster data
            if field.type() == QMetaType.Type.QString:
                raster_nodata = 0
                class_names: Set[str] = set(field_values)
                class_names = sorted(
                    class_names,
                    key=lambda v: (
                        v not in [None, NULL],
                        natural_sort_key(v)
                        if v not in [None, NULL] else ''
                    )
                )

                LUT = {None: raster_nodata,
                       NULL: raster_nodata
                       }

                # add a color for each class
                color = QColor('black')
                raster_color_table.append(QgsColorRampShader.ColorRampItem(float(raster_nodata), color, 'no data'))
                for v in class_names:
                    if v not in LUT.keys():
                        LUT[v] = len(LUT) - 1
                        color = nextColor(color, mode='cat')
                        raster_color_table.append(QgsColorRampShader.ColorRampItem(
                            float(LUT[v]), color, str(v)))

                numeric_values = [LUT[v] for v in field_values]

            elif field.type() in [
                QMetaType.Type.Bool,
                QMetaType.Type.Int, QMetaType.Type.UInt,
                QMetaType.Type.LongLong, QMetaType.Type.ULongLong,
                QMetaType.Type.Double, QMetaType.Type.Double
            ]:
                # convert int/bool/floats to 1-D raster class valuess

                candidates = [0, -1, -9999]

                for c in candidates:
                    if c not in field_values:
                        raster_nodata = c
                        break
                if raster_nodata is None:
                    raster_nodata = min([v for v in field_values if v is not None]) - 1

                for v in field_values:
                    if v in [None, NULL]:
                        numeric_values.append(raster_nodata)
                    else:
                        numeric_values.append(v)

            elif field.type() == QMetaType.Type.QDateTime:
                # convert datetime values to raster class values
                raster_nodata = -9999
                for v in field_values:
                    if isinstance(v, QDateTime):
                        numeric_values.append(v.toSecsSinceEpoch())
                    else:
                        numeric_values.append(raster_nodata)

            if raster_nodata is not None and numeric_values is not None:
                raster_data = np.asarray(numeric_values).reshape((1, 1, ns))
            else:
                # fallback: empty image
                raster_nodata = -9999
                raster_data = raster_nodata * np.ones((1, 1, ns))

        if raster_data.shape != (nb, 1, ns):
            raise AssertionError

        raster_metadata['band_count'] = nb
        self.mRasterData = raster_data
        self.mColorTable = raster_color_table
        self.mNoData = raster_nodata
        self.mRasterMetadata = raster_metadata

    def activeFeatureIds(self) -> List[int]:
        return [f.id() for f in self.mFeatures]

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
        return self.mNoDataValue

    def dataType(self, bandNo: int) -> Qgis.DataType:
        if isinstance(self.mRasterData, np.ndarray):
            return numpyToQgisDataType(self.mRasterData.dtype)
        else:
            return Qgis.DataType.UnknownDataType

    def bandCount(self) -> int:
        if isinstance(self.mRasterData, np.ndarray):
            return self.mRasterData.shape[0]
        else:
            return 0

    def xSize(self) -> int:
        if isinstance(self.mRasterData, np.ndarray):
            return self.mRasterData.shape[2]
        else:
            return 0

    def ySize(self) -> int:
        if isinstance(self.mRasterData, np.ndarray):
            return self.mRasterData.shape[1]
        else:
            return 0

    def capabilities(self):

        # scap = super().capabilities()

        RC = Qgis.RasterInterfaceCapability

        caps = (
            RC.Size | RC.IdentifyValue | RC.Identify  # noqa: W503
        )
        return Qgis.RasterInterfaceCapabilities(caps)

    def htmlMetadata(self) -> str:
        md = ' Dummy '
        md += self.fieldConverter().htmlMetadata()
        return md

    def crs(self) -> QgsCoordinateReferenceSystem:
        return defaultCrs()

    def name(self):
        return self.__class__.__name__

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
        return Qgis.RasterColorInterpretation.Undefined

    def colorTable(self, bandNo: int) -> List[QgsColorRampShader.ColorRampItem]:
        return self.mColorTable[:]

    def clone(self) -> 'VectorLayerFieldRasterDataProvider':
        dp = VectorLayerFieldRasterDataProvider(None)
        dp.setDataSourceUri(self.dataSourceUri(expandAuthConfig=True))
        # share vector layer cache
        dp.mFeatureSourceID = self.mFeatureSourceID
        dp.setActiveFeatures(self.activeFeatures(), self.activeField())
        # dp.setActiveField(self.activeField())
        dp.setParent(VectorLayerFieldRasterDataProvider.PARENT)

        features = [QgsFeature(f) for f in self.activeFeatures()]
        field = QgsField(self.activeField())
        dp.setActiveFeatures(features)
        dp.setActiveField(field)
        # dp.setParent(VectorLayerFieldRasterDataProvider.PARENT)
        dp.setParent(self.parent())
        # print(f'#CLONE  {self.extent()}  ->  {dp.extent()}')
        # self._refs_.append(dp)

        return dp

    def isValid(self) -> bool:
        # return isinstance(self.mRasterData, np.ndarray)
        return True

    def identify(
        self,
        point: QgsPointXY,
        format: QgsRaster.IdentifyFormat,
        boundingBox: QgsRectangle = ...,
        width: int = ...,
        height: int = ...,
        dpi: int = ...
    ) -> QgsRasterIdentifyResult:

        results = dict()

        x = int(point.x())
        if isinstance(self.mRasterData, np.ndarray):

            if format == QgsRaster.IdentifyFormat.IdentifyFormatValue:
                array = self.mRasterData
                if 0 <= x < array.shape[-1]:
                    for b in range(self.bandCount()):
                        results[b + 1] = float(array[b, 0, x])
            elif format in [QgsRaster.IdentifyFormat.IdentifyFormatHtml, QgsRaster.IdentifyFormat.IdentifyFormatText]:
                results[0] = 'Dummy HTML / Text'

        return QgsRasterIdentifyResult(format, results)


#
# class SpectralLibraryRasterDataProvider(QgsRasterDataProvider):
#     """
#     An
#     """
#
#     def __init__(self, *args, speclib=None, fids: List[int] = None, **kwds):
#
#         super().__init__(*args, **kwds)
#
#         self.mSpeclib: QgsVectorLayer = None
#         self.mProfileFields: QgsFields = QgsFields()
#         self.mARRAYS: Dict[Tuple[SpectralSetting, ...], Tuple[np.ndarray, List[np.ndarray]]] = dict()
#         self.mActiveProfileSettings: Tuple[SpectralSetting, ...] = None
#         self.mActiveProfileField: QgsField = None
#
#         if speclib:
#             self.initData(speclib, fids)
#
#     def createFieldLayer(self,
#                          field: QgsField,
#                          settings: Tuple[dict, ...]) -> QgsRasterLayer:
#         i = self.profileFields().indexOf(field.name())
#         assert i >= 0
#
#         layer = QgsRasterLayer(self.speclib().source(),
#                                '<no name>',
#                                SpectralLibraryRasterDataProvider.providerKey())
#         assert layer.isValid()
#         dp: SpectralLibraryRasterDataProvider = layer.dataProvider()
#         dp.linkProvider(self)
#         dp.setActiveProfileField(field)
#         dp.setActiveProfileSettings(settings)
#
#         activeFieldSetting = dp.activeProfileFieldSetting()
#         name = f'{field.name()} ({activeFieldSetting.n_bands()} bands, {activeFieldSetting.xUnit()})'
#         layer.setName(name)
#         return layer
#
#     def createFieldLayers(self,
#                           fields: QgsFields = None,
#                           profileSettingsList: List[Tuple[dict, ...]] = None,
#                           one_setting_per_field: bool = True) -> List[QgsRasterLayer]:
#
#         FIELD_LAYERS = []
#         FIELD_NAMES = set()
#
#         if not isinstance(fields, QgsFields):
#             fields = self.profileFields()
#         else:
#             for f in fields:
#                 assert f in self.profileFields()
#
#         if profileSettingsList is None:
#             profileSettingsList = self.profileSettingsList()
#         else:
#             for settings in profileSettingsList:
#                 assert settings in self.profileSettingsList()
#
#         for settings in profileSettingsList:
#             for i, setting in enumerate(settings):
#                 if isinstance(setting, SpectralSetting):
#                     field = fields.at(i)
#                     if one_setting_per_field and field.name() in FIELD_NAMES:
#                         continue
#                     FIELD_LAYERS.append(self.createFieldLayer(field, settings))
#         return FIELD_LAYERS
#
#     def capabilities(self):
#         caps = QgsRasterInterface.Size | QgsRasterInterface.Identify | QgsRasterInterface.IdentifyValue
#         return QgsRasterDataProvider.ProviderCapabilities(caps)
#
#     def name(self):
#         return 'Name'
#
#     @classmethod
#     def providerKey(cls) -> str:
#         return 'speclibraster'
#
#     @classmethod
#     def description(self) -> str:
#         return 'SpectralLibraryRasterDataProvider'
#
#     @classmethod
#     def createProvider(cls, uri, providerOptions, flags=None):
#         # compatibility with Qgis < 3.16, ReadFlags only available since 3.16
#         flags = QgsDataProvider.ReadFlags()
#         provider = SpectralLibraryRasterDataProvider(uri, providerOptions, flags)
#         return provider
#
#     def dataSourceUri(self, expandAuthConfig=False):
#         s = ""
#
#     def crs(self) -> QgsCoordinateReferenceSystem:
#         return defaultCrs()
#
#     def isValid(self) -> bool:
#         return True
#         return self.mARRAYS is not None
#
#     def _field_and_settings(self,
#                             field: QgsField = None,
#                             settings: Tuple[dict, ...] = None) -> \
#             Tuple[QgsField, Tuple[dict, ...]]:
#         if field is None:
#             field = self.activeProfileField()
#         if settings is None:
#             settings = self.activeProfileSettings()
#         return field, settings
#
#     def profileFields(self) -> QgsFields:
#         return self.mProfileFields
#
#     def profileSetting(self,
#                        field: QgsField = None,
#                        settings: Tuple[dict, ...] = None) -> dict:
#         field, settings = self._field_and_settings(field, settings)
#         if not (isinstance(field, QgsField) and len(settings) > 0):
#             return None
#         return settings[self.mProfileFields.indexOf(field.name())]
#
#     def profileArray(self,
#                      field: QgsField = None,
#                      settings: Tuple[dict, ...] = None) -> np.ndarray:
#         field, settings = self._field_and_settings(field, settings)
#         if not isinstance(field, QgsField):
#             return np.empty((0,), dtype=int)
#         fid, arrays = self.mARRAYS[settings]
#         return arrays[self.mProfileFields.indexOf(field.name())]
#
#     def profileFIDs(self,
#                     settings: Tuple[dict, ...] = None) -> np.ndarray:
#         if settings is None:
#             settings = self.activeProfileSettings()
#         fids, arrays = self.mARRAYS.get(settings, (np.empty((0,), dtype=int), []))
#         return fids
#
#     def setActiveProfileField(self, field: QgsField):
#         assert field in self.mProfileFields
#         self.mActiveProfileField = field
#
#     def activeProfileField(self) -> QgsField:
#         return self.mActiveProfileField
#
#     def activeProfileFieldSetting(self) -> dict:
#         i = self.profileFields().indexOf(self.activeProfileField().name())
#         return self.activeProfileSettings()[i]
#
#     def activeProfileFIDs(self) -> List[int]:
#         return self.profileFIDs(self.activeProfileSettings())
#
#     def setActiveProfileSettings(self, settings: Tuple[dict, ...]):
#         assert settings in self.mARRAYS.keys()
#         self.mActiveProfileSettings = settings
#
#     def activeProfileSettings(self) -> Tuple[dict, ...]:
#         return self.mActiveProfileSettings
#
#     def xSize(self) -> int:
#         return len(self.profileFIDs())
#
#     def ySize(self) -> int:
#         if len(self.mARRAYS) > 0:
#             return 1
#         else:
#             return 0
#
#     def sourceDataType(self, bandNo):
#         return self.dataType(bandNo)
#
#     def dataType(self, bandNo: int) -> Qgis.DataType:
#         array = self.profileArray()
#         t = Qgis.DataType.UnknownDataType
#         for qgis_type, dtype in QGIS2NUMPY_DATA_TYPES.items():
#             if dtype == array.dtype:
#                 t = qgis_type
#                 break
#         return t
#
#     def block(self,
#               bandNo: int,
#               boundingBox: QgsRectangle,
#               width: int,
#               height: int,
#               feedback: QgsRasterBlockFeedback = None) -> QgsRasterBlock:
#         band_data: np.ndarray = self.profileArray()[bandNo - 1, :]
#
#         data_subset = band_data
#         dt = self.dataType(bandNo)
#         block = QgsRasterBlock(dt, width, height)
#         block.setData(band_data.tobytes())
#         return block
#
#     def bandStatistics(self,
#                        bandNo: int,
#                        stats: QgsRasterBandStats.Stats = QgsRasterBandStats.Stats.All,
#                        extent: QgsRectangle = QgsRectangle(),
#                        sampleSize: int = 0,
#                        feedback: QgsRasterBlockFeedback = None) -> QgsRasterBandStats:
#
#         if extent is None:
#             extent = QgsRectangle()
#         else:
#             extent = QgsRectangle(extent)
#
#         stats = QgsRasterBandStats()
#         band_data: np.ndarray = self.profileArray()[bandNo - 1, :]
#
#         stats.sum = band_data.sum()
#         stats.minimumValue = band_data.min()
#         stats.maximumValue = band_data.max()
#         stats.mean = band_data.mean()
#         stats.extent = extent
#         return stats
#
#     def generateBandName(self, band_no: int):
#         setting = self.profileSetting()
#
#         if isinstance(setting, SpectralSetting) and band_no > 0 and band_no <= setting.n_bands():
#             wl = setting.x()[band_no - 1]
#             wlu = setting.xUnit()
#             return f'Band {band_no} {wl} {wlu}'
#
#         return ''
#
#     def bandCount(self) -> int:
#         setting = self.profileSetting()
#         if not isinstance(setting, dict):
#             return 0
#         else:
#             return self.profileSetting().n_bands()
#
#     def profileSettingsList(self) -> List[Tuple[dict, ...]]:
#         return list(self.mARRAYS.keys())
#
#     def initData(self, speclib: QgsVectorLayer, fids: List[int] = None):
#         self.mSpeclib = speclib
#         self.mProfileFields = profile_fields(speclib)
#         self.mARRAYS = featuresToArrays(speclib, self.mProfileFields, fids=fids)
#
#     def linkProvider(self, provider):
#         assert isinstance(provider, SpectralLibraryRasterDataProvider)
#         self.mSpeclib = provider.mSpeclib
#         self.mProfileFields = provider.mProfileFields
#         self.mARRAYS = provider.mARRAYS
#
#     def clone(self) -> 'SpectralLibraryRasterDataProvider':
#         dp = SpectralLibraryRasterDataProvider(None)
#         dp.mARRAYS = self.mARRAYS
#         dp.mProfileFields = self.mProfileFields
#         dp.mActiveProfileSettings = self.mActiveProfileSettings
#         dp.mSpeclib = self.mSpeclib
#
#         return dp
#
#     def speclib(self) -> QgsVectorLayer:
#         return self.mSpeclib
#
#     def fields(self) -> QgsFields:
#         return self.mProfileFields
#
#     def extent(self) -> QgsRectangle:
#
#         rect = QgsRectangle()
#         rect.setXMaximum(self.xSize())
#         rect.setYMaximum(self.ySize())
#         return rect
#

def registerDataProvider():
    registry = QgsProviderRegistry.instance()

    metadata = QgsProviderMetadata(
        VectorLayerFieldRasterDataProvider.providerKey(),
        VectorLayerFieldRasterDataProvider.description(),
        VectorLayerFieldRasterDataProvider.createProvider
    )
    registry.registerProvider(metadata)
    QgsMessageLog.logMessage('VectorLayerRasterDataProvider registered', level=Qgis.MessageLevel.Info)
