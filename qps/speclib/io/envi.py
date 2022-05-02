# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/envi.py

    Input/Output of ENVI spectral library data
    ---------------------
    Beginning            : 2018-12-17
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
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

import csv
import os
import pathlib
import re
import tempfile
import time
import typing
import uuid
from typing import Tuple, Union

import numpy as np
from osgeo import gdal, gdal_array

from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QFormLayout
from qgis.core import QgsExpression, QgsFeatureRequest, QgsFeatureIterator
from qgis.core import QgsField, QgsFields, QgsFeature, QgsProcessingFeedback
from qgis.core import QgsVectorLayer, QgsExpressionContext, QgsExpressionContextScope
from qgis.gui import QgsFieldExpressionWidget, QgsFieldComboBox
from .. import EMPTY_VALUES, FIELD_FID, FIELD_VALUES, FIELD_NAME
from ..core import create_profile_field, profile_fields, profile_field_names
from ..core.spectrallibrary import VSI_DIR, LUT_IDL2GDAL
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryExportWidget, \
    SpectralLibraryImportWidget
from ..core.spectralprofile import encodeProfileValueDict, groupBySpectralProperties, SpectralSetting, \
    decodeProfileValueDict, prepareProfileValueDict
from ...qgsrasterlayerproperties import stringToType

# lookup GDAL Data Type and its size in bytes
LUT_GDT_SIZE = {gdal.GDT_Byte: 1,
                gdal.GDT_UInt16: 2,
                gdal.GDT_Int16: 2,
                gdal.GDT_UInt32: 4,
                gdal.GDT_Int32: 4,
                gdal.GDT_Float32: 4,
                gdal.GDT_Float64: 8,
                gdal.GDT_CInt16: 2,
                gdal.GDT_CInt32: 4,
                gdal.GDT_CFloat32: 4,
                gdal.GDT_CFloat64: 8}

LUT_GDT_NAME = {gdal.GDT_Byte: 'Byte',
                gdal.GDT_UInt16: 'UInt16',
                gdal.GDT_Int16: 'Int16',
                gdal.GDT_UInt32: 'UInt32',
                gdal.GDT_Int32: 'Int32',
                gdal.GDT_Float32: 'Float32',
                gdal.GDT_Float64: 'Float64',
                gdal.GDT_CInt16: 'Int16',
                gdal.GDT_CInt32: 'Int32',
                gdal.GDT_CFloat32: 'Float32',
                gdal.GDT_CFloat64: 'Float64'}

FILTER_SLI = 'ENVI Spectral Library (*.sli)'
CSV_PROFILE_NAME_COLUMN_NAMES = ['spectra names', 'name']
CSV_GEOMETRY_COLUMN = 'wkt'


def flushCacheWithoutException(dataset: gdal.Dataset):
    """
    Tries to flush the gdal.Dataset cache up to 5 times, waiting 1 second in between.
    :param dataset: gdal.Dataset
    """
    nTry = 5
    n = 0
    success = False

    while not success and n < nTry:
        try:
            dataset.FlushCache()
            success = True
        except RuntimeError:
            time.sleep(1)
        n += 1


def findENVIHeader(path: str) -> (str, str):
    """
    Get a path and returns the ENVI header (*.hdr) and the ENVI binary file (e.g. *.sli) for
    :param path: str
    :return: (str, str), e.g. ('pathESL.hdr', 'pathESL.sli')
    """
    # the two file names we want to extract
    pathHdr = None
    pathSLI = None

    # 1. find header file
    paths = [os.path.splitext(path)[0] + '.hdr', path + '.hdr']
    for p in paths:
        if os.path.exists(p):
            pathHdr = p
            break

    if pathHdr is None:
        # no header file, no ENVI file
        return None, None

    # 2. find binary file
    if not path.endswith('.hdr') and os.path.isfile(path):
        # this should be the default
        pathSLI = path
    else:
        # find a binary part ending
        paths = [os.path.splitext(pathHdr)[0] + '.sli',
                 pathHdr + '.sli',
                 os.path.splitext(pathHdr)[0] + '.esl',
                 pathHdr + '.esl',
                 ]
        for p in paths:
            if os.path.isfile(p):
                pathSLI = p
                break

    if pathSLI is None:
        return None, None

    return pathHdr, pathSLI


