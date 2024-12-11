import datetime
import enum
import json
import math
import pickle
import sys
from json import JSONDecodeError
from math import nan
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import NULL, QByteArray, QDateTime, QJsonDocument, Qt, QVariant
from qgis.core import QgsCoordinateReferenceSystem, QgsExpressionContext, QgsFeature, QgsField, QgsFields, QgsGeometry, \
    QgsMapLayer, QgsPointXY, QgsProcessingFeedback, QgsPropertyTransformer, QgsRasterLayer, QgsVectorLayer
from . import create_profile_field, is_profile_field, profile_field_indices, profile_fields
from .. import defaultSpeclibCrs, EMPTY_VALUES
from ...qgisenums import QMETATYPE_QDATETIME, QMETATYPE_QSTRING, QMETATYPE_QVARIANTMAP
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...unitmodel import BAND_INDEX, BAND_NUMBER
from ...utils import qgsField, qgsRasterLayer, saveTransform

# The values that describe a spectral profiles
# y in 1st position ot show profile values in string representations first
EMPTY_PROFILE_VALUES = {'y': None, 'x': None, 'xUnit': None, 'yUnit': None, 'bbl': None}
JSON_SEPARATORS = (',', ':')


def prepareProfileValueDict(x: Union[np.ndarray, List[Any], Tuple] = None,
                            y: Union[np.ndarray, List[Any], Tuple] = None,
                            xUnit: str = None,
                            yUnit: str = None,
                            bbl: Union[np.ndarray, List[Any], Tuple] = None,
                            prototype: dict = None) -> dict:
    """
    Creates a profile value dictionary from inputs
    :param y:
    :param prototype:
    :param bbl:
    :param yUnit:
    :param xUnit:
    :param x:
    :return:
    """

    if isinstance(prototype, dict) and len(prototype) > 0:
        d = {k: v for k, v in prototype.items() if v is not None}

    else:
        d = dict()

    if isinstance(y, np.ndarray):
        y = y.tolist()
    elif isinstance(y, tuple):
        y = list(y)

    if isinstance(x, np.ndarray):
        x = x.tolist()
    elif isinstance(x, tuple):
        x = list(x)

    if isinstance(bbl, np.ndarray):
        bbl = bbl.astype(int).tolist()
    elif isinstance(bbl, tuple):
        bbl = list(bbl)

    if isinstance(x, list):
        d['x'] = x

    if isinstance(y, list):
        d['y'] = y

    if isinstance(bbl, list):
        d['bbl'] = bbl

    if isinstance(xUnit, str) and xUnit != '':
        d['xUnit'] = xUnit
    if isinstance(yUnit, str) and yUnit != '':
        d['yUnit'] = yUnit

    # consistency checks
    # Minimum requirement: a dictionary with a key 'y' and a list of values with length > 0
    y = d.get('y', None)
    if not isinstance(y, list) and len(y) > 0:
        return {}

    x = d.get('x', None)
    if x:
        assert isinstance(x, list)
        assert len(x) == len(y), f'x has length {len(x)} instead of {len(y)}'

    bbl = d.get('bbl', None)
    if bbl:
        assert isinstance(bbl, list)
        assert len(bbl) == len(y), f'bbl has length {len(bbl)} instead of {len(y)}'

    return d


def validateProfileValueDict(d: dict, allowEmpty: bool = False) -> Tuple[bool, str, dict]:
    """
    Validates a profile dictionary
    :param allowEmpty:
    :type allowEmpty:
    :param d: dictionary that describes a spectral profile
    :return: tuple (bool, str, dict),
        with (bool = is_valid,
              str = error message in case of invalid dictionary
              dict = profile dictionary in case of valid dictionary)
    """
    if allowEmpty and d in [dict(), None]:
        return True, '', d
    try:
        assert isinstance(d, dict), 'Input is not a profile dictionary'

        # enhanced consistency checks
        y = d.get('y', None)
        assert isinstance(y, (list, np.ndarray)), f'Unsupported type to store y values: {y}'
        assert len(y) > 0, 'Missing y values'
        arr = np.asarray(y)
        assert np.issubdtype(arr.dtype, np.number), f'data type of y values in not numeric: {arr.dtype.name}'

        x = d.get('x', None)
        if x is not None:
            assert isinstance(x, (list, np.ndarray)), f'Unsupported type to store x values: {x}'
            assert len(x) == len(y), f'Unequal number of y ({len(y)}) and x ({len(x)}) values.'
            arr = np.asarray(x)
            if np.issubdtype(arr.dtype, str):
                # allow date-time strings
                arr = np.asarray(arr, dtype=np.datetime64)
            else:
                assert np.issubdtype(arr.dtype, np.number), f'None-numeric data type of y values: {arr.dtype.name}'

        xUnit = d.get('xUnit', None)
        if xUnit:
            assert x is not None, 'xUnit defined but missing x values'
            assert isinstance(xUnit, str), f'Unsupported type to store xUnit: {xUnit} ({type(xUnit)})'
        yUnit = d.get('yUnit', None)
        if yUnit:
            assert isinstance(yUnit, str), f'Unsupported type to store yUnit: {yUnit} ({type(yUnit)})'

        bbl = d.get('bbl', None)
        if bbl is not None:
            assert isinstance(bbl, (list, np.ndarray)), f'Unsupported type to bbl values: {bbl}'
            assert len(y) == len(bbl), f'Unequal number of y ({len(y)}) and bbl ({len(bbl)}) values.'
            arr = np.asarray(bbl)
            assert np.issubdtype(arr.dtype, np.number), f'None-numeric bbl value data type: {arr.dtype.name}'

    except Exception as ex:
        return False, str(ex), dict()
    else:
        return True, '', d


