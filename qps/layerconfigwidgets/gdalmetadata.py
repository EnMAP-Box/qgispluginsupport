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
import datetime
import math
import pathlib
import re
import typing
from typing import List, Pattern, Tuple, Union
from osgeo import gdal, ogr

from qgis.PyQt.QtCore import QRegExp, QTimer, Qt, NULL, QVariant, QAbstractTableModel, QModelIndex, \
    QSortFilterProxyModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLineEdit, QDialogButtonBox, QComboBox, QWidget, \
    QDialog, QAction, QTableView
from qgis.core import QgsFeatureSink, QgsAttributeTableConfig, QgsRasterLayer, QgsVectorLayer, QgsMapLayer, \
    QgsEditorWidgetSetup, \
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

    def layer(self) -> QgsMapLayer:
        return self.mMapLayer

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

    def setLayer(self, mapLayer: QgsMapLayer, spectralProperties: QgsRasterLayerSpectralProperties = None):
        if self.mMapLayer == mapLayer:
            self.syncToLayer(spectralProperties=spectralProperties)
            return
        editable = self.isEditable()

        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer
        else:
            self.mMapLayer = None

        self.syncToLayer(spectralProperties=spectralProperties)

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

    def syncToLayer(self, spectralProperties: QgsRasterLayerSpectralProperties = None):
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
        RANGE.setReadOnly(True)
        # RANGEConstraints = QgsFieldConstraints()
        # RANGEConstraints.setConstraintExpression(f'"{BandFieldNames.BandRange}" > 0')

        OFFSET = QgsField(BandFieldNames.Offset, type=QVariant.Double)
        GAIN = QgsField(BandFieldNames.Gain, type=QVariant.Double)
        # add fields
        for field in [BANDNO,
                      DOMAIN,
                      bandName, NODATA, BBL, WL, WLU, FWHM, RANGE, OFFSET, GAIN]:
            field: QgsField
            field.setComment(self.FIELD_TOOLTIP.get(field.name(), ''))
            self.addAttribute(field)

        self.commitChanges(b)

        for field in self.fields():
            i = self.fields().lookupField(field.name())
            self.setEditorWidgetSetup(i, QgsGui.editorWidgetRegistry().findBest(self, field.name()))

        config = self.attributeTableConfig()
        columns: List[QgsAttributeTableConfig.ColumnConfig] = config.columns()
        for column in columns:
            if column.name == BandFieldNames.Domain:
                column.hidden = True
        config.setColumns(columns)
        self.setAttributeTableConfig(config)

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
                if not (a is None or b is None) and math.isfinite(a) and math.isfinite(b):
                    v_min = a - 0.5 * b
                    v_max = a + 0.5 * b
                    bandRange = '{:0.3f} - {:0.3f}'.format(v_min, v_max)
                else:
                    bandRange = None
                bandRanges.append(bandRange)

            ds: gdal.Dataset = gdal.Open(lyr.source())
            gdalBandNames = []
            gdalNoData = []
            gdalScale = []
            gdalOffset = []

            for b in range(ds.RasterCount):
                band: gdal.Band = ds.GetRasterBand(b+1)
                gdalBandNames.append(band.GetDescription())
                gdalNoData.append(band.GetNoDataValue())
                gdalScale.append(band.GetScale())
                gdalOffset.append(band.GetOffset())
            del ds

            KEY2VALUE = {
                BandFieldNames.Number: lambda i: i + 1,
                BandFieldNames.Wavelength: lambda i: wl[i],
                BandFieldNames.WavelengthUnit: lambda i: wlu[i],
                BandFieldNames.BadBand: lambda i: bbl[i],
                BandFieldNames.Range: lambda i: bandRanges[i],
                BandFieldNames.FWHM: lambda i: fwhm[i],
                BandFieldNames.NoData: lambda i: dp.sourceNoDataValue(i + 1),
                BandFieldNames.Name: lambda i: gdalBandNames[i],
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

        if isinstance(ds, gdal.Dataset):
            for f in self.getFeatures():
                f: QgsFeature
                bandNo = f.attribute(BandFieldNames.Number)
                band: gdal.Band = ds.GetRasterBand(bandNo)
                domain = f.attribute(BandFieldNames.Domain)
                if domain in ['', NULL]:
                    domain = None

                for field in f.fields():
                    if field.isReadOnly():
                        continue

                    n = field.name()

                    if n == BandFieldNames.Name:
                        name = f.attribute(BandFieldNames.Name)
                        band.SetDescription(name)
                        continue

                    value = f.attribute(n)
                    enviName = self.FIELD2GDALKey.get(field.name(), None)
                    if enviName:
                        if value in [None, NULL]:
                            band.SetMetadataItem(enviName, '', domain)
                        else:
                            band.SetMetadataItem(enviName, str(value), domain)
            ds.FlushCache()
            del ds


class GDALMetadataItem(object):

    def __init__(self,
                 obj: str = None,
                 domain: str = None,
                 key: str = None,
                 value: str = None
                 ):
        self.obj: str = obj
        self.domain: str = domain
        self.key: str = key
        self.value: str = value

    def __setitem__(self, key, value):
        if key == 0:
            self.obj = str(value)
        elif key == 1:
            self.domain = str(value)
        elif key == 2:
            self.key = str(value)
        elif key == 3:
            self.value = str(value)
        else:
            raise NotImplementedError()

    def __getitem__(self, item):
        return list(self.__dict__.values())[item]

    def __copy__(self):
        return GDALMetadataItem(obj=self.obj,
                                domain=self.domain,
                                key=self.key,
                                value=self.value)


class GDALMetadataModel(QAbstractTableModel):
    CI_MajorObject = 0
    CI_Domain = 1
    CI_Key = 2
    CI_Value = 3

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.mIsEditable: bool = False
        self.mColumnNames = {self.CI_MajorObject: 'Object',
                             self.CI_Domain: 'Domain',
                             self.CI_Key: 'Key',
                             self.CI_Value: 'Value'}

        self.mColumnToolTips = {self.CI_MajorObject: 'Object the metadata item is attached to',
                                self.CI_Domain: 'Metadata domain',
                                self.CI_Key: 'Metadata key',
                                self.CI_Value: 'Metadata value (String)'}

        self.mFeatures: List[GDALMetadataItem] = []
        self.mFeaturesBackup: List[GDALMetadataItem] = []

        self.mMapLayer: QgsMapLayer = None

    def startEditing(self):
        self.setEditable(True)

    def domains(self) -> List[str]:
        return list(set([f.domain for f in self.mFeatures]))

    def major_objects(self) -> List[str]:
        return list(set([f.obj for f in self.mFeatures]))

    def setEditable(self, isEditable: bool):
        self.mIsEditable = bool(isEditable)

    def isEditable(self) -> bool:
        return self.mIsEditable

    def setLayer(self, mapLayer: QgsMapLayer, spectralProperties: QgsRasterLayerSpectralProperties = None):
        if self.mMapLayer == mapLayer:
            self.syncToLayer(spectralProperties=spectralProperties)
            return

        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer
        else:
            self.mMapLayer = None

        self.syncToLayer(spectralProperties=spectralProperties)

    def layer(self) -> QgsMapLayer:
        return self.mMapLayer

    def rollBack(self):
        self.beginResetModel()
        self.mFeatures.clear()
        self.mFeaturesBackup.extend(self.mFeaturesBackup.copy())
        self.endResetModel()

    def createMajorObjectFeatures(self,
                                  obj: gdal.MajorObject,
                                  sub_object: str = None) -> List[GDALMetadataItem]:

        domains = obj.GetMetadataDomainList()
        if not domains:
            return []
        features = []
        for domain in domains:
            MD = obj.GetMetadata(domain)
            if isinstance(MD, dict):
                for key, value in MD.items():

                    name = obj.__class__.__name__
                    if sub_object:
                        name += f'_{sub_object}'
                    item = GDALMetadataItem(obj=name,
                                            domain=domain,
                                            key=key,
                                            value=value)
                    features.append(item)
        return features

    def syncToLayer(self, spectralProperties: QgsRasterLayerSpectralProperties = None):

        self.beginResetModel()
        self.mFeatures.clear()
        self.mFeaturesBackup.clear()

        lyr = self.mMapLayer
        features = []
        t0 = datetime.datetime.now()
        if isGDALRasterLayer(lyr):
            ds: gdal.Dataset = gdal.Open(lyr.source())
            if isinstance(ds, gdal.Dataset):
                features.extend(self.createMajorObjectFeatures(ds))
                for b in range(1, ds.RasterCount + 1):
                    band: gdal.Band = ds.GetRasterBand(b)
                    features.extend(self.createMajorObjectFeatures(band, f'{b}'))
            del ds

        elif isOGRVectorLayer(lyr):
            match = RX_OGR_URI.search(lyr.source())
            if isinstance(match, typing.Match):
                D = match.groupdict()
                ds: ogr.DataSource = ogr.Open(D['path'])
                if isinstance(ds, ogr.DataSource):
                    features.extend(self.createMajorObjectFeatures(ds))

                    layername = D.get('layername', None)
                    layerid = D.get('layerid', None)

                    if layername:
                        ogrLayer: ogr.Layer = ds.GetLayerByName(layername)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layername))
                    else:
                        if not layerid:
                            layerid = 0
                        ogrLayer: ogr.Layer = ds.GetLayerByIndex(layerid)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layerid))
                del ds

        self.mFeatures.extend(features)
        self.mFeaturesBackup.extend(features.copy())
        self.endResetModel()
        print(f'DEBUG: add & commit features {datetime.datetime.now() - t0}')

    def applyToLayer(self):
        pass

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mFeatures)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mColumnNames)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames[section]
            if role == Qt.ToolTipRole:
                return self.mColumnToolTips[section]

        elif orientation == Qt.Vertical:
            if role == Qt.DisplayRole:
                return section + 1

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        if index.column() == self.CI_Value and self.isEditable():
            flags = flags | Qt.ItemIsEditable

        return flags

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:

        if not index.isValid():
            return None

        col = index.column()

        item = self.mFeatures[index.row()]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            return item[col]
        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return False

        if not self.isEditable():
            return False

        edited = False
        col = index.column()
        row = index.row()
        item = self.mFeatures[row]
        value = str(value)
        if role == Qt.EditRole:
            if item[col] != value:
                edited = True
                self.mFeatures[row][col] = value

        if edited:
            self.dataChanged.emit(index, index, [role])
        return edited


