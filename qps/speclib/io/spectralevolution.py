# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/spectralrevolution.py

    Input of Spectral Evolution spectral library data
    ---------------------
    Beginning            : 2022-06-03
    Copyright            : (C) 2022 by Benjamin Jakimow
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
import os
import pathlib
import re
import typing

from qgis.PyQt.QtCore import QVariant, QDate, QTime
from qgis.core import QgsVectorLayer, QgsFields, QgsExpressionContext, QgsFeature, \
    QgsField, QgsProcessingFeedback, QgsPointXY, QgsGeometry
from qgis.gui import QgsFileWidget
from .. import FIELD_NAME
from ..core import create_profile_field
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportWidget
from ..core.spectralprofile import prepareProfileValueDict, encodeProfileValueDict, ProfileEncoding


class SEDAttributes(object):
    Version = 'Version'
    Reference = 'Reference'
    Target = 'Target'
    Reflectance = 'Reflectance'
    Comment = 'Comment'
    FileName = 'FileName'
    Instrument = 'Instrument'
    Detectors = 'Detectors'
    Measurement = 'Measurement'
    Date_T = 'DateTarget'
    Date_R = 'DateReference'
    Time_T = 'TimeTarget'
    Time_R = 'TimeReference'
    Temperature_T = 'Temperature_T'
    Temperature_R = 'Temperature_R'
    BatteryVoltage_T = 'BatteryVoltage_T'
    BatteryVoltage_R = 'BatteryVoltage_R'
    Averages_R = 'Averages_R'
    Averages_T = 'Averages_T'
    Integration_T = 'Integration_T'
    Integration_R = 'Integration_R'
    DarkMode_R = 'DarkMode_R'
    DarkMode_T = 'DarkMode_T'
    ForeOptic_R = 'ForeOptic_R'
    ForeOptic_T = 'ForeOptic_T'
    RadiometricCalibration = 'RadiometricCalibration'
    Units = 'Units'
    WavelengthRange = 'WavelengthRange'
    Latitude = 'Latitude'
    Longitude = 'Longitude'
    Altitude = 'Altitude'
    GPSTime = 'GPSTime'
    Satellites = 'Satellites'
    CalibratedReferenceCorrectionFile = 'CalRefCorFile'
    Channels = 'Channels'


SED_FIELDS = QgsFields()
SED_FIELDS.append(QgsField(FIELD_NAME, QVariant.String))
SED_FIELDS.append(create_profile_field(SEDAttributes.Reference, encoding=ProfileEncoding.Text))
SED_FIELDS.append(create_profile_field(SEDAttributes.Target, encoding=ProfileEncoding.Text))
SED_FIELDS.append(create_profile_field(SEDAttributes.Reflectance, encoding=ProfileEncoding.Text))
SED_FIELDS.append(QgsField(SEDAttributes.Comment, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Version, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.FileName, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Instrument, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Detectors, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Measurement, QVariant.String))

SED_FIELDS.append(QgsField(SEDAttributes.Date_R, QVariant.Date))
SED_FIELDS.append(QgsField(SEDAttributes.Date_T, QVariant.Date))
SED_FIELDS.append(QgsField(SEDAttributes.Time_R, QVariant.Time))
SED_FIELDS.append(QgsField(SEDAttributes.Time_T, QVariant.Time))

SED_FIELDS.append(QgsField(SEDAttributes.Temperature_R, QVariant.Double))
SED_FIELDS.append(QgsField(SEDAttributes.Temperature_T, QVariant.Double))

SED_FIELDS.append(QgsField(SEDAttributes.BatteryVoltage_T, QVariant.Double))
SED_FIELDS.append(QgsField(SEDAttributes.BatteryVoltage_R, QVariant.Double))

SED_FIELDS.append(QgsField(SEDAttributes.Integration_R, QVariant.Int))
SED_FIELDS.append(QgsField(SEDAttributes.Integration_T, QVariant.Int))

SED_FIELDS.append(QgsField(SEDAttributes.Averages_R, QVariant.Int))
SED_FIELDS.append(QgsField(SEDAttributes.Averages_T, QVariant.Int))

SED_FIELDS.append(QgsField(SEDAttributes.DarkMode_R, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.DarkMode_T, QVariant.String))

SED_FIELDS.append(QgsField(SEDAttributes.ForeOptic_R, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.ForeOptic_T, QVariant.String))

