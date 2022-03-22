"""
***************************************************************************
    layerconfigwidget/gdalmetadata.py - A QgsMapLayerConfigWidget to show GDAL Metadata
    -----------------------------------------------------------------------
    begin                : 2020-02-24
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import math
import pathlib
import re
import typing
from typing import List, Pattern, Tuple, Union

from osgeo import gdal, ogr
from qgis.PyQt.QtCore import QRegExp, QTimer, Qt, NULL, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLineEdit, QDialogButtonBox, QComboBox, QWidget, \
    QDialog
from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsMapLayer, QgsEditorWidgetSetup, \
    QgsRasterDataProvider, Qgis, QgsField, QgsFieldConstraints, QgsDefaultValue, QgsFeature
from qgis.gui import QgsGui, QgsMapCanvas, QgsMapLayerConfigWidgetFactory, QgsMessageBar, QgsDualView, \
    QgsAttributeTableModel, QgsAttributeEditorContext

from .core import QpsMapLayerConfigWidget
from ..classification.classificationscheme import ClassificationScheme, ClassificationSchemeWidget
from ..qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ..utils import loadUi, gdalDataset

try:
    from qgis.gui import QgsFieldCalculator

    FIELD_CALCULATOR = True
except ImportError:
    FIELD_CALCULATOR = False

PROTECTED = [
    'IMAGE_STRUCTURE:INTERLEAVE',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_NAME',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_DESC'
    ':AREA_OR_POINT'
]

MAJOR_OBJECTS = [gdal.Dataset.__name__, gdal.Band.__name__, ogr.DataSource.__name__, ogr.Layer.__name__]


class GDALErrorHandler(object):
    def __init__(self):
        self.err_level = gdal.CE_None
        self.err_no = 0
        self.err_msg = ''

    def handler(self, err_level, err_no, err_msg):
        self.err_level = err_level
        self.err_no = err_no
        self.err_msg = err_msg

        if err_level == gdal.CE_Warning:
            pass

        if err_level > gdal.CE_Warning:
            raise RuntimeError(err_level, err_no, err_msg)


def filterFeatures(layer: QgsVectorLayer, regex: QRegExp) -> List[int]:
    fids = []
    for f in layer.getFeatures():
        f: QgsFeature
        for k, v in f.attributeMap().items():
            if regex.indexIn(str(v), 0) >= 0:
                fids.append(f.id())
                break

    return fids


class BandFieldNames(object):
    Domain = 'Domain'
    Number = 'Band'
    Name = 'Band Name'
    BadBand = 'BBL'
    Range = 'Range'
    Offset = 'Data Offset'
    Gain = 'Data Gain'
    NoData = 'No Data'
    FWHM = 'FWHM'
    Wavelength = 'Wavelength'
    WavelengthUnit = 'Wavelength Unit'


class GDALMetadataModelBase(QgsVectorLayer):

    def __init__(self):
        super().__init__('none?', '', 'memory')

        self.mMapLayer: QgsMapLayer = None
        self.initFields()

    def createDomainField(self) -> QgsField:
        DOMAIN = QgsField(BandFieldNames.Domain, type=QVariant.String)
        constraint = QgsFieldConstraints()
        DOMAIN.setReadOnly(True)
        DOMAIN.setDefaultValueDefinition(QgsDefaultValue(''))
        return DOMAIN

    def bandKey(self, bandNo: int) -> str:
        assert bandNo > 0
        if isinstance(self.mMapLayer, QgsRasterLayer) \
                and isinstance(self.mMapLayer.dataProvider(), QgsRasterDataProvider):
            z = self.mMapLayer.dataProvider()
        else:
            z = 0
        return f'{gdal.Band.__name__}_{str(bandNo).zfill(z)}'

    def layerKey(self, layerId=Union[int, str]) -> str:
        layerId = str(layerId)
        if re.match(r'^\d+$', layerId):
            return f'{ogr.Layer.__name__}id_{layerId}'
        else:
            return f'{ogr.Layer.__name__}name_{layerId}'

    def mapKey(self, major_object: str, domain: str, key: str) -> str:
        return f'{major_object}/{domain}/{key}'

    def setLayer(self, mapLayer: QgsMapLayer):
        if self.mMapLayer == mapLayer:
            self.syncToLayer()
            return
        editable = self.isEditable()

        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer
        else:
            self.mMapLayer = None

        self.syncToLayer()

        self.commitChanges(not editable)

    def toFieldValue(self, value):

        if value in ['', None, NULL]:
            return None
        elif isinstance(value, float) and math.isnan(value):
            return None
        return value

    def asMap(self) -> dict:
        raise NotImplementedError

    def initFields(self):
        raise NotImplementedError()

    def syncToLayer(self):
        raise NotImplementedError()

    def applyToLayer(self):
        raise NotImplementedError()


def isGDALRasterLayer(lyr) -> bool:
    b = isinstance(lyr, QgsRasterLayer) \
        and lyr.isValid() \
        and lyr.dataProvider().name() == 'gdal'
    return b


def isOGRVectorLayer(lyr) -> bool:
    b = isinstance(lyr, QgsVectorLayer) \
        and lyr.isValid() \
        and lyr.dataProvider().name() == 'ogr'
    return b


class GDALBandMetadataModel(GDALMetadataModelBase):
    FIELD2GDALKey = {
        BandFieldNames.BadBand: 'bbl',
        BandFieldNames.Range: 'band width',
        BandFieldNames.Wavelength: 'wavelength',
        BandFieldNames.WavelengthUnit: 'wavelength units',
        BandFieldNames.FWHM: 'fwhm',
        BandFieldNames.Offset: 'data offset values',
        BandFieldNames.Gain: 'data gain values'
    }

    FIELD_TOOLTIP = {
        BandFieldNames.Number: 'Band Number',
        BandFieldNames.Name: 'Band Name',
        BandFieldNames.Range: 'Band range from (min, max) with<br>'
                              + 'min = wavelength - 0.5 FWHM<br>'
                              + 'max = wavelength + 0.5 FWHM',
        BandFieldNames.Wavelength: 'Wavelength',
        BandFieldNames.WavelengthUnit: "Wavelength Unit, e.g. 'nm', 'μm'",
        BandFieldNames.NoData: 'Band NoData value to mask pixel',
        BandFieldNames.Domain: "Metadata domain.<br>'' = default domain<br>'ENVI' = ENVI domain",
        BandFieldNames.BadBand: 'bad band multiplier value. <br>0 = exclude, <br>1 = use band',
        BandFieldNames.FWHM: 'Full width at half maximum or band width, respectively',
        BandFieldNames.Offset: 'Offset of data values',
        BandFieldNames.Gain: 'Gain of data values',
    }

    def __init__(self):
        super().__init__()

        self.mDataLookup: List[Tuple[QgsField, Pattern]] = []

    def initFields(self):
        assert self.fields().count() == 0
        # define default fields
        b = self.isEditable()
        self.startEditing()

        DOMAIN = self.createDomainField()
        BANDNO = QgsField(BandFieldNames.Number, type=QVariant.Int)
        constraints = QgsFieldConstraints()
        # todo: constraint unique combination of (domain, band number, key)
        # constraints.setConstraint(QgsFieldConstraints.ConstraintUnique)
        constraints.setConstraint(QgsFieldConstraints.ConstraintNotNull)
        constraints.setConstraint(QgsFieldConstraints.ConstraintUnique)
        constraints.setConstraintStrength(QgsFieldConstraints.ConstraintNotNull,
                                          QgsFieldConstraints.ConstraintStrengthHard)
        constraints.setConstraintStrength(QgsFieldConstraints.ConstraintUnique,
                                          QgsFieldConstraints.ConstraintStrengthHard)

        BANDNO.setConstraints(constraints)
        BANDNO.setReadOnly(True)

        bandName = QgsField(BandFieldNames.Name, type=QVariant.String, len=-1, )

        NODATA = QgsField(BandFieldNames.NoData, type=QVariant.Double)

        BBL = QgsField(BandFieldNames.BadBand, type=QVariant.Int)
        BBL.setDefaultValueDefinition(QgsDefaultValue('1'))
        BBL.setEditorWidgetSetup(QgsEditorWidgetSetup())

        WL = QgsField(BandFieldNames.Wavelength, type=QVariant.Double)

        WLU = QgsField(BandFieldNames.WavelengthUnit, type=QVariant.String)
        # wluConstraints = QgsFieldConstraints()
        # wluConstraints.setConstraintExpression('"{BandPropertyKeys.WavelengthUnit}" in [\'nm\', \'m\']')
        # WLU.setConstraints(wluConstraints)

        FWHM = QgsField(BandFieldNames.FWHM, type=QVariant.Double)
        FWHMConstraints = QgsFieldConstraints()
        FWHMConstraints.setConstraintExpression(f'"{BandFieldNames.FWHM}" is NULL or "{BandFieldNames.FWHM}" > 0')
        FWHM.setConstraints(FWHMConstraints)

        RANGE = QgsField(BandFieldNames.Range, type=QVariant.String)
        # RANGEConstraints = QgsFieldConstraints()
        # RANGEConstraints.setConstraintExpression(f'"{BandFieldNames.BandRange}" > 0')

        OFFSET = QgsField(BandFieldNames.Name, type=QVariant.Double)
        GAIN = QgsField(BandFieldNames.Gain, type=QVariant.Double)
        # add fields
        for field in [BANDNO, DOMAIN, bandName, NODATA, BBL, WLU, FWHM, RANGE, OFFSET, OFFSET, GAIN]:
            field: QgsField
            field.setComment(self.FIELD_TOOLTIP.get(field.name(), ''))
            self.addAttribute(field)

        self.commitChanges(b)

        for field in self.fields():
            i = self.fields().lookupField(field.name())
            self.setEditorWidgetSetup(i, QgsGui.editorWidgetRegistry().findBest(self, field.name()))

    def asMap(self) -> dict:

        data = dict()
        if not isGDALRasterLayer(self):
            return data

        for f in self.getFeatures():
            f: QgsFeature

            ds: gdal.Dataset = gdalDataset(self.mMapLayer)

            major_object = f.attribute('')
            bandNo = f.attribute(BandFieldNames.Number)
            bandKey = self.bandKey(bandNo)
            bandName = f.attribute(BandFieldNames.Name)
            bandDomain = f.attribute(BandFieldNames.Domain)
            for field in f.fields():
                n = field.name()
                value = f.attribute(n)
                gdalKey = self.FIELD2GDALKey.get(field.name(), None)
                if gdalKey:
                    mapKey = self.mapKey(self.bandKey(bandNo), bandDomain, gdalKey)

                    if value in [None, NULL]:
                        value = ''
                    else:
                        value = str(value).strip()
                    data[mapKey] = value
        return data

    def syncToLayer(self, *args, spectralProperties: QgsRasterLayerSpectralProperties = None):
        self.startEditing()
        self.deleteFeatures(self.allFeatureIds())
        self.commitChanges(False)
        lyr = self.mMapLayer

        if isGDALRasterLayer(lyr):
            self.beginEditCommand('Sync to layer')
            if spectralProperties is None:
                spectralProperties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)

            dp: QgsRasterDataProvider = lyr.dataProvider()

            wl = spectralProperties.wavelengths()
            wlu = spectralProperties.wavelengthUnits()
            bbl = spectralProperties.badBands()
            fwhm = spectralProperties.fullWidthHalfMaximum()
            bandRanges = []
            for a, b in zip(wl, fwhm):
                bandRange = None
                if math.isfinite(a) and math.isfinite(b):
                    bandRange = f'{a - 0.5 * b} - {a + 0.5 * b}'
                bandRanges.append(bandRange)

            KEY2VALUE = {
                BandFieldNames.Number: lambda i: i + 1,
                BandFieldNames.Wavelength: lambda i: wl[i],
                BandFieldNames.WavelengthUnit: lambda i: wlu[i],
                BandFieldNames.BadBand: lambda i: bbl[i],
                BandFieldNames.Range: lambda i: bandRanges[i],
                BandFieldNames.FWHM: lambda i: fwhm[i],
                BandFieldNames.NoData: lambda i: dp.sourceNoDataValue(i + 1),
                BandFieldNames.Name: lambda i: dp.generateBandName(i + 1),
                BandFieldNames.Domain: lambda i: domain,
            }

            domain = ''

            for i in range(lyr.bandCount()):
                b = i + 1
                f = QgsFeature(self.fields())
                for field in self.fields():
                    field: QgsField
                    n = field.name()
                    value = None
                    if n in KEY2VALUE.keys():
                        value = self.toFieldValue(KEY2VALUE[n](i))
                    else:
                        itemKey = spectralProperties.bandItemKey(b, field.name())
                        value = spectralProperties.value(itemKey)
                        value = self.toFieldValue(value)

                    f.setAttribute(n, value)
                assert self.addFeature(f)
            self.endEditCommand()
        assert self.commitChanges(False)

    def applyToLayer(self, *args):

        if not (isGDALRasterLayer(self.mMapLayer)) and self.isEditable():
            return

        ds: gdal.Dataset = None
        try:
            ds = gdalDataset(self.mMapLayer)
        except Exception as ex:
            pass

        data = self.asMap()

        if isinstance(ds, gdal.Dataset):
            for f in self.getFeatures():
                f: QgsFeature
                bandNo = f.attribute(BandFieldNames.Number)
                band: gdal.Band = ds.GetRasterBand(bandNo)
                name = f.attribute(BandFieldNames.Name)
                band.SetDescription(name)

                for field in f.fields():
                    n = field.name()
                    value = f.attribute(n)
                    enviName = self.FIELD2GDALKey.get(field.name(), None)
                    if enviName:
                        if value in [None, NULL]:
                            band.SetMetadataItem(enviName, '')
                        else:
                            band.SetMetadataItem(enviName, str(value))
            ds.FlushCache()
            del ds


class GDALMetadataModel(GDALMetadataModelBase):
    FN_MajorObject = 'Object'
    FN_Domain = 'Domain'
    FN_Key = 'Key'
    FN_Value = 'Value'

    def __init__(self):
        super().__init__()

    def initFields(self):
        assert self.fields().count() == 0

        self.startEditing()

        MAJOR_OBJECT = QgsField(name=self.FN_MajorObject, type=QVariant.String)
        MAJOR_OBJECT.setReadOnly(True)
        constraints = QgsFieldConstraints()
        # todo: constraint unique combination of (domain, band number, key)
        # constraints.setConstraint(QgsFieldConstraints.ConstraintUnique)
        constraints.setConstraint(QgsFieldConstraints.ConstraintNotNull)
        constraints.setConstraintStrength(QgsFieldConstraints.ConstraintNotNull,
                                          QgsFieldConstraints.ConstraintStrengthHard)

        DOMAIN = QgsField(self.FN_Domain, type=QVariant.String)
        DOMAIN.setReadOnly(True)
        KEY = QgsField(self.FN_Key, type=QVariant.String)
        KEY.setReadOnly(True)
        VALUE = QgsField(self.FN_Value, type=QVariant.String)

        for a in [MAJOR_OBJECT, DOMAIN, KEY, VALUE]:
            assert self.addAttribute(a)
        assert self.commitChanges()

    def addMajorObjectFeatures(self, obj: gdal.MajorObject, sub_object: str = None):
        domains = obj.GetMetadataDomainList()
        if not domains:
            return
        for domain in domains:
            MD = obj.GetMetadata_Dict(domain)
            if isinstance(MD, dict):
                for key, value in MD.items():
                    f = QgsFeature(self.fields())
                    name = obj.__class__.__name__
                    if sub_object:
                        name += f'_{sub_object}'
                    f.setAttribute(self.FN_MajorObject, name)
                    f.setAttribute(self.FN_Domain, domain)
                    f.setAttribute(self.FN_Key, key)
                    f.setAttribute(self.FN_Value, value)
                    assert self.addFeature(f)

    def syncToLayer(self):
        editable = self.isEditable()
        if not editable:
            if not self.startEditing():
                err = self.error()
                s = ""
                return
        self.deleteFeatures(self.allFeatureIds())
        self.commitChanges(False)
        self.beginEditCommand('Sync to layer')
        lyr = self.mMapLayer
        objField: QgsField = self.fields().field(self.FN_MajorObject)
        c = objField.constraints()
        if isGDALRasterLayer(lyr):
            c.setConstraintExpression(
                f'"{self.FN_Domain}" in [\'{gdal.Band.__name__}\', \'{gdal.Dataset.__name__}\']')

            ds: gdal.Dataset = gdal.Open(lyr.source())
            if isinstance(ds, gdal.Dataset):
                self.addMajorObjectFeatures(ds)
                for b in range(1, ds.RasterCount + 1):
                    band: gdal.Band = ds.GetRasterBand(b)
                    self.addMajorObjectFeatures(band, f'{b}')
            del ds
        elif isOGRVectorLayer(lyr):
            c.setConstraintExpression(
                f'"{self.FN_Domain}" in [\'{ogr.DataSource.__name__}\', \'{ogr.Layer.__name__}\']')

            match = RX_OGR_URI.search(lyr.source())
            if isinstance(match, typing.Match):
                D = match.groupdict()
                ds: ogr.DataSource = ogr.Open(D['path'])
                if isinstance(ds, ogr.DataSource):
                    self.addMajorObjectFeatures(ds)

                    layername = D.get('layername', None)
                    layerid = D.get('layerid', None)

                    if layername:
                        ogrLayer: ogr.Layer = ds.GetLayerByName(layername)
                        self.addMajorObjectFeatures(ogrLayer, sub_object=layername)
                    else:
                        if not layerid:
                            layerid = 0
                        ogrLayer: ogr.Layer = ds.GetLayerByIndex(layerid)
                        self.addMajorObjectFeatures(ogrLayer, sub_object=layerid)
                del ds

        objField.setConstraints(c)
        self.endEditCommand()
        assert self.commitChanges(not editable)

    def applyToLayer(self):
        pass


def list_or_empty(values, domain: str = None) -> str:
    """
    Takes a list and returns it as string
    :param values: list
    :param domain: str, (optional) with data domain. if `ENVI`, the returned str will start end end with parentheses
    :return: str
    """
    for v in values:
        if v in ['', None, 'None']:
            return ''
    values = [str(v) for v in values]
    result = ', '.join(values)
    if domain == 'ENVI':
        result = f'{{{result}}}'
    return result


class GDALMetadataItemDialog(QDialog):

    def __init__(self, *args,
                 major_objects: typing.List[str] = [],
                 domains: typing.List[str] = [],
                 **kwds):
        super().__init__(*args, **kwds)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'gdalmetadatamodelitemwidget.ui'
        loadUi(pathUi, self)

        for mo in major_objects:
            assert RX_MAJOR_OBJECT_ID.match(mo), mo

        self.tbKey: QLineEdit
        self.tbValue: QLineEdit
        self.cbDomain: QComboBox
        self.cbMajorObject: QComboBox

        self.cbMajorObject.addItems(major_objects)
        self.cbDomain.addItems(domains)

        self.tbKey.textChanged.connect(self.validate)
        self.tbValue.textChanged.connect(self.validate)
        self.cbDomain.currentTextChanged.connect(self.validate)
        self.cbMajorObject.currentTextChanged.connect(self.validate)
        self.validate()

    def validate(self, *args):
        errors = []

        item = self.metadataItem()
        if item['key'] == '':
            errors.append('missing key')
        if item['value'] in [None, NULL, '']:
            errors.append('missing value')

        self.infoLabel.setText('\n'.join(errors))
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(len(errors) == 0)

    def setKey(self, name: str):
        self.tbKey.setText(str(name))

    def setValue(self, value: str):
        self.tbValue.setText(str(value))

    def setDomain(self, domain: str):

        idx = self.cbDomain.findText(domain)
        if idx >= 0:
            self.cbDomain.setCurrentIndex(idx)
        else:
            self.cbDomain.setCurrentText(domain)

    def setMajorObject(self, major_object: str) -> bool:
        i = self.cbMajorObject.findText(str(major_object))
        if i >= 0:
            self.cbMajorObject.setCurrentIndex(i)
            return True
        return False

    def metadataItem(self) -> dict:
        d = dict(key=self.tbKey.text(),
                 value=self.tbValue.text(),
                 domain=self.cbDomain.currentText(),
                 major_object=self.cbMajorObject.currentText())
        return d


RX_MAJOR_OBJECT_ID = re.compile('^('
                                + fr'{gdal.Dataset.__name__}'
                                + fr'|{gdal.Band.__name__}_(?P<bandnumber>\d+)'
                                + fr'|{ogr.DataSource.__name__}'
                                + fr'|{ogr.Layer.__name__}[_ ]?((id_)?(?P<layerid>\d+)|(name_)?(?P<layername>.+))'
                                + ')$')

RX_OGR_URI = re.compile(r'(?P<path>[^|]+)(\|('
                        + r'layername=(?P<layername>[^|]+)'
                        + r'|layerid=(?P<layerid>[^|]+)'
                        + r'|option:(?P<option>[^|]*)'
                        + r'|geometrytype=(?P<geometrytype>[a-zA-Z0-9]*)'
                        + r'|subset=(?P<subset>(?:.*[\r\n]*)*)\\Z'
                        + r'))*', re.I)


class GDALMetadataModelConfigWidget(QpsMapLayerConfigWidget):

    def __init__(self, layer: QgsMapLayer = None, canvas: QgsMapCanvas = None, parent: QWidget = None):
        """
        Constructor
        :param layer: QgsMapLayer
        :param canvas: QgsMapCanvas
        :param parent:
        :type parent:
        """

        if layer is None:
            layer = QgsRasterLayer()
        if canvas is None:
            canvas = QgsMapCanvas()

        super(GDALMetadataModelConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'gdalmetadatamodelwidget.ui'
        loadUi(pathUi, self)

        self.mIsEditable: bool = False

        self.mMessageBar: QgsMessageBar
        self.tbFilter: QLineEdit
        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)
        self._cs = None

        self.mAttributeEditorContext = QgsAttributeEditorContext()
        self.mAttributeEditorContext.setMainMessageBar(self.messageBar())
        self.mAttributeEditorContext.setMapCanvas(self.canvas())

        self.mBandAttributeEditorContext = QgsAttributeEditorContext()
        self.mBandAttributeEditorContext.setMainMessageBar(self.messageBar())
        self.mBandAttributeEditorContext.setMapCanvas(self.canvas())

        self.bandMetadataModel = GDALBandMetadataModel()
        self.bandDualView: QgsDualView

        self.bandDualView.init(self.bandMetadataModel, self.canvas())
        self.bandDualView.currentChanged.connect(self.onBandFormModeChanged)

        self.btnBandTableView.setDefaultAction(self.actionBandTableView)
        self.btnBandFormView.setDefaultAction(self.actionBandFormView)
        self.actionBandTableView.triggered.connect(lambda: self.bandDualView.setView(QgsDualView.AttributeTable))
        self.actionBandFormView.triggered.connect(lambda: self.bandDualView.setView(QgsDualView.AttributeEditor))

        self.metadataModel = GDALMetadataModel()
        self.dualView: QgsDualView
        self.dualView.init(self.metadataModel, self.canvas())
        self.dualView.currentChanged.connect(self.onFormModeChanged)
        self.btnTableView.setDefaultAction(self.actionTableView)
        self.btnFormView.setDefaultAction(self.actionFormView)
        self.actionTableView.triggered.connect(lambda: self.dualView.setView(QgsDualView.AttributeTable))
        self.actionFormView.triggered.connect(lambda: self.dualView.setView(QgsDualView.AttributeEditor))

        self.btnBandCalculator.setDefaultAction(self.actionBandCalculator)
        self.btnCalculator.setDefaultAction(self.actionCalculator)
        self.actionBandCalculator.triggered.connect(lambda: self.showCalculator(self.bandDualView))
        self.actionCalculator.triggered.connect(lambda: self.showCalculator(self.dualView))

        updateBandFilter = lambda: self.updateFilter(self.bandDualView, self.tbBandFilter.text())
        updateFilter = lambda: self.updateFilter(self.dualView, self.tbFilter.text())

        self.tbBandFilter.textChanged.connect(updateBandFilter)
        self.optionBandMatchCase.changed.connect(updateBandFilter)
        self.optionBandRegex.changed.connect(updateBandFilter)

        self.tbFilter.textChanged.connect(updateFilter)
        self.optionMatchCase.changed.connect(updateFilter)
        self.optionRegex.changed.connect(updateFilter)

        assert isinstance(self.classificationSchemeWidget, ClassificationSchemeWidget)

        self.is_gdal = self.is_ogr = self.supportsGDALClassification = False
        self.classificationSchemeWidget.setIsEditable(False)

        self.setLayer(layer)

        self.btnAddItem.setDefaultAction(self.actionAddItem)
        self.btnRemoveItem.setDefaultAction(self.actionRemoveItem)
        self.btnReset.setDefaultAction(self.actionReset)

        self.actionReset.triggered.connect(self.metadataModel.rollBack)
        self.actionRemoveItem.setEnabled(False)
        self.actionAddItem.triggered.connect(self.onAddItem)
        self.actionRemoveItem.triggered.connect(self.onRemoveSelectedItems)
        self.onEditableChanged(self.metadataModel.isEditable())

        self.setEditable(False)

    def setEditable(self, isEditable: bool):

        self.btnBandCalculator.setVisible(isEditable)
        self.btnCalculator.setVisible(isEditable)

        self.btnAddItem.setVisible(isEditable)
        self.btnRemoveItem.setVisible(isEditable)
        self.btnReset.setVisible(isEditable)

        if isEditable:
            self.metadataModel.startEditing()
            self.bandMetadataModel.startEditing()
        else:
            self.metadataModel.commitChanges()
            self.bandMetadataModel.commitChanges()

        assert self.metadataModel.isEditable() == isEditable
        assert self.bandMetadataModel.isEditable() == isEditable

    def showCalculator(self, dualView: QgsDualView):
        assert isinstance(dualView, QgsDualView)
        masterModel: QgsAttributeTableModel = dualView.masterModel()
        if FIELD_CALCULATOR:
            calc: QgsFieldCalculator = QgsFieldCalculator(dualView.masterModel().layer(), self)
            if calc.exec_() == QDialog.Accepted:
                col = masterModel.fieldCol(calc.changedAttributeId())
                if col >= 0:
                    masterModel.reload(masterModel.index(0, col), masterModel.index(masterModel.rowCount() - 1, col))

    def onBandFormModeChanged(self, index: int):
        self.actionBandTableView.setChecked(self.bandDualView.view() == QgsDualView.AttributeTable)
        self.actionBandFormView.setChecked(self.bandDualView.view() == QgsDualView.AttributeEditor)

    def onFormModeChanged(self, index: int):
        self.actionTableView.setChecked(self.dualView.view() == QgsDualView.AttributeTable)
        self.actionFormView.setChecked(self.dualView.view() == QgsDualView.AttributeEditor)

    def showMessage(self, msg: str, level: Qgis.MessageLevel):

        if level == Qgis.Critical:
            duration = 200
        else:
            duration = 50
        line1 = msg.splitlines()[0]
        self.messageBar().pushMessage('', line1, msg, level, duration)

    def messageBar(self) -> QgsMessageBar:
        return self.mMessageBar

    def onWavelengthUnitsChanged(self):
        wlu = self.bandMetadataModel.wavelenghtUnit()

        wlu = self.cbWavelengthUnits.currentData(role=Qt.UserRole)
        self.bandMetadataModel.setWavelengthUnit(wlu)

    def onAddItem(self):
        protectedDomains = [p.split(':')[0] for p in PROTECTED if not p.startswith(':')]
        domains = [d for d in self.metadataModel.domains() if d not in protectedDomains]
        d = GDALMetadataItemDialog(parent=self,
                                   domains=domains,
                                   major_objects=self.metadataModel.major_objects())

        if d.exec_() == QDialog.Accepted:
            item = d.metadataItem()
            self.metadataModel.addItem(item)

    def onRemoveSelectedItems(self):

        rows = self.tvGDALMetadata.selectionModel().selectedRows()

        items = [self.tvGDALMetadata.model().data(row, role=Qt.UserRole) for row in rows]
        for item in items:
            self.metadataModel.removeItem(item)

    def onSelectionChanged(self, *args):

        n = self.dualView.masterModel().layer().selectedFeatureCount()
        self.actionRemoveItem.setEnabled(n > 0)

    def onEditableChanged(self, *args):
        isEditable = self.metadataModel.isEditable()
        self.btnAddItem.setVisible(isEditable)
        self.btnRemoveItem.setVisible(isEditable)
        self.btnReset.setVisible(isEditable)
        self.actionReset.setEnabled(isEditable)
        self.actionAddItem.setEnabled(isEditable)

        self.btnBandCalculator.setVisible(isEditable)
        self.actionBandCalculator.setEnabled(isEditable)

        if isEditable:
            self.bandMetadataModel.startEditing()
        else:
            self.bandMetadataModel.commitChanges()

        self.onSelectionChanged()  # this sets the actionRemoveItem

    def setLayer(self, layer: QgsMapLayer):
        """
        Set the maplayer
        :param layer:
        :type layer:
        :return:
        :rtype:
        """

        if not (isinstance(layer, QgsMapLayer) and layer.isValid()):
            self.is_gdal = self.is_ogr = self.supportsGDALClassification = False
        else:
            self.supportsGDALClassification = False
            self.is_gdal = isGDALRasterLayer(layer)
            self.is_ogr = isOGRVectorLayer(layer)

            if isinstance(layer, QgsRasterLayer):
                self.setPanelTitle('GDAL Metadata')
                self.setToolTip('Layer metadata according to the GDAL Metadata model')
                self.setWindowIcon(QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))
                self.supportsGDALClassification = \
                    self.is_gdal and layer.dataProvider().dataType(1) in \
                    [Qgis.Byte, Qgis.UInt16, Qgis.Int16, Qgis.UInt32, Qgis.Int32, Qgis.Int32]

            elif isinstance(layer, QgsVectorLayer):
                self.setPanelTitle('OGR Metadata')
                self.setToolTip('Layer metadata according to the OGR Metadata model')
                self.setWindowIcon(QIcon(':/qps/ui/icons/edit_ogr_metadata.svg'))

            self.syncToLayer(layer)

    def apply(self):
        if self.is_gdal:
            ds = gdalDataset(self.mapLayer(), gdal.GA_Update)
            assert isinstance(ds, gdal.Dataset)

            if self.supportsGDALClassification:
                cs = self.classificationSchemeWidget.classificationScheme()
                if isinstance(cs, ClassificationScheme):
                    # self.mapLayer().dataProvider().setEditable(True)
                    cs.saveToRaster(ds)
                    ds.FlushCache()

        self.bandMetadataModel.applyToLayer()
        self.metadataModel.applyToLayer()

        QTimer.singleShot(1000, self.syncToLayer)

    def syncToLayer(self, *args):

        super().syncToLayer(*args)
        lyr = self.mapLayer()
        if lyr != self.bandMetadataModel.mMapLayer:
            self.bandMetadataModel.setLayer(lyr)
            self.metadataModel.setLayer(lyr)
            self.optionRegex.changed.emit()
            self.optionBandRegex.changed.emit()
        else:
            self.bandMetadataModel.syncToLayer()
            self.metadataModel.syncToLayer()

        QTimer.singleShot(500, self.autosizeAllColumns)

        if self.supportsGDALClassification:
            self._cs = ClassificationScheme.fromMapLayer(lyr)
        else:
            self._cs = None

        if isinstance(self._cs, ClassificationScheme) and len(self._cs) > 0:
            self.gbClassificationScheme.setVisible(True)
            self.classificationSchemeWidget.setClassificationScheme(self._cs)
        else:
            self.classificationSchemeWidget.classificationScheme().clear()
            self.gbClassificationScheme.setVisible(False)

        self.gbBandNames.setVisible(self.is_gdal)

    def autosizeAllColumns(self):
        self.bandDualView.autosizeAllColumns()
        self.dualView.autosizeAllColumns()

    def updateFilter(self, dualView: QgsDualView, text: str):

        if self.optionMatchCase.isChecked():
            matchCase = Qt.CaseSensitive
        else:
            matchCase = Qt.CaseInsensitive

        if self.optionRegex.isChecked():
            syntax = QRegExp.RegExp
        else:
            syntax = QRegExp.Wildcard
        rx = QRegExp(text, cs=matchCase, syntax=syntax)
        metadataModel = dualView.masterModel().layer()
        if rx.isValid():
            filteredFids = filterFeatures(metadataModel, rx)
            dualView.setFilteredFeatures(filteredFids)
        else:
            dualView.setFilteredFeatures()

        dualView.autosizeAllColumns()


class GDALMetadataConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(GDALMetadataConfigWidgetFactory, self).__init__('GDAL/OGR Metadata',
                                                              QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))
        self.mIsGDAL = False
        self.mIsOGR = False

        self.mIconGDAL = QIcon(':/qps/ui/icons/edit_gdal_metadata.svg')
        self.mIconOGR = QIcon(':/qps/ui/icons/edit_ogr_metadata.svg')

    def supportsLayer(self, layer):
        self.mIsGDAL = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        self.mIsOGR = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'
        return self.mIsGDAL or self.mIsOGR

    def icon(self) -> QIcon:
        if self.mIsGDAL:
            return QIcon(self.mIconGDAL)
        if self.mIsOGR:
            return QIcon(self.mIconOGR)
        return QIcon()

    def layerPropertiesPagePositionHint(self) -> str:
        return 'mOptsPage_Legend'

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

    def createWidget(self, layer, canvas, dockWidget=True, parent=None) -> GDALMetadataModelConfigWidget:
        w = GDALMetadataModelConfigWidget(layer, canvas, parent=parent)
        # w.metadataModel.setIsEditable(True)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w

    def title(self) -> str:
        if self.mIsGDAL:
            return 'GDAL Metadata'
        if self.mIsOGR:
            return 'OGR Metadata'
        return 'Metadata'
