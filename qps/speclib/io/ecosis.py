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

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import csv
import re
from pathlib import Path
from typing import List, Union

from qgis.PyQt.QtCore import QUrlQuery
from qgis.core import QgsExpressionContext, QgsFeature, QgsField, QgsFields, QgsGeometry, QgsProcessingFeedback, \
    QgsProviderRegistry, QgsVectorLayer
from .envi import readCSVMetadata
from ..core import create_profile_field
from ..core.spectrallibraryio import SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import encodeProfileValueDict, prepareProfileValueDict, ProfileEncoding, \
    SpectralProfileFileReader


class EcoSISSpectralLibraryReader(SpectralProfileFileReader):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.path()

    def asFeatures(self) -> List[QgsFeature]:

        csvLyr = self.loadCSVLayer()

        rxIsNum = re.compile(r'^\d+(\.\d+)?$')
        wlFields = QgsFields()
        mdFields = QgsFields()

        dstFields = QgsFields()
        profileField = create_profile_field(self.KEY_Reflectance, encoding=ProfileEncoding.Json)
        dstFields.append(profileField)

        wl = []

        for i, field in enumerate(csvLyr.fields()):
            field: QgsField
            if field.isNumeric() and rxIsNum.match(field.name()):
                wl.append(float(field.name()))
                wlFields.append(field)
            else:
                mdFields.append(field)
                dstFields.append(field)

        profiles: List[QgsFeature] = []

        for i, f in enumerate(csvLyr.getFeatures()):
            f: QgsFeature
            f2 = QgsFeature(dstFields)

            y = [f.attribute(field.name()) for field in wlFields]
            xUnit = None
            d = prepareProfileValueDict(x=wl, y=y, xUnit=xUnit)
            dump = encodeProfileValueDict(d, profileField)
            f2.setAttribute(profileField.name(), dump)

            if f.hasGeometry():
                g = f.geometry()
                f2.setGeometry(QgsGeometry(g))

            # for field in mdFields:
            #    f2.setAttribute(field.name(), f.attribute(field.name()))
            profiles.append(f2)
        del csvLyr
        return profiles
        s = ""

    def loadCSVLayer(self, **kwargs) -> QgsVectorLayer:
        cLat = cLon = None
        with open(self.path(), newline='') as csvfile:
            reader = csv.reader(csvfile)
            hdr_row = next(reader)

            for c in hdr_row:
                if re.match(r'^(lat|latitude)$', c, re.I):
                    cLat = c
                if re.match(r'^(lon|longitude)$', c, re.I):
                    cLon = c
        # see https://api.qgis.org/api/classQgsVectorLayer.html#details or
        # https://qgis.org/pyqgis/master/core/QgsVectorLayer.html#delimited-text-file-data-provider-delimitedtext
        # for details of the delimitedtext driver
        query = QUrlQuery()
        # query.addQueryItem('encoding', 'UTF-8')
        query.addQueryItem('detectTypes', 'yes')
        # query.addQueryItem('watchFile', 'no')
        # query.addQueryItem('type', 'csv')
        # query.addQueryItem('subsetIndex', 'no')
        # query.addQueryItem('useHeader', 'yes')
        query.addQueryItem('delimiter', kwargs.get('delimiter', ','))
        query.addQueryItem('quote', kwargs.get('quote', '"'))
        if 'xField' in kwargs and 'yField' in kwargs:
            query.addQueryItem('xField', kwargs['xField'])
            query.addQueryItem('yField', kwargs['yField'])
        elif cLat and cLon:
            query.addQueryItem('xField', cLon)
            query.addQueryItem('yField', cLat)
        query.addQueryItem('crs', kwargs.get('crs', 'EPSG:4326'))
        query.addQueryItem('geomType', kwargs.get('geomType', 'point'))
        uri = self.path().as_uri() + '?' + query.toString()
        # uri = path.as_posix()
        lyr = QgsVectorLayer(uri, self.path().name, 'delimitedtext')
        assert lyr.isValid()
        return lyr


class EcoSISSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mENVIHdr: dict = dict()

    @classmethod
    def spectralLibraryIO(cls) -> 'EcoSISSpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(EcoSISSpectralLibraryIO)

    def sourceFields(self) -> QgsFields:

        fields = QgsFields()
        if self.source() in ['', None]:
            return fields

        fields.append(create_profile_field(EcoSISSpectralLibraryIO.FIELDNAME_PROFILE))
        EcoSISSpectralLibraryIO.loadCSVLayer({}, self.source())
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
        return 'EcoSIS'

    def filter(self) -> str:
        return "EcoSIS text file (*.csv)"

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
    FIELDNAME_PROFILE = 'profile'

    def __init__(self, *args, **kwds):
        super(EcoSISSpectralLibraryIO, self).__init__(*args, **kwds)

        assert 'delimitedtext' in QgsProviderRegistry.instance().providerList(), \
            'QGIS runs without "delimitedtext" data provider '

    @classmethod
    def formatName(cls) -> str:
        return 'EcoSIS dataset'

    @classmethod
    def filter(self) -> str:
        return "EcoSIS dataset file (*.csv)"

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return EcoSISSpectralLibraryImportWidget()

    @classmethod
    def importProfiles(cls,
                       path: Union[str, Path],
                       importSettings=None,
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:
        if importSettings is None:
            importSettings = dict()
        path = Path(path)

        lyr = cls.loadCSVLayer(importSettings, path)

        profiles: List[QgsFeature] = []

        dstFields, otherFields, profileField, wl, wlFields = cls.dataFields(lyr)

        n = lyr.featureCount()
        next_step = 5  # step size in percent
        feedback.setProgressText(f'Load {n} profiles')
        for i, f in enumerate(lyr.getFeatures()):
            f: QgsFeature
            f2 = QgsFeature(dstFields)

            y = [f.attribute(field.name()) for field in wlFields]
            xUnit = None
            d = prepareProfileValueDict(x=wl, y=y, xUnit=xUnit)
            dump = encodeProfileValueDict(d, profileField)
            f2.setAttribute(cls.FIELDNAME_PROFILE, dump)

            if f.hasGeometry():
                g = f.geometry()
                f2.setGeometry(QgsGeometry(g))

            for field in otherFields:
                f2.setAttribute(field.name(), f.attribute(field.name()))
            profiles.append(f2)

            progress = 100 * i / n
            if progress >= next_step:
                next_step += 5
                feedback.setProgress(progress)
        return profiles

    @classmethod
    def dataFields(cls, lyr):
        rxIsNum = re.compile(r'^\d+(\.\d+)?$')
        wlFields = QgsFields()
        otherFields = QgsFields()
        dstFields = QgsFields()
        profileField = create_profile_field(cls.FIELDNAME_PROFILE, encoding=ProfileEncoding.Json)
        dstFields.append(profileField)

        wl = []
        for i, field in enumerate(lyr.fields()):
            field: QgsField
            if field.isNumeric() and rxIsNum.match(field.name()):
                wl.append(float(field.name()))
                wlFields.append(field)
            else:
                otherFields.append(field)
                dstFields.append(field)
        return dstFields, otherFields, profileField, wl, wlFields

    @classmethod
    def loadCSVLayer(cls, importSettings, path):
        cLat = cLon = None
        with open(path, newline='') as csvfile:
            reader = csv.reader(csvfile)
            hdr_row = next(reader)

            for c in hdr_row:
                if re.match(r'^(lat|latitude)$', c, re.I):
                    cLat = c
                if re.match(r'^(lon|longitude)$', c, re.I):
                    cLon = c
        # see https://api.qgis.org/api/classQgsVectorLayer.html#details or
        # https://qgis.org/pyqgis/master/core/QgsVectorLayer.html#delimited-text-file-data-provider-delimitedtext
        # for detaisl of delimitedtext driver
        query = QUrlQuery()
        # query.addQueryItem('encoding', 'UTF-8')
        query.addQueryItem('detectTypes', 'yes')
        # query.addQueryItem('watchFile', 'no')
        # query.addQueryItem('type', 'csv')
        # query.addQueryItem('subsetIndex', 'no')
        # query.addQueryItem('useHeader', 'yes')
        query.addQueryItem('delimiter', importSettings.get('delimiter', ','))
        query.addQueryItem('quote', importSettings.get('quote', '"'))
        if 'xField' in importSettings and 'yField' in importSettings:
            query.addQueryItem('xField', importSettings['xField'])
            query.addQueryItem('yField', importSettings['yField'])
        elif cLat and cLon:
            query.addQueryItem('xField', cLon)
            query.addQueryItem('yField', cLat)
        query.addQueryItem('crs', importSettings.get('crs', 'EPSG:4326'))
        query.addQueryItem('geomType', importSettings.get('geomType', 'point'))
        uri = path.as_uri() + '?' + query.toString()
        # uri = path.as_posix()
        lyr = QgsVectorLayer(uri, path.name, 'delimitedtext')
        assert lyr.isValid()
        return lyr
