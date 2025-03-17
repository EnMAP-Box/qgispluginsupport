import enum
import os.path
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple, Union

import numpy as np
from osgeo import gdal
from osgeo.gdal import Band

from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsDefaultValue, QgsFeature, QgsField, QgsFieldConstraints, QgsObjectCustomProperties, \
    QgsRasterDataProvider, QgsRasterLayer, QgsVectorLayer, QgsVectorLayerCache
from qgis.gui import QgsAttributeTableFilterModel, QgsAttributeTableModel, QgsAttributeTableView, QgsMapCanvas
from .qgisenums import QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from .unitmodel import UnitLookup

rx_bands = re.compile(r'^band[_\s]*(?P<band>\d+)$', re.IGNORECASE)
rx_more_information = re.compile(r'^more[_\n]*information$', re.IGNORECASE)
rx_key_value_pair = re.compile(r'^(?P<key>[^=]+)=(?P<value>.+)$')
rx_envi_array = re.compile(r'^{\s*(?P<value>([^}]+))\s*}$')

rx_is_int = re.compile(r'^\s*\d+\s*$')

EXCLUDED_GDAL_DOMAINS = ['IMAGE_STRUCTURE', 'DERIVED_SUBDATASETS']


def stringsToInts(values: List[str]) -> Union[List[Optional[int]]]:
    results = []
    for v in values:
        try:
            n = int(v)
            results.append(n)
        except ValueError:
            results.append(None)
    return results


def stringsToNums(values: List[str]) -> Union[List[Optional[int]], List[Optional[float]]]:
    results = []
    for v in values:
        try:
            n = float(v)
            n = int(n) if n.is_integer() else n
            results.append(n)
        except (ValueError, TypeError):
            results.append(None)
    return results


def stringToType(value: str):
    """
    Converts a string into a matching int, float or string
    """
    if not isinstance(value, str):
        return value

    if rx_is_int.match(value):
        return int(value.strip())
    else:
        try:
            return float(value.strip())
        except ValueError:
            pass
    return value


def stringToTypeList(value: str) -> List:
    """
    extracts a list of types from the string in 'value'
    """
    matchENVI = rx_envi_array.match(value)
    if matchENVI:
        # removes leading & trailing { and spaces }
        value = matchENVI.group('value')
        # remove inline comments

    return [stringToType(v) for v in re.split(r'[\s,;]+', value)]


class SpectralPropertyOrigin(object):
    """
    A key that indicates from which metadata source the SpectralPropertyKey was read
    """
    ProviderHtml = 'provider_html'
    GDALBand = 'gdal_band'
    GDALDataset = 'gdal_dataset'
    Deduced = 'deduced'  # deduced from other data values
    LayerProperties = 'layer_property'


class SpectralPropertyKeys(enum.StrEnum):
    """
    Enumeration of Spectral Property Keys
    """
    BadBand = 'bbl'
    Wavelength = 'wavelength'
    WavelengthUnit = 'wavelength_unit'
    FWHM = 'fwhm'
    BandWidth = 'bandwidth'
    DataOffset = 'data_offset'
    DataGain = 'data_gain'
    DataReflectanceOffset = 'data_reflectance_offset'
    DataReflectanceGain = 'data_reflectance_gain'
    AcquisitionDateTime = 'acquisition_datetime'
    StartTime = 'start_time'
    EndTime = 'end_time'


