import datetime
import os
import pathlib
import pickle
import sys
import warnings
import typing
from collections import namedtuple
import json

from PyQt5.QtCore import pyqtSignal, QObject
from qgis._core import QgsTask, QgsVectorLayer, QgsField, QgsFeatureRequest, QgsFeature

from qgis.PyQt.QtCore import QPoint, QVariant, QByteArray
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsFeature, QgsPointXY, QgsCoordinateReferenceSystem, QgsField, QgsFields, \
    QgsMapLayer, QgsRasterLayer, QgsVectorLayer, QgsGeometry, QgsRaster, QgsPoint, QgsProcessingFeedback
from qgis.gui import QgsMapCanvas
from osgeo import gdal, ogr
import numpy as np

from . import profile_fields, profile_field_indices, first_profile_field_index, field_index

from ...utils import SpatialPoint, px2geo, geo2px, parseWavelength, createQgsField, \
    qgsFields2str, str2QgsFields, qgsFieldAttributes2List, SignalObjectWrapper
from ...plotstyling.plotstyling import PlotStyle
from ...externals import pyqtgraph as pg

from .. import SPECLIB_CRS, EMPTY_VALUES, FIELD_VALUES, FIELD_FID, FIELD_NAME, ogrStandardFields, createStandardFields

# a single profile is identified by its QgsFeature id and profile_field index or profile_field name

EMPTY_PROFILE_VALUES = {'x': None, 'y': None, 'xUnit': None, 'yUnit': None, 'bbl': None}


def prepareProfileValueDict(x: None, y: None, xUnit: str = None, yUnit: str = None, bbl=None, prototype: dict = None):
    """
    Creates a profile value dictionary from inputs
    :param d:
    :return:
    """
    if isinstance(prototype, dict):
        d = prototype.copy()
    else:
        d = EMPTY_PROFILE_VALUES.copy()

    if isinstance(x, np.ndarray):
        x = x.tolist()

    if isinstance(y, np.ndarray):
        y = y.tolist()

    if isinstance(bbl, np.ndarray):
        bbl = bbl.astype(bool).tolist()

    if isinstance(x, list):
        d['x'] = x

    if isinstance(y, list):
        d['y'] = y

    if isinstance(bbl, list):
        d['bbl'] = bbl

    # ensure x/y/bbl are list or None
    assert d['x'] is None or isinstance(d['x'], list)
    assert d['y'] is None or isinstance(d['y'], list)
    assert d['bbl'] is None or isinstance(d['bbl'], list)

    # ensure same length
    if isinstance(d['x'], list):
        assert isinstance(d['y'], list), 'y values need to be specified'

        assert len(d['x']) == len(d['y']), \
            'x and y need to have the same number of values ({} != {})'.format(len(d['x']), len(d['y']))

    if isinstance(d['bbl'], list):
        assert isinstance(d['y'], list), 'y values need to be specified'
        assert len(d['bbl']) == len(d['y']), \
            'y and bbl need to have the same number of values ({} != {})'.format(len(d['y']), len(d['bbl']))

    if isinstance(xUnit, str):
        d['xUnit'] = xUnit
    if isinstance(yUnit, str):
        d['yUnit'] = yUnit

    return d


def encodeProfileValueDict(d: dict) -> QByteArray:
    """
    Serializes a SpectralProfile value dictionary into a QByteArray
    extracted with `decodeProfileValueDict`.
    :param d: dict
    :return: str
    """
    if not isinstance(d, dict):
        return None
    d2 = {}
    for k in EMPTY_PROFILE_VALUES.keys():
        v = d.get(k)
        # save keys with information only
        if v is not None:
            d2[k] = v
    return QByteArray(pickle.dumps(d2))


def decodeProfileValueDict(dump: QByteArray) -> dict:
    """
    Converts a json / pickle dump  into a SpectralProfile value dictionary
    :param dump: str
    :return: dict
    """
    d = EMPTY_PROFILE_VALUES.copy()

    if dump not in EMPTY_VALUES:
        d2 = pickle.loads(dump)
        d.update(d2)
    return d