def isProfileValueDict(d: dict) -> bool:
    """
    Returns True if the input is a valid dictionary with spectral profile values
    """
    return validateProfileValueDict(d)[0]


class ProfileEncoding(enum.Enum):
    Text = 0
    Json = 1
    Map = 1
    Dict = 1
    Bytes = 2
    Binary = 3

    @staticmethod
    def fromInput(input) -> 'ProfileEncoding':
        if input is None:
            return ProfileEncoding.Text
        elif isinstance(input, ProfileEncoding):
            return input
        elif isinstance(input, str):
            input = input.lower()
            for name, member in ProfileEncoding.__members__.items():
                if name.lower() == input:
                    return member
        elif isinstance(input, QgsField):
            if input.type() == 8:
                return ProfileEncoding.Json
            elif input.type() == QVariant.ByteArray:
                return ProfileEncoding.Bytes
            else:
                return ProfileEncoding.Text

        raise NotImplementedError(f'Unable to return ProfileEncoding for "{input}"')


def nanToNone(v):
    """
    Converts NaN, NULL, or Inf values to None, as these can be serialized with json.dump (to "null" strings)
    :param v:
    :return:
    """
    if isinstance(v, (float, int)) and not math.isfinite(v) or v is NULL:
        return None
    else:
        return v


def noneToNan(v):
    """
    Returns a NaN in case the value v is None
    :param v:
    :return:
    """
    return nan if v is None else v


def encodeProfileValueDict(d: dict,
                           encoding: Union[str, QgsField, ProfileEncoding],
                           jsonFormat: QJsonDocument.JsonFormat = QJsonDocument.Compact) -> Any:
    """
    Serializes a SpectralProfile dictionary into JSON string or JSON string compressed as QByteArray
    extracted with `decodeProfileValueDict`.
    :param d: dict
    :param encoding: QgsField Field definition
    :return: QByteArray or str, respecting the datatype that can be stored in field
    """
    if not (isinstance(d, dict) and 'y' in d.keys()):
        return None

    encoding = ProfileEncoding.fromInput(encoding)

    d2 = {}
    for k in EMPTY_PROFILE_VALUES.keys():
        v = d.get(k)
        # save keys with information only
        if v is not None:
            if isinstance(v, np.ndarray):
                v = v.tolist()
            d2[k] = v

    # convert date/time X values to strings
    xValues = d2.get('x')
    if xValues and len(xValues) > 0:
        if isinstance(xValues[0], datetime.datetime):
            d2['x'] = [x.isoformat() for x in xValues]
        elif isinstance(xValues[0], QDateTime):
            d2['x'] = [x.toString(Qt.ISODate) for x in xValues]

    if encoding == ProfileEncoding.Dict:
        # convert None to NaN
        d2['y'] = [noneToNan(v) for v in d2['y']]
        return d2

    # save as JSON string or byte compressed JSON
    # convert NaN to null

    # convert NaN, -Inf, Inf to None
    # see https://datatracker.ietf.org/doc/html/rfc8259
    for k in ['x', 'y', 'bbl']:
        if k in d2:
            d2[k] = [nanToNone(v) for v in d2[k]]

    if encoding in [ProfileEncoding.Bytes, ProfileEncoding.Binary]:
        jsonDoc = QJsonDocument.fromVariant(d2)
        return jsonDoc.toBinaryData()
    else:
        # encoding = TEXT
        return json.dumps(d2, ensure_ascii=False, allow_nan=False)