SED_FIELDS.append(QgsField(SEDAttributes.RadiometricCalibration, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Units, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.WavelengthRange, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Latitude, QVariant.Double))
SED_FIELDS.append(QgsField(SEDAttributes.Longitude, QVariant.Double))
SED_FIELDS.append(QgsField(SEDAttributes.Altitude, QVariant.Double))
SED_FIELDS.append(QgsField(SEDAttributes.GPSTime, QVariant.Time))
SED_FIELDS.append(QgsField(SEDAttributes.Satellites, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.CalibratedReferenceCorrectionFile, QVariant.String))
SED_FIELDS.append(QgsField(SEDAttributes.Channels, QVariant.Int))

KEY2FIELD = {
    'Comment': SEDAttributes.Comment,
    'Version': SEDAttributes.Version,
    'File Name': SEDAttributes.FileName,
    'Instrument': SEDAttributes.Instrument,
    'Detectors': SEDAttributes.Detectors,
    'Measurement': SEDAttributes.Measurement,
    'Radiometric Calibration': SEDAttributes.RadiometricCalibration,
    'Units': SEDAttributes.Units,
    'Wavelength Range': SEDAttributes.WavelengthRange,
    'Latitude': SEDAttributes.Latitude,
    'Longitude': SEDAttributes.Longitude,
    'Altitude': SEDAttributes.Altitude,
    'GPS Time': SEDAttributes.GPSTime,
    'Satellites': SEDAttributes.Satellites,
    'Calibrated Reference Correction File': SEDAttributes.CalibratedReferenceCorrectionFile,
    'Channels': SEDAttributes.Channels,
}

rx_metadata = re.compile('^(?P<key>[^:]+):(?P<value>.*)$')
rx_table_header = re.compile(r'^Wvl[^:]+')
rx_sed_file = re.compile(r'\.sed$', re.I)


class SEDFile(object):
    """
    Wrapper class to access a single SED File.
    """

    def __init__(self, path: str = None):
        super(SEDFile, self).__init__()
        self.mFeature = QgsFeature(SED_FIELDS)

        if path is not None:
            self.readFromSEDFile(path)

    def feature(self) -> QgsFeature:
        return self.mFeature

    def readFromSEDFile(self, path: typing.Union[str, pathlib.Path]):
        """
        Reads data from a binary file
        :param path:
        :return:
        """
        path = pathlib.Path(path)
        self.mFeature = QgsFeature(SED_FIELDS)
        self.mFeature.setAttribute(FIELD_NAME, path.name)

        fields: QgsFields = self.mFeature.fields()

        with open(path, 'r') as f:
            LINES = list(f.readlines())

            iFirstDataLine = None
            for i, line in enumerate(LINES):
                match_meta = rx_metadata.match(line)
                if match_meta:
                    key = match_meta.group('key')
                    value = match_meta.group('value').strip()
                    if value in ['', None]:
                        continue

                    # split into values for multiple fields / special fields
                    splitted = value.split(',')

                    if key == 'Date':
                        self.mFeature.setAttribute(SEDAttributes.Date_R,
                                                   QDate.fromString(splitted[0], 'MM/dd/yyyy'))
                        self.mFeature.setAttribute(SEDAttributes.Date_T,
                                                   QDate.fromString(splitted[1], 'MM/dd/yyyy'))

                    elif key == 'Time':
                        self.mFeature.setAttribute(SEDAttributes.Time_R,
                                                   QTime.fromString(splitted[0], 'hh:mm:ss'))
                        self.mFeature.setAttribute(SEDAttributes.Time_T,
                                                   QTime.fromString(splitted[1], 'hh:mm:ss'))

                    elif key == 'Temperature (C)':
                        self.mFeature.setAttribute(SEDAttributes.Temperature_R, float(splitted[0]))
                        self.mFeature.setAttribute(SEDAttributes.Temperature_T, float(splitted[2]))

                    elif key == 'Battery Voltage':
                        self.mFeature.setAttribute(SEDAttributes.BatteryVoltage_R, float(splitted[0]))
                        self.mFeature.setAttribute(SEDAttributes.BatteryVoltage_T, float(splitted[1]))

                    elif key == 'Averages':
                        self.mFeature.setAttribute(SEDAttributes.Averages_R, int(splitted[0]))
                        self.mFeature.setAttribute(SEDAttributes.Averages_T, int(splitted[1]))

                    elif key == 'Integration':
                        self.mFeature.setAttribute(SEDAttributes.Integration_R, int(splitted[0]))
                        self.mFeature.setAttribute(SEDAttributes.Integration_T, int(splitted[2]))

                    elif key == 'Dark Mode':
                        self.mFeature.setAttribute(SEDAttributes.DarkMode_R, splitted[0])
                        self.mFeature.setAttribute(SEDAttributes.DarkMode_T, splitted[1])

                    elif key == 'Foreoptic':
                        self.mFeature.setAttribute(SEDAttributes.ForeOptic_R, splitted[0])
                        self.mFeature.setAttribute(SEDAttributes.ForeOptic_T, splitted[1])

                    elif key in KEY2FIELD.keys():
                        fieldName = KEY2FIELD[key]

                        field: QgsField = fields.field(fieldName)

                        if field.type() == QVariant.String:
                            value = str(value)
                        elif field.type() == QVariant.Int:
                            value = int(value)
                        elif field.type() == QVariant.Double:
                            value = float(value)
                        elif field.type() == QVariant.Time:
                            value = QTime.fromString(value, 'hh:mm:ss')
                        else:
                            s = ""
                        self.mFeature.setAttribute(fieldName, value)
                    else:
                        s = ""

                elif rx_table_header.match(line):
                    iFirstDataLine = i + 1
                    break

            if iFirstDataLine:
                wvl = []
                rad_r = []
                rad_t = []
                refl = []
                for line in LINES[iFirstDataLine:]:
                    splitted = [float(v) for v in re.split(r'\s+', line.strip())]
                    if len(splitted) != 4:
                        break
                    wvl.append(splitted[0])
                    rad_r.append(splitted[1])
                    rad_t.append(splitted[2])
                    refl.append(splitted[3])

            yUnit = self.mFeature.attribute(SEDAttributes.Units)
            profile_r = prepareProfileValueDict(x=wvl, y=rad_r, xUnit='nm', yUnit=yUnit)
            profile_t = prepareProfileValueDict(x=wvl, y=rad_t, xUnit='nm', yUnit=yUnit)
            profile_ref = prepareProfileValueDict(x=wvl, y=refl, xUnit='nm', yUnit='%')

            dump_r = encodeProfileValueDict(profile_r,
                                            encoding=fields.field(SEDAttributes.Reference))
            dump_t = encodeProfileValueDict(profile_t,
                                            encoding=fields.field(SEDAttributes.Target))
            dump_ref = encodeProfileValueDict(profile_ref,
                                              encoding=fields.field(SEDAttributes.Reflectance))

            self.mFeature.setAttribute(SEDAttributes.Reference, dump_r)
            self.mFeature.setAttribute(SEDAttributes.Target, dump_t)
            self.mFeature.setAttribute(SEDAttributes.Reflectance, dump_ref)

            c_lat = self.mFeature.attribute(SEDAttributes.Latitude)
            c_lon = self.mFeature.attribute(SEDAttributes.Longitude)

            g = QgsGeometry.fromPointXY(QgsPointXY(c_lon, c_lat))
            self.mFeature.setGeometry(g)


class SEDSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(SEDSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None
        self.mFields: QgsFields = SED_FIELDS

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(SEDSpectralLibraryIO)

    def supportsMultipleFiles(self) -> bool:
        return True

    def filter(self) -> str:
        return "Spectral Evolution File (*.sed);;Any file (*.*)"

    def setSource(self, source: str):
        if self.mSource != source:
            self.mSource = source
            self.sigSourceChanged.emit()

    def sourceFields(self) -> QgsFields:
        return QgsFields(self.mFields)

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()

        return context


class SEDSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'Spectral Evolutions'

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return SEDSpectralLibraryImportWidget()

    @classmethod
    def readSEDFile(cls, filePath: str) -> QgsFeature:
        """
        Reads a Spectral Evolutions file (*.sed)
        :param filePath:
        :return:
        """
        path = pathlib.Path(filePath)
        return SEDFile(path).asFeature()

    @classmethod
    def importProfiles(cls,
                       path: typing.Union[str, pathlib.Path],
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[QgsFeature]:
        profiles = []

        if isinstance(path, str):
            sources = QgsFileWidget.splitFilePaths(path)
        elif isinstance(path, pathlib.Path):
            sources = []
            if path.is_dir():
                for entry in os.scandir(path):
                    if entry.is_file() and rx_sed_file.match(entry.name):
                        sources.append(entry.path)
            elif path.is_file():
                sources.append(path.as_posix())

        # expected_fields = importSettings.get()

        feedback.setProgress(0)
        n_total = len(sources)
        for i, file in enumerate(sources):
            file = pathlib.Path(file)

            sed: SEDFile = SEDFile(file)
            profiles.append(sed.feature())

            feedback.setProgress((i + 1) / n_total)
        return profiles
