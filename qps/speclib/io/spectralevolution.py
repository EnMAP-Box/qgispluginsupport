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
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import datetime
import os
import pathlib
import re
from typing import List, Union

from qgis.core import QgsExpressionContext, QgsFeature, QgsFields, QgsPointXY, \
    QgsProcessingFeedback, QgsVectorLayer
from qgis.gui import QgsFileWidget
from ..core.spectrallibraryio import SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import prepareProfileValueDict, SpectralProfileFileReader
from ...qgisenums import QMETATYPE_QSTRING


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


KEY2TYPE = {
    'Comment': QMETATYPE_QSTRING,
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


class SEDFile(SpectralProfileFileReader):
    """
    Wrapper class to access a single SED File.
    """

    def __init__(self, *args, **kwds):
        super(SEDFile, self).__init__(*args, *kwds)
        # self.mFeature = QgsFeature(SED_FIELDS)

        if self.mPath is not None:
            self.readFromSEDFile(self.mPath)

    def readFromSEDFile(self, path: Union[str, pathlib.Path]):
        """
        Reads data from a binary file
        :param path:
        :return:
        """

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

                    self.mMetadata[key] = value

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

            if 'Date' in self.mMetadata and 'Time' in self.mMetadata:
                d1, d2 = self.mMetadata['Date'].split(',')
                t1, t2 = self.mMetadata['Time'].split(',')
                self.mReferenceTime = datetime.datetime.strptime(d1 + ' ' + t1, '%m/%d/%Y %H:%M:%S')
                self.mTargetTime = datetime.datetime.strptime(d2 + ' ' + t2, '%m/%d/%Y %H:%M:%S')

            if 'Latitude' in self.mMetadata and 'Longitude' in self.mMetadata:
                self.mTargetCoordinate = QgsPointXY(float(self.mMetadata['Longitude']),
                                                    float(self.mMetadata['Latitude']))

            yUnit = self.mMetadata.get('Units', None)
            profile_r = prepareProfileValueDict(x=wvl, y=rad_r, xUnit='nm', yUnit=yUnit)
            profile_t = prepareProfileValueDict(x=wvl, y=rad_t, xUnit='nm', yUnit=yUnit)
            profile_refl = prepareProfileValueDict(x=wvl, y=refl, xUnit='nm', yUnit='%')

            self.mReference = profile_r
            self.mTarget = profile_t
            self.mReflectance = profile_refl


class SEDSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(SEDSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None

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
        return QgsFields(SpectralProfileFileReader.standardFields())

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
                       path: Union[str, pathlib.Path],
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:
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
        t0 = datetime.datetime.now()
        dt = datetime.timedelta(seconds=3)
        n_total = len(sources)
        for i, file in enumerate(sources):
            file = pathlib.Path(file)

            sed: SEDFile = SEDFile(file)
            profiles.extend(sed.asFeatures())
            if datetime.datetime.now() - t0 > dt:
                feedback.setProgress((i + 1) / n_total)
                t0 = datetime.datetime.now()
        return profiles