def decodeProfileValueDict(dump: Union[QByteArray, str, dict], numpy_arrays: bool = False) -> dict:
    """
    Converts a text / json / pickle / bytes representation of a SpectralProfile into a dictionary.

    In case the input "dump" cannot be converted, the returned dictionary is empty ({})
    :param numpy_arrays:
    :param dump: str
    :return: dict
    """

    if dump in EMPTY_VALUES:
        return {}

    d: Optional[dict] = None
    jsonDoc = None

    if isinstance(dump, bytes):
        dump = QByteArray(dump)
    if isinstance(dump, QByteArray):
        if dump.count() > 0 and dump.at(0) == b'{':
            jsonDoc = QJsonDocument.fromJson(dump)
        else:
            jsonDoc = QJsonDocument.fromBinaryData(dump)
        if jsonDoc.isNull():
            try:
                dump = pickle.loads(dump)

            except EOFError as ex:
                pass
            except pickle.UnpicklingError as ex:
                pass

    if isinstance(dump, str):
        try:
            dump = json.loads(dump)
            if isinstance(dump, dict):
                d = dump
        except JSONDecodeError:
            pass
    elif isinstance(dump, dict):
        d = dump
    elif isinstance(dump, QJsonDocument):
        d = dump.toVariant()

    if d is None and isinstance(jsonDoc, QJsonDocument) and not jsonDoc.isNull():
        d = jsonDoc.toVariant()

    # minimum requirement for a spectral profile dictionary
    # 1. is a dict, 2. contains a 'y' key
    # see isProfileValueDict(d) for more extensive check
    if not (isinstance(d, dict) and 'y' in d.keys()):
        return {}

    for k in ['x', 'y', 'bbl']:
        if k in d.keys():
            d[k] = [noneToNan(v) for v in d[k]]

    if numpy_arrays:
        for k in ['x', 'y', 'bbl']:
            if k in d.keys():
                arr = np.asarray(d[k])
                if arr.dtype == object:
                    arr = arr.astype(float)
                d[k] = arr
    return d


class SpectralSetting(object):
    """
    A spectral settings describes general "Sensor" properties of one or multiple spectral profiles.
    n y-values, e.g. reflectance or radiance, by
    1. n x values, e.g. the wavelength of each band
    2. an xUnit, e.g. the wavelength unit 'micrometers'
    3. an yUnit, e.g. 'reflectance'
    """

    @classmethod
    def fromRasterLayer(cls, layer: QgsRasterLayer) -> Optional['SpectralSetting']:
        layer = qgsRasterLayer(layer)
        if not (isinstance(layer, QgsRasterLayer) and layer.isValid()):
            return None

        props = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)

        wl = props.wavelengths()
        wlu = props.wavelengthUnits()[0]
        bbl = props.badBands()
        del layer

        if wl is None:
            return None
        else:
            return SpectralSetting(wl, xUnit=wlu, bbl=bbl)

    @classmethod
    def fromDictionary(cls, d: dict, field_name: str = None) -> Optional['SpectralSetting']:
        if not isinstance(d, dict) or 'y' not in d.keys():
            # no spectral values no spectral setting
            return None
        x = d.get('x', None)
        xUnit = d.get('xUnit', None)
        if x is None:
            if xUnit in [BAND_INDEX, None]:
                x = list(range(len(d['y'])))
            elif xUnit == BAND_NUMBER:
                x = list(range(1, len(d['y']) + 1))

        return SpectralSetting(x,
                               xUnit=xUnit,
                               yUnit=d.get('yUnit', None),
                               bbl=d.get('bbl', None),
                               field_name=field_name
                               )

    @classmethod
    def fromValue(cls, value) -> Optional['SpectralSetting']:
        d: dict = decodeProfileValueDict(value)
        if len(d) > 0:
            return SpectralSetting.fromDictionary(d)
        else:
            return None

    def __init__(self,
                 x: Union[int, tuple, list, np.ndarray],
                 xUnit: Optional[str] = BAND_INDEX,
                 yUnit: Optional[str] = None,
                 bbl: Optional[Union[tuple, list, np.ndarray]] = None,
                 field: Optional[QgsField] = None,
                 field_name: Optional[str] = None,
                 field_encoding: Optional[ProfileEncoding] = None):

        assert isinstance(x, (tuple, list, np.ndarray, int)), f'{x}'

        if isinstance(x, int):
            x = tuple(list(range(x)))
            xUnit = BAND_INDEX
        elif isinstance(x, np.ndarray):
            x = tuple(x.tolist())
        elif isinstance(x, list):
            x = tuple(x)

        if bbl is not None:
            assert len(bbl) == len(x)
            bbl = tuple(bbl)

        self.mX: Tuple = x
        self.mXUnit: str = xUnit
        self.mYUnit: str = yUnit
        self.mBadBandList: Tuple = bbl
        self.mHash = hash((self.mX, self.mXUnit, self.mYUnit, self.mBadBandList))

        # other properties, which will not be used to distinct SpectralSettings from each other
        self.mFieldEncoding = ProfileEncoding.Text
        if isinstance(field, QgsField):
            self.mFieldName = field.name()
            self.mFieldEncoding = ProfileEncoding.fromInput(field)
        else:
            self.mFieldName: str = field_name
            if field_encoding:
                self.mFieldEncoding = ProfileEncoding.fromInput(field_encoding)

    def fieldEncoding(self) -> ProfileEncoding:
        return self.mFieldEncoding

    def fieldName(self) -> str:
        """
        Returns the name of the QgsField to which profiles within this setting are linked to
        :return: str
        """
        return self.mFieldName

    def __str__(self):
        return f'SpectralSetting:({self.n_bands()} bands {self.xUnit()} {self.yUnit()})'.strip()

    def x(self) -> Optional[List]:
        if self.mX:
            return list(self.mX)
        return None

    def n_bands(self) -> int:
        if self.mX:
            return len(self.mX)
        else:
            return 0

    def yUnit(self) -> str:
        return self.mYUnit

    def xUnit(self) -> str:
        return self.mXUnit

    def bbl(self):
        """
        Shortcut for bad band list
        :return:
        """
        return self.badBandList()

    def badBandList(self):
        """
        Returns the band band list
        :return:
        """
        return self.mBadBandList

    def __eq__(self, other):
        if not isinstance(other, SpectralSetting):
            return False
        return self.mHash == other.mHash

    def __hash__(self):
        return self.mHash

    def writeToLayer(self, layer: QgsRasterLayer):
        """
        Writes the band and wavelength information to this layer
        """
        layer = qgsRasterLayer(layer)
        assert self.n_bands() == layer.bandCount()

        assert isinstance(layer, QgsRasterLayer)
        assert layer.isValid()
        properties = QgsRasterLayerSpectralProperties(layer.bandCount())
        x = self.x()
        bbl = self.bbl()
        wlu = self.xUnit()
        if x:
            properties.setBandValues(None, 'wl', x)
        if bbl:
            properties.setBandValues(None, 'bbl', bbl)
        if wlu:
            properties.setBandValues(None, 'wlu', wlu)

        for k in properties.keys():
            layer.setCustomProperty(k, properties.value(k))

        if True:
            # write to QGISPAM layer metadata
            # follows https://enmap-box.readthedocs.io/en/latest/dev_section/rfc_list/rfc0002.html
            for b in range(self.n_bands()):
                key = f'QGISPAM/band/{b + 1}//wavelength_units'
                layer.setCustomProperty(key, wlu)
                key = f'QGISPAM/band/{b + 1}//wavelength'
                layer.setCustomProperty(key, x[b])

                if bbl:
                    key = f'QGISPAM/band/{b + 1}//bad_band_multiplier'
                    layer.setCustomProperty(key, bbl[b])
        err, success = layer.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
        if not success:
            print(err, file=sys.stderr)

        if False:
            # write to GDAL PAM
            if layer.dataProvider().name() == 'gdal':
                path = layer.source()
                del layer

                ds: gdal.Dataset = gdal.Open(path, gdal.GA_Update)
                # set at dataset level
                METADATA = ds.GetMetadata()
                METADATA['wavelength_units'] = wlu
                METADATA['wavelength'] = '{' + ','.join([str(v) for v in x]) + '}'
                ds.SetMetadata(METADATA)
                ds.SetMetadata(METADATA, 'ENVI')

                # set at band level
                for b in range(ds.RasterCount):
                    band: gdal.Band = ds.GetRasterBand(b + 1)
                    METADATA = band.GetMetadata()
                    METADATA['wavelength_unit'] = wlu
                    METADATA['wavelength'] = str(x[b])
                    band.SetMetadata(METADATA)
                ds.FlushCache()
                del ds