class SpectralProfile(QgsFeature):
    """
    A QgsFeature specialized to reading Spectral Profile data from BLOB fields
    A single SpectralProfile allows to access all Spectral Profiles within multiple QgsFields of a QgsFeature
    """
    crs = SPECLIB_CRS

    @staticmethod
    def profileName(basename: str, pxPosition: QPoint = None, geoPosition: QgsPointXY = None, index: int = None):
        """
        Unified method to generate the name of a single profile
        :param basename: base name
        :param pxPosition: optional, pixel position in source image
        :param geoPosition: optional, pixel position in geo-coordinates
        :param index: index, e.g. n'th-1 profile that was sampled from a data set
        :return: name
        """

        name = basename

        if isinstance(index, int):
            name += str(index)

        if isinstance(pxPosition, QPoint):
            name += '({}:{})'.format(pxPosition.x(), pxPosition.y())
        elif isinstance(geoPosition, QgsPoint):
            name += '({}:{})'.format(geoPosition.x(), geoPosition.y())
        return name.replace(' ', ':')

    @staticmethod
    def fromMapCanvas(mapCanvas, position) -> list:
        """
        Returns a list of Spectral Profiles the raster layers in QgsMapCanvas mapCanvas.
        :param mapCanvas: QgsMapCanvas
        :param position: SpatialPoint
        """
        assert isinstance(mapCanvas, QgsMapCanvas)
        profiles = [SpectralProfile.fromRasterLayer(lyr, position) for lyr in mapCanvas.layers() if
                    isinstance(lyr, QgsRasterLayer)]
        return [p for p in profiles if isinstance(p, SpectralProfile)]

    @staticmethod
    def fromRasterSources(sources: list, position: SpatialPoint) -> list:
        """
        Returns a list of Spectral Profiles
        :param sources: list-of-raster-sources, e.g. file paths, gdal.Datasets, QgsRasterLayers
        :param position: SpatialPoint
        :return: [list-of-SpectralProfiles]
        """
        profiles = [SpectralProfile.fromRasterSource(s, position) for s in sources]
        return [p for p in profiles if isinstance(p, SpectralProfile)]

    @staticmethod
    def fromRasterLayer(layer: QgsRasterLayer, position: SpatialPoint):
        """
        Reads a SpectralProfile from a QgsRasterLayer
        :param layer: QgsRasterLayer
        :param position: SpatialPoint
        :return: SpectralProfile or None, if profile is out of layer bounds.
        """

        position = position.toCrs(layer.crs())
        if not layer.extent().contains(position):
            return None

        results = layer.dataProvider().identify(position, QgsRaster.IdentifyFormatValue).results()
        wl, wlu = parseWavelength(layer)

        y = list(results.values())
        y = [v if isinstance(v, (int, float)) else float('NaN') for v in y]

        profile = SpectralProfile()
        profile.setValues(x=wl, y=y, xUnit=wlu)
        profile.setCoordinates(position)

        return profile

    @staticmethod
    def fromRasterSource(source,
                         position,
                         crs: QgsCoordinateReferenceSystem = None,
                         gt: list = None,
                         fields: QgsFields = None):
        """
        Returns the Spectral Profiles from source at position `position`
        :param source: str | gdal.Dataset | QgsRasterLayer - the raster source
        :param position: list of positions
                        QPoint -> pixel index position
                        QgsPointXY -> pixel geolocation position in layer/raster CRS
                        SpatialPoint -> pixel geolocation position, will be transformed into layer/raster CRS
        :param crs: QgsCoordinateReferenceSystem - coordinate reference system of raster source, defaults to the raster source CRS
        :param gt: geo-transformation 6-tuple, defaults to the GT of the raster source
        :return: SpectralProfile with QgsPoint-Geometry in EPSG:43
        """

        if isinstance(source, str):
            ds = gdal.Open(source)
        elif isinstance(source, gdal.Dataset):
            ds = source
        elif isinstance(source, QgsRasterLayer):
            ds = gdal.Open(source.source())

        assert isinstance(ds, gdal.Dataset)

        file = ds.GetDescription()
        if os.path.isfile(file):
            baseName = os.path.basename(file)
        else:
            baseName = 'Spectrum'

        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        if not isinstance(gt, list):
            gt = ds.GetGeoTransform()

        geoCoordinate = None
        if isinstance(position, QPoint):
            px = position
            geoCoordinate = SpatialPoint(crs, px2geo(px, gt, pxCenter=True)).toCrs(SPECLIB_CRS)
        elif isinstance(position, SpatialPoint):
            px = geo2px(position.toCrs(crs), gt)
            geoCoordinate = position.toCrs(SPECLIB_CRS)
        elif isinstance(position, QgsPointXY):
            px = geo2px(position, ds.GetGeoTransform())
            geoCoordinate = SpatialPoint(crs, position).toCrs(SPECLIB_CRS)
        else:
            raise Exception('Unsupported type of argument "position" {}'.format('{}'.format(position)))

        # check out-of-raster
        if px.x() < 0 or px.y() < 0:
            return None
        if px.x() > ds.RasterXSize - 1 or px.y() > ds.RasterYSize - 1:
            return None

        y = ds.ReadAsArray(px.x(), px.y(), 1, 1)

        y = y.flatten()
        for b in range(ds.RasterCount):
            band = ds.GetRasterBand(b + 1)
            nodata = band.GetNoDataValue()
            if nodata and y[b] == nodata:
                return None

        wl, wlu = parseWavelength(ds)

        profile = SpectralProfile(fields=fields)
        # profile.setName(SpectralProfile.profileName(baseName, pxPosition=px))
        profile.setValues(x=wl, y=y, xUnit=wlu)
        profile.setCoordinates(geoCoordinate)
        # profile.setSource('{}'.format(ds.GetDescription()))
        return profile

    @staticmethod
    def fromQgsFeature(feature: QgsFeature, profile_field: typing.Union[int, str, QgsField] = None) \
            -> 'SpectralProfile':
        """
        Converts a QgsFeature into a SpectralProfile
        :param feature: QgsFeature
        :param profile_field: index, name or QgsField of QgsField that stores the Spectral Profile BLOB. Defaults to the first BLOB field
        :return:
        """
        assert isinstance(feature, QgsFeature)
        if not isinstance(profile_field, int):
            if profile_field is None:
                profile_field = first_profile_field_index(feature)
            else:
                profile_field = field_index(feature, profile_field)
        assert profile_field >= 0
        sp = SpectralProfile(id=feature.id(), fields=feature.fields(), profile_field=profile_field)
        sp.setAttributes(feature.attributes())
        sp.setGeometry(feature.geometry())
        return sp

    def __init__(self, parent=None,
                 id: int = None,
                 fields: QgsFields = None,
                 profile_field: typing.List[typing.Union[int, str, QgsField]] = None):
        """
        :param parent:
        :param fields:
        :param values:
        :param profile_field: name or index of profile_field that contains the spectral values information.
                            Needs to be a BLOB profile_field.
        """
        if fields is None:
            fields = createStandardFields()
        assert isinstance(fields, QgsFields)
        super(SpectralProfile, self).__init__(fields)

        if isinstance(id, int):
            super().setId(id)

        assert isinstance(fields, QgsFields)
        if profile_field is None:
            for f in self.fields():
                if f.type() == QVariant.ByteArray:
                    profile_field = f
                    break

        self.mCurrentProfileFieldIndex: int = self._profile_field_index(profile_field)
        assert self.mCurrentProfileFieldIndex > 0, f'Unable to find BLOB profile_field "{profile_field}" with spectral profiles'
        # self.mProfileKey: SpectralProfileKey = SpectralProfileKey(self.id(), profile_field)

        self.mValueCache: typing.Dict[int, dict] = dict()

    def _profile_field_index(self, field) -> int:
        if isinstance(field, int):
            return field
        elif isinstance(field, QgsField):
            return self.fields().indexOf(field.name())
        elif isinstance(field, str):
            return self.fields().indexOf(field)
        elif field is None:
            # return default profile_field
            return self.mCurrentProfileFieldIndex
        else:
            return -1

    def __add__(self, other):
        return self._math_(self, '__add__', other)

    def __radd__(self, other):
        return self._math_(other, '__add__', self)

    def __sub__(self, other):
        return self._math_(self, '__sub__', other)

    def __rsub__(self, other):
        return self._math_(other, '__sub__', self)

    def __mul__(self, other):
        return self._math_(self, '__mul__', other)

    def __rmul__(self, other):
        return self._math_(other, '__mul__', self)

    def __truediv__(self, other):
        return self._math_(self, '__truediv__', other)

    def __rtruediv__(self, other):
        return self._math_(other, '__truediv__', self)

    def __div__(self, other):
        return self._math_(self, '__div__', other)

    def __rdiv__(self, other):
        return self._math_(other, '__div__', self)

    def __abs__(self, other):
        return self._math_(self, '__abs__', other)

    def _math_(self, left, op, right):
        """
        handles basic math operations with another SpectralProfile of same lengths
        :param left:
        :param op:
        :param right:
        :return:
        """
        if np.isscalar(left):
            left = np.ones(len(self)) * left
        elif isinstance(left, SpectralProfile):
            left = np.asarray(left.yValues())
        if np.isscalar(right):
            right = np.ones(len(self)) * right
        elif isinstance(right, SpectralProfile):
            right = np.asarray(right.yValues())

        sp = self.clone()
        yvals = getattr(left, op)(right)
        sp.setValues(self.xValues(), yvals)
        return sp

    def fieldNames(self) -> typing.List[str]:
        """
        Returns all profile_field names
        :return:
        """
        return self.fields().names()

    def setName(self, name: str):
        warnings.warn('Not supported anymore, as a name might be retrieved with an expression',
                      DeprecationWarning, stacklevel=2)

    def name(self) -> str:
        warnings.warn('Not supported anymore', DeprecationWarning, stacklevel=2)
        return None

    def setSource(self, uri: str):
        warnings.warn('Not supported anymore', DeprecationWarning, stacklevel=2)

    def source(self):
        warnings.warn('Not supported anymore', DeprecationWarning, stacklevel=2)
        return None

    def setCurrentProfileField(self, field: typing.Union[str, int, QgsField]) -> int:
        """
        Sets the current profile profile_field the SpectralProfile loads and saves data from/to-
        :param field: str|int|QgsField
        """
        self.mCurrentProfileFieldIndex = self._profile_field_index(field)
        return self.mCurrentProfileFieldIndex

    def currentProfileField(self) -> int:
        return self.mCurrentProfileFieldIndex

    def setCoordinates(self, pt):
        if isinstance(pt, SpatialPoint):
            sp = pt.toCrs(SpectralProfile.crs)
            self.setGeometry(QgsGeometry.fromPointXY(sp))
        elif isinstance(pt, QgsPointXY):
            self.setGeometry(QgsGeometry.fromPointXY(pt))

    def geoCoordinate(self):
        return self.geometry()

    def updateMetadata(self, metaData: dict):
        if isinstance(metaData, dict):
            for key, value in metaData.items():
                self.setMetadata(key, value)

    def removeField(self, name):
        fields = self.fields()
        values = self.attributes()
        i = self.fieldNameIndex(name)
        if i >= 0:
            fields.remove(i)
            values.pop(i)
            self.setFields(fields)
            self.setAttributes(values)

    def nb(self, profile_field=None) -> int:
        """
        Returns the number of profile bands / profile values
        :return: int
        :rtype:
        """
        return len(self.yValues(profile_field=profile_field))

    def isEmpty(self, profile_field=None) -> bool:
        """
        Returns True if there is not ByteArray stored in the BLOB value profile_field
        :return: bool
        """
        fidx = self._profile_field_index(profile_field)
        return self.attribute(fidx) in [None, QVariant()]

    def values(self, profile_field_index: typing.List[typing.Union[int, str, QgsField]] = None) -> dict:
        """
        Returns a dictionary with 'x', 'y', 'xUnit' and 'yUnit' values.
        :return: {'x':list,'y':list,'xUnit':str,'yUnit':str, 'bbl':list}
        """
        profile_field_index = self._profile_field_index(profile_field_index)
        if profile_field_index not in self.mValueCache.keys():
            byteArray = self.attribute(profile_field_index)
            d = decodeProfileValueDict(byteArray)

            # save a reference to the decoded dictionary
            self.mValueCache[profile_field_index] = d

        return self.mValueCache[profile_field_index]

    def setValues(self, x=None, y=None, xUnit: str = None, yUnit: str = None, bbl=None, profile_field=None,
                  profile_value_dict: dict = None, **kwds):

        # d = self.values().copy()
        if not isinstance(profile_value_dict, dict):
            profile_value_dict = prepareProfileValueDict(x=x, y=y, xUnit=xUnit, yUnit=yUnit, bbl=bbl,
                                                         prototype=self.values(
                                                             profile_field_index=profile_field))

        field_index = self._profile_field_index(profile_field)
        self.setAttribute(field_index, encodeProfileValueDict(profile_value_dict))
        self.mValueCache[field_index] = profile_value_dict

    def xValues(self, profile_field=None) -> list:
        """
        Returns the x Values / wavelength information.
        If wavelength information is not undefined it will return a list of band indices [0, ..., n-1]
        :return: [list-of-numbers]
        """
        x = self.values(profile_field_index=profile_field)['x']

        if not isinstance(x, list):
            return list(range(len(self.yValues())))
        else:
            return x

    def yValues(self, profile_field=None) -> list:
        """
        Returns the x Values / DN / spectral profile values.
        List is empty if not numbers are stored
        :return: [list-of-numbers]
        """
        y = self.values(profile_field_index=profile_field)['y']
        if not isinstance(y, list):
            return []
        else:
            return y

    def bbl(self, profile_field=None) -> list:
        """
        Returns the BadBandList.
        :return:
        :rtype:
        """
        bbl = self.values(profile_field_index=profile_field).get('bbl')
        if not isinstance(bbl, list):
            bbl = np.ones(self.nb(profile_field=profile_field), dtype=np.byte).tolist()
        return bbl

    def setXUnit(self, unit: str, profile_field=None):
        d = self.values(profile_field_index=profile_field)
        d['xUnit'] = unit
        self.setValues(profile_field=profile_field, **d)

    def xUnit(self, profile_field=None) -> str:
        """
        Returns the semantic unit of x values, e.g. a wavelength unit like 'nm' or 'um'
        :return: str
        """
        return self.values(profile_field_index=profile_field)['xUnit']

    def setYUnit(self, unit: str = None, profile_field=None):
        """
        :param unit:
        :return:
        """
        d = self.values(profile_field_index=profile_field)
        d['yUnit'] = unit
        self.setValues(profile_field=profile_field, **d)

    def yUnit(self, profile_field=None) -> str:
        """
        Returns the semantic unit of y values, e.g. 'reflectances'"
        :return: str
        """

        return self.values(profile_field_index=profile_field)['yUnit']

    def clone(self):
        """
        Create a clone of this SpectralProfile
        :return: SpectralProfile
        """
        return self.__copy__()

    def plot(self) -> QWidget:
        """
        Plots this profile to an new PyQtGraph window
        :return:
        """
        from ..gui.spectrallibraryplotwidget import SpectralProfilePlotDataItem

        pdi = SpectralProfilePlotDataItem(self)
        pdi.setClickable(True)
        pw = pg.plot(title=self.name())
        pw.getPlotItem().addItem(pdi)

        style = PlotStyle.fromPlotDataItem(pdi)
        style.setLineColor('green')
        style.setMarkerSymbol('Triangle')
        style.setMarkerColor('green')
        style.apply(pdi)

        return pw
        # pg.QAPP.exec_()

    def __reduce_ex__(self, protocol):

        return self.__class__, (), self.__getstate__()

    def __getstate__(self):

        if self.mValueCache is None:
            self.values()
        wkt = self.geometry().asWkt()
        state = (qgsFields2str(self.fields()), qgsFieldAttributes2List(self.attributes()), wkt)
        dump = pickle.dumps(state)
        return dump

    def __setstate__(self, state):
        state = pickle.loads(state)
        fields, attributes, wkt = state
        fields = str2QgsFields(fields)
        self.setFields(fields)
        self.setGeometry(QgsGeometry.fromWkt(wkt))
        self.setAttributes(attributes)

    def __copy__(self):
        sp = SpectralProfile(fields=self.fields())
        sp.setId(self.id())
        sp.setAttributes(self.attributes())
        sp.setGeometry(QgsGeometry.fromWkt(self.geometry().asWkt()))
        if isinstance(self.mValueCache, dict):
            sp.values()
        return sp

    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if not np.array_equal(self.fieldNames(), other.fieldNames()):
            return False

        names1 = self.fieldNames()
        names2 = other.fieldNames()
        for i1, n in enumerate(self.fieldNames()):
            if n == FIELD_FID:
                continue
            elif n == FIELD_VALUES:
                if self.xValues() != other.xValues():
                    return False
                if self.yValues() != other.yValues():
                    return False
                if self.xUnit() != other.xUnit():
                    return False
            else:
                i2 = names2.index(n)
                if self.attribute(i1) != other.attribute(i2):
                    return False

        return True

    def __hash__(self):

        return hash(id(self))

    def setId(self, id):
        self.setAttribute(FIELD_FID, id)
        if id is not None:
            super(SpectralProfile, self).setId(id)

    """
    def __eq__(self, other):
        if not isinstance(other, SpectralProfile):
            return False
        if len(self.mValues) != len(other.mValues):
            return False
        return all(a == b for a,b in zip(self.mValues, other.mValues)) \
            and self.mValuePositions == other.mValuePositions \
            and self.mValueUnit == other.mValueUnit \
            and self.mValuePositionUnit == other.mValuePositionUnit \
            and self.mGeoCoordinate == other.mGeoCoordinate \
            and self.mPxCoordinate == other.mPxCoordinate

    def __ne__(self, other):
        return not self.__eq__(other)
    """

    def __len__(self):
        return len(self.yValues())


