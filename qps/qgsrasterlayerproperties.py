import re
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Pattern, Union, Dict

import numpy as np
from osgeo import gdal
from osgeo.gdal import Band
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsDefaultValue, QgsFeature, QgsField, QgsFieldConstraints, QgsObjectCustomProperties, \
    QgsRasterDataProvider, QgsRasterLayer, QgsVectorLayer, QgsVectorLayerCache
from qgis.gui import QgsAttributeTableFilterModel, QgsAttributeTableModel, QgsAttributeTableView, QgsMapCanvas

from .qgisenums import QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING

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
        except ValueError:
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


class SpectralPropertySourceKey(object):
    """
    A key that indicates from which metadata source the SpectralPropertyKey was read
    """
    Band = 'gdal_band'
    Dataset = 'gdal_dataset'
    LayerProperties = 'layer_property'


class SpectralPropertyKeys(object):
    """
    Enumeration of Spectral Property Keys
    """
    BadBand = 'bbl'
    Wavelength = 'wavelength'
    WavelengthUnit = 'wavelength_unit'
    BandWidth = 'bandwidth'
    DataOffset = 'data_offset'
    DataGain = 'data_gain'
    DataReflectanceOffset = 'data_reflectance_offset'
    DataReflectanceGain = 'data_reflectance_gain'
    FWHM = 'fwhm'