def groupBySpectralProperties(profiles: Union[QgsVectorLayer, List[QgsFeature]],
                              excludeEmptyProfiles: bool = True,
                              profile_field: Union[int, str, QgsField] = None
                              ) -> Dict[SpectralSetting, List[QgsFeature]]:
    """
    Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

        xValues: None | [list-of-xvalues with n>0 elements]
        xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
        yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

    :return: {SpectralSetting:[list-of-profiles]}
    """
    if isinstance(profiles, QgsVectorLayer):
        profiles = profiles.getFeatures()
    if isinstance(profiles, QgsFeature):
        profiles = [profiles]
    results = dict()

    # will be initialized with 1st SpectralProfile

    pField: QgsField = None
    pFieldIdx: int = None

    for p in profiles:
        assert isinstance(p, QgsFeature)
        if pField is None:
            # initialize the profile field to group profiles on
            pFields: QgsFields = profile_fields(p.fields())
            if pFields.count() == 0:
                # no profile fields = nothing to group
                return {}

            if profile_field is None:
                pField = pFields.at(0)
            else:
                pField = qgsField(p.fields(), profile_field)
                pField = pFields.field(pField.name())

            assert is_profile_field(pField)
            pFieldIdx = p.fields().lookupField(pField.name())

        d: dict = decodeProfileValueDict(p.attribute(pFieldIdx))

        y = d.get('y', [])
        if excludeEmptyProfiles:
            if not (isinstance(y, list) and len(y) > 0):
                continue

        x = d.get('x', len(y))

        xUnit = d.get('xUnit', None)
        yUnit = d.get('yUnit', None)

        key = SpectralSetting(x=x, xUnit=xUnit, yUnit=yUnit, field_name=pField.name())

        if key not in results.keys():
            results[key] = []
        results[key].append(p)
    return results


