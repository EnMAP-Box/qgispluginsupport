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
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import copy
import datetime
import importlib.util
import json
import math
import pathlib
import re
from pathlib import Path
from typing import Any, Dict, List, Match, Pattern, Tuple, Union

from osgeo import gdal, ogr
from qgis.core import edit, Qgis, QgsAttributeTableConfig, QgsDefaultValue, QgsEditorWidgetSetup, QgsFeature, \
    QgsFeatureRequest, QgsField, QgsFieldConstraints, QgsMapLayer, QgsRasterDataProvider, QgsRasterLayer, QgsVectorLayer
from qgis.gui import QgsAttributeEditorContext, QgsAttributeTableModel, QgsDualView, QgsFieldCalculator, QgsGui, \
    QgsMapCanvas, QgsMapLayerConfigWidgetFactory, QgsMessageBar
from qgis.PyQt.QtCore import NULL, QAbstractTableModel, QMimeData, QModelIndex, QRegExp, \
    QSortFilterProxyModel, Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, \
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QSizePolicy, QTableView, QWidget

from .core import QpsMapLayerConfigWidget
from .. import debugLog
from ..classification.classificationscheme import ClassificationScheme, ClassificationSchemeWidget
from ..qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from ..qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ..utils import gdalDataset, loadUi, ogrDataSource

HAS_PYSTAC = importlib.util.find_spec('pystac') is not None

PROTECTED = [
    'IMAGE_STRUCTURE:INTERLEAVE',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_NAME',
    'DERIVED_SUBDATASETS:DERIVED_SUBDATASET_1_DESC'
    ':AREA_OR_POINT'
]

MAJOR_OBJECTS = [gdal.Dataset.__name__, gdal.Band.__name__, ogr.DataSource.__name__, ogr.Layer.__name__]

MDF_GDAL_BANDMETADATA = 'qgs/gdal_band_metadata'


class MetadataUtils(object):
    """
    A class to parse metadata files
    """
    rxSingle = re.compile(r'^(?P<key>[^=\n]+)= *(?P<value>[^{ ][^{}\n]*)', re.M)
    rxArray = re.compile(r'^(?P<key>[^=\n]+)= *{(?P<values>[^{}]+)}', re.M)

    @staticmethod
    def parseEnviHeader(text: str) -> Dict[str, Union[str, List]]:

        # remove comments
        lines = text.splitlines(False)
        lines = [line for line in lines if not re.search(r'\s*#.*', line)]
        lines = '\n'.join(lines)

        ENVI = dict()
        r1 = MetadataUtils.rxSingle.findall(lines)
        r2 = MetadataUtils.rxArray.findall(lines)
        for r in r1 + r2:
            value = re.sub(' *\n+ *', ' ', r[1].strip()).strip()
            if len(value) > 0:
                if r in r2:
                    value = re.split(r' *, *', value)
                ENVI[r[0].strip()] = value

        md = dict()

        if len(ENVI) > 0:

            LUT = {'wavelength units': BandFieldNames.WavelengthUnit,
                   'wavelength': BandFieldNames.Wavelength,
                   'fwhm': BandFieldNames.FWHM,
                   'bbl': BandFieldNames.BadBand,
                   'band names': BandFieldNames.Name,
                   'data gain values': BandFieldNames.Scale,
                   'data offset values': BandFieldNames.Offset,
                   'data ignore value': BandFieldNames.NoData
                   }

            for enviKey, fieldName in LUT.items():
                if enviKey in ENVI.keys():
                    md[fieldName] = ENVI[enviKey]

        return md

    @staticmethod
    def parseSTAC(text: str) -> Dict:

        md = dict()
        if not HAS_PYSTAC:
            return md

        try:
            d = json.loads(text)
        except ValueError:
            return md

        import pystac
        from pystac import STACTypeError
        try:
            stac_item = pystac.Item.from_dict(d)

            # field, keys
            field_items = {'eo:bands': [
                ('common_name', BandFieldNames.Name),
                ('center_wavelength', BandFieldNames.Wavelength),
                ('full_width_half_max', BandFieldNames.FWHM),
            ],
                'raster:bands': [
                    ('nodata', BandFieldNames.NoData),
                    ('scale', BandFieldNames.Scale),
                    ('offset', BandFieldNames.Offset),
                ],
            }

            for asset_key, asset in stac_item.assets.items():

                for field_group, group_members in field_items.items():
                    if field_group in asset.extra_fields:
                        for iBand, band_info in enumerate(asset.extra_fields[field_group]):
                            for (stac_member, tag) in group_members:
                                if stac_member in band_info:
                                    md[tag] = md.get(tag, []) + [band_info[stac_member]]
                                if field_group == 'eo:bands' and stac_member == 'center_wavelength':
                                    # by default, STAC wavelength are micrometers
                                    md[BandFieldNames.WavelengthUnit] = (md.get(BandFieldNames.WavelengthUnit, [])
                                                                         + ['μm'])

        except STACTypeError:
            return md
        return md


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


