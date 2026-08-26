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
import re
from pathlib import Path
from typing import Union

from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsPointXY

from ..core.spectralprofile import prepareProfileValueDict, SpectralProfileFileReader
from ...utils import readDateTime


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
    'Comment': QMetaType.Type.QString,
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

    @classmethod
    def id(cls) -> str:
        return 'SED'

    @classmethod
    def shortHelp(cls) -> str:
        return 'Spectral Evolution (<a href="https://spectralevolution.com">https://spectralevolution.com</a>)'

    @classmethod
    def canReadFile(cls, path: Union[str, Path]) -> bool:
        path = Path(path)
        return rx_sed_file.search(path.name) is not None

    def readFromSEDFile(self, path: Union[str, Path]):
        """
        Reads data from a binary file
        :param path:
        :return:
        """

        with open(path, 'r') as f:
            LINES = list(f.readlines())

            iFirstDataLine = None

            header_cols = []
            for i, line in enumerate(LINES):
                match_meta = rx_metadata.match(line)
                if match_meta:
                    key = match_meta.group('key')
                    value = match_meta.group('value').strip()
                    if value in ['', None]:
                        continue

                    self.mMetadata[key] = value

                else:
                    match_hdr = rx_table_header.match(line)
                    if match_hdr:
                        header_cols.extend(match_hdr.group().split('\t'))
                        iFirstDataLine = i + 1
                        break

            header_cols = [h.strip() for h in header_cols]

            if 'Wvl' not in header_cols:
                raise Exception(f'Unable to find Wvl column in {path}')

            # Prepare data lists for known column types
            data_dict = {}
            for header in header_cols:
                data_dict[header] = []

            nc = len(header_cols)
            for line in LINES[iFirstDataLine:]:
                line = line.strip()
                if not line:
                    continue  # skip empty lines

                # Split the line by whitespace or comma
                values = re.split(r'[\s,]+', line)

                # Parse numeric values, try float first, fallback to string
                parsed_values = []
                for v in values:
                    try:
                        parsed_values.append(float(v))
                    except ValueError:
                        parsed_values.append(v)

                # If we have enough values, populate the appropriate columns
                if len(parsed_values) == nc:
                    for h, v in zip(header_cols, parsed_values):
                        data_dict[h].append(v)

            # Extract the standard data columns if they exist
            wvl = data_dict['Wvl']
            yUnit = self.mMetadata.get('Units', None)

            for column in data_dict.keys():
                y = data_dict[column]
                if column == 'Wvl':
                    continue
                elif column in ['Reflect. %', 'Tgt./Ref. %']:
                    profile = prepareProfileValueDict(x=wvl, y=y, xUnit='nm', yUnit='%')
                    self.mReflectance = profile
                elif column in ['Rad. (Ref.)', ]:
                    profile = prepareProfileValueDict(x=wvl, y=y, xUnit='nm', yUnit=yUnit)
                    self.mReference = profile
                elif column in ['Rad. (Target)']:
                    profile = prepareProfileValueDict(x=wvl, y=y, xUnit='nm', yUnit=yUnit)
                    self.mTarget = profile
                else:
                    pass

            if 'Date' in self.mMetadata and 'Time' in self.mMetadata:
                d1, d2 = self.mMetadata['Date'].split(',')
                t1, t2 = self.mMetadata['Time'].split(',')
                dt1, hint = readDateTime(d1 + ' ' + t1)
                dt2, _ = readDateTime(d2 + ' ' + t2, hint)
                self.mReferenceTime = dt1
                self.mTargetTime = dt2

                # self.mReferenceTime = datetime.datetime.strptime(d1 + ' ' + t1, '%m/%d/%Y %H:%M:%S')
                # self.mTargetTime = datetime.datetime.strptime(d2 + ' ' + t2, '%m/%d/%Y %H:%M:%S')

            if 'Latitude' in self.mMetadata and 'Longitude' in self.mMetadata:
                try:
                    self.mTargetCoordinate = QgsPointXY(float(self.mMetadata['Longitude']),
                                                        float(self.mMetadata['Latitude']))
                except ValueError:
                    pass