class SpectralProfileFileReader(object):
    """
    Base class for file readers of spectral profile measurement files
    """
    KEY_Reference = 'reference'  # dictionary with reference profile data
    KEY_Target = 'target'  # dictionary with target profile data
    KEY_Reflectance = 'reflectance'  # dictionary with reflectance profile values (if defined)
    KEY_ReferenceTime = 'timeR'  # time of reference profile acquisition
    KEY_TargetTime = 'timeT'  # time of target profile acquisition
    KEY_Metadata = 'metadata'  # dictionary with more / original / untransformed metadata (file type specific)
    KEY_Name = 'name'  # file name (basename)
    KEY_Path = 'path'  # file path (full path)

    _STANDARD_FIELDS = None

    def __init__(self, path: Union[str, Path]):
        path = Path(path)
        assert path.is_file()

        # member attributes each profile should be able to descrbied

        self.mPath = path

        self.mReference: Optional[dict] = None
        self.mReferenceTime: Optional[datetime.datetime] = None
        self.mReferenceCoordinate: Optional[QgsPointXY] = None

        self.mTarget: Optional[dict] = None
        self.mTargetTime: Optional[datetime.datetime] = None
        self.mTargetCoordinate: Optional[QgsPointXY] = None

        self.mReflectance: Optional[dict] = None

        # store for other values. can be saved in JSON
        self.mMetadata: dict = dict()

    @staticmethod
    def standardFields() -> QgsFields:
        """
        Standard field provided in a QgsFeature returned with .asFeature()
        :return:
        """
        if not isinstance(SpectralProfileFileReader._STANDARD_FIELDS, QgsFields):
            fields = QgsFields()
            fields.append(
                create_profile_field(SpectralProfileFileReader.KEY_Reference, encoding=ProfileEncoding.Dict))
            fields.append(
                create_profile_field(SpectralProfileFileReader.KEY_Target, encoding=ProfileEncoding.Dict))
            fields.append(
                create_profile_field(SpectralProfileFileReader.KEY_Reflectance, encoding=ProfileEncoding.Dict))
            fields.append(QgsField(SpectralProfileFileReader.KEY_ReferenceTime, QMETATYPE_QDATETIME))
            fields.append(QgsField(SpectralProfileFileReader.KEY_TargetTime, QMETATYPE_QDATETIME))
            fields.append(QgsField(SpectralProfileFileReader.KEY_Name, QMETATYPE_QSTRING))
            fields.append(QgsField(SpectralProfileFileReader.KEY_Path, QMETATYPE_QSTRING))
            fields.append(QgsField(SpectralProfileFileReader.KEY_Metadata, QMETATYPE_QVARIANTMAP))
            SpectralProfileFileReader._STANDARD_FIELDS = fields
        return SpectralProfileFileReader._STANDARD_FIELDS

    def path(self) -> Path:
        return self.mPath

    def name(self) -> str:
        return self.mPath.name

    def asMap(self) -> dict:
        """
        Returns a dictionary that contains the basic profile attributes
        Values can be accessed using the SpectralProfileFieReader.KEY_* attribute names
        :return: dict
        """
        attributes = dict()
        if len(self.mMetadata) > 0:
            attributes[self.KEY_Metadata] = self.metadata()

        if self.mReference:
            attributes[self.KEY_Reference] = self.reference()

        if self.mTarget:
            attributes[self.KEY_Target] = self.target()

        if self.mReflectance:
            attributes[self.KEY_Reflectance] = self.reflectance()

        if self.mReferenceTime:
            attributes[self.KEY_ReferenceTime] = self.referenceTime().isoformat()

        if self.mTargetTime:
            attributes[self.KEY_TargetTime] = self.targetTime().isoformat()

        if self.mPath:
            attributes[self.KEY_Name] = self.mPath.name
            attributes[self.KEY_Path] = self.mPath.as_posix()

        return attributes

    def asFeature(self) -> QgsFeature:
        """Returns the file content as QgsFeature"""

        f = QgsFeature(self.standardFields())
        attributes = self.asMap()

        from .spectrallibrary import SpectralLibraryUtils
        SpectralLibraryUtils.setAttributeMap(f, attributes)

        if self.mTargetCoordinate:
            f.setGeometry(QgsGeometry.fromPointXY(self.mTargetCoordinate))
        elif self.mReferenceCoordinate:
            f.setGeometry(QgsGeometry.fromPointXY(self.mReferenceCoordinate))

        return f

    def reference(self) -> Optional[dict]:
        """
        Returns the (white) reference profile dictionary
        :return:
        """
        return self.mReference.copy()

    def target(self) -> Optional[dict]:
        """
        Returns the target profile dictionary
        :return:
        """
        return self.mTarget.copy()

    def reflectance(self) -> Optional[dict]:
        """
        Returns the reflectance profile, either as stored in the file or
         calculated as target/reference
        :return:
        """
        if self.mReflectance:
            return self.mReflectance.copy()
        elif (self.mTarget and self.mReference):
            d = self.mTarget.copy()
            d['y'] = [t / r for t, r in zip(self.mTarget['y'], self.mReference['y'])]
            d['yUnit'] = '-'
            return d
        else:
            return None

    def referenceCoordinate(self) -> Optional[QgsPointXY]:
        """
        Coordinate of the reference measurement (EPSG:4326)
        :return: QgsPointXY
        """
        return self.mReferenceCoordinate

    def targetCoordinate(self) -> Optional[QgsPointXY]:
        """
        Coordinate of the target measurement (EPSG:4326)
        :return: QgsPointXY
        """
        return self.mTargetCoordinate

    def referenceTime(self) -> datetime.datetime:
        return self.mReferenceTime

    def targetTime(self) -> datetime.datetime:
        return self.mTargetTime

    def metadata(self) -> dict:
        return self.mMetadata.copy()