class QgsRasterLayerSpectralProperties(QgsObjectCustomProperties):
    """
    Stores spectral properties of a raster layer source
    """
    LOOKUP_PATTERNS = {
        SpectralPropertyKeys.FWHM: re.compile(
            r'^(fwhm|full[ -_]width[ -_]half[ -_]maximum)$', re.I),
        SpectralPropertyKeys.BadBand: re.compile(
            r'^(bbl|bad[ -_]?Band|bad[ -_]?band[ -_]?multiplier|bad[ -_]?band[ -_]?list)$', re.I),
        SpectralPropertyKeys.WavelengthUnit: re.compile(
            r'^(wlu|wavelength[ -_]??units?)$', re.I),
        SpectralPropertyKeys.Wavelength: re.compile(
            r'^(wl|wavelengths?|center[_ ]?wavelengths?)$', re.I),
        SpectralPropertyKeys.BandWidth: re.compile(
            r'^(bw|bandwiths?)$', re.I),
        SpectralPropertyKeys.DataGain: re.compile(
            r'^(data[ -_]?gain([ -_]?values?)?)$', re.I),
        SpectralPropertyKeys.DataOffset: re.compile(
            r'^(data[ -_]?offset([ -_]?values?)?)$', re.I),
        SpectralPropertyKeys.DataReflectanceGain: re.compile(
            r'^(data[ -_]?reflectance[ -_]?gain([ -_]?values?)?)$', re.I),
        SpectralPropertyKeys.DataReflectanceOffset: re.compile(
            r'^(data[ -_]?reflectance[ -_]?offset([ -_]?values?)?)$', re.I),
        SpectralPropertyKeys.AcquisitionDateTime: re.compile(
            r'^(acquisition[ -_]?datetime$)', re.I),
        SpectralPropertyKeys.StartTime: re.compile(r'^start[ -_]?time$', re.I),
        SpectralPropertyKeys.EndTime: re.compile(r'^end[ -_]?time$', re.I)
    }

    @classmethod
    def combinedLookupPattern(cls) -> Pattern:
        patters = '|'.join([rx.pattern for rx in QgsRasterLayerSpectralProperties.LOOKUP_PATTERNS.values()])
        return re.compile(f'({patters})', re.IGNORECASE)

    @classmethod
    def fromRasterLayer(cls, layer: Union[QgsRasterLayer, gdal.Dataset, str, Path]) \
            -> Optional['QgsRasterLayerSpectralProperties']:
        """
        Returns the QgsRasterLayerSpectralProperties for a raster layer
        """

        layer = cls.asRasterLayer(layer)

        if not (isinstance(layer, QgsRasterLayer)
                and layer.isValid() and layer.bandCount() > 0):
            return None
        obj = cls(layer.bandCount())
        # read from layer custom properties
        obj.readFromLayer(layer, overwrite=False)
        # read missing properties from data provider / data source
        obj.readFromProvider(layer.dataProvider(), overwrite=False)

        return obj

    def __init__(self, bandCount: int):
        assert bandCount > 0
        super().__init__()
        self.mBandCount = bandCount

    def __eq__(self, other):
        if not isinstance(other, QgsRasterLayerSpectralProperties):
            return False
        k1 = set(self.keys())
        k2 = set(other.keys())
        if k1 != k2:
            return False
        for k in k1:
            if self.value(k) != other.value(k):
                return False
        return True

    def bandCount(self) -> int:
        """
        Returns the band count.
        """
        return self.mBandCount

    @staticmethod
    def itemKey(itemKey: str) -> str:
        """
        Returns a normalized item key according to the patterns registered in
        QgsRasterLayerSpectralProperties.NORMALIZATION_PATTERNS.
        For example FWHM or FullWidthHalfMaximum is normalized to fwhm.

        Note that only the last section of a key is normalized.
        For example section/FWHM -> section/fwhm but
                    FWHM/BadBandList -> FWHM/bbl
        """
        sections = itemKey.split('/')
        for replacement, rx in QgsRasterLayerSpectralProperties.LOOKUP_PATTERNS.items():

            match = rx.search(sections[-1])
            if match:
                sections[-1] = sections[-1].replace(match.group(), replacement)

        return '/'.join(sections)

    # @staticmethod
    # def bandKey(bandNo: int) -> str:
    #    """
    #    Generates a band key like "band_3"
    #    """
    #    assert bandNo > 0
    #    return f'band_{bandNo}'

    # def bandItemKey(self, bandNo: int, itemKey: str):
    #    """
    #    Generates a band item key like "band_3/itemA"
    #    """
    #    return f'{self.bandKey(bandNo)}/{self.itemKey(itemKey)}'

    # def bandValue(self, bandNo: int, itemKey: str) -> Any:
    #    """
    #    Returns the band values for band bandNo and a specific item key.
    #    """
    #    return self.bandValues([bandNo], itemKey)[0]

    # def setBandValue(self, bandNo: Union[int, str], itemKey: str, value):
    #    self.setBandValues([bandNo], itemKey, [value])

    def setBandValues(self, bands: Optional[List[int]], itemKey: str, values, origin: str = None):
        """
        Sets the n values to the corresponding n bands
        if bands = None|'all'|'*'|':', it is expected values contains either a single value or n = bandCount() values.
        """
        assert isinstance(itemKey, str)
        if bands in [None, 'all', '*', ':']:
            bands = list(range(1, self.bandCount() + 1))
        for b in bands:
            assert isinstance(b, int) and 0 < b <= self.bandCount()
        if isinstance(values, (str, int, float)):
            values = [values for _ in bands]
        elif isinstance(values, list) and len(values) == 1 and len(bands) > 1:
            values = [values[0] for _ in bands]

        assert len(values) == len(bands)
        assert 0 < len(bands) <= self.bandCount()

        itemKey = self.itemKey(itemKey)

        data: dict = self.value(itemKey, {})
        for value, band in zip(values, bands):
            # self.setValue(self.bandItemKey(band, itemKey), value)
            data[band] = value
        if origin:
            data['_origin_'] = origin
        self.setValue(itemKey, data)

    def bandValues(self, bands: Optional[List[int]], itemKey, default=None) -> List[Any]:
        """
        Returns the n values for n bands and itemKey.
        Returns the default value in case the itemKey is undefined for a band.
        """
        if bands in [None, 'all']:
            bands = list(range(1, self.bandCount() + 1))
        itemKey = self.itemKey(itemKey)
        data: dict = self.value(itemKey, {})
        assert isinstance(data, dict)
        return [data.get(b, default) for b in bands]

        # values = [self.value(f'{self.bandKey(b)}/{itemKey}') for b in bands]
        # if default is not None:
        #    values = [v if v is not None else default for v in values]
        # return values

    def dataOffsets(self, default: Optional[Union[int, float]] = None) -> Optional[List[Optional[float]]]:
        return self.bandValues(None, SpectralPropertyKeys.DataOffset, default=default)

    def dataGains(self, default: Optional[Union[int, float]] = None) -> Optional[List[Optional[float]]]:
        return self.bandValues(None, SpectralPropertyKeys.DataGain, default=default)

    def setWavelengths(self, values):
        """
        Shortcut to set the wavlengths for all bands
        :param values:
        """
        self.setBandValues('*', SpectralPropertyKeys.Wavelength, values)

    def setWavelengthUnits(self, units):
        """
        Shortcut to set the wavelength units
        :param units:
        """
        self.setBandValues('*', SpectralPropertyKeys.WavelengthUnit, units)

    def wavelengths(self) -> Optional[List[Optional[float]]]:
        """
        Returns n = .bandCount() wavelengths.
        """
        return self.bandValues(None, SpectralPropertyKeys.Wavelength)

    def wavelengthUnits(self) -> List[str]:
        """
        Returns n= .bandCount() wavelength units.
        """
        return self.bandValues(None, SpectralPropertyKeys.WavelengthUnit)

    def badBands(self, default: Optional[int] = None) -> List[int]:
        """
        Convenience function to return bad band (multiplier) values as list
        0 = False = do not use
        1 = True = do not use
        None = Not set
        values > 1 might be used for other special meanings

        Potentially other values can be used as well, for example to add different masks.
        Assumes 1 = True by default.
        """
        return [int(v) if isinstance(v, int) else v
                for v in self.bandValues(None, SpectralPropertyKeys.BadBand, default=default)]

    def fwhm(self, default=None) -> List[float]:
        """
        Returns the FWHM values for each band
        """
        return self.bandValues(None, SpectralPropertyKeys.FWHM, default=default)

    def fullWidthHalfMaximum(self, default=None) -> List[float]:
        """
        Returns the FWHM values for each band
        """
        return self.fwhm(default)

    @classmethod
    def asRasterLayer(cls,
                      layer: Union[QgsRasterLayer, str, Path, gdal.Dataset],
                      loadDefaultStyle: bool = False) -> Optional[QgsRasterLayer]:

        if isinstance(layer, gdal.Dataset):
            layer = layer.GetDescription()

        if isinstance(layer, Path):
            layer = layer.as_posix()

        if isinstance(layer, str):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=loadDefaultStyle)
            layer = QgsRasterLayer(layer, name=os.path.basename(layer), options=options)

        if isinstance(layer, QgsRasterLayer) and layer.isValid():
            return layer

        return None

    def writeToLayer(self, layer: Union[QgsRasterLayer, str, Path]) -> Optional[QgsRasterLayer]:
        """
        Saves the spectral properties into the custom layer properties of a QgsRasterLayer.
        Does not affect the underlying data source.
        Returns the used QgsRasterLayer instance, e.g. to be used in subclasses.
        See .readFromLayer(layer: QgsRasterLayer)
        :param layer:
        :return:
        """

        layer = self.asRasterLayer(layer)
        assert layer.isValid()
        assert layer.bandCount() == self.bandCount()

        for key in SpectralPropertyKeys:
            if key in self.keys():
                values = self.bandValues(None, key)
                layer.setCustomProperty(key, values)

        if False:
            # backward compatibility QGISPAM:
            # see https://enmap-box.readthedocs.io/en/latest/dev_section/rfc_list/rfc0002.html

            def writeQGISPAM(attribute_key: str, values: list):
                for i, v in enumerate(values):
                    pamkey = f'QGISPAM/band/{i + 1}//{attribute_key}'
                    layer.setCustomProperty(pamkey, v)

            if SpectralPropertyKeys.Wavelength in self.keys():
                writeQGISPAM('wavelengths', self.wavelengths())
            if SpectralPropertyKeys.WavelengthUnit in self.keys():
                writeQGISPAM('wavelength_units', self.wavelengthUnits())
            if SpectralPropertyKeys.FWHM in self.keys():
                writeQGISPAM('fwhm', self.wavelengthUnits())
            if SpectralPropertyKeys.BadBand in self.keys():
                writeQGISPAM('bad_band_multiplier', self.wavelengthUnits())

        return layer

    def writeToSource(self, layer: [QgsRasterLayer, str, Path], write_envi: bool = False) -> bool:
        """
        Tries to save the spectral properties to a data source
        :param write_envi: bool, set True to write in case of GDAL Datasets values explicitly into the ENVI domain.
        :param layer:
        :return:
        """
        layer = self.asRasterLayer(layer)
        assert layer and layer.isValid()
        assert layer.bandCount() == self.bandCount()

        src = layer.source()
        basename = layer.name()
        provider = layer.dataProvider().name()
        layer.setDataSource('', '', '')

        if provider == 'gdal':
            with gdal.Open(src) as ds:
                self.writeToGDALDataset(ds, write_envi=write_envi)

        layer.setDataSource(src, basename, provider)
        return True

    def convertToMicrometers(self,
                             wl: List[Union[float, int, None]],
                             wlu: List[Union[str, None]]) -> Tuple[List[Union[float, None]], List[Union[float, None]]]:
        """
        Converts a list of wavelength values wl with wavelength units wlu into micrometers.
        :param wl: list of wavelength values
        :param wlu: list of corresponding wavelength units
        :return: wavelengths in micrometers.
        """
        wl_um = []
        wlu_um = []
        for v, u in zip(wl, wlu):
            if v is not None and u is not None:
                wl_um.append(UnitLookup.convertLengthUnit(v, u, 'μm'))
                wlu_um.append('μm')
            else:
                wl_um.append(None)
                wlu_um.append(None)

        return wl_um, wlu_um

    @classmethod
    def wrapEnviList(cls, values: list):
        """
        Converts a list of values into an ENVI Header style list entry string.
        See https://www.nv5geospatialsoftware.com/docs/ENVIHeaderFiles.html
        :param values: list of values, e.g. [400, 500, 600]
        :return: string like '{400, 500, 600}'
        """
        values = ','.join([str(v) for v in values])
        return f'{{{values}}}'

    def writeToGDALDataset(self, ds: gdal.Dataset, write_envi: bool = False):

        wl = self.wavelengths()
        wlu = self.wavelengthUnits()
        fwhm = self.fwhm()
        bbl = self.badBands()

        offsets = self.dataOffsets()
        gains = self.dataGains()

        # convert wl and fwhm to micrometers (or None)
        wl_um, _ = self.convertToMicrometers(wl, wlu)
        fwhm_um, _ = self.convertToMicrometers(fwhm, wlu)

        for b in range(self.bandCount()):
            band: gdal.Band = ds.GetRasterBand(b + 1)

            if wl[b] is not None:
                band.SetMetadataItem('CENTRAL_WAVELENGTH_UM', str(wl_um[b]), 'IMAGERY')
            if fwhm[b] is not None:
                band.SetMetadataItem('FWHM_UM', str(fwhm_um[b]), 'IMAGERY')
            if bbl[b] is not None:
                band.SetMetadataItem('bbl', str(bbl[b]))

            if offsets[b] is not None:
                band.SetOffset(offsets[b])

            if gains[b] is not None:
                band.SetScale(gains[b])

        if write_envi:
            if any(wl):
                ds.SetMetadataItem('wavelengths', self.wrapEnviList(wl), 'ENVI')

            for v in wlu:
                if v not in [None, '']:
                    ds.SetMetadataItem('wavelength units', v, 'ENVI')
                    break

            if any(fwhm):
                ds.SetMetadataItem('fwhm', self.wrapEnviList(fwhm), 'ENVI')

            if any(bbl):
                ds.SetMetadataItem('bbl', self.wrapEnviList(bbl), 'ENVI')

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument):
        """
        Writes the spectral properties as XML
        """
        root = doc.createElement('spectralproperties')
        super().writeXml(root, doc)
        parentNode.appendChild(root)

    def readXml(self, parentNode, keyStartsWith: str = ''):
        """
        Reads the spectral properties from and QDomNode
        """
        root = parentNode.namedItem('spectralproperties')
        if root.isNull():
            return None
        else:
            super(QgsRasterLayerSpectralProperties, self).readXml(root, keyStartsWith=keyStartsWith)

    def readFromLayer(self, layer: QgsRasterLayer, overwrite: bool = False):
        """
        Reads spectral properties from QgsRasterLayer custom layer properties.
        :param layer: QgsRasterLayer
        :param overwrite: bool, if set True, will overwrite existing spectral properties,
                          e.g. properties derived from a GDAL dataset.
        """
        assert isinstance(layer, QgsRasterLayer)

        customProperties = layer.customProperties()
        assert self.bandCount() == layer.bandCount()

        for k in SpectralPropertyKeys:
            if k in self.keys() and overwrite is False:
                # key exists in properties, do not overwrite
                continue

            rx = self.LOOKUP_PATTERNS[k]
            if rx is None:
                continue

            for k2 in customProperties.keys():

                cleaned_key = re.sub(r'^(enmapbox|qps)/', '', k2, re.I)

                if rx.match(cleaned_key):
                    values = customProperties.value(k2)

                    #  stored as list of values
                    if isinstance(values, list):
                        if len(values) in [self.bandCount(), 1]:
                            self.setBandValues(None, k, values, origin=SpectralPropertyOrigin.LayerProperties)

                    # stored as Dict[<band number>] = <band values>
                    elif isinstance(values, dict):
                        _values = []
                        _bands = []
                        for b in range(1, self.bandCount() + 1):
                            if b in values:
                                _values.append(values[b])
                                _bands.append(b)
                        if len(_values) > 0:
                            self.setBandValues(_bands, _values, origin=SpectralPropertyOrigin.LayerProperties)

            if SpectralPropertyKeys.Wavelength in self.keys() and SpectralPropertyKeys.WavelengthUnit not in self.keys():
                wlu = self.deduceWavelengthUnit(self.wavelengths())
                if wlu:
                    self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, wlu,
                                       origin=SpectralPropertyOrigin.Deduced)

    def readFromGDALDataset(self, ds: gdal.Dataset, overwrite: bool = False):
        """
        Reads spectral properties from a GDAL Dataset
        :param overwrite: overwrite existing values, e.g. those found in layer custom properties
        :param ds: gdal.Dataset
        """
        assert isinstance(ds, gdal.Dataset)

        # reads metadata from GDAL data sets
        # priority:

        # 1. band level first, data set level second
        # 2. default domain first, ENVI domain, other domains

        def domainList(mo: gdal.MajorObject) -> List[str]:
            """
            Returns a list of domain keys available for the GDAL object
            :param mo: MajorObject
            :return: list of domain strings
            """
            domains = mo.GetMetadataDomainList()
            domains = [] if domains is None else [d for d in domains if d not in EXCLUDED_GDAL_DOMAINS]
            return domains

        def singleValue(b: gdal.MajorObject, key: str) -> Optional[str]:
            """
            Returns a band value if it matches the regular expression defined by 'key'
            :param b: gdal.Band
            :param key: SpectralPropertyKeys.<key>
            :return: str value or None
            """
            rx = self.LOOKUP_PATTERNS[key]
            for d in domainList(b):
                md: Dict[str, str] = b.GetMetadata_Dict(d)
                for k, v in md.items():
                    if rx.match(k) and v not in ['', None]:
                        return v
            return None

        def valueList(mo: gdal.MajorObject, key: str) -> Optional[List[str]]:
            values = singleValue(mo, key)
            if values:
                result = [v.strip() for v in re.split(r'[, {}]+', values)]
                return [v for v in result if len(v) > 0]
            return None

        # 1- look into IMAGERY domain
        # https://gdal.org/en/stable/user/raster_data_model.html#imagery-domain-remote-sensing

        band_wl = []
        band_wlu = []
        band_fwhm = []
        band_bbl = []
        band_offset = []
        band_scale = []
        band_ref_scale = []
        band_ref_offset = []

        o_wl = o_wlu = o_fwhm = o_bbl = o_offset = o_scale = o_ref_scale = o_ref_offset = SpectralPropertyOrigin.GDALBand
        for b in range(ds.RasterCount):
            band: Band = ds.GetRasterBand(b + 1)

            # 1. try IMAGERY domain
            wl = band.GetMetadataItem('CENTRAL_WAVELENGTH_UM', 'IMAGERY')
            fwhm = band.GetMetadataItem('FWHM_UM', 'IMAGERY')
            wlu = None
            if wl:
                wlu = 'μm'

            if wl is None:
                wl = singleValue(band, SpectralPropertyKeys.Wavelength)

            if fwhm is None:
                fwhm = singleValue(band, SpectralPropertyKeys.FWHM)

            if wlu is None:
                wlu = singleValue(band, SpectralPropertyKeys.WavelengthUnit)

            bbl = singleValue(band, SpectralPropertyKeys.BadBand)
            offset = band.GetOffset()
            scale = band.GetScale()

            refl_offset = singleValue(band, SpectralPropertyKeys.DataReflectanceOffset)
            refl_scale = singleValue(band, SpectralPropertyKeys.DataReflectanceGain)

            band_wl.append(wl)
            band_fwhm.append(fwhm)
            band_wlu.append(wlu)
            band_bbl.append(bbl)
            band_offset.append(offset)
            band_scale.append(scale)
            band_ref_scale.append(refl_scale)
            band_ref_offset.append(refl_offset)

        if not any(band_wl):
            # search in dataset domains
            band_wl = valueList(ds, SpectralPropertyKeys.Wavelength)
            o_wl = SpectralPropertyOrigin.GDALDataset

        if not any(band_wlu):
            band_wlu = valueList(ds, SpectralPropertyKeys.WavelengthUnit)
            o_wlu = SpectralPropertyOrigin.GDALDataset

        if not any(band_bbl):
            band_bbl = valueList(ds, SpectralPropertyKeys.BadBand)
            o_bbl = SpectralPropertyOrigin.GDALDataset

        if not any(band_fwhm):
            band_fwhm = valueList(ds, SpectralPropertyKeys.FWHM)
            o_fwhm = SpectralPropertyOrigin.GDALDataset

        def anyValue(values: Optional[list]) -> bool:
            if values is None:
                return False
            return any([v is not None for v in values])

        def canWrite(values, key) -> bool:

            if overwrite is False and key in self.keys():
                return False
            return anyValue(values)

        # set wavelength
        if canWrite(band_wl, SpectralPropertyKeys.Wavelength):
            band_wl = stringsToNums(band_wl)
            self.setBandValues(None, SpectralPropertyKeys.Wavelength, band_wl, origin=o_wl)

        if overwrite or SpectralPropertyKeys.WavelengthUnit not in self.keys():

            if anyValue(band_wlu):
                self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, band_wlu, origin=o_wlu)
            else:
                # try to derive wavelength unit from wavelength values
                if anyValue(self.wavelengths()):
                    band_wlu = self.deduceWavelengthUnit(band_wl)
                if anyValue(band_wlu):
                    self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, band_wlu,
                                       origin=SpectralPropertyOrigin.Deduced)
        if canWrite(band_bbl, SpectralPropertyKeys.BadBand):
            self.setBandValues(None, SpectralPropertyKeys.BadBand, stringsToInts(band_bbl), origin=o_bbl)
            s = ""

        # set other keys
        for values, origin, key in [
            (band_fwhm, o_fwhm, SpectralPropertyKeys.FWHM),
            (band_offset, o_offset, SpectralPropertyKeys.DataOffset),
            (band_scale, o_scale, SpectralPropertyKeys.DataGain),
            (band_ref_offset, o_ref_offset, SpectralPropertyKeys.DataReflectanceOffset),
            (band_ref_scale, o_ref_scale, SpectralPropertyKeys.DataReflectanceGain),
        ]:
            if canWrite(values, key):
                self.setBandValues(None, key, stringsToNums(values), origin=origin)

        s = ""

    def asMap(self) -> dict:

        d = dict()
        d['_bandCount_'] = self.bandCount()
        for k in self.keys():
            value = self.value(k, None)
            if value:
                d[k] = value
        return d

    @classmethod
    def fromMap(cls, d: dict) -> 'QgsRasterLayerSpectralProperties':

        p = cls(d['_bandCount_'])
        for k, v in d.items():
            if not k.startswith('_'):
                p.setValue(k, v)
        return p

    def deduceWavelengthUnit(self, wavelength: Union[float, List[float]]) -> str:
        """
        Deduces a wavelength unit from the values in a wavelength list
        :param wavelength:
        :return:
        """
        wlu = None
        if not isinstance(wavelength, list):
            wavelength = [wavelength]

        for wl in wavelength:
            if wl:
                if 100 <= wl:
                    wlu = 'nm'
                elif 0 < wl < 100:  # even TIR sensors are below 100 μm
                    wlu = 'μm'
            if wlu:
                break

        return wlu

    def readFromProvider(self, provider: QgsRasterDataProvider, overwrite: bool = False):
        """
        Reads the spectral properties from a QgsRasterDataProvider.
        """
        assert isinstance(provider, QgsRasterDataProvider)

        if provider.name() == 'gdal':
            uri = provider.dataSourceUri()

            ds: gdal.Dataset = gdal.Open(uri)
            if isinstance(ds, gdal.Dataset):
                self.readFromGDALDataset(ds, overwrite=overwrite)
                del ds
                return

        # wavelength() can be available for custom providers like EE
        if hasattr(provider, 'wavelength'):
            if overwrite or SpectralPropertyKeys.Wavelength not in self.keys():
                wl = np.array([provider.wavelength(bandNo) for bandNo in range(1, provider.bandCount() + 1)]).tolist()
                wlu = 'nm'
                self.setBandValues(None, SpectralPropertyKeys.Wavelength, wl)
                self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, wlu)