def value2str(v: Any) -> str:
    """
    Converts a QgsFeature attribute value into a string
    """
    if v in [None, NULL]:
        return ''
    else:
        return str(v)


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
    # Domain = 'Domain'
    Number = 'Band'
    Name = 'Band Name'
    BadBand = 'BBL'
    Offset = 'Offset'
    Scale = 'Scale'
    NoData = 'No Data'
    FWHM = 'FWHM'
    Wavelength = 'Wavelength'
    WavelengthUnit = 'Wavelength Unit'
    Range = 'Wavelength Range'
    # ENVI Header
    # ENVIDataGain = 'Data Gain' # GDAL 3.6 -> Scale
    # ENVIDataOffset = 'Data Offset' # GDAL 3.6 -> Offset
    ENVIDataReflectanceGain = 'Data Refl. Gain'
    ENVIDataReflectanceOffset = 'Data Refl. Offset'


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


class GDALBandMetadataModel(QgsVectorLayer):
    FIELD2GDALKey = {
        BandFieldNames.BadBand: 'bbl',
        BandFieldNames.Range: 'band width',
        BandFieldNames.Wavelength: 'wavelength',
        BandFieldNames.WavelengthUnit: 'wavelength units',
        BandFieldNames.FWHM: 'fwhm',
        BandFieldNames.Offset: 'data offset values',
        BandFieldNames.Scale: 'data gain values'
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
        # BandFieldNames.Domain: "Metadata domain.<br>'' = default domain<br>'ENVI' = ENVI domain",
        BandFieldNames.BadBand: 'Bad band multiplier value. <br>0 = exclude, <br>1 = use band',
        BandFieldNames.FWHM: 'Full width at half maximum or band width, respectively',
        BandFieldNames.Offset: 'Data offset',
        BandFieldNames.Scale: 'Data scale or gain',

        # BandFieldNames.ENVIDataOffset: 'ENVI Header Data Offset<br>Values can differ from normal (GDAL) data offset',
        # BandFieldNames.ENVIDataGain: 'ENVI Header Data Gain<br>Values can differ from normal (GDAL) data scale',
    }

    def __init__(self):
        super().__init__('none?', '', 'memory')

        self.mMapLayer: QgsMapLayer = None
        self.initFields()

        self.mDataLookup: List[Tuple[QgsField, Pattern]] = []

        self.hasEdits: bool = False

        def setEditsTrue():
            self.hasEdits = True

        self.dataChanged.connect(setEditsTrue)
        self.committedFeaturesAdded.connect(setEditsTrue)
        self.committedFeaturesRemoved.connect(setEditsTrue)
        self.committedAttributeValuesChanges.connect(setEditsTrue)

    def resetChangesFlag(self) -> bool:
        v = self.wasChangedFlag
        self.wasChangedFlag = False
        return v

    def layer(self) -> QgsMapLayer:
        return self.mMapLayer

    def createDomainField(self) -> QgsField:
        DOMAIN = QgsField(BandFieldNames.Domain, type=QMETATYPE_QSTRING)
        constraint = QgsFieldConstraints()
        DOMAIN.setReadOnly(True)
        DOMAIN.setDefaultValueDefinition(QgsDefaultValue(''))
        return DOMAIN

    def bandKey(self, bandNo: int) -> str:
        assert bandNo > 0
        if isinstance(self.mMapLayer, QgsRasterLayer) \
                and isinstance(self.mMapLayer.dataProvider(), QgsRasterDataProvider):
            self.mMapLayer: QgsRasterLayer
            z = math.floor(math.log10(self.mMapLayer.bandCount())) + 1
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

        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer
        else:
            self.mMapLayer = None

        self.syncToLayer(spectralProperties=spectralProperties)

    def toFieldValue(self, value):

        if value in ['', None, NULL]:
            return None
        elif isinstance(value, float) and math.isnan(value):
            return None
        return value

    def resetEditsFlag(self) -> bool:
        v = self.hasEdits
        self.hasEdits = False
        return v

    def initFields(self):
        assert self.fields().count() == 0
        # define default fields
        is_editable = self.isEditable()
        self.startEditing()

        # DOMAIN = self.createDomainField()
        BANDNO = QgsField(BandFieldNames.Number, type=QMETATYPE_INT)
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

        bandName = QgsField(BandFieldNames.Name, type=QMETATYPE_QSTRING, len=-1, )

        NODATA = QgsField(BandFieldNames.NoData, type=QMETATYPE_DOUBLE)

        BBL = QgsField(BandFieldNames.BadBand, type=QMETATYPE_INT)
        BBL.setDefaultValueDefinition(QgsDefaultValue('1'))
        BBL.setEditorWidgetSetup(QgsEditorWidgetSetup())

        WL = QgsField(BandFieldNames.Wavelength, type=QMETATYPE_DOUBLE)

        WLU = QgsField(BandFieldNames.WavelengthUnit, type=QMETATYPE_QSTRING)
        # wluConstraints = QgsFieldConstraints()
        # wluConstraints.setConstraintExpression('"{BandPropertyKeys.WavelengthUnit}" in [\'nm\', \'m\']')
        # WLU.setConstraints(wluConstraints)

        FWHM = QgsField(BandFieldNames.FWHM, type=QMETATYPE_DOUBLE)
        FWHMConstraints = QgsFieldConstraints()
        FWHMConstraints.setConstraintExpression(f'"{BandFieldNames.FWHM}" is NULL or "{BandFieldNames.FWHM}" > 0')
        FWHM.setConstraints(FWHMConstraints)

        RANGE = QgsField(BandFieldNames.Range, type=QMETATYPE_QSTRING)
        RANGE.setReadOnly(True)
        # RANGEConstraints = QgsFieldConstraints()
        # RANGEConstraints.setConstraintExpression(f'"{BandFieldNames.BandRange}" > 0')

        OFFSET = QgsField(BandFieldNames.Offset, type=QMETATYPE_DOUBLE)
        SCALE = QgsField(BandFieldNames.Scale, type=QMETATYPE_DOUBLE)

        # ENVI_OFFSET = QgsField(BandFieldNames.ENVIDataOffset, type=QMETATYPE_DOUBLE)
        # ENVI_GAIN = QgsField(BandFieldNames.ENVIDataGain, type=QMETATYPE_DOUBLE)

        # add fields
        for field in [BANDNO,
                      # DOMAIN,
                      bandName, NODATA, BBL, WL, WLU, FWHM, RANGE, OFFSET, SCALE,
                      # ENVI_OFFSET, ENVI_GAIN
                      ]:
            field: QgsField
            field.setComment(self.FIELD_TOOLTIP.get(field.name(), ''))
            self.addAttribute(field)

        self.commitChanges(is_editable)

        for field in self.fields():
            i = self.fields().lookupField(field.name())
            self.setEditorWidgetSetup(i, QgsGui.editorWidgetRegistry().findBest(self, field.name()))

        config = self.attributeTableConfig()
        columns: List[QgsAttributeTableConfig.ColumnConfig] = config.columns()
        for column in columns:
            # if column.name == BandFieldNames.Domain:
            #     column.hidden = True
            pass
        config.setColumns(columns)
        self.setAttributeTableConfig(config)

        self.commitChanges(not is_editable)

    def asMap(self) -> dict:

        data = dict()
        for f in self.getFeatures():
            f: QgsFeature

            bandNo = f.attribute(BandFieldNames.Number)
            # bandDomain = f.attribute(BandFieldNames.Domain)

            for field in f.fields():
                n = field.name()
                value = f.attribute(n)
                gdalKey = self.FIELD2GDALKey.get(field.name(), None)
                if gdalKey:
                    mapKey = self.mapKey(self.bandKey(bandNo), '', gdalKey)

                    if value in [None, NULL]:
                        value = ''
                    else:
                        value = str(value).strip()
                    data[mapKey] = value
        return data

    @classmethod
    def bandMetadataFromMimeData(cls, mimeData: QMimeData) -> Dict[str, Union[str, List]]:

        metadata = dict()

        ENVI: dict = dict()
        STAC: dict = dict()

        if len(metadata) == 0 and mimeData.hasUrls():
            max_size = 10 ** 1024 * 1024  # 10 MBytes
            for url in mimeData.urls():
                url: QUrl
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.exists() and path.stat().st_size < max_size:
                        if path.name.lower().endswith('.hdr'):
                            with open(path) as f:
                                ENVI = MetadataUtils.parseEnviHeader(f.read())
                        elif path.name.lower().endswith('.json'):
                            with open(path) as f:
                                STAC = MetadataUtils.parseSTAC(f.read())
        elif mimeData.hasText():
            text = mimeData.text()
            ENVI = MetadataUtils.parseEnviHeader(mimeData.text())
            STAC = MetadataUtils.parseSTAC(mimeData.text())

        elif mimeData.hasFormat(MDF_GDAL_BANDMETADATA):
            dump = mimeData.data(MDF_GDAL_BANDMETADATA)
            data = bytes(dump).decode('UTF-8')
            metadata.update(json.loads(data) if data != '' else dict())
            return metadata

        for md in [ENVI, STAC]:
            if len(md) > 0:
                return md

        return dict()

    def onWillShowBandContextMenu(self, menu: QMenu, index: QModelIndex):
        tv: QTableView = menu.parent()
        if isinstance(tv, QTableView):
            cName = tv.model().headerData(index.column(), Qt.Horizontal)
        else:
            cName = self.fields().names()[index.column()]

        aCopyMD: QAction = menu.addAction('Copy Metadata')
        aCopyMD.triggered.connect(self.copyBandMetadata)

        aCopyCol: QAction = menu.addAction(f'Copy {cName}')
        aCopyCol.triggered.connect(lambda *args, f=cName: self.copyBandMetadata(field=f))

        mPaste: QMenu = menu.addMenu('Paste Metadata')

        metadata: dict = self.bandMetadataFromMimeData(QApplication.clipboard().mimeData())

        mPaste.setEnabled(self.isEditable() and len(metadata))
        mPaste.triggered.connect(self.pasteBandMetadata)
        aPasteAll = mPaste.addAction('All')

        aPasteAll.triggered.connect(lambda *args, md=metadata: self.pasteBandMetadata(metadata=md))

        for n in self.fields().names():
            field: QgsField = self.fields().field(n)
            if not field.isReadOnly():
                a: QAction = mPaste.addAction(n)

                if n in metadata.keys():
                    a.setEnabled(True)
                    a.triggered.connect(lambda *args, md={n: metadata[n]}: self.pasteBandMetadata(*args, metadata=md))
                else:
                    a.setEnabled(False)

    def pasteBandMetadata(self, *args, metadata: dict = None) -> List[str]:
        if not self.isEditable():
            return

        if not isinstance(metadata, dict):
            metadata = self.bandMetadataFromMimeData(QApplication.clipboard().mimeData())
            if len(args) > 0 and isinstance(args[0], QAction):
                n = args[0].text()
                if n in metadata.keys():
                    metadata = {n: metadata[n]}
        if not isinstance(metadata, dict):
            return

        fields = [k for k in metadata.keys() if k in self.fields().names()
                  and not self.fields().field(k).isReadOnly()]
        for b, feature in enumerate(self.orderedFeatures()):
            for f in fields:
                fieldId: int = self.fields().lookupField(f)
                value = metadata.get(f, None)
                if isinstance(value, str):
                    self.changeAttributeValue(feature.id(), fieldId, value)
                elif isinstance(value, list):
                    if b < len(value):
                        self.changeAttributeValue(feature.id(), fieldId, value[b])
        self.dataChanged.emit()
        return fields

    def copyBandMetadata(self, bands: List[int] = None, field: str = None):

        if field is None:
            fields = self.fields().names()
        else:
            assert field in self.fields().names()
            fields = [field]

        MD = {f: [] for f in fields}

        for b, feature in enumerate(self.orderedFeatures()):
            feature: QgsFeature
            for f in MD.keys():
                v = feature.attribute(f)
                if v == NULL:
                    v = None
                MD[f].append(v)
        data = json.dumps(MD)
        mimeData = QMimeData()
        mimeData.setData(MDF_GDAL_BANDMETADATA, data.encode('utf-8'))
        mimeData.setText(data)
        QApplication.clipboard().setMimeData(mimeData)

    def syncToLayer(self, *args, spectralProperties: QgsRasterLayerSpectralProperties = None):

        was_editable = self.isEditable()

        if was_editable:
            self.rollBack()

        with edit(self):
            self.deleteFeatures(self.allFeatureIds())

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

                lyrScale = []
                lyrOffset = []
                lyrNoData = []

                # ENVIDataOffset = spectralProperties.bandValues(None, 'data_gain')
                # ENVIDataGain = spectralProperties.bandValues(None, 'data_offset')

                # hide ENVI specific columns if they do not provide meaningfull information
                # show_envi = any(ENVIDataOffset) or any(ENVIDataGain)

                tableConfig = self.attributeTableConfig()
                columnConfigs = tableConfig.columns()

                for c in columnConfigs:
                    c: QgsAttributeTableConfig.ColumnConfig
                    # if c.name in [BandFieldNames.ENVIDataOffset, BandFieldNames.ENVIDataGain]:
                    #    c.hidden = not show_envi
                tableConfig.setColumns(columnConfigs)
                self.setAttributeTableConfig(tableConfig)

                for b in range(ds.RasterCount):
                    band: gdal.Band = ds.GetRasterBand(b + 1)
                    gdalBandNames.append(band.GetDescription())
                    gdalNoData.append(band.GetNoDataValue())
                    gdalScale.append(band.GetScale())
                    gdalOffset.append(band.GetOffset())

                    lyrScale.append(dp.bandScale(b + 1))
                    lyrOffset.append(dp.bandOffset(b + 1))
                    lyrNoData.append(dp.sourceNoDataValue(b + 1))

                del ds

                KEY2VALUE = {
                    BandFieldNames.Number: lambda i: i + 1,
                    BandFieldNames.Wavelength: lambda i: wl[i],
                    BandFieldNames.WavelengthUnit: lambda i: wlu[i],
                    BandFieldNames.BadBand: lambda i: bbl[i],
                    BandFieldNames.Range: lambda i: bandRanges[i],
                    BandFieldNames.FWHM: lambda i: fwhm[i],
                    BandFieldNames.NoData: lambda i: gdalNoData[i],
                    BandFieldNames.Name: lambda i: gdalBandNames[i],
                    # BandFieldNames.Domain: lambda i: domain,
                    BandFieldNames.Offset: lambda i: gdalOffset[i],
                    BandFieldNames.Scale: lambda i: gdalScale[i],

                    # BandFieldNames.ENVIDataOffset: lambda i: ENVIDataOffset[i],
                    # BandFieldNames.ENVIDataGain: lambda i: ENVIDataGain[i],
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
                self.hasEdits = False
        self.hasEdits = False
        if was_editable:
            self.startEditing()

    def orderedFeatures(self) -> List[QgsFeature]:
        request = QgsFeatureRequest()
        request.addOrderBy('"Band"', True, True)
        return self.getFeatures(request)

    def applyToGDALSource(self):

        cpl_state_pam: str = gdal.GetConfigOption('GDAL_PAM_ENABLED', 'YES')
        gdal.SetConfigOption('GDAL_PAM_ENABLED', 'YES')

        ds = gdalDataset(self.mMapLayer, eAccess=gdal.GA_Update)
        assert isinstance(ds, gdal.Dataset)

        is_envi: bool = ds.GetDriver().ShortName == 'ENVI'

        domain = None
        if is_envi:
            domain = 'ENVI'

        for f in self.orderedFeatures():
            f: QgsFeature
            bandNo = f.attribute(BandFieldNames.Number)
            # assert f.id() == bandNo
            band: gdal.Band = ds.GetRasterBand(bandNo)
            if not isinstance(band, gdal.Band):
                continue

            # domain = f.attribute(BandFieldNames.Domain)
            # if domain in ['', NULL]:
            #    domain = None

            for field in f.fields():
                if field.isReadOnly():
                    continue

                n = field.name()
                value = f.attribute(n)
                if value == NULL:
                    value = None

                # handle metadata available with designated GDAL API access
                if n == BandFieldNames.Name:
                    band.SetDescription(value2str(value))

                elif n == BandFieldNames.Scale:
                    if value:
                        band.SetScale(value)
                    else:
                        band.SetScale(1)

                elif n == BandFieldNames.Offset:
                    if value:
                        band.SetOffset(value)
                    else:
                        band.SetOffset(0)

                elif n == BandFieldNames.NoData:
                    if value:
                        band.SetNoDataValue(value)
                    else:
                        band.DeleteNoDataValue()

                else:
                    # handle non-designated metadata values
                    v = value2str(value)
                    md_key = self.FIELD2GDALKey.get(field.name(), None)
                    if md_key:
                        band.SetMetadataItem(md_key, v, domain)

        self.driverSpecific(ds)
        ds.FlushCache()
        del ds

        gdal.SetConfigOption('GDAL_PAM_ENABLED', cpl_state_pam)

    def applyToOGRSource(self):
        pass

    def applyToLayer(self, *args):

        if self.hasEdits:
            if isGDALRasterLayer(self.mMapLayer):
                self.applyToGDALSource()
            elif isOGRVectorLayer(self.mMapLayer):
                self.applyToOGRSource()

            self.resetEditsFlag()

            self.mMapLayer.reload()

    def driverSpecific(self, ds: gdal.Dataset):

        drv: gdal.Driver = ds.GetDriver()

        if drv.ShortName == 'ENVI':
            wlu = ds.GetRasterBand(1).GetMetadataItem('wavelength units')
            ds.SetMetadataItem('wavelength units', wlu, 'ENVI')
            bandNames = []
            wl = []
            for b in range(ds.RasterCount):
                band: gdal.Band = ds.GetRasterBand(b + 1)
                bandNames.append(band.GetDescription())
                wl.append(band.GetMetadataItem('wavelengths'))


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
        self.initialValue: str = value

    def isModified(self) -> bool:
        return self.value != self.initialValue

    def __str__(self):
        return f'{self.obj}:{self.domain}:{self.key}:{self.value}'

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
        self.hasEdits: bool = False

        def setEditsTrue():
            self.hasEdits = True

        self.rowsInserted.connect(setEditsTrue)
        self.rowsRemoved.connect(setEditsTrue)
        self.dataChanged.connect(setEditsTrue)

        self.mIsEditable: bool = False
        self.mColumnNames = {self.CI_MajorObject: 'Object',
                             self.CI_Domain: 'Domain',
                             self.CI_Key: 'Key',
                             self.CI_Value: 'Value'}

        self.mColumnToolTips = {self.CI_MajorObject: 'Object the metadata item is attached to',
                                self.CI_Domain: 'Metadata domain',
                                self.CI_Key: 'Metadata key',
                                self.CI_Value: 'Metadata value (always a text value)'}

        self.mMajorObjectIds: List[str] = []
        self.mFeatures: List[GDALMetadataItem] = []
        self.mFeaturesBackup: List[GDALMetadataItem] = []

        self.mMapLayer: QgsMapLayer = None

    def startEditing(self):
        self.setEditable(True)

    def domains(self) -> List[str]:
        return list(set([f.domain for f in self.mFeatures]))

    def majorObjects(self) -> List[str]:
        return self.mMajorObjectIds[:]

    def potentialMajorObjects(self) -> List[str]:

        if isGDALRasterLayer(self.mMapLayer):
            return [gdal.Dataset.__name__, gdal.Band.__name__]
        elif isOGRVectorLayer(self.mMapLayer):
            return [ogr.DataSource.__name__, ogr.Layer.__name__]

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
        self.mFeatures.extend(copy.deepcopy(self.mFeaturesBackup))
        self.endResetModel()

    def majorObjectId(self, obj: gdal.MajorObject, sub_object: str = None) -> str:

        moId = obj.__class__.__name__
        if sub_object is not None:
            moId += f'_{sub_object}'
        return moId

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
                    item = GDALMetadataItem(obj=self.majorObjectId(obj, sub_object),
                                            domain=domain,
                                            key=key,
                                            value=value)
                    features.append(item)
        return features

    def syncToLayer(self, spectralProperties: QgsRasterLayerSpectralProperties = None):

        lyr = self.mMapLayer
        features: List[GDALMetadataItem] = []
        majorObjectIds: List[str] = []

        t0 = datetime.datetime.now()
        if isGDALRasterLayer(lyr):

            ds: gdal.Dataset = gdal.Open(lyr.source())
            if isinstance(ds, gdal.Dataset):
                majorObjectIds.append(self.majorObjectId(ds, None))
                features.extend(self.createMajorObjectFeatures(ds))
                for b in range(1, ds.RasterCount + 1):
                    band: gdal.Band = ds.GetRasterBand(b)
                    features.extend(self.createMajorObjectFeatures(band, b))
                    majorObjectIds.append(self.majorObjectId(band, b))
            del ds

        elif isOGRVectorLayer(lyr):
            match = RX_OGR_URI.search(lyr.source())
            if isinstance(match, Match):
                D = match.groupdict()
                ds: ogr.DataSource = ogr.Open(D['path'])
                if isinstance(ds, ogr.DataSource):
                    features.extend(self.createMajorObjectFeatures(ds))
                    majorObjectIds.append(self.majorObjectId(ds, None))
                    layername = D.get('layername', None)
                    layerid = D.get('layerid', None)

                    if layername:
                        ogrLayer: ogr.Layer = ds.GetLayerByName(layername)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layername))
                        majorObjectIds.append(self.majorObjectId(ogrLayer, sub_object=layername))
                    else:
                        if not layerid:
                            layerid = 0
                        ogrLayer: ogr.Layer = ds.GetLayerByIndex(layerid)
                        features.extend(self.createMajorObjectFeatures(ogrLayer, sub_object=layerid))
                        majorObjectIds.append(self.majorObjectId(ogrLayer, sub_object=layerid))
                del ds

        self.beginResetModel()
        self.mFeatures.clear()
        self.mMajorObjectIds.clear()
        self.mFeaturesBackup.clear()

        self.mMajorObjectIds.extend(majorObjectIds)
        self.mFeatures.extend(features)
        self.mFeaturesBackup.extend(copy.deepcopy(features))
        self.endResetModel()
        debugLog(f'DEBUG: add & commit features {datetime.datetime.now() - t0}')

    def appendMetadataItem(self, item: GDALMetadataItem):
        assert isinstance(item, GDALMetadataItem)
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self.mFeatures.append(item)
        self.endInsertRows()

    def applyToGDALSource(self):

        cpl_state_pam: str = gdal.GetConfigOption('GDAL_PAM_ENABLED', 'YES')
        gdal.SetConfigOption('GDAL_PAM_ENABLED', 'YES')

        ds: gdal.Dataset = gdalDataset(self.mMapLayer, gdal.GA_Update)
        assert isinstance(ds, gdal.Dataset)

        modified = [f for f in self.mFeatures if f.isModified()]
        for item in [f for f in modified if f.obj == gdal.Dataset.__name__]:
            assert gdal.CPLE_None == ds.SetMetadataItem(item.key, str(item.value), item.domain)

        LUT_BANDS = {}
        for item in [f for f in modified if gdal.Band.__name__ in f.obj]:
            b = int(item.obj.split('_')[-1])
            LUT_BANDS[b] = LUT_BANDS.get(b, []).append(item)

        for b, items in LUT_BANDS.items():
            band: gdal.Dataset = ds.GetRasterBand(b)
            assert isinstance(band, gdal.Band)
            assert gdal.CPLE_None == band.SetMetadataItem(item.key, str(item.value), item.domain)

        ds.FlushCache()
        del ds

        gdal.SetConfigOption('GDAL_PAM_ENABLED', cpl_state_pam)

    def applyToOGRSource(self):
        ds: ogr.DataSource = ogrDataSource(self.mMapLayer, update=gdal.GA_Update)
        assert isinstance(ds, ogr.DataSource)

        modified = [f for f in self.mFeatures if f.isModified()]
        for item in modified:
            match = RX_MAJOR_OBJECT_ID.match(item.obj)
            assert match
            if item.obj == ogr.DataSource.__name__:
                assert gdal.CPLE_None == ds.SetMetadataItem(item.key, str(item.value), item.domain)
            else:
                D = match.groupdict()
                layerid = D.get('layerid', None)
                layername = D.get('layername', None)

                layer = None
                if layerid:
                    layer: ogr.Layer = ds.GetLayerByIndex(int(layerid))
                elif layername:
                    layer: ogr.Layer = ds.GetLayerByName(layername)
                assert isinstance(layer, ogr.Layer)
                assert gdal.CPLE_None == layer.SetMetadataItem(item.key, str(item.value), item.domain)

        ds.FlushCache()
        del ds
        s = ""

    def applyToLayer(self):

        if self.hasEdits:

            if isGDALRasterLayer(self.mMapLayer):
                self.applyToGDALSource()

            elif isOGRVectorLayer(self.mMapLayer):
                self.applyToOGRSource()

            self.resetEditsFlag()

    def resetEditsFlag(self) -> bool:
        v = self.hasEdits
        self.hasEdits = False
        return v

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mFeatures)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mColumnNames)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
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

    def data(self, index: QModelIndex, role: int = ...) -> Any:

        if not index.isValid():
            return None

        col = index.column()

        item = self.mFeatures[index.row()]

        if role in [Qt.DisplayRole, Qt.EditRole]:
            return item[col]
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = ...) -> bool:

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
                 major_objects: List[str] = [],
                 domains: List[str] = [],
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