class SpectralSetting(object):
    """
    A spectral settings described the boundary conditions of one or multiple spectral profiles with
    n y-values, e.g. reflectances or radiances, by
    1. n x values, e.g. the wavelenght of each band
    2. an xUnit, e.g. the wavelength unit 'micrometers'
    3. an yUnit, e.g. 'reflectance'
    """

    def __init__(self, x, xUnit: str = None, yUnit=None, bbl: list = None, field_name: str = None):

        assert isinstance(x, (tuple, list, np.ndarray))

        if isinstance(x, np.ndarray):
            x = x.tolist()
        if isinstance(x, list):
            x = tuple(x)

        self._x: typing.Tuple = x
        self._xUnit: str = xUnit
        self._yUnit: str = yUnit
        self._bbl: list = bbl
        self._hash = hash((self._x, self._xUnit, self._yUnit, self._bbl))
        self._field_name: str = field_name

    def fieldName(self) -> str:
        """
        Returns the name of the QgsField to which profiles within this setting are linked to
        :return: str
        """
        return self._field_name

    def __str__(self):
        return f'SpectralSetting:({self.n_bands()} bands {self.xUnit()} {self.yUnit()})'.strip()

    def x(self) -> typing.List:
        return list(self._x)

    def n_bands(self) -> int:
        return len(self._x)

    def yUnit(self):
        return self._yUnit

    def xUnit(self):
        return self._xUnit

    def bbl(self):
        return self._bbl

    def __eq__(self, other):
        if not isinstance(other, SpectralSetting):
            return False
        return self._hash == other._hash

    def __hash__(self):
        return self._hash


