import re
import sys
import typing

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsRasterLayer, QgsField, QgsVectorLayer, QgsFieldConstraints, QgsFeature, \
    QgsDefaultValue, QgsVectorLayerCache, QgsObjectCustomProperties, QgsRasterDataProvider
from qgis.gui import QgsAttributeTableView, QgsAttributeTableFilterModel, QgsMapCanvas, QgsAttributeTableModel

rx_bands = re.compile(r'^Band[_ ](?P<band>\d+)$')
rx_key_value_pair = re.compile('^(?P<key>[^ =]+)=(?P<value>.+)$')


def stringToType(value: str):
    t = str
    for candidate in [int, float]:
        try:
            _ = candidate(value)
            t = candidate
        except ValueError:
            continue
    return t(value)


class QgsRasterLayerSpectralProperties(QgsObjectCustomProperties):
    NORMALIZATION_PATTERNS = {
        'fwhm': re.compile('(fwhm|fullwidthhalfmaximum)$', re.IGNORECASE),
        'bbl': re.compile('(bbl|badBand|badbandmultiplier|badbandlist)$', re.IGNORECASE),
        'wlu': re.compile('(wlu|wavelength[ _]?units?)$', re.IGNORECASE),
        'wl': re.compile('(wl|wavelengths?)$', re.IGNORECASE),
    }

    @staticmethod
    def fromRasterLayer(layer: QgsRasterLayer):
        if isinstance(layer, str):
            options = QgsRasterLayer.LayerOptions(loadDefaultStyle=True)
            return QgsRasterLayerSpectralProperties.fromRasterLayer(QgsRasterLayer(layer, options=options))

        if not isinstance(layer, QgsRasterLayer) and layer.isValid():
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
        return self.mBandCount

    @staticmethod
    def normalizeItemKey(itemKey: str) -> str:

        for replacement, rx in QgsRasterLayerSpectralProperties.NORMALIZATION_PATTERNS.items():
            match = rx.search(itemKey)
            if match:
                itemKey = itemKey.replace(match.group(), replacement)

        return itemKey

    @staticmethod
    def bandKey(bandNo: int) -> str:
        return f'band_{bandNo}'

    def bandItemKey(self, bandNo: int, itemKey: str):
        return f'{self.bandKey(bandNo)}/{self.normalizeItemKey(itemKey)}'

    def bandValue(self, bandNo: int, itemKey: str) -> typing.Any:
        return self.bandValues([bandNo], itemKey)

    def setBandValue(self, bandNo: typing.Union[int, str], itemKey: str, value):
        self.setBandValues([bandNo], itemKey, [value])

    def setBandValues(self, bands: typing.List[int], itemKey, values):
        if bands in [None, 'all']:
            bands = list(range(1, self.bandCount() + 1))
        for b in bands:
            assert isinstance(b, int) and 0 < b <= self.bandCount()
        if isinstance(values, (str, int, float)):
            values = [values for _ in bands]

        assert len(values) == len(bands)
        assert 0 < len(bands) <= self.bandCount()
        for value, band in zip(values, bands):
            self.setValue(self.bandItemKey(band, itemKey), value)

    def bandValues(self, bands: typing.List[int], itemKey) -> typing.List[typing.Any]:
        if bands in [None, 'all']:
            bands = list(range(1, self.bandCount() + 1))
        itemKey = self.normalizeItemKey(itemKey)
        return [self.value(f'{self.bandKey(b)}/{itemKey}') for b in bands]

    def wavelengths(self) -> typing.List[float]:
        return self.bandValues(None, 'wavelength')

    def wavelengthUnits(self) -> typing.List[str]:
        return self.bandValues(None, 'wavelength_units')

    def fullWidthHalfMaximum(self) -> typing.List[float]:
        return self.bandValues(None, 'fwhm')

    def writeXml(self, parentNode: QDomElement, doc: QDomDocument):

        root = doc.createElement('spectralproperties')
        super().writeXml(root, doc)
        parentNode.appendChild(root)

    def readXml(self, parentNode, keyStartsWith=''):

        root = parentNode.namedItem('spectralproperties')
        if root.isNull():
            return None
        else:
            super(QgsRasterLayerSpectralProperties, self).readXml(root, keyStartsWith=keyStartsWith)

    def readFromLayer(self, layer: QgsRasterLayer):
        assert isinstance(layer, QgsRasterLayer)

        customProperties = layer.customProperties()
        nb = layer.bandCount()
        for b in range(1, nb + 1):
            bandKey = f'band_{b}'
            keys = [k for k in customProperties.keys() if k.startswith(bandKey)]
            for k in keys:
                self.setValue(self.bandItemKey(b, k.removeprefix(bandKey)[1:]),
                              stringToType(customProperties.value(k)))

    def _readFromProvider(self, provider: QgsRasterDataProvider):
        assert isinstance(provider, QgsRasterDataProvider)

        html = provider.htmlMetadata()
        doc = QDomDocument()
        success, err, errLine, errColumn = doc.setContent(f'<root>{html}</root>')

        if success:
            root = doc.documentElement()
            trNode = root.firstChildElement('tr')
            while not trNode.isNull():
                td1 = trNode.firstChildElement('td')
                td2 = td1.nextSibling().toElement()
                if not (td1.isNull() or td2.isNull()):
                    value = td2.text()
                    match = rx_bands.match(td1.text().replace(' ', '_'))
                    if match:
                        bandNo = int(match.group('band'))
                        li = td2.firstChildElement('ul').firstChildElement('li').toElement()
                        if li.isNull():
                            self.setValue(self.bandKey(bandNo), stringToType(value))
                        else:
                            while not li.isNull():
                                value = li.text()
                                match2 = rx_key_value_pair.match(value)
                                if match2:
                                    itemKey = match2.group('key')
                                    itemValue = match2.group('value')

                                    self.setValue(self.bandItemKey(bandNo, itemKey), stringToType(itemValue))
                                else:
                                    pass
                                li = li.nextSibling().toElement()

                trNode = trNode.nextSibling()