class QgsRasterLayerSpectralProperties(QgsObjectCustomProperties):
    """
    Stores spectral properties of a raster layer source
    """
    LOOKUP_PATTERNS = {
        SpectralPropertyKeys.FWHM: re.compile(
            r'(fwhm|full[ -_]width[ -_]half[ -_]maximum)$', re.I),
        SpectralPropertyKeys.BadBand: re.compile(
            r'(bbl|bad[ -_]?Band|bad[ -_]?band[ -_]?multiplier|bad[ -_]band[ -_]list)$', re.I),
        SpectralPropertyKeys.WavelengthUnit: re.compile(
            r'(wlu|wavelength[ -_]?units?)$', re.I),
        SpectralPropertyKeys.Wavelength: re.compile(
            r'(wl|wavelengths?|center[_ ]wavelengths?)$', re.I),
        SpectralPropertyKeys.BandWidth: re.compile(
            r'(bw|bandwiths?)$', re.I),
        SpectralPropertyKeys.DataGain: re.compile(
            r'(data[ -_]gain([ -_]values?)?)$', re.I),
        SpectralPropertyKeys.DataOffset: re.compile(
            r'(data[ -_]offset([ -_]values?)?)$', re.I),
        SpectralPropertyKeys.DataReflectanceGain: re.compile(
            r'(data[ -_]reflectance[ -_]gain([ -_]values?)?)$', re.I),
        SpectralPropertyKeys.DataReflectanceOffset: re.compile(
            r'(data[ -_]reflectance[ -_]offset([ -_]values?)?)$', re.I)
    }

    @staticmethod
    def combinedLookupPattern() -> Pattern:
        patters = '|'.join([rx.pattern for rx in QgsRasterLayerSpectralProperties.LOOKUP_PATTERNS.values()])
        return re.compile(f'({patters})', re.IGNORECASE)

    @staticmethod
    def fromRasterLayer(layer: Union[QgsRasterLayer, gdal.Dataset, str, Path]) \
            -> Optional['QgsRasterLayerSpectralProperties']:
        """
        Returns the QgsRasterLayerSpectralProperties for a raster layer
        """
        if isinstance(layer, QgsRasterDataProvider):
            obj = QgsRasterLayerSpectralProperties(layer.bandCount())
            obj._readFromProvider(layer)
            return obj

        if isinstance(layer, gdal.Dataset):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=True)
            layer = QgsRasterLayer(layer.GetDescription(), 'lyr', 'gdal', options=options)

        if isinstance(layer, Path):
            layer = layer.as_posix()

        if isinstance(layer, str):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=True)
            return QgsRasterLayerSpectralProperties.fromRasterLayer(QgsRasterLayer(layer, options=options))

        if not (isinstance(layer, QgsRasterLayer)
                and layer.isValid() and layer.bandCount() > 0):
            return None
        obj = QgsRasterLayerSpectralProperties(layer.bandCount())
        obj._readFromProvider(layer.dataProvider())
        obj.readFromLayer(layer)
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

    @staticmethod
    def bandKey(bandNo: int) -> str:
        """
        Generates a band key like "band_3"
        """
        assert bandNo > 0
        return f'band_{bandNo}'

    def bandItemKey(self, bandNo: int, itemKey: str):
        """
        Generates a band item key like "band_3/itemA"
        """
        return f'{self.bandKey(bandNo)}/{self.itemKey(itemKey)}'

    def bandValue(self, bandNo: int, itemKey: str) -> Any:
        """
        Returns the band values for band bandNo and a specific item key.
        """
        return self.bandValues([bandNo], itemKey)[0]

    def setBandValue(self, bandNo: Union[int, str], itemKey: str, value):
        self.setBandValues([bandNo], itemKey, [value])

    def setBandValues(self, bands: Optional[List[int]], itemKey, values):
        """
        Sets the n values to the corresponding n bands
        if bands = None|'all'|'*'|':', it is expected values contains either a single value or n = bandCount() values.
        """
        if bands in [None, 'all', '*', ':']:
            bands = list(range(1, self.bandCount() + 1))
        for b in bands:
            assert isinstance(b, int) and 0 < b <= self.bandCount()
        if isinstance(values, (str, int, float)):
            values = [values for _ in bands]

        assert len(values) == len(bands)
        assert 0 < len(bands) <= self.bandCount()
        for value, band in zip(values, bands):
            self.setValue(self.bandItemKey(band, itemKey), value)

    def bandValues(self, bands: Optional[List[int]], itemKey, default=None) -> List[Any]:
        """
        Returns the n values for n bands and itemKey.
        Returns the default value in case the itemKey is undefined for a band.
        """
        if bands in [None, 'all']:
            bands = list(range(1, self.bandCount() + 1))
        itemKey = self.itemKey(itemKey)

        values = [self.value(f'{self.bandKey(b)}/{itemKey}') for b in bands]
        if default is not None:
            values = [v if v is not None else default for v in values]
        return values

    def dataOffsets(self, default: float = float('nan')) -> List[float]:
        return self.bandValues(None, SpectralPropertyKeys.DataOffset, default=default)

    def dataGains(self, default: float = float('nan')):
        return self.bandValues(None, SpectralPropertyKeys.DataGain, default=default)

    def wavelengths(self) -> List[float]:
        """
        Returns n = .bandCount() wavelengths.
        """
        return self.bandValues(None, SpectralPropertyKeys.Wavelength)

    def wavelengthUnits(self) -> List[str]:
        """
        Returns n= .bandCount() wavelength units.
        """
        return self.bandValues(None, SpectralPropertyKeys.WavelengthUnit)

    def badBands(self, default: int = 1) -> List[int]:
        """
        Convenience function to return bad band (multiplier) values as list
        0 = False = do not use
        1 = True = do use (default)
        values > 1 might be used for other special meanings

        Potentially other values can be used as well, for example to add different masks.
        Assumes 1 = True by default.
        """
        return [int(v) for v in self.bandValues(None, SpectralPropertyKeys.BadBand, default=default)]

    def fwhm(self, default=None) -> List[float]:
        """
        Returns the FWHM values for each band
        """
        return self.bandValues(None, SpectralPropertyKeys.BandWidth, default=default)

    def fullWidthHalfMaximum(self, default=None) -> List[float]:
        """
        Returns the FWHM values for each band
        """
        return self.fwhm(default)

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

    def readFromLayer(self, layer: QgsRasterLayer):
        """
        Reads the spectral properties from the layer definition / custom layer properties.
        Will override other existing spectral properties.
        """
        assert isinstance(layer, QgsRasterLayer)

        customProperties = layer.customProperties()
        nb = layer.bandCount()
        for b in range(1, nb + 1):
            bandKey = f'band_{b}'
            keys = [k for k in customProperties.keys() if k.startswith(bandKey)]
            for k in keys:
                self.setValue(self.bandItemKey(b, k.removeprefix(bandKey)[1:]),
                              stringToType(customProperties.value(k)))

    def _readFromGDALDataset(self, ds: gdal.Dataset):
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
                return re.split(r'[, {}]+', values)
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
        if not any(band_wlu):
            band_wlu = valueList(ds, SpectralPropertyKeys.WavelengthUnit)

        if not any(band_bbl):
            band_bbl = valueList(ds, SpectralPropertyKeys.BadBand)

        if not any(band_fwhm):
            band_fwhm = valueList(ds, SpectralPropertyKeys.FWHM)

        # set wavelength
        if band_wl and any(band_wl):
            band_wl = stringsToNums(band_wl)
            self.setBandValues(None, SpectralPropertyKeys.Wavelength, band_wl)
        if band_wlu and any(band_wlu):
            self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, band_wlu)
        elif band_wl and any(band_wl):
            # derive wavelength unit from wavelength values
            band_wlu = None
            for wl in band_wlu:
                if wl:
                    s = ""
            if band_wlu:
                self.setBandValues(None, SpectralPropertyKeys.WavelengthUnit, band_wlu)

        if band_bbl and any(band_bbl):
            self.setBandValues(None, SpectralPropertyKeys.BadBand, stringsToInts(band_bbl))

        # set other keys
        for array, key in [
            (band_fwhm, SpectralPropertyKeys.FWHM),
            (band_offset, SpectralPropertyKeys.DataOffset),
            (band_scale, SpectralPropertyKeys.DataGain),
            (band_ref_offset, SpectralPropertyKeys.DataReflectanceOffset),
            (band_ref_scale, SpectralPropertyKeys.DataReflectanceGain),
        ]:
            if array and any(array):
                self.setBandValues(None, key, stringsToNums(array))

    def _readFromProvider(self, provider: QgsRasterDataProvider):
        """
        Reads the spectral properties from a QgsRasterDataProvider.
        (To be implemented within a QgsRasterDataProvider)
        """
        assert isinstance(provider, QgsRasterDataProvider)

        if provider.name() == 'gdal':
            uri = provider.dataSourceUri()

            ds: gdal.Dataset = gdal.Open(uri)
            if isinstance(ds, gdal.Dataset):
                self._readFromGDALDataset(ds)
                del ds
                return

        html = provider.htmlMetadata()
        doc = QDomDocument()
        success, err, errLine, errColumn = doc.setContent(f'<root>{html}</root>')
        rx_spectral_property = QgsRasterLayerSpectralProperties.combinedLookupPattern()

        def addSpectralProperty(bandNo: int, text: str):
            match = rx_key_value_pair.match(text)
            if match:
                key = match.group('key')
                value = match.group('value')
                if rx_spectral_property.match(key):
                    self.setValue(self.bandItemKey(bandNo, key), stringToType(value))

        if success:
            root = doc.documentElement()
            trNode = root.firstChildElement('tr')
            while not trNode.isNull():
                td1 = trNode.firstChildElement('td')
                td1_text = td1.text().replace(' ', '_')
                td2 = td1.nextSibling().toElement()
                li = td2.firstChildElement('ul').firstChildElement('li').toElement()

                if not (td1.isNull() or td2.isNull()):
                    # value = td2.text()
                    # print(value)
                    match_band = rx_bands.match(td1_text)
                    match_more = rx_more_information.match(td1_text)
                    # bandNo = None
                    if match_band:
                        bandNo = int(match_band.group('band'))
                        while not li.isNull():
                            addSpectralProperty(bandNo, li.text())
                            li = li.nextSibling().toElement()
                    elif match_more:
                        while not li.isNull():
                            matchPair = rx_key_value_pair.match(li.text())
                            if matchPair:
                                key = matchPair.group('key')
                                value = matchPair.group('value')
                                if rx_spectral_property.match(key):
                                    matchENVI = rx_envi_array.match(value)
                                    if matchENVI:
                                        value = matchENVI.group('value')
                                    values = re.split(r'[\s,;]+', value)

                                    if len(values) == self.bandCount():
                                        values = [stringToType(v) for v in values]
                                        self.setBandValues(None, self.itemKey(key), values)
                                    elif len(values) == 1:
                                        self.setBandValues(None, self.itemKey(key), stringToType(values[0]))

                            li = li.nextSibling().toElement()

                trNode = trNode.nextSibling()

        # wavelength() can be available for custom providers like EE
        if hasattr(provider, 'wavelength'):
            wl = np.array([provider.wavelength(bandNo) for bandNo in range(1, provider.bandCount() + 1)]).tolist()
            wlu = 'Nanometers'
            self.setBandValues(None, 'wl', wl)
            self.setBandValues(None, 'wlu', wlu)


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