def groupBySpectralProperties(profiles: typing.List[SpectralProfile],
                              excludeEmptyProfiles: bool = True,
                              profile_field: typing.Union[int, str, QgsField] = None
                              ) -> typing.Dict[SpectralSetting, typing.List[SpectralProfile]]:
    """
    Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

        xValues: None | [list-of-xvalues with n>0 elements]
        xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
        yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

    :return: {SpectralSetting:[list-of-profiles]}
    """

    results = dict()

    # will be initialized with 1st SpectralProfile
    p_field = profile_field
    p_field_idx = None

    for p in profiles:
        assert isinstance(p, SpectralProfile)
        if p_field_idx is None:
            # initialize the profile field to group profiles on
            p_fields = profile_fields(p)
            p_field_indices = profile_field_indices(p)
            p_field_names = [f.name() for f in p_fields]

            if profile_field is None:
                p_field = p_fields[0]
                p_field_idx = p_field_indices[0]
            elif isinstance(profile_field, int):
                assert profile_field in p_field_indices
                p_field_idx = profile_field
                p_field = p_fields[p_field_indices.index(p_field_idx)]
            elif isinstance(profile_field, str):
                p_field_idx = p_field_indices[p_field_names.index(profile_field)]
                p_field = p_fields[p_field_names.index(profile_field)]
            elif isinstance(profile_field, QgsField):
                p_field_idx = p_field_indices[p_field_names.index(profile_field.name())]
                p_field = p_fields[p_field_names.index(profile_field.name())]

        d = p.values(profile_field_index=p_field_idx)

        if excludeEmptyProfiles:
            if not isinstance(d['y'], list):
                continue
            if not len(d['y']) > 0:
                continue

        x = p.xValues(profile_field=p_field_idx)
        if len(x) == 0:
            x = None
        # y = None if d['y'] in [None, []] else tuple(d['y'])

        xUnit = None if d['xUnit'] in [None, ''] else d['xUnit']
        yUnit = None if d['yUnit'] in [None, ''] else d['yUnit']

        key = SpectralSetting(x=x, xUnit=xUnit, yUnit=yUnit, field_name=p_field.name())

        if key not in results.keys():
            results[key] = []
        results[key].append(p)
    return results