class BandPropertyCalculator(QgsFieldCalculator):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        assert self.objectName() == 'QgsFieldCalculatorBase'
        self.setWindowTitle('Band Property Calculator')

        cbOnlyUpdate: QCheckBox = self.findChild(QCheckBox, name='mOnlyUpdateSelectedCheckBox')
        gbNewField: QGroupBox = self.findChild(QGroupBox, name='mNewFieldGroupBox')
        cbFields: QComboBox = self.findChild(QComboBox, name='mExistingFieldComboBox')
        gbUpdate: QGroupBox = self.findChild(QGroupBox, name='mUpdateExistingGroupBox')

        if isinstance(cbOnlyUpdate, QCheckBox) and \
                isinstance(gbNewField, QGroupBox) and \
                isinstance(cbFields, QComboBox) and \
                isinstance(gbUpdate, QGroupBox):

            gridLayout: QGridLayout = self.layout()

            # remove them all from their parent layouts
            for w in [cbOnlyUpdate, gbNewField, cbFields, gbUpdate]:
                layout = w.parentWidget().layout()
                layout.takeAt(layout.indexOf(w))

            gbNewField.setVisible(False)
            gbNewField.setChecked(False)

            gbUpdate.setVisible(False)
            gbUpdate.setChecked(True)
            # gb.setCheckable(False)
            gbUpdate.setTitle('Update band property')

            cbOnlyUpdate.setText('Only update selected bands')

            # rename the label from 'Feature' to 'Band'
            pw: QWidget = self.findChild(QWidget, name='mExpressionPreviewWidget')
            if isinstance(pw, QWidget):
                label = pw.findChild(QLabel, name='label_2')
                if isinstance(label, QLabel):
                    label.setText('Band')
            s = ""
            # re-add
            vl = QHBoxLayout()
            vl.setSpacing(4)
            vl.addWidget(cbOnlyUpdate)
            vl.addSpacing(15)
            vl.addWidget(QLabel('Band Property', parent=self))
            # vl.addWidget(QLabel('Property'))
            # cbFields.setParent(self)
            vl.addWidget(cbFields)
            cbFields.setParent(self)
            cbFields.setVisible(True)
            cbFields.setCurrentIndex(1)  # set on Band Name
            policy: QSizePolicy = cbFields.sizePolicy()
            policy.setHorizontalStretch(2)
            cbFields.setSizePolicy(policy)
            gridLayout.addItem(vl, 0, 0, 1, 2)
            s = ""
            return


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
        self.bandDualView.tableView().willShowContextMenu.connect(
            self.bandMetadataModel.onWillShowBandContextMenu)
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

        self.btnEdit.setDefaultAction(self.optionEdit)
        self.btnBandEdit.setDefaultAction(self.optionBandEdit)

        self.optionEdit.toggled.connect(self.onEditToggled)
        self.optionBandEdit.toggled.connect(self.onBandEditToggled)

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
        self.btnBandReset.setDefaultAction(self.actionBandReset)

        self.actionBandReset.triggered.connect(self.bandMetadataModel.rollBack)
        self.actionReset.triggered.connect(self.metadataModel.rollBack)
        self.actionRemoveItem.setEnabled(False)
        self.actionAddItem.triggered.connect(self.onAddItem)
        self.actionRemoveItem.triggered.connect(self.onRemoveSelectedItems)

        self.onBandEditToggled(self.optionBandEdit.isChecked())
        self.onEditToggled(self.optionEdit.isChecked())

        self.onBandFormModeChanged()
        self.setEditable(False)

    def onCustomBandContextMenuRequested(self, *args):
        s = ""

    def setBandModelView(self, viewMode: QgsDualView.ViewMode):
        self.bandDualView.setView(viewMode)
        self.onBandFormModeChanged()

    def setEditable(self, isEditable: bool):

        self.optionEdit.setChecked(isEditable)
        self.optionBandEdit.setChecked(isEditable)

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
        calc: QgsFieldCalculator = BandPropertyCalculator(dualView.masterModel().layer(), self)

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
        major_objects = self.metadataModel.majorObjects()
        d = GDALMetadataItemDialog(parent=self,
                                   domains=domains,
                                   major_objects=major_objects)

        if d.exec_() == QDialog.Accepted:
            item = d.metadataItem()
            # set init
            item.initialValue = None
            self.metadataModel.appendMetadataItem(item)

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

    def onBandEditToggled(self, isEditable: bool):

        # self.btnBandCalculator.setVisible(isEditable)
        self.actionBandCalculator.setEnabled(isEditable)
        self.actionBandReset.setEnabled(isEditable)
        if isEditable:
            self.bandMetadataModel.startEditing()
        else:
            self.bandMetadataModel.commitChanges()

    def onEditToggled(self, isEditable: bool):

        self.metadataModel.setEditable(isEditable)
        # self.btnAddItem.setVisible(isEditable)
        # self.btnRemoveItem.setVisible(isEditable)
        # self.btnReset.setVisible(isEditable)

        self.actionReset.setEnabled(isEditable)
        self.actionAddItem.setEnabled(isEditable)
        self.actionRemoveItem.setEnabled(isEditable)

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

        has_changes = self.metadataModel.hasEdits or self.bandMetadataModel.hasEdits

        if has_changes:
            try:
                if self.is_gdal:
                    ds = gdalDataset(self.mapLayer(), gdal.GA_Update)
                    assert isinstance(ds, gdal.Dataset)
                    if self.supportsGDALClassification:
                        cs = self.classificationSchemeWidget.classificationScheme()
                        if isinstance(cs, ClassificationScheme):
                            # self.mapLayer().dataProvider().setEditable(True)
                            cs.saveToRaster(ds)
                            ds.FlushCache()
                    del ds

                self.mMapLayer.reload()
                self.bandMetadataModel.applyToLayer()
                self.metadataModel.applyToLayer()
            except (RuntimeError,) as ex:

                info = f'Cannot write to: {self.mapLayer().source()}'
                self.messageBar().pushMessage(info, Qgis.MessageLevel.Info)

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

        self.bandMetadataModel.resetEditsFlag()
        self.metadataModel.resetEditsFlag()

        debugLog(f'Total Sync time: {datetime.datetime.now() - t0}')

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
        w.setEditable(False)
        return w

    def title(self) -> str:
        if self.mIsGDAL:
            return 'GDAL Metadata'
        if self.mIsOGR:
            return 'OGR Metadata'
        return 'Metadata'