class QgsRasterLayerSpectralPropertiesTable(QgsVectorLayer):
    """
    A container to expose spectral properties of QgsRasterLayers
    Conceptually similar to QgsRasterLayerTemporalProperties, just for spectral properties
    """

    def __init__(self):

        super().__init__('none?', '', 'memory')
        self.startEditing()
        bandNo = QgsField('band', type=QMETATYPE_INT, comment='Band Number')
        constraints = QgsFieldConstraints()
        constraints.setConstraint(QgsFieldConstraints.ConstraintUnique)
        constraints.setConstraint(QgsFieldConstraints.ConstraintNotNull)
        bandNo.setConstraints(constraints)
        bandNo.setReadOnly(True)
        self.addAttribute(bandNo)
        assert self.commitChanges()

    def initDefaultFields(self):
        b = self.isEditable()
        self.startEditing()

        BBL = QgsField('BBL', type=QMETATYPE_BOOL, comment='Band Band List')
        BBL.setDefaultValueDefinition(QgsDefaultValue('True'))
        self.addAttribute(BBL)

        WL = QgsField('WL', type=QMETATYPE_DOUBLE, comment='Wavelength of band center')
        self.addAttribute(WL)

        WLU = QgsField('WLU', type=QMETATYPE_QSTRING, comment='Wavelength Unit')
        wluConstraints = QgsFieldConstraints()
        wluConstraints.setConstraintExpression('"WLU" in [\'nm\', \'m\']')
        WLU.setConstraints(wluConstraints)
        self.addAttribute(WLU)

        WL_MIN = QgsField('WLmin', type=QMETATYPE_DOUBLE, comment='Minimum Wavelength')
        self.addAttribute(WL_MIN)
        WL_MAX = QgsField('WLmax', type=QMETATYPE_DOUBLE, comment='Maximum Wavelength')
        self.addAttribute(WL_MAX)

        FWHM = QgsField('FWHM', type=QMETATYPE_DOUBLE, comment='Full width at half maximum')
        fwhmConstraints = QgsFieldConstraints()
        fwhmConstraints.setConstraintExpression('"FWHM" > 0')
        FWHM.setConstraints(fwhmConstraints)
        self.addAttribute(FWHM)
        self.commitChanges(b)

    def fieldIndex(self, field: Union[int, str, QgsField]) -> int:
        if isinstance(field, int):
            return field
        elif isinstance(field, str):
            return self.fields().lookupField(field)
        elif isinstance(field, QgsField):
            return self.fields().indexFromName(field.name())

    def setValue(self, field: Union[int, str, QgsField], bandNo: int, value: Any) -> bool:
        return self.setValues(field, [bandNo], [value])

    def setValues(self,
                  field: Union[int, str, QgsField],
                  bands: List[int],
                  values: List[Any]) -> bool:
        i = self.fieldIndex(field)
        if i < 0:
            print(f'Spectral Property Field {field} does not exists', file=sys.stderr)
            return False
        self.startEditing()
        if bands is None:
            bands = list(range(1, self.featureCount() + 1))
        for bandNo, value in zip(bands, values):
            self.setAttribute(bandNo, value)
        return self.commitChanges()

    def value(self, field: Union[int, str, QgsField], bandNo: int) -> Any:
        return self.values(field, [bandNo])

    def values(self,
               field: Union[int, str, QgsField],
               bands: List[int] = None) -> Optional[List[Any]]:
        i = self.fieldIndex(field)
        if i < 0:
            print(f'Spectral Property Field {field} does not exists', file=sys.stderr)
            return None
        if bands is None:
            bands = list(range(1, self.mSpectralProperties.featureCount() + 1))
        self.mSpectralProperties: QgsVectorLayer
        values = []
        for band in bands:
            values.append(self.mSpectralProperties.getFeature(band)[i])
        return values

    def names(self) -> List[str]:
        """
        Returns the available property names
        """
        return self.fields().names()

    # convenient accessors
    def wavelengths(self) -> list:
        return self.values('WL')

    def setWavelengths(self, wl: list):
        self.setValues('WL', list(range(1, len(wl))))

    def wavelength(self, bandNo: int):
        return self.value('WL', bandNo)

    def setWavelength(self, bandNo: int, value: float):
        self.setValue('WL', bandNo, value)

    def _readBandProperty(self, layer: QgsRasterLayer, bandNo: int, propertyName: str):
        if propertyName == 'BBL':
            return True
        if propertyName == 'band':
            return bandNo
        return None

    def _readBandProperties(self, rasterLayer: QgsRasterLayer):
        self.startEditing()
        self.selectAll()
        self.removeSelection()
        assert self.commitChanges(False)

        for b in range(rasterLayer.bandCount()):

            bandFeature = QgsFeature(self.fields())
            for bandProperty in self.names():
                bandFeature.setAttribute(bandProperty, self._readBandProperty(rasterLayer, b, bandProperty))
            bandFeature.setAttribute('band', b + 1)
            self.addFeature(bandFeature)
        assert self.commitChanges()
        assert self.featureCount() == rasterLayer.bandCount()
        # s = ""

    def _writeToLayer(self, layer: QgsRasterLayer):
        pass


class QgsRasterLayerSpectralPropertiesTableWidget(QWidget):

    def __init__(self, spectralProperties: QgsRasterLayerSpectralPropertiesTable, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setWindowTitle('QgsRasterLayerSpectralPropertiesWidget')
        self.mSpectralProperties: QgsRasterLayerSpectralPropertiesTable = spectralProperties
        self.mVectorLayerCache = QgsVectorLayerCache(self.mSpectralProperties, 256)
        self.mAttributeTableModel = QgsAttributeTableModel(self.mVectorLayerCache)
        self.mAttributeTableModel.loadLayer()
        self.mCanvas = QgsMapCanvas()
        self.mFilterModel = QgsAttributeTableFilterModel(self.mCanvas, self.mAttributeTableModel)
        self.mTableView = QgsAttributeTableView()
        self.mTableView.setModel(self.mFilterModel)
        self.mLayout = QVBoxLayout()
        self.mLayout.addWidget(self.mTableView)
        self.setLayout(self.mLayout)