def value2hdrString(values):
    """
    Converts single values or a list of values into an ENVI header string
    :param values: valure or list-of-values, e.g. int(23) or [23,42]
    :return: str, e.g. 23 to "23" (single value), [23,24,25] to "{23,42}" (lists)
    """
    s = None
    maxwidth = 75

    if isinstance(values, (tuple, list)):
        lines = ['{']
        values = ['{}'.format(v).replace(',', '-') if v is not None else '' for v in values]
        line = ' '
        n_values = len(values)
        for i, v in enumerate(values):
            line += v

            if i < n_values - 1:
                line += ', '

            if len(line) > maxwidth:
                lines.append(line)
                line = ' '

        line += '}'
        lines.append(line)
        s = '\n'.join(lines)

    else:
        s = '{}'.format(values)

    return s


def readCSVMetadata(pathESL) -> QgsVectorLayer:
    pathCSV = os.path.splitext(pathESL)[0] + '.csv'
    if not os.path.isfile(pathCSV):
        return None

    lyr = QgsVectorLayer(pathCSV)
    # lyrCSV = QgsVectorLayer(pathCSV, 'csv', 'delimitedtext')

    if lyr.isValid():
        return lyr
    else:
        return None


def writeCSVMetadata(pathCSV: str, profiles: typing.List[QgsFeature], profile_names: typing.List[str]):
    """
    :param pathCSV:
    :param profiles:
    :param profile_names:
    :return:
    """
    assert isinstance(profiles, list)
    if len(profiles) == 0:
        return
    assert len(profiles) == len(profile_names)
    refProfile = profiles[0]
    excludedNames = CSV_PROFILE_NAME_COLUMN_NAMES + [CSV_GEOMETRY_COLUMN, FIELD_FID]
    for n in profile_field_names(refProfile):
        excludedNames.append(n)
    fieldNames = [n for n in refProfile.fields().names() if n not in excludedNames]
    allFieldNames = ['spectra names'] + fieldNames + [CSV_GEOMETRY_COLUMN]

    with open(pathCSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=allFieldNames)
        writer.writeheader()
        for p, spectrumName in zip(profiles, profile_names):
            assert isinstance(p, QgsFeature)
            d = {}

            if spectrumName in [None, NULL, QVariant()]:
                spectrumName = ''
            d['spectra names'] = str(spectrumName).replace(',', '-')
            d[CSV_GEOMETRY_COLUMN] = p.geometry().asWkt()
            for name in fieldNames:
                v = p.attribute(name)
                if v not in EMPTY_VALUES:
                    d[name] = v
            writer.writerow(d)


class EnviSpectralLibraryExportWidget(SpectralLibraryExportWidget):
    PROFILE_FIELD = 'profile_field'
    PROFILE_NAMES = 'profile_names'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mProfileField = QgsFieldComboBox()
        self.mNameExpr = QgsFieldExpressionWidget()
        layout: QFormLayout = self.layout()
        layout.addRow('Profile Values', self.mProfileField)
        layout.addRow('Profile Name', self.mNameExpr)

    @classmethod
    def spectralLibraryIO(cls) -> 'EnviSpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(EnviSpectralLibraryIO)

    def setSpeclib(self, speclib: QgsVectorLayer):
        pfields: QgsFields = profile_fields(speclib)
        self.mProfileField.setFields(pfields)
        if pfields.count() > 0 and self.mProfileField.currentIndex() < 0:
            self.mProfileField.setCurrentIndex(0)

        self.mNameExpr.setFields(speclib.fields())

    def supportsMultipleSpectralSettings(self) -> bool:
        return False

    def formatName(self) -> str:
        return EnviSpectralLibraryIO.formatName()

    def filter(self) -> str:
        return "Envi Spectral Library (*.sli)"

    def exportSettings(self, settings: dict) -> dict:
        settings[self.PROFILE_FIELD] = self.mProfileField.currentField()
        settings[self.PROFILE_NAMES] = self.mNameExpr.expression()
        return settings


class EnviSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mSourceFields: QgsFields = QgsFields()
        self.mSourceMetadata: dict = dict()

    @classmethod
    def spectralLibraryIO(cls) -> 'EnviSpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(EnviSpectralLibraryIO)

    def sourceFields(self) -> QgsFields:
        return self.mSourceFields

    def setSource(self, source: str):
        self.mSource = source
        self.mSourceFields, self.mSourceMetadata = EnviSpectralLibraryIO.sourceFieldsMetadata(self.mSource)
        self.sigSourceChanged.emit()

    def createExpressionContext(self) -> QgsExpressionContext:
        print('Create Expression Context')
        context = QgsExpressionContext()

        # context.setFields(self.sourceFields())
        # scope = QgsExpressionContextScope()
        # for k, v in self.mENVIHdr.items():
        #    scope.setVariable(k, str(v))
        # context.appendScope(scope)
        # self._c = context
        return context

    def formatName(self) -> str:
        return 'Envi Spectral Library'

    def filter(self) -> str:
        return "Envi Spectral Library (*.sli *.esl)"

    def setSpeclib(self, speclib: QgsVectorLayer):
        super().setSpeclib(speclib)

    def importSettings(self, settings: dict) -> dict:
        """
        Returns the settings required to import the library
        :param settings:
        :return:
        """
        return settings


class EnviSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super(EnviSpectralLibraryIO, self).__init__(*args, **kwds)

    @staticmethod
    def sourceFieldsMetadata(source) -> Tuple[QgsFields, dict]:
        """
        Returns the set of fields as QgsFields which can be read from the ENVI spectral library
        """

        fields = QgsFields()

        if source in ['', None] or not os.path.isfile(source):
            return fields, dict()

        md = readENVIHeader(source, typeConversion=True)
        if not isinstance(md, dict):
            # unable to read header content
            return fields, dict()

        n_profiles = md.get('lines')

        fields.append(create_profile_field(FIELD_VALUES))
        fields.append(QgsField(FIELD_NAME, QVariant.String))
        # add ENVI Header fields
        to_exclude = SINGLE_VALUE_TAGS
        for k, v in md.items():
            if isinstance(v, list) and k not in to_exclude and len(v) == n_profiles:
                field = None
                if isinstance(v[0], float):
                    fields.append(QgsField(k, QVariant.Double))
                elif isinstance(v[0], int):
                    fields.append(QgsField(k, QVariant.Int))
                else:
                    fields.append(QgsField(k, QVariant.String))

        # add CSV fields
        lyrCSV = readCSVMetadata(source)
        if isinstance(lyrCSV, QgsVectorLayer):
            n = lyrCSV.fields().count()
            for i in range(n):
                fieldCSV: QgsField = lyrCSV.fields().at(i)
                if fieldCSV.name() not in fields.names():
                    fields.append(fieldCSV)
        del lyrCSV
        return fields, md

    @classmethod
    def formatName(cls) -> str:
        return 'ENVI Spectral Library'

    @classmethod
    def createExportWidget(cls) -> SpectralLibraryExportWidget:
        return EnviSpectralLibraryExportWidget()

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return EnviSpectralLibraryImportWidget()

    @classmethod
    def importProfiles(cls,
                       path: Union[str, pathlib.Path],
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[QgsFeature]:

        path = pathlib.Path(path).as_posix()
        assert isinstance(path, str)

        pathHdr, pathESL = findENVIHeader(path)
        fields, md = EnviSpectralLibraryIO.sourceFieldsMetadata(pathHdr)

        tmpVrt = tempfile.mktemp(prefix='tmpESLVrt', suffix='.esl.vrt', dir=os.path.join(VSI_DIR, 'ENVIIO'))
        ds = esl2vrt(pathESL, tmpVrt)
        profileArray = ds.ReadAsArray()

        # remove the temporary VRT, as it was created internally only
        ds.GetDriver().Delete(ds.GetDescription())

        nSpectra, nbands = profileArray.shape
        yUnit = None
        xUnit = md.get('wavelength units')
        xValues = md.get('wavelength')
        zPlotTitles = md.get('z plot titles')
        if isinstance(zPlotTitles, str) and len(zPlotTitles.split(',')) >= 2:
            xUnit, yUnit = zPlotTitles.split(',')[0:2]

        # get official ENVI Spectral Library standard values
        # a) defined in header item "spectra names"
        # b) implicitly by profile order as "Spectrum 1, Spectrum 2, ..."
        spectraNames = md.get('spectra names', [f'Spectrum {i + 1}' for i in range(nSpectra)])

        lyrCSV = readCSVMetadata(path)

        # thanks to Ann for https://bitbucket.org/jakimowb/qgispluginsupport/issues/3/speclib-envypy

        bbl = md.get('bbl', None)
        if bbl:
            bbl = np.asarray(bbl, dtype=np.byte).tolist()

        profiles: typing.List[QgsFeature] = []

        featureIterator = None
        copyFields = []
        if isinstance(lyrCSV, QgsVectorLayer):
            request = QgsFeatureRequest()
            featureIterator = lyrCSV.getFeatures(request)
            copyFields = [n for n in lyrCSV.fields().names() if n in fields.names()]

        for i in range(nSpectra):
            f = QgsFeature(fields)

            d = prepareProfileValueDict(y=profileArray[i, :],
                                        x=xValues,
                                        xUnit=xUnit,
                                        yUnit=yUnit,
                                        bbl=bbl)
            dump = encodeProfileValueDict(d, f.attribute(FIELD_VALUES))
            f.setAttribute(FIELD_VALUES, dump)
            if FIELD_NAME in fields.names():
                f.setAttribute(FIELD_NAME, spectraNames[i])

            if isinstance(featureIterator, QgsFeatureIterator):
                csvFeature = featureIterator.__next__()
                if csvFeature.hasGeometry():
                    f.setGeometry(csvFeature.geometry())
                for n in copyFields:
                    f.setAttribute(n, csvFeature.attribute(n))

            profiles.append(f)

        return profiles

    @classmethod
    def exportProfiles(cls,
                       path: str,
                       profiles: typing.Union[typing.List[QgsFeature], QgsVectorLayer],
                       exportSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[str]:

        profiles, fields, crs, wkbType = cls.extractWriterInfos(profiles, exportSettings)
        if len(profiles) == 0:
            return []

        if EnviSpectralLibraryExportWidget.PROFILE_FIELD not in exportSettings.keys():

            pfields = profile_field_names(fields)
            assert len(pfields) > 0, 'missing profile fields'
            profile_field = pfields[0]
        else:
            profile_field = exportSettings[EnviSpectralLibraryExportWidget.PROFILE_FIELD]

        assert profile_field in fields.names()

        expr = QgsExpression(exportSettings.get(
            EnviSpectralLibraryExportWidget.PROFILE_NAMES,
            "format('Profile %1', $id)"))

        path = pathlib.Path(path)
        dn = path.parent
        bn, ext = os.path.splitext(path.name)

        if not re.search(r'\.(sli|esl)', ext, re.I):
            ext = '.sli'

        writtenFiles = []

        os.makedirs(dn, exist_ok=True)

        drv: gdal.Driver = gdal.GetDriverByName('ENVI')
        assert isinstance(drv, gdal.Driver)

        iGrp = -1

        for setting, profiles in groupBySpectralProperties(profiles, profile_field=profile_field).items():
            if len(profiles) == 0:
                continue

            iGrp += 1
            setting: SpectralSetting

            xValues, wlu, yUnit, bbl = setting.x(), setting.xUnit(), setting.yUnit(), setting.bbl()

            # get profile names
            profileNames = []
            expressionContext = QgsExpressionContext()
            context = QgsExpressionContext()
            scope = QgsExpressionContextScope()
            context.appendScope(scope)

            pData = []
            for p in profiles:
                context.setFeature(p)
                name = expr.evaluate(context)
                profileNames.append(name)

                d = decodeProfileValueDict(p.attribute(setting.fieldName()), )
                pData.append(np.asarray(d['y']))

            # stack profiles
            pData = np.vstack(pData)

            # convert array to data type GDAL is able to write
            if pData.dtype == np.int64:
                pData = pData.astype(np.int32)
            elif pData.dtype == object:
                pData = pData.astype(float)
            # todo: other cases?

            if iGrp == 0:
                pathDst = dn / f'{bn}{ext}'
            else:
                pathDst = dn / f'{bn}.{iGrp}{ext}'

            eType = gdal_array.NumericTypeCodeToGDALTypeCode(pData.dtype)

            """
            Create(utf8_path, int xsize, int ysize, int bands=1, GDALDataType eType, char ** options=None) -> Dataset
            """

            ds = drv.Create(pathDst.as_posix(), pData.shape[1], pData.shape[0], 1, eType)
            band = ds.GetRasterBand(1)
            assert isinstance(band, gdal.Band)
            band.WriteArray(pData)

            assert isinstance(ds, gdal.Dataset)

            # write ENVI header metadata
            # ds.SetDescription(speclib.name())
            ds.SetMetadataItem('band names', 'Spectral Library', 'ENVI')
            ds.SetMetadataItem('spectra names', value2hdrString(profileNames), 'ENVI')

            hdrString = value2hdrString(xValues)
            if hdrString not in ['', None]:
                ds.SetMetadataItem('wavelength', hdrString, 'ENVI')

            if wlu not in ['', '-', None]:
                ds.SetMetadataItem('wavelength units', wlu, 'ENVI')

            if bbl not in ['', '-', None]:
                ds.SetMetadataItem('bbl', value2hdrString(bbl), 'ENVI')

            flushCacheWithoutException(ds)

            pathHDR = [p for p in ds.GetFileList() if p.endswith('.hdr')][0]
            ds = None

            # re-write ENVI Hdr with file type = ENVI Spectral Library
            file = open(pathHDR)
            hdr = file.readlines()
            file.close()
            for iLine in range(len(hdr)):
                if re.search(r'file type =', hdr[iLine]):
                    hdr[iLine] = 'file type = ENVI Spectral Library\n'
                    break

            file = open(pathHDR, 'w', encoding='utf-8')
            file.writelines(hdr)
            file.flush()
            file.close()

            # write JSON properties
            # speclib.writeJSONProperties(pathDst)

            # write other metadata to CSV
            pathCSV = os.path.splitext(pathHDR)[0] + '.csv'

            writeCSVMetadata(pathCSV, profiles, profileNames)
            writtenFiles.append(pathDst.as_posix())

        return writtenFiles


REQUIRED_TAGS = ['byte order', 'data type', 'header offset', 'lines', 'samples', 'bands']
SINGLE_VALUE_TAGS = REQUIRED_TAGS + ['description', 'wavelength', 'wavelength units']


def canRead(pathESL) -> bool:
    """
    Checks if a file can be read as SpectraLibrary
    :param pathESL: path to ENVI Spectral Library (ESL)
    :return: True, if pathESL can be read as Spectral Library.
    """
    pathESL = str(pathESL)
    if not os.path.isfile(pathESL):
        return False
    hdr = readENVIHeader(pathESL, typeConversion=False)
    if hdr is None or hdr['file type'] != 'ENVI Spectral Library':
        return False
    return True


def esl2vrt(pathESL, pathVrt=None):
    """
    Creates a GDAL Virtual Raster (VRT) that allows to read an ENVI Spectral Library file
    :param pathESL: path ENVI Spectral Library file (binary part)
    :param pathVrt: (optional) path of created GDAL VRT.
    :return: GDAL VRT
    """

    hdr = readENVIHeader(pathESL, typeConversion=False)
    assert hdr is not None and hdr['file type'] == 'ENVI Spectral Library'

    if hdr.get('file compression') == '1':
        raise Exception('Can not read compressed spectral libraries')

    eType = LUT_IDL2GDAL[int(hdr['data type'])]
    xSize = int(hdr['samples'])
    ySize = int(hdr['lines'])
    bands = int(hdr['bands'])
    byteOrder = 'LSB' if int(hdr['byte order']) == 0 else 'MSB'

    if pathVrt is None:
        id = uuid.UUID()
        pathVrt = '/vsimem/{}.esl.vrt'.format(id)

    ds = describeRawFile(pathESL, pathVrt, xSize, ySize, bands=bands, eType=eType, byteOrder=byteOrder)
    for key, value in hdr.items():
        if isinstance(value, list):
            value = u','.join(v for v in value)
        ds.SetMetadataItem(key, value, 'ENVI')
    flushCacheWithoutException(ds)
    return ds


def readENVIHeader(pathESL, typeConversion=False) -> dict:
    """
    Reads an ENVI Header File (*.hdr) and returns its values in a dictionary
    :param pathESL: path to ENVI Header
    :param typeConversion: Set on True to convert values related to header keys with numeric
    values into numeric data types (int / float)
    :return: dict
    """
    assert isinstance(pathESL, str)
    if not os.path.isfile(pathESL):
        return None

    pathHdr, pathBin = findENVIHeader(pathESL)
    if pathHdr is None:
        return None

    # hdr = open(pathHdr).readlines()
    file = open(pathHdr, encoding='utf-8')
    hdr = file.readlines()
    file.close()

    i = 0
    while i < len(hdr):
        if '{' in hdr[i]:
            while '}' not in hdr[i]:
                hdr[i] = hdr[i] + hdr.pop(i + 1)
        i += 1

    hdr = [''.join(re.split('\n[ ]*', line)).strip() for line in hdr]
    # keep lines with <tag>=<value> structure only
    hdr = [line for line in hdr if re.search(r'^[^=]+=', line)]

    # restructure into dictionary of type
    # md[key] = single value or
    # md[key] = [list-of-values]
    md = dict()
    for line in hdr:
        tmp = line.split('=')
        key, value = tmp[0].strip(), '='.join(tmp[1:]).strip()
        if value.startswith('{') and value.endswith('}'):
            value = [v.strip() for v in value.strip('{}').split(',')]
            if len(value) > 0 and len(value[0]) > 0:
                md[key] = value
        else:
            if len(value) > 0:
                md[key] = value

    # check required metadata tags
    for k in REQUIRED_TAGS:
        if k not in md.keys():
            return None

    if typeConversion:
        for k in list(md.keys()):
            value = md[k]
            if isinstance(value, list):
                value = [stringToType(v) for v in value]
            else:
                value = stringToType(value)
            md[k] = value

    return md


def describeRawFile(pathRaw, pathVrt, xsize, ysize,
                    bands=1,
                    eType=gdal.GDT_Byte,
                    interleave='bsq',
                    byteOrder='LSB',
                    headerOffset=0) -> gdal.Dataset:
    """
    Creates a VRT to describe a raw binary file
    :param pathRaw: path of raw image
    :param pathVrt: path of destination VRT
    :param xsize: number of image samples / columns
    :param ysize: number of image lines
    :param bands: number of image bands
    :param eType: the GDAL data type
    :param interleave: can be 'bsq' (default),'bil' or 'bip'
    :param byteOrder: 'LSB' (default) or 'MSB'
    :param headerOffset: header offset in bytes, default = 0
    :return: gdal.Dataset of created VRT
    """
    assert xsize > 0
    assert ysize > 0
    assert bands > 0
    assert eType > 0

    assert eType in LUT_GDT_SIZE.keys(), 'dataType "{}" is not a valid gdal datatype'.format(eType)
    interleave = interleave.lower()

    assert interleave in ['bsq', 'bil', 'bip']
    assert byteOrder in ['LSB', 'MSB']

    drvVRT = gdal.GetDriverByName('VRT')
    assert isinstance(drvVRT, gdal.Driver)
    dsVRT = drvVRT.Create(pathVrt, xsize, ysize, bands=0, eType=eType)
    assert isinstance(dsVRT, gdal.Dataset)

    # vrt = ['<VRTDataset rasterXSize="{xsize}" rasterYSize="{ysize}">'.format(xsize=xsize,ysize=ysize)]

    vrtDir = os.path.dirname(pathVrt)
    if pathRaw.startswith(vrtDir):
        relativeToVRT = 1
        srcFilename = os.path.relpath(pathRaw, vrtDir)
    else:
        relativeToVRT = 0
        srcFilename = pathRaw

    for b in range(bands):
        if interleave == 'bsq':
            imageOffset = headerOffset
            pixelOffset = LUT_GDT_SIZE[eType]
            lineOffset = pixelOffset * xsize
        elif interleave == 'bip':
            imageOffset = headerOffset + b * LUT_GDT_SIZE[eType]
            pixelOffset = bands * LUT_GDT_SIZE[eType]
            lineOffset = xsize * bands
        else:
            raise Exception('Interleave {} is not supported'.format(interleave))

        options = ['subClass=VRTRawRasterBand']
        options.append('SourceFilename={}'.format(srcFilename))
        options.append('dataType={}'.format(LUT_GDT_NAME[eType]))
        options.append('ImageOffset={}'.format(imageOffset))
        options.append('PixelOffset={}'.format(pixelOffset))
        options.append('LineOffset={}'.format(lineOffset))
        options.append('ByteOrder={}'.format(byteOrder))

        # md = {}
        # md['source_0'] = xml
        # vrtBand = dsVRT.GetRasterBand(b + 1)
        assert dsVRT.AddBand(eType, options=options) == 0

        vrtBand = dsVRT.GetRasterBand(b + 1)
        assert isinstance(vrtBand, gdal.Band)
        # vrtBand.SetMetadata(md, 'vrt_sources')
        # vrt.append('  <VRTRasterBand dataType="{dataType}" band="{band}"
        # subClass="VRTRawRasterBand">'.format(dataType=LUT_GDT_NAME[eType], band=b+1))
    flushCacheWithoutException(dsVRT)
    return dsVRT