class QgsRasterLayerSpectralPropertiesTable(QgsVectorLayer):
    """
    A container to expose spectral properties of QgsRasterLayers
    Conceptually similar to QgsRasterLayerTemporalProperties, just for spectral properties
    """

    def __init__(self):

        super().__init__('none?', '', 'memory')
        self.startEditing()
        bandNo = QgsField('band', type=QVariant.Int, comment='Band Number')
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

        BBL = QgsField('BBL', type=QVariant.Bool, comment='Band Band List')
        BBL.setDefaultValueDefinition(QgsDefaultValue('True'))
        self.addAttribute(BBL)

        WL = QgsField('WL', type=QVariant.Double, comment='Wavelength of band center')
        self.addAttribute(WL)

        WLU = QgsField('WLU', type=QVariant.String, comment='Wavelength Unit')
        wluConstraints = QgsFieldConstraints()
        wluConstraints.setConstraintExpression('"WLU" in [\'nm\', \'m\']')
        WLU.setConstraints(wluConstraints)
        self.addAttribute(WLU)

        WL_MIN = QgsField('WLmin', type=QVariant.Double, comment='Minimum Wavelength')
        self.addAttribute(WL_MIN)
        WL_MAX = QgsField('WLmax', type=QVariant.Double, comment='Maximum Wavelength')
        self.addAttribute(WL_MAX)

        FWHM = QgsField('FWHM', type=QVariant.Double, comment='Full width at half maximum')
        fwhmConstraints = QgsFieldConstraints()
        fwhmConstraints.setConstraintExpression('"FWHM" > 0')
        FWHM.setConstraints(fwhmConstraints)
        self.addAttribute(FWHM)
        self.commitChanges(b)

    def fieldIndex(self, field: typing.Union[int, str, QgsField]) -> int:
        if isinstance(field, int):
            return field
        elif isinstance(field, str):
            return self.fields().lookupField(field)
        elif isinstance(field, QgsField):
            return self.fields().indexFromName(field.name())

    def setValue(self, field: typing.Union[int, str, QgsField], bandNo: int, value: typing.Any) -> bool:
        return self.setValues(field, [bandNo], [value])

    def setValues(self,
                  field: typing.Union[int, str, QgsField],
                  bands: typing.List[int],
                  values: typing.List[typing.Any]) -> bool:
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

    def value(self, field: typing.Union[int, str, QgsField], bandNo: int) -> typing.Any:
        return self.values(field, [bandNo])

    def values(self,
               field: typing.Union[int, str, QgsField],
               bands: typing.List[int] = None) -> typing.List[typing.Any]:
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

    def names(self) -> typing.List[str]:
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
        s = ""

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