class GDALMetadataModel_OLD(GDALMetadataModelBase):
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

    def createMajorObjectFeatures(self, obj: gdal.MajorObject, sub_object: str = None) -> List[QgsFeature]:

        domains = obj.GetMetadataDomainList()
        if not domains:
            return []
        features = []
        for domain in domains:
            MD = obj.GetMetadata(domain)
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
                    features.append(f)
        return features

    def syncToLayer(self, spectralProperties: QgsRasterLayerSpectralProperties = None):
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

        features = []
        t0 = datetime.datetime.now()
        if isGDALRasterLayer(lyr):
            c.setConstraintExpression(
                f'"{self.FN_Domain}" in [\'{gdal.Band.__name__}\', \'{gdal.Dataset.__name__}\']')

            ds: gdal.Dataset = gdal.Open(lyr.source())
            if isinstance(ds, gdal.Dataset):
                features.extend(self.createMajorObjectFeatures(ds))
                for b in range(1, ds.RasterCount + 1):
                    band: gdal.Band = ds.GetRasterBand(b)
                    features.extend(self.createMajorObjectFeatures(band, f'{b}'))
            del ds

        elif isOGRVectorLayer(lyr):
            c.setConstraintExpression(
                f'"{self.FN_Domain}" in [\'{ogr.DataSource.__name__}\', \'{ogr.Layer.__name__}\']')

            match = RX_OGR_URI.search(lyr.source())
            if isinstance(match, typing.Match):
                D = match.groupdict()
                ds: ogr.DataSource = ogr.Open(D['path'])
                if isinstance(ds, ogr.DataSource):
                    features.extend(self.createMajorObjectFeatures(ds))

                    layername = D.get('layername', None)
                    layerid = D.get('layerid', None)

                    if layername:
                        ogrLayer: ogr.Layer = ds.GetLayerByName(layername)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layername))
                    else:
                        if not layerid:
                            layerid = 0
                        ogrLayer: ogr.Layer = ds.GetLayerByIndex(layerid)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layerid))
                del ds

        print(f'DEBUG: create features {datetime.datetime.now() - t0}')
        t0 = datetime.datetime.now()
        objField.setConstraints(c)
        print(f'DEBUG: A set contraints {datetime.datetime.now() - t0}')
        t0 = datetime.datetime.now()
        assert self.addFeatures(features, QgsFeatureSink.FastInsert)
        print(f'DEBUG: B Add features {datetime.datetime.now() - t0}')
        t0 = datetime.datetime.now()
        self.endEditCommand()
        print(f'DEBUG: C end edit command {datetime.datetime.now() - t0}')
        t0 = datetime.datetime.now()
        assert self.commitChanges(not editable)
        print(f'DEBUG: E commit {datetime.datetime.now() - t0}')
        print(f'DEBUG: add & commit features {datetime.datetime.now() - t0}')

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
        if item.key == '':
            errors.append('missing key')
        if item.value in [None, NULL, '']:
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

    def metadataItem(self) -> GDALMetadataItem:
        return GDALMetadataItem(
            key=self.tbKey.text(),
            value=self.tbValue.text(),
            domain=self.cbDomain.currentText(),
            obj=self.cbMajorObject.currentText())


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

