import sys
import typing
import unittest

from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qgis._core import QgsRasterLayer, QgsFields, QgsField, QgsVectorLayer, QgsFieldConstraints, QgsFeature, \
    QgsDefaultValue, QgsVectorLayerCache
from qgis._gui import QgsAttributeTableView, QgsAttributeTableFilterModel, QgsMapCanvas, QgsAttributeTableModel

from qgis.PyQt.QtCore import QAbstractListModel


class QgsRasterLayerSpectralProperties(QgsVectorLayer):
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

        WL = QgsField('WL', type=QVariant.Double, comment='Wavelength at band center')
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
        self.startEditing()
        if bands is None:
            bands = list(range(1, self.featureCount() + 1))
        for bandNo, value in zip(bands, values):
            self.setAttribute(bandNo, value)
        return self.commitChanges()

    def values(self, field: typing.Union[int, str, QgsField], bands: typing.List[int] = None) -> typing.List[typing.Any]:
        i = self.fieldIndex(field)
        if i < 0:
            print(f'Spectral Property Field {field} does not exists', file=sys.stderr)
            return None
        if bands is None:
            bands = list(range(1, self.mSpectralProperties.featureCount()+1))
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

    def setWavelength(self, bandNo: int, value:float):
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


class QgsRasterLayerSpectralPropertiesWidget(QWidget):

    def __init__(self, spectralProperties: QgsRasterLayerSpectralProperties, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setWindowTitle('QgsRasterLayerSpectralPropertiesWidget')
        self.mSpectralProperties: QgsRasterLayerSpectralProperties = spectralProperties
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