import sys
import typing
import unittest

from PyQt5.QtCore import QVariant
from qgis._core import QgsRasterLayer, QgsFields, QgsField, QgsVectorLayer, QgsFieldConstraints, QgsFeature, \
    QgsDefaultValue

from qgis.PyQt.QtCore import QAbstractListModel


class QgsRasterLayerSpectralProperties(QAbstractListModel):
    """
    A container to expose spectral properties of QgsRasterLayers
    Conceptually similar to QgsRasterLayerTemporalProperties, just for spectral properties
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        uri = '?'
        self.mSpectralProperties = QgsVectorLayer('none?', 'spectralproperties', 'memory')
        self.mSpectralProperties.startEditing()

        band = QgsField('band', type=QVariant.Int, comment='Band Number')
        constraints = QgsFieldConstraints()
        constraints.setConstraint(QgsFieldConstraints.ConstraintUnique)
        constraints.setConstraint(QgsFieldConstraints.ConstraintNotNull)
        band.setConstraints(constraints)

        self.mSpectralProperties.startEditing()
        self.mSpectralProperties.addAttribute(band)
        assert self.mSpectralProperties.commitChanges()

    def initDefaultFields(self):

        BBL = QgsField('BBL', type=QVariant.Bool, comment='Band Band List')
        BBL.setDefaultValueDefinition(QgsDefaultValue())
        self.mFields.append()
        self.mFields.append(QgsField('WL', type=QVariant.Float, comment='Band center wavelength'))
        self.mFields.append(QgsField('WLU', type=QVariant.Float, comment='Wavelength Unit'))
        self.mFields.append(QgsField('Min. WL', type=QVariant.Float, comment='Minimum Wavelength'))
        self.mFields.append(QgsField('Max. WL', type=QVariant.Float, comment='Maximum Wavelength'))
        self.mFields.append(QgsField('FWHM', type=QVariant.Float, comment='Full width at half maximum'))

    def fieldIndex(self, field: typing.Union[int, str, QgsField]) -> int:
        if isinstance(field, int):
            return field
        elif isinstance(field, str):
            return self.mSpectralProperties.fields().lookupField(field)
        elif isinstance(field, QgsField):
            return self.mSpectralProperties.fields().indexFromName(field.name())

    def setValue(self, field: typing.Union[int, str, QgsField], bandNo: int, value: typing.Any) -> bool:
        return self.setValues(field, [bandNo], [value])

    def value(self, field: typing.Union[int, str, QgsField], bandNo: int) -> typing.Any:
        return self.values(field, [bandNo])

    def setValues(self,
                  field: typing.Union[int, str, QgsField],
                  bands: typing.List[int],
                  values: typing.List[typing.Any]) -> bool:
        i = self.fieldIndex(field)
        if i < 0:
            print(f'Spectral Property Field {field} does not exists', file=sys.stderr)
            return False
        self.mSpectralProperties: QgsVectorLayer
        self.mSpectralProperties.startEditing()
        for bandNo, value in zip(bands, values):
            self.mSpectralProperties.setAttribute
        return self.mSpectralProperties.commitChanges()

    def values(self, field: typing.Union[int, str, QgsField], bands: typing.List[int] = None) -> typing.List[typing.Any]:
        i = self.fieldIndex(field)
        if i < 0:
            print(f'Spectral Property Field {field} does not exists', file=sys.stderr)
            return None
        if bands is None:
            bands = list(range(self.mSpectralProperties.featureCount()))
        self.mSpectralProperties: QgsVectorLayer
        values = []
        for band in bands:
            values.append(self.mSpectralProperties.getFeature(band)[i])
        return values

    def wavelengths(self) -> list:
        return self.values('WL')

    def setWavelengths(self, wl: list):
        pass

    def wavelength(self, band: int):
        pass

    def setWavelength(self, band: int):
        pass

    def setBadBand(self, band: int, is_bad: bool):
        pass

    def isBadBand(self, band: int) -> bool:
        pass

    def bandBands(self) -> typing.List:
        pass

    def _readFromLayer(self, layer: QgsRasterLayer):
        self.mSpectralProperties.startEditing()
        self.mSpectralProperties.selectAll()
        self.mSpectralProperties.removeSelection()
        assert self.mSpectralProperties.commitChanges(False)

        for b in range(layer.bandCount()):

            self.mSpectralProperties.addFeature(QgsFeature(self.mSpectralProperties.fields()))
        assert self.mSpectralProperties.commitChanges()
        assert self.mSpectralProperties.featureCount() == layer.bandCount()

    def _writeToLayer(self, layer: QgsRasterLayer):
        pass