RX_LEADING_BAND_NUMBER = re.compile(r'^Band \d+:')

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
        self.btnBandMatchCase.setDefaultAction(self.optionBandMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)
        self.btnBandRegex.setDefaultAction(self.optionBandRegex)
        self.mClassificationScheme: ClassificationScheme = None
        self.classificationSchemeWidget: ClassificationSchemeWidget

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

        self.actionBandTableView.setCheckable(True)
        self.actionBandFormView.setCheckable(True)

        self.btnBandTableView.setDefaultAction(self.actionBandTableView)
        self.btnBandFormView.setDefaultAction(self.actionBandFormView)
        self.actionBandTableView.triggered.connect(lambda: self.setBandModelView(QgsDualView.AttributeTable))
        self.actionBandFormView.triggered.connect(lambda: self.setBandModelView(QgsDualView.AttributeEditor))

        self.metadataModel = GDALMetadataModel()
        self.metadataProxyModel = QSortFilterProxyModel()
        self.metadataProxyModel.setSourceModel(self.metadataModel)
        self.metadataProxyModel.setFilterKeyColumn(-1)  # filter on all columns
        self.metadataView: QTableView
        self.metadataView.setModel(self.metadataProxyModel)
        # self.dualView: QgsDualView
        # self.dualView.init(self.metadataModel, self.canvas())
        # self.dualView.currentChanged.connect(self.onFormModeChanged)
        # self.btnTableView.setDefaultAction(self.actionTableView)
        # self.btnFormView.setDefaultAction(self.actionFormView)
        # self.actionTableView.triggered.connect(lambda: self.dualView.setView(QgsDualView.AttributeTable))
        # self.actionFormView.triggered.connect(lambda: self.dualView.setView(QgsDualView.AttributeEditor))

        self.btnBandCalculator.setDefaultAction(self.actionBandCalculator)
        self.actionBandCalculator.triggered.connect(lambda: self.showCalculator(self.bandDualView))
        # self.btnCalculator.setDefaultAction(self.actionCalculator)
        # self.actionCalculator.triggered.connect(lambda: self.showCalculator(self.dualView))

        updateBandFilter = lambda: self.updateFilter(
            self.bandDualView, self.tbBandFilter.text(), self.optionBandMatchCase, self.optionBandRegex)
        updateFilter = lambda: self.updateFilter(
            self.metadataView, self.tbFilter.text(), self.optionMatchCase, self.optionRegex)

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

        self.onBandFormModeChanged()
        self.setEditable(False)

    def setBandModelView(self, viewMode: QgsDualView.ViewMode):
        self.bandDualView.setView(viewMode)
        self.onBandFormModeChanged()

    def setEditable(self, isEditable: bool):

        for btn in [self.btnBandCalculator,
                    self.btnAddItem,
                    self.btnRemoveItem,
                    self.btnReset]:
            btn: QWidget
            btn.setVisible(isEditable)

        for a in [self.actionAddItem,
                  self.actionRemoveItem,
                  self.actionReset,
                  self.actionBandCalculator]:
            a.setEnabled(isEditable)

        self.classificationSchemeWidget.setIsEditable(isEditable)

        if isEditable:
            # self.metadataModel.startEditing()
            self.metadataModel.setEditable(True)
            self.bandMetadataModel.startEditing()
        else:
            # self.metadataModel.commitChanges()
            self.metadataModel.setEditable(False)
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

    def onBandFormModeChanged(self, *args):
        self.actionBandTableView.setChecked(self.bandDualView.view() == QgsDualView.AttributeTable)
        self.actionBandFormView.setChecked(self.bandDualView.view() == QgsDualView.AttributeEditor)
        s = ""

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

        # n = self.dualView.masterModel().layer().selectedFeatureCount()
        self.metadataView: QTableView
        idx = self.metadataView.selectedIndexes()

        self.actionRemoveItem.setEnabled(self.metadataModel.isEditable() and len(idx) > 0)

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
            # self.bandMetadataModel.setLayer(None)
            # self.metadataModel.setLayer(None)
            self.updateGroupVisibilities()
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

        t0 = datetime.datetime.now()
        super().syncToLayer(*args)
        lyr = self.mapLayer()
        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
        if lyr != self.bandMetadataModel.layer():
            self.bandMetadataModel.setLayer(lyr, spectralProperties=prop)
            self.metadataModel.setLayer(lyr, spectralProperties=prop)
        else:
            self.bandMetadataModel.syncToLayer(spectralProperties=prop)
            self.metadataModel.syncToLayer(spectralProperties=prop)

        # update filters
        self.optionRegex.changed.emit()
        self.optionBandRegex.changed.emit()

        QTimer.singleShot(500, self.autosizeAllColumns)

        if self.supportsGDALClassification:
            self.mClassificationScheme = ClassificationScheme.fromMapLayer(lyr)
        else:
            self.mClassificationScheme = None

        self.updateGroupVisibilities()

        print(f'DEBUG: Total Sync time: {datetime.datetime.now() - t0}')

    def updateGroupVisibilities(self):

        if self.supportsGDALClassification \
                and isinstance(self.mClassificationScheme, ClassificationScheme) \
                and len(self.mClassificationScheme) > 0:
            self.gbClassificationScheme.setVisible(True)
            self.classificationSchemeWidget.setClassificationScheme(self.mClassificationScheme)
        else:
            self.classificationSchemeWidget.classificationScheme().clear()
            self.gbClassificationScheme.setVisible(False)

        self.gbBandNames.setVisible(self.is_gdal)
        self.gbGDALMetadata.setVisible(self.is_gdal or self.is_ogr)

    def autosizeAllColumns(self):
        self.bandDualView.autosizeAllColumns()
        # self.dualView.autosizeAllColumns()
        self.metadataView.resizeColumnsToContents()

    def updateFilter(self,
                     view: Union[QgsDualView, QTableView],
                     text: str,
                     optionMatchCase: QAction,
                     optionRegex: QAction):

        if optionMatchCase.isChecked():
            matchCase = Qt.CaseSensitive
        else:
            matchCase = Qt.CaseInsensitive

        if optionRegex.isChecked():
            syntax = QRegExp.RegExp
        else:
            syntax = QRegExp.Wildcard

        rx = QRegExp(text, cs=matchCase, syntax=syntax)
        if isinstance(view, QgsDualView):
            metadataModel = view.masterModel().layer()
            if rx.isValid():
                filteredFids = filterFeatures(metadataModel, rx)
                view.setFilteredFeatures(filteredFids)
            else:
                view.setFilteredFeatures([])

            view.autosizeAllColumns()
        elif isinstance(view, QTableView):
            proxyModel: QSortFilterProxyModel = view.model()
            proxyModel.setFilterRegExp(rx)


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