class SpectralProfileBlock(object):
    """
    A block of spectral profiles that share the same properties like wavelength, wavelength unit etc.
    """

    @staticmethod
    def dummy(n=5, n_bands=10, wlu='nm') -> typing.Optional['SpectralProfileBlock']:
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
    def fromSpectralLibrary(speclib: QgsVectorLayer,
                            profile_field: typing.Union[int, str, QgsField] = None,
                            feedback: QgsProcessingFeedback = None):
        if profile_field is None:
            profile_field = first_profile_field_index(speclib)
            assert profile_field > -1, 'QgsVectorLayer does not contain a profile column'
        from .spectrallibrary import read_profiles
        return SpectralProfileBlock.fromSpectralProfiles(read_profiles(speclib, profile_field=profile_field),
                                                         profile_field=profile_field,
                                                         feedback=feedback)

    @staticmethod
    def fromSpectralProfiles(profiles: typing.List[SpectralProfile],
                             profile_field: typing.Union[int, str, QgsField],
                             feedback: QgsProcessingFeedback = None):

        for spectral_setting, profiles in groupBySpectralProperties(profiles,
                                                                    profile_field=profile_field,
                                                                    excludeEmptyProfiles=True).items():
            ns: int = len(profiles)
            fids = [p.id() for p in profiles]
            nb = spectral_setting.n_bands()
            ref_profile = np.asarray(profiles[0].yValues())
            dtype = ref_profile.dtype
            blockArray = np.empty((nb, 1, ns), dtype=dtype)
            blockArray[:, 0, 0] = ref_profile

            for i in range(1, len(profiles)):
                blockArray[:, 0, i] = np.asarray(profiles[i].yValues(), dtype=dtype)
            block = SpectralProfileBlock(blockArray, spectral_setting, fids=fids)
            yield block

    @staticmethod
    def fromSpectralProfile(self, profile: SpectralProfile):

        data = np.asarray(profile.yValues())

        setting = SpectralSetting(profile.xValues(), xUnit=profile.xUnit(), yUnit=profile.yUnit())
        return SpectralProfileBlock(data, setting, fids=[profile.id()])

    def __init__(self, data: np.ndarray,
                 spectralSetting: SpectralSetting,
                 fids: typing.List[int] = None,
                 metadata: dict = None):

        assert isinstance(spectralSetting, SpectralSetting)
        assert isinstance(data, np.ndarray)
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
        self.mFIDs: typing.List[int] = None

        if not isinstance(metadata, dict):
            metadata = dict()
        self.mMetadata = metadata

        if fids is not None:
            self.setFIDs(fids)

    def metadata(self) -> dict:
        """
        Returns a copy of the metadata
        :return:
        """
        return self.mMetadata.copy()

    def setFIDs(self, fids: typing.List[int]):
        """
        :param fids:
        :return:
        """
        assert len(fids) == self.n_profiles(), \
            f'Number of Feature IDs ({len(fids)}) must be equal to number of profiles ({self.n_profiles()})'
        self.mFIDs = fids

    def fids(self) -> typing.List[int]:
        return self.mFIDs

    def spectralSetting(self) -> SpectralSetting:
        return self.mSpectralSetting

    def xValues(self) -> np.ndarray:
        return self.mXValues

    def xUnit(self) -> str:
        return self.mSpectralSetting.xUnit()

    def n_profiles(self) -> int:
        return int(np.product(self.mData.shape[1:]))

    def n_bands(self) -> int:
        return self.mData.shape[0]

    def yUnit(self) -> str:
        return self.mSpectralSetting.yUnit()

    def toVariantMap(self) -> dict:

        kwds = dict()
        kwds['metadata'] = self.metadata()
        kwds['profiledata'] = self.mData
        kwds['keys'] = self.mFIDs
        SS = self.spectralSetting()
        kwds['x'] = SS.x()
        kwds['x_unit'] = SS.xUnit()
        kwds['y_unit'] = SS.yUnit()
        kwds['bbl'] = SS.bbl()

        return kwds

    @staticmethod
    def fromVariantMap(kwds: dict) -> typing.Optional['SpectralProfileBlock']:

        values = kwds['profiledata']
        assert isinstance(values, np.ndarray)

        SS = SpectralSetting(kwds.get('x', list(range(values.shape[0]))),
                             xUnit=kwds.get('x_unit', None),
                             yUnit=kwds.get('y_unit'),
                             bbl=kwds.get('bbl')
                             )
        return SpectralProfileBlock(values, SS,
                                    fids=kwds.get('keys', None),
                                    metadata=kwds.get('metadata', None)
                                    )

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

    def __iter__(self):
        y, x = self.mData.shape[1:]

        xValues = self.wavelengths()
        xUnit = self.wavelengthUnit()
        yUnit = self.yUnit()

        for j in range(y):
            for x in range(x):
                yValues = self.mData[:, y, x]
                profile = SpectralProfile()
                profile.setValues(x=xValues, y=yValues, xUnit=xUnit, yUnit=yUnit)
                yield profile

        encodeProfileValueDict()

    def profileValueDictionaries(self) -> typing.List[dict]:
        """
        Converts the block data into profile value dictionaries
        :return:
        """
        yy, xx = np.unravel_index(np.arange(self.n_profiles()), self.mData.shape[1:])
        spectral_settings = self.spectralSetting()

        xUnit = spectral_settings.xUnit()
        yUnit = spectral_settings.yUnit()
        xValues = spectral_settings.x()

        for j, i in zip(yy, xx):
            d = prepareProfileValueDict(x=xValues,
                                        y=self.mData[:, j, i],
                                        xUnit=xUnit,
                                        yUnit=yUnit)
            yield d

    def profileValueByteArrays(self) -> typing.List[QByteArray]:
        """
        Converts the block profiles data into serialized profile value dictionaries
        :return:
        """
        for d in self.profileValueDictionaries():
            yield encodeProfileValueDict(d)

    def data(self) -> np.ndarray:
        """
        Spectral profiles as np.ndarray with (always) 3 dimensions:
        (bands, profile number, 1) or - e.g. if profiles are from a spectral library
        (bands, y position, x position) - e.g. if profiles come from an image subset
        :return: np.ndarray
        """
        return self.mData


