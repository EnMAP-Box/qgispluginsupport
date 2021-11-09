# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/ecosis.py

    Input/Output of EcoSYS spectral library data
    ---------------------
    Beginning            : 2019-08-23
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import csv as pycsv
import io
import os
import pathlib
import re
import sys
import typing

from PyQt5.QtCore import QUrlQuery
from qgis._core import QgsFeature, QgsFields, QgsField, QgsExpressionContext, QgsVectorLayer

from qgis.PyQt.QtCore import QObject, QVariant
from qgis.PyQt.QtWidgets import QMenu, QFileDialog, QProgressDialog
from qgis.core import QgsProcessingFeedback
from .. import createStandardFields
from ..core.spectrallibrary import SpectralProfile, SpectralLibrary, FIELD_FID, FIELD_VALUES, createQgsField
from ..core.spectrallibraryio import SpectralLibraryIO
from ...utils import findTypeFromString
from ..core import profile_field_list, create_profile_field, profile_fields
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryExportWidget, \
    SpectralLibraryImportWidget
from ..core.spectralprofile import encodeProfileValueDict, SpectralProfile, groupBySpectralProperties
from ..core.spectrallibrary import SpectralLibrary, VSI_DIR, LUT_IDL2GDAL

class EcoSISCSVDialect(pycsv.Dialect):
    delimiter = ','
    quotechar = '"'
    doublequote = True
    skipinitialspace = False
    lineterminator = '\n'
    escapechar = '\\'
    quoting = pycsv.QUOTE_NONE


def findDialect(file) -> pycsv.Dialect:
    if isinstance(file, str):
        file = open(file, 'r', encoding='utf-8')

    line = ''
    while len(line) == 0:
        line = file.readline()

    delimiters = [',', ';', '\t']
    counts = [len(line.split(delimiter)) for delimiter in delimiters]

    dialect = EcoSISCSVDialect()
    dialect.delimiter = delimiters[counts.index(max(counts))]
    dialect.lineterminator = '\n\r' if line.endswith('\n\r') else line[-1]

    file.seek(0)
    s = ""
    return dialect


class EcoSISSpectralLibraryImportWidget(SpectralLibraryImportWidget):
    FIELDNAME_PROFILE = 'profile'
    FIELDNAME_NAME = 'name'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mENVIHdr: dict = dict()

    @classmethod
    def spectralLibraryIO(cls) -> 'EnviSpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(EcoSISSpectralLibraryIO)

    def sourceFields(self) -> QgsFields:

        fields = QgsFields()
        if self.source() in ['', None]:
            return fields

        fields.append(create_profile_field(self.FIELDNAME_PROFILE))
        fields.append(QgsField(self.FIELDNAME_NAME, QVariant.String))

        lyrCSV = readCSVMetadata(self.source())
        if isinstance(lyrCSV, QgsVectorLayer):
            n = lyrCSV.fields().count()
            for i in range(n):
                fieldCSV: QgsField = lyrCSV.fields().at(i)
                if fieldCSV.name() not in fields.names():
                    fields.append(fieldCSV)
        return fields

    def setSource(self, source: str):
        self.mSource = source
        self.mENVIHdr.clear()



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



class EcoSISSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super(EcoSISSpectralLibraryIO, self).__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'EcoSYS Spectral Library'


    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return EcoSISSpectralLibraryImportWidget()

    @classmethod
    def importProfiles(cls,
                       path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:

        path = pathlib.Path(path)

        profiles: typing.List[QgsFeature] = []

        query = QUrlQuery()
        # query.addQueryItem('encoding', 'UTF-8')
        query.addQueryItem('detectTypes', 'yes')
        query.addQueryItem('geomType', 'none')
        # query.addQueryItem('watchFile', 'no')
        # query.addQueryItem('type', 'csv')
        # query.addQueryItem('subsetIndex', 'no')
        # query.addQueryItem('useHeader', 'yes')
        query.addQueryItem('delimiter', ',')

        uri = path.as_uri() + '?' + query.toString()
        # uri = path.as_posix()
        lyr = QgsVectorLayer(uri, os.path.basename(path), 'delimitedtext')

        # the EcoSIS CSV outputs are encoded as UTF-8 with BOM
        with open(path, 'r', encoding='utf-8-sig') as f:

            bn = os.path.basename(path)

            dialect = findDialect(f)

            reader = pycsv.DictReader(f, dialect=dialect)
            fieldnames = reader.fieldnames

            if fieldnames[0].startswith('\ufeff'):
                s = ""
            fieldnames = [n for n in fieldnames if len(n) > 0]

            xUnit = yUnit = None
            xValueNames = []
            for fieldName in reversed(fieldnames):
                if re.search(r'^\d+(\.\d+)?$', fieldName):
                    xValueNames.insert(0, fieldName)
                else:
                    break
            s = ""
            xValues = [float(n) for n in xValueNames]
            if len(xValues) == 0:
                s = ""
            if xValues[0] > 200:
                xUnit = 'nm'

            fieldnames = [n for n in fieldnames if n not in xValueNames]

            # speclib = SpectralLibrary()
            # speclib.startEditing()
            # speclib.addMissingFields(createStandardFields())

            profiles = []
            LUT_FIELD_TYPES = dict()

            fields = QgsFields()
            fields.append(create_profile_field('profiles'))

            missing_field_definitions = fieldnames[:]

            for i, row in enumerate(reader):

                if len(fieldnames) > 0:
                    for fieldName in missing_field_definitions[:]:
                        fieldValue = row[fieldName]
                        if fieldValue == 'NA':
                            continue

                        fieldType = findTypeFromString(fieldValue)
                        LUT_FIELD_TYPES[fieldName] = fieldType

                        fields.append(createQgsField(fieldName, fieldType(fieldValue)))
                        missing_field_definitions.remove(fieldName)

                feature = QgsFeature(fields=fields)

                valueDict = {'y': [float(row[n]) for n in xValueNames],
                             'x': xValues}

                feature.setAttribute('profiles', encodeProfileValueDict(valueDict))

                for fieldName, fieldType in LUT_FIELD_TYPES.items():
                    fieldValue = fieldType(row[fieldName])
                    feature.setAttribute(fieldName, fieldValue)

                profiles.append(feature)
        return profiles

class _DEPR_EcoSISSpectralLibraryIO(SpectralLibraryIO):
    """
    I/O Interface for the EcoSIS spectral library format.
    See https://ecosis.org for details.
    """

    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        if not isinstance(path, str) and os.path.isfile(path):
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if len(line) > 0:
                        # most-right header name must be a number
                        lastColumn = [c for c in re.split(r'[\t\n;,]', line) if c != ''][-1]
                        return re.search(r'^\d+(\.\d+)?$', lastColumn) is not None
        except Exception as ex:
            print(ex, file=sys.stderr)

        return False

    @classmethod
    def readFrom(cls,
                 path,
                 feedback: QgsProcessingFeedback = None) -> SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of SpectralLibrary
        :return: SpectralLibrary
        """

        # the EcoSIS CSV outputs are encoded as UTF-8 with BOM
        with open(path, 'r', encoding='utf-8-sig') as f:

            bn = os.path.basename(path)

            dialect = findDialect(f)

            reader = pycsv.DictReader(f, dialect=dialect)
            fieldnames = reader.fieldnames

            if fieldnames[0].startswith('\ufeff'):
                s = ""
            fieldnames = [n for n in fieldnames if len(n) > 0]

            xUnit = yUnit = None
            xValueNames = []
            for fieldName in reversed(fieldnames):
                if re.search(r'^\d+(\.\d+)?$', fieldName):
                    xValueNames.insert(0, fieldName)
                else:
                    break
            s = ""
            xValues = [float(n) for n in xValueNames]
            if len(xValues) == 0:
                s = ""
            if xValues[0] > 200:
                xUnit = 'nm'

            fieldnames = [n for n in fieldnames if n not in xValueNames]

            speclib = SpectralLibrary()
            speclib.startEditing()
            speclib.addMissingFields(createStandardFields())

            profiles = []
            LUT_FIELD_TYPES = dict()
            missing_field_definitions = [n for n in fieldnames if n not in speclib.fields().names()]
            for i, row in enumerate(reader):
                if len(missing_field_definitions) > 0:
                    for fieldName in missing_field_definitions[:]:
                        fieldValue = row[fieldName]
                        if fieldValue == 'NA':
                            continue

                        fieldType = findTypeFromString(fieldValue)
                        LUT_FIELD_TYPES[fieldName] = fieldType

                        qgsField = createQgsField(fieldName, fieldType(fieldValue))
                        speclib.addAttribute(qgsField)
                        assert speclib.commitChanges()
                        speclib.startEditing()
                        missing_field_definitions.remove(fieldName)

                profile = SpectralProfile(fields=speclib.fields())
                yValues = [float(row[n]) for n in xValueNames]
                profile.setValues(x=xValues, y=yValues, xUnit=xUnit, yUnit=yUnit)

                for fieldName, fieldType in LUT_FIELD_TYPES.items():
                    fieldValue = fieldType(row[fieldName])
                    profile.setAttribute(fieldName, fieldValue)

                if FIELD_NAME not in fieldnames:
                    profile.setAttribute(FIELD_NAME, '{}:{}'.format(bn, i + 1))
                else:
                    profile.setAttribute(FIELD_NAME, row[FIELD_NAME])
                profiles.append(profile)

            speclib.addProfiles(profiles)

            s = ""
        s = ""
        assert speclib.commitChanges()
        return speclib

    @classmethod
    def write(cls, speclib: SpectralLibrary, path: str, feedback: QProgressDialog = None, delimiter: str = ';'):
        """
        Writes the SpectralLibrary to path and returns a list of written files that can be used to open the spectral library with readFrom
        """
        assert is_spectral_library(speclib)
        basePath, ext = os.path.splitext(path)
        s = ""

        writtenFiles = []
        fieldNames = [n for n in speclib.fields().names() if n not in [FIELD_VALUES, FIELD_FID]]
        groups = speclib.groupBySpectralProperties()
        for i, setting in enumerate(groups.keys()):
            # in-memory text buffer
            stream = io.StringIO()
            xValues, xUnit, yUnit = setting.x(), setting.xUnit(), setting.yUnit()
            profiles = groups[setting]
            if i == 0:
                path = basePath + ext
            else:
                path = basePath + '{}{}'.format(i + 1, ext)

            headerNames = fieldNames + [str(v) for v in xValues]
            W = pycsv.DictWriter(stream, fieldnames=headerNames, dialect=EcoSISCSVDialect())
            W.writeheader()

            for profile in profiles:
                assert isinstance(profile, SpectralProfile)

                rowDict = dict()
                for n in fieldNames:
                    v = profile.attribute(n)
                    if v in [None, QVariant(None), '']:
                        v = 'NA'
                    rowDict[n] = v

                yValues = profile.yValues()
                for i, xValue in enumerate(xValues):
                    rowDict[str(xValue)] = yValues[i]
                W.writerow(rowDict)

            stream.write('\n')
            lines = stream.getvalue().replace('\r', '')

            with open(path, 'w', encoding='utf-8') as f:
                f.write(lines)
                writtenFiles.append(path)

        return writtenFiles

    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def read(speclib: SpectralLibrary):

            path, filter = QFileDialog.getOpenFileName(caption='EcoSIS CSV File',
                                                       filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if os.path.isfile(path):

                sl = EcoSISSpectralLibraryIO.readFrom(path)
                if is_spectral_library(sl):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add EcoSIS profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('EcoSIS')
        m.setToolTip('Adds profiles from an EcoSIS csv text file.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))

    @classmethod
    def addExportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu) -> list:

        def write(speclib: SpectralLibrary):
            path, filter = QFileDialog.getSaveFileName(caption='Write to EcoSIS CSV File',
                                                       filter='EcoSIS CSV (*.csv);;Text files (*.txt)')
            if isinstance(path, str) and len(path) > 0:
                sl = EcoSISSpectralLibraryIO.write(spectralLibrary, path)

        m = menu.addAction('EcoSIS CSV')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))