class SpectralProfileBlock(object):
    """
    A block of spectral profiles that share the same properties like wavelength, wavelength unit etc.
    """

    @staticmethod
    def dummy(n=5, n_bands=10, wlu='nm') -> Optional['SpectralProfileBlock']:
        """
        Creates a dummy block, e.g. to be used for testing
        :return:
        :rtype:
        """
        from ...testing import TestObjects
        profiles = list(TestObjects.spectralProfiles(n, n_bands=n_bands, wlu=wlu))
        profile_field = profile_field_indices(profiles[0])[0]
        return list(SpectralProfileBlock.fromSpectralProfiles(profiles,
                                                              profile_field=profile_field
                                                              ))[0]

    @staticmethod
    def fromSpectralProfiles(profiles: List[QgsFeature],
                             profile_field: Union[int, str, QgsField] = None,
                             crs: QgsCoordinateReferenceSystem = None,
                             feedback: QgsProcessingFeedback = None):

        if crs is None:
            crs = defaultSpeclibCrs()

        for spectral_setting, profiles in groupBySpectralProperties(profiles,
                                                                    profile_field=profile_field,
                                                                    excludeEmptyProfiles=True).items():
            ns: int = len(profiles)
            fids = [p.id() for p in profiles]
            nb = spectral_setting.n_bands()
            ref_d: dict = decodeProfileValueDict(profiles[0].attribute(spectral_setting.fieldName()), numpy_arrays=True)
            ref_profile: np.ndarray = ref_d['y']
            dtype = ref_profile.dtype
            blockArray = np.empty((nb, 1, ns), dtype=dtype)
            blockArray[:, 0, 0] = ref_profile

            pos_x_array = np.empty((1, ns), dtype=float)
            pos_y_array = np.empty((1, ns), dtype=float)
            pos_x_array.fill(np.nan)
            pos_y_array.fill(np.nan)
            del ref_profile

            for i, profile in enumerate(profiles):
                d = decodeProfileValueDict(profile.attribute(spectral_setting.fieldName()))
                blockArray[:, 0, i] = np.asarray(d['y'], dtype=dtype)
                if profile.hasGeometry():
                    pt: QgsPointXY = profile.geometry().asPoint()
                    pos_x_array[0, i] = pt.x()
                    pos_y_array[0, i] = pt.y()

            block = SpectralProfileBlock(blockArray, spectral_setting, fids=fids)
            if np.any(np.isfinite(pos_x_array)):
                block.setPositions(pos_x_array, pos_y_array, crs)
            yield block

    def __init__(self,
                 data: Union[np.ndarray, np.ma.masked_array],
                 spectralSetting: SpectralSetting,
                 fids: List[int] = None,
                 positionsX: np.ndarray = None,
                 positionsY: np.ndarray = None,
                 crs: QgsCoordinateReferenceSystem = None,
                 metadata: dict = None):

        assert isinstance(spectralSetting, SpectralSetting)
        assert isinstance(data, (np.ndarray, np.ma.masked_array))
        assert data.ndim <= 3
        if data.ndim == 1:
            data = data.reshape((data.shape[0], 1, 1))
        elif data.ndim == 2:
            data = data.reshape((data.shape[0], data.shape[1], 1))
        self.mData: np.ndarray = data

        if spectralSetting.x is None:
            xValues = np.arange(data.shape[0])
        else:
            xValues = np.asarray(spectralSetting.x())

        assert len(xValues) == self.n_bands()

        self.mSpectralSetting = spectralSetting
        self.mXValues: np.ndarray = xValues
        self.mFIDs: List[int] = None

        if not isinstance(metadata, dict):
            metadata = dict()
        self.mMetadata = metadata

        self.mCrs: QgsCoordinateReferenceSystem = None
        self.mPositionsX: np.ndarray = None
        self.mPositionsY: np.ndarray = None

        if fids is not None:
            self.setFIDs(fids)

        if positionsX:
            self.setPositions(positionsX, positionsY, crs)

    def metadata(self) -> dict:
        """
        Returns a copy of the metadata
        :return:
        """
        return self.mMetadata.copy()

    def setFIDs(self, fids: List[int]):
        """
        :param fids:
        :return:
        """
        assert len(fids) == self.n_profiles(), \
            f'Number of Feature IDs ({len(fids)}) must be equal to number of profiles ({self.n_profiles()})'
        self.mFIDs = fids

    def fids(self) -> List[int]:
        """
        Returns the fid for each profile (flattened list)
        :return: list
        """
        return self.mFIDs

    def spectralSetting(self) -> SpectralSetting:
        """
        Returns the spectral setting of the profiles, i.e. wavelength information
        :return: SpectralSetting
        """
        return self.mSpectralSetting

    def xValues(self) -> np.ndarray:
        """
        Returns the x axis values, e.g. wavelenght for each band
        :return: numpy array
        """
        return self.mXValues

    def xUnit(self) -> str:
        """
        Returns the unit of the x axis values
        :return:
        """
        return self.mSpectralSetting.xUnit()

    def n_profiles(self) -> int:
        """
        Returns the number of profiles in the block (including masked!)
        :return: int
        """
        return int(np.prod(self.mData.shape[1:]))

    def n_bands(self) -> int:
        """
        Returns the number of profile bands
        :return: int
        """
        return self.mData.shape[0]

    def yUnit(self) -> str:
        """
        Returns the unit of the profile values (y Unit)
        :return: str
        """
        return self.mSpectralSetting.yUnit()

    def toVariantMap(self) -> dict:
        """
        Converts the profile block into a dictionary
        :return: dict
        """
        kwds = dict()
        kwds['metadata'] = self.metadata()
        kwds['profiledata'] = self.mData
        kwds['geodata'] = (self.mPositionsX, self.mPositionsY, self.mCrs)
        kwds['keys'] = self.mFIDs
        SS = self.spectralSetting()
        kwds['x'] = SS.x()
        kwds['x_unit'] = SS.xUnit()
        kwds['y_unit'] = SS.yUnit()
        kwds['bbl'] = SS.bbl()

        return kwds

    @staticmethod
    def fromVariantMap(kwds: dict) -> Optional['SpectralProfileBlock']:
        values = kwds['profiledata']
        assert isinstance(values, np.ndarray)
        geodata = kwds.get('geodata', None)
        SS = SpectralSetting(kwds.get('x', list(range(values.shape[0]))),
                             xUnit=kwds.get('x_unit', None),
                             yUnit=kwds.get('y_unit'),
                             bbl=kwds.get('bbl')
                             )
        block = SpectralProfileBlock(values, SS,
                                     fids=kwds.get('keys', None),
                                     metadata=kwds.get('metadata', None)
                                     )
        if isinstance(geodata, tuple) and isinstance(geodata[0], np.ndarray):
            block.setPositions(*geodata)
        return block

    def __eq__(self, other):
        if not isinstance(other, SpectralProfileBlock):
            return False

        for k, v in self.__dict__.items():
            if isinstance(v, np.ndarray):
                if not np.all(v == other.__dict__.get(k, None)):
                    return False
            elif v != other.__dict__.get(k, None):
                return False

        return True

    def __len__(self) -> int:
        return self.n_profiles()

    def geoPositions(self) -> Tuple[np.ndarray, np.ndarray, QgsCoordinateReferenceSystem]:
        """
        Returns the geoposition data for each pixel in the profile block data
        :return: (numpy 2D array x coordinates,
                  numpy 2D array y coordinates,
                  QgsCoordinateReferenceSystem

        """
        assert self.hasGeoPositions()
        assert self.mPositionsX.shape == self.mPositionsY.shape
        assert self.mPositionsX.shape == self.mData.shape[1:]
        return self.mPositionsX, self.mPositionsY, self.mCrs

    def hasGeoPositions(self) -> bool:
        """
        Returns True if profile in the block .data() array is described by a geocoordinate
        :return:
        """
        result = isinstance(self.mPositionsY, np.ndarray) \
                 and isinstance(self.mPositionsX, np.ndarray) \
                 and isinstance(self.mCrs, QgsCoordinateReferenceSystem)
        return result

    def crs(self) -> QgsCoordinateReferenceSystem:
        """
        Returns the coordinate reference system for internal geo-positions
        :return: QgsCoordinateReferenceSystem
        """
        return self.mCrs

    def toCrs(self, newCrs: QgsCoordinateReferenceSystem) -> bool:
        """
        Transform the internal geo-positions to a new coordinate reference system
        :param newCrs: coordinate reference system
        :return: bool, is True if the transformation was successful
        """
        assert isinstance(newCrs, QgsCoordinateReferenceSystem)
        newPosX, newPosY = saveTransform((self.mPositionsX, self.mPositionsY), self.crs(), newCrs)
        if isinstance(newPosX, np.ndarray):
            self.mPositionsX = newPosX
            self.mPositionsY = newPosY
            self.mCrs = newCrs
            return True
        return False

    def setPositions(self,
                     pos_x: np.ndarray,
                     pos_y: np.ndarray,
                     crs: Union[str, QgsCoordinateReferenceSystem]):
        """
        Sets the geo-positions of each spectral profile in this block.
        If set, SpectralProfiles returned with .profiles() will contain a QgsGeometry in crs coordinates-
        :param pos_x: array with x coordinates
        :param pos_y: array with y coordinates
        :param crs: coordinate reference system
        :return:
        """
        shape = self.mData.shape[1:]
        assert pos_x is not None
        assert pos_y is not None
        if not isinstance(pos_x, np.ndarray):
            pos_x = np.asarray(pos_x).reshape(shape)

        if not isinstance(pos_y, np.ndarray):
            pos_y = np.asarray(pos_y).reshape(shape)

        assert isinstance(pos_x, np.ndarray)
        assert isinstance(pos_y, np.ndarray)
        assert pos_x.shape == pos_y.shape
        assert pos_x.shape == shape

        crs = QgsCoordinateReferenceSystem(crs)
        # assert crs.isValid()
        self.mPositionsX = pos_x
        self.mPositionsY = pos_y
        self.mCrs = crs

    def profiles(self) -> Iterable[QgsFeature]:
        """
        Returns the profile block data as SpectralProfiles
        :return: iterator
        """
        fields = QgsFields()
        fieldName = self.spectralSetting().fieldName()
        fieldEncoding: ProfileEncoding = self.spectralSetting().fieldEncoding()
        fields.append(create_profile_field(name=fieldName, encoding=fieldEncoding))

        for fid, d, geometry in self.profileValueDictionaries():
            profile = QgsFeature(fields)
            profile.setId(fid)
            profile.setGeometry(geometry)
            profile.setAttribute(fieldName, encodeProfileValueDict(d, fieldEncoding))
            yield profile

    def __iter__(self):
        return self.profiles()

    def profileValueDictionaries(self) -> List[Tuple[int, dict, QgsGeometry]]:
        """
        Converts the block data into profile value dictionaries
        :return: (fid: int, value_dict: dict, geometry: QgsGeometry)
        """
        yy, xx = np.unravel_index(np.arange(self.n_profiles()), self.mData.shape[1:])
        spectral_settings = self.spectralSetting()

        xUnit = spectral_settings.xUnit()
        yUnit = spectral_settings.yUnit()
        xValues = spectral_settings.x()
        bbl = spectral_settings.bbl()
        hasGeoPositions = self.hasGeoPositions()

        fids = self.fids()
        masked: bool = isinstance(self.mData, np.ma.MaskedArray)
        for j, i in zip(yy, xx):
            yValues = self.mData[:, j, i]
            if masked and np.ma.alltrue(yValues.mask):
                # skip profile, as the entire profile is masked
                continue
            if hasGeoPositions:
                g = QgsGeometry.fromPointXY(QgsPointXY(self.mPositionsX[j, i],
                                                       self.mPositionsY[j, i]))
            else:
                g = QgsGeometry()
            d = prepareProfileValueDict(x=xValues,
                                        y=yValues,
                                        bbl=bbl,
                                        xUnit=xUnit,
                                        yUnit=yUnit)
            if fids:
                yield fids[i], d, g
            else:
                yield None, d, g

    def profileValueByteArrays(self) -> List[Tuple[int, QByteArray, QgsGeometry]]:
        """
        Converts the block data into serialized value dictionaries
        that can be stored in a QByteArray field
        :return: (fid: int, value_dict: dict, geometry: QgsGeometry)
            fid = profile id, might be None
            geometry = profile geometry, might be None
        :return:
        """
        exampleField = QgsField('tmp', QVariant.ByteArray)
        for fid, d, g in self.profileValueDictionaries():
            yield fid, encodeProfileValueDict(d, exampleField), g

    def data(self) -> np.ndarray:
        """
        Spectral profiles as np.ndarray with (always) 3 dimensions:
        (bands, profile number, 1) or - e.g. if profiles are from a spectral library
        (bands, y position, x position) - e.g. if profiles come from an image subset
        :return: np.ndarray
        """
        return self.mData


class SpectralProfilePropertyTransformer(QgsPropertyTransformer):
    """
    A QgsPropertyTransformer to transform encoded spectral profile dictionaries,
    e.g. as returned by QgsProperty expressions, into the correct encoding as
    required by a QgsField data type (str, json or bytes).
    """

    def __init__(self, encoding: Union[str, ProfileEncoding, QgsField]):
        super().__init__()
        self.mEncoding = ProfileEncoding.fromInput(encoding)

    def clone(self) -> 'QgsPropertyTransformer':
        return SpectralProfilePropertyTransformer(self.mEncoding)

    def transform(self, context: QgsExpressionContext, value: Any) -> Any:
        if value:
            d = decodeProfileValueDict(value)
            return encodeProfileValueDict(d, encoding=self.mEncoding)
        return None