class SpectralProfileLoadingTask(QgsTask):

    def __init__(self, speclib: QgsVectorLayer,
                 fids: typing.List[int] = None,
                 callback: typing.Callable = None):
        super().__init__('Load spectral profiles', QgsTask.CanCancel)
        assert isinstance(speclib, QgsVectorLayer)
        self.mCallback: typing.Callable = callback
        self.mSpeclib: QgsVectorLayer = speclib
        self.mSpeclibSource: str = speclib.source()
        self.mPathSpeclib: pathlib.Path = pathlib.Path(speclib.source())
        self.mProfileFields: typing.List[QgsField] = profile_fields(speclib)

        if fids:
            #
            fids = list(set(fids).intersection(speclib.allFeatureIds()))
            assert isinstance(fids, list)
        self.mFIDs = fids
        self.exception: Exception = None
        assert len(self.mProfileFields) > 0
        self.mTimeDelta = datetime.timedelta(seconds=2)
        self.RESULTS: typing.Dict[int, SpectralProfile] = dict()

    def dependentLayers(self):
        return [self.mSpeclibSource]

    def canCancel(self) -> bool:
        return True

    def finished(self, result: bool):
        if self.mCallback is not None:
            self.mCallback(result, self)

    def run(self):

        try:
            speclib = self.mSpeclib

            if not isinstance(speclib, QgsVectorLayer):
                options = QgsVectorLayer.LayerOptions(loadDefaultStyle=False)
                speclib = QgsVectorLayer(self.mPathSpeclib.as_posix(), options=options)
            assert speclib.isValid()
            field_indices = [speclib.fields().lookupField(f.name()) for f in self.mProfileFields]

            request = QgsFeatureRequest()
            t_progress = datetime.datetime.now() + self.mTimeDelta

            if self.mFIDs:
                request.setFilterFids(self.mFIDs)
                n_total = len(self.mFIDs)
            else:
                n_total = speclib.featureCount()

            n_done = 0
            for f in speclib.getFeatures(request):
                if self.isCanceled():
                    return False

                f: QgsFeature
                sp = SpectralProfile.fromQgsFeature(f, profile_field=field_indices[0])
                for idx in field_indices:
                    # de-serialize the profile information
                    sp.values(profile_field_index=idx)
                self.RESULTS[sp.id()] = sp
                n_done += 1

                if n_done % 25 == 0:
                    if datetime.datetime.now() > t_progress:
                        t_progress += self.mTimeDelta
                        self.setProgress(n_done / n_total * 100)
                        # self.sigProfilesLoaded.emit(LoadedProfiles(RESULTS))
                        # RESULTS = dict()
                # if len(RESULTS) > 0:
                #    self.sigProfilesLoaded.emit(LoadedProfiles(RESULTS))
            self.setProgress(100)
        except Exception as ex:
            self.exception = ex
            return False

        return True
