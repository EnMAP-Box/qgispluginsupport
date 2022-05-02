# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/asd.py

    Input/Output of ASD spectral library data
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
import datetime
import enum
import os
import pathlib
import re
import struct
import typing
import warnings

import numpy as np

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsFields, QgsExpressionContext, QgsFeature, \
    QgsField, QgsPointXY, QgsGeometry, QgsProcessingFeedback
from qgis.gui import QgsFileWidget
from .. import FIELD_NAME
from ..core import create_profile_field
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportWidget
from ..core.spectralprofile import prepareProfileValueDict, encodeProfileValueDict

"""

Offset Size Type Description Comment
3 char co[3]; // File Version - as6
3 157 char comments[157]; // comment field
160 18 struct tm when; // time when spectrum was saved
178 1 byte program_version; // ver. of the programcreatinf this file.
// major ver in upper nibble, min in lower
179 1 byte file_version; // spectrum file format version
180 1 byte itime; // Not used after v2.00
181 1 byte dc_corr; // 1 if DC subtracted, 0 if not
182 4 time_t (==long) dc_time; // Time of last dc, seconds since 1/1/1970
186 1 byte data_type; // see *_TYPE below
187 4 time_t (==long) ref_time; // Time of last wr, seconds since 1/1/1970
191 4 float ch1_wavel; // calibrated starting wavelength in nm
195 4 float wavel_step; // calibrated wavelength step in nm
199 1 byte data_format; // format of spectrum.
200 1 byte old_dc_count; // Num of DC measurements in the avg
201 1 byte old_ref_count; // Num of WR in the average
202 1 byte old_sample_count; // Num of spec samples in the avg
203 1 byte application; // Which application created APP_DATA
204 2 ushort channels; // Num of channels in the detector
206 128 APP_DATA app_data; // Application-specific data
334 56 GPS_DATA gps_data; // GPS position, course, etc.
390 4 ulong it; // The actual integration time in ms
394 2 int fo; // The fo attachment's view in degrees
396 2 int dcc; // The dark current correction value
398 2 uint calibration; // calibration series
400 2 uint instrument_num; // instrument number
402 4 float ymin; // setting of the y axis' min value
406 4 float ymax; // setting of the y axis' max value
410 4 float xmin; // setting of the x axis' min value
414 4 float xmax; // setting of the x axis' max value
418 2 uint ip_numbits; // instrument's dynamic range
420 1 byte xmode; // x axis mode. See *_XMODE
421 4 byte flags[4]; // flags(0) = AVGFIX'ed
// flags(1) see below
425 2 unsigned dc_count; // Num of DC measurements in the avg
427 2 unsigned ref_count; // Num of WR in the average
429 2 unsigned sample_count; // Num of spec samples in the avg
431 1 byte instrument; // Instrument type. See defs below
432 4 ulong bulb; // The id number of the cal bulb
436 2 uint swir1_gain; // gain setting for swir 1
438 2 uint swir2_gain; // gain setting for swir 2
440 2 uint swir1_offset; // offset setting for swir 1
442 2 uint swir2_offset; // offset setting for swir 2
444 4 float splice1_wavelength; // wavelength of VNIR and SWIR1 splice
448 4 float splice2_wavelength; // wavelength of SWIR1 and SWIR2 splice
452 27 float SmartDetectorType // Data from OL731 device
479 5 byte spare[5]; // fill to 484 bytes
"""

ASD_VERSIONS = ['ASD', 'asd', 'as6', 'as7', 'as8']

RX_ASDFILE = re.compile(r'.*\.(asd|\d+)$')


class SpectrumDataType(enum.IntEnum):
    RAW_TYPE = 0
    REF_TYPE = 1
    RAD_TYPE = 2
    NOUNITS_TYPE = 3
    IRRAD_TYPE = 4
    QI_TYPE = 5
    TRANS_TYPE = 6
    UNKNOWN_TYPE = 7
    ABS_TYPE = 8


class SpectrumDataFormat(enum.Enum):
    FLOAT_FORMAT = 0
    INTEGER_FORMAT = 1
    DOUBLE_FORMAT = 2
    UNKOWN_FORMAT = 3


class InstrumentType(enum.Enum):
    UNKOWN_INSTRUMENT = 0
    PSII_INSTRUMENT = 1
    LSVNIR_INSTRUMENT = 2
    FSVNIR_INSTRUMENT = 3
    FSFR_INSTRUMENT = 4
    FSNIR_INSTRUMENT = 5
    CHEM__INSTRUMENT = 6
    FSFR_UNATTENDED_INSTRUMENT = 7


class GPS_DATA(object):

    # time_t = == long
    def __init__(self, DATA):
        ASD_GPS_DATA = struct.Struct("< 5d H c l H 5c 2c").unpack(DATA)
        # ASD_GPS_DATA2 = struct.Struct("= 5d 2b cl 2b 5B 2c").unpack(DATA)
        self.true_heading, self.speed, latDM, lonDM, self.altitude = ASD_GPS_DATA[0:5]
        latD = int(latDM / 100)
        lonD = int(lonDM / 100)
        latM = latDM - (latD * 100)
        lonM = lonDM - (lonD * 100)
        # convert Degree + Minute to DecimalDegrees
        self.latitude = latD + latM / 60
        self.longitude = lonD + lonM / 60
        self.longitude *= -1  #
        self.flags = ASD_GPS_DATA[5]  # unpack this into bits
        self.hardware_mode = ASD_GPS_DATA[6]
        self.timestamp = ASD_GPS_DATA[7]
        self.timestamp = np.datetime64('1970-01-01') + np.timedelta64(ASD_GPS_DATA[7], 's')
        self.flags2 = ASD_GPS_DATA[8]  # unpack this into bits
        self.satellites = ASD_GPS_DATA[9:15]
        self.filler = ASD_GPS_DATA[10]

        s = ""


class SmartDetectorType(object):

    def __init__(self, DATA):
        """

        :param DATA:
        """
        # 27 byte struct
        # 1 i int   4           4
        # 3 f float 12         16
        # 1 h short 2          18
        # 1 b byte  1          19
        # 2 f float 8          27

        if DATA is not None:
            DETECTOR = struct.Struct('< 1i 3f 1h 1b 2f').unpack(DATA)
        else:
            DETECTOR = [None, None, None, None, None, None, None, None]
        self.serial_number, self.Signal, self.dark, self.ref, self.Status, self.avg, self.humid, self.temp = DETECTOR


class UTC_TIME(object):

    def __init__(self, DATA):
        self.tm_year, self.tm_mon, self.tm_mday, \
            self.tm_hour, self.tm_min, self.tm_sec, \
            self.tm_wday, self.tm_yday, self.tm_isdst = struct.Struct("= 9h").unpack(DATA)


class TM_STRUCT(object):

    def __init__(self, DATA):
        self.tm_sec, self.tm_min, self.tm_hour, self.tm_mday, \
            self.tm_mon, self.tm_year, self.tm_wday, \
            self.tm_yday, self.tm_isdst = struct.Struct("= 9h").unpack(DATA)

    def date(self):
        return datetime.date(self.year(), self.month(), self.day())

    def datetime(self):
        return datetime.datetime(self.year(), self.month(), self.day(), hour=self.tm_hour, minute=self.tm_min,
                                 second=self.tm_sec)

    def time(self):
        return datetime.time(hour=self.tm_hour, minute=self.tm_min, second=self.tm_sec)

    def datetime64(self) -> np.datetime64:
        return np.datetime64(
            '{:04}-{:02}-{:02}T{:02}:{:02}:{:02}'.format(self.year(), self.month(), self.day(), self.tm_hour,
                                                         self.tm_min, self.tm_sec))

    def doy(self) -> int:
        return self.tm_yday

    def day(self) -> int:
        return self.tm_mday

    def month(self) -> int:
        return self.tm_mon + 1

    def year(self) -> int:
        return self.tm_year + 1900


ASD_FIELDS = QgsFields()
ASD_FIELDS.append(QgsField(FIELD_NAME, QVariant.String))
ASD_FIELDS.append(create_profile_field('Reference'))
ASD_FIELDS.append(create_profile_field('Spectrum'))
ASD_FIELDS.append(QgsField('co', QVariant.String))
ASD_FIELDS.append(QgsField('instrument', QVariant.String))
ASD_FIELDS.append(QgsField('instrument_num', QVariant.Int))
ASD_FIELDS.append(QgsField('sample_count', QVariant.Int))


class ASDBinaryFile(object):
    """
    Wrapper class to access a ASD File Format binary file.
    See ASD File Format, version 8, revision B, ASD Inc.,
    a PANalytical company, 2555 55th Street, Suite 100 Boulder, CO 80301.
    """

    def __init__(self, path: str = None):
        super(ASDBinaryFile, self).__init__()
        self.name: str = ''
        # initialize all variables in the ASD Binary file header
        self.co: str = None
        self.comments: str = None
        self.when: TM_STRUCT = None
        self.program_version: int = None
        self.file_version: int = None
        self.itime: int = None
        self.dc_corr: int = None
        self.dc_time: np.datetime64 = None
        self.data_type: SpectrumDataType = None
        self.ref_time: np.datetime64 = None
        self.ch1_wavel: float = None
        self.wavel_step: float = None
        self.data_format: SpectrumDataFormat = None
        self.old_dc_count: int = None
        self.old_ref_count: int = None
        self.old_sample_count: int = None
        self.application: int = None
        self.channels: int = None
        self.app_data = None
        self.gps_data: GPS_DATA = None
        self.it: int = None
        self.fo: int = None
        self.dcc: int = None
        self.calibration: int = None
        self.instrument_num: int = None
        self.ymin: float = None
        self.ymax: float = None
        self.xmin: float = None
        self.ymax: float = None
        self.ip_numbits: int = None
        self.xmode: int = None
        self.flags: tuple = None
        self.dc_count: int = None
        self.ref_count: int = None
        self.sample_count: int = None
        self.instrument: InstrumentType = None
        self.bulb = None
        self.swir1_gain = None
        self.swir2_gain = None
        self.swir1_offset = None
        self.swir2_offset = None
        self.splice1_wavelength = None
        self.splice2_wavelength = None
        self.SmartDetectorType = None
        self.spare = None

        self.Spectrum = None
        self.ReferenceFlag: bool = None
        self.ReferenceTime: np.datetime64 = None
        self.SpectrumTime: np.datetime64 = None
        self.SpectrumDescription: str = None
        self.Reference = None

        if path is not None:
            self.readFromBinaryFile(path)

    def xValues(self) -> np.ndarray:
        values = np.linspace(self.ch1_wavel, self.ch1_wavel + self.channels * self.wavel_step - 1, self.channels)
        return values

    def yValues(self) -> np.ndarray:
        warnings.warn('Use yValuesSpectrum', DeprecationWarning)
        return self.yValuesSpectrum()

    def yValuesSpectrum(self) -> np.ndarray:
        return self.Spectrum

    def yValuesReference(self) -> np.ndarray:
        return self.Reference

    def asFeature(self, fields: QgsFields = None) -> QgsFeature:
        """
        Returns the input as QgsFeature with attributes defined in ASD_FIELDS
        :return:
        """

        if not isinstance(fields, QgsFields):
            fields = ASD_FIELDS

        f = QgsFeature(fields)

        GPS = self.gps_data

        x, y = GPS.longitude, GPS.latitude
        g = QgsGeometry.fromPointXY(QgsPointXY(x, y))
        f.setGeometry(g)
        f.setAttribute(FIELD_NAME, self.name)
        f.setAttribute('co', self.co)
        f.setAttribute('instrument', self.instrument.name)
        f.setAttribute('instrument_num', self.instrument_num)
        f.setAttribute('sample_count', self.sample_count)

        x = self.xValues()
        ySpectrum = self.yValuesSpectrum()
        if ySpectrum is not None:
            spectrum_dict = prepareProfileValueDict(x=x, y=self.yValuesSpectrum(), xUnit='nm')
            f.setAttribute('Spectrum', encodeProfileValueDict(spectrum_dict, fields.field('Spectrum')))

        yReference = self.yValuesReference()
        if yReference is not None:
            reference_dict = prepareProfileValueDict(x=x, y=self.yValuesReference(), xUnit='nm')
            f.setAttribute('Reference', encodeProfileValueDict(reference_dict, fields.field('Reference')))

        return f

    def readFromBinaryFile(self, path: typing.Union[str, pathlib.Path]):
        """
        Reads data from a binary file
        :param path:
        :return:
        """
        path = pathlib.Path(path)
        with open(path, 'rb') as f:
            DATA = f.read()
            self.name = path.name

            def sub(start, length):
                return DATA[start:start + length]

            def n_string(start: int) -> typing.Tuple[str, int]:
                # 2 byte int for length
                # 2 + length
                # empty string = 2 byte = 0
                # h = short, H = unsigned short
                len_string = struct.unpack('<H', sub(start, 2))[0]
                result = ''
                if len_string > 0:
                    # result = struct.unpack('<c',sub(start + 2, len_string) )[0]
                    result = sub(start + 2, len_string).decode('ascii')
                return result, 2 + len_string

            self.co = DATA[0:3].decode('utf-8')
            self.comments = DATA[3:(3 + 157)].decode('utf-8')

            self.when = TM_STRUCT(DATA[160:(160 + 18)])
            self.program_version = DATA[178]
            self.file_version = DATA[179]
            self.itime = DATA[180]
            self.dc_corr = DATA[181]
            self.dc_time = np.datetime64('1970-01-01') + np.timedelta64(struct.unpack('<l', DATA[182:182 + 4])[0], 's')
            self.data_type = SpectrumDataType(DATA[186])
            self.ref_time = np.datetime64('1970-01-01') + np.timedelta64(struct.unpack('<l', DATA[182:182 + 4])[0], 's')
            self.ch1_wavel = struct.unpack('<f', sub(191, 4))[0]
            self.wavel_step = struct.unpack('<f', sub(195, 4))[0]
            self.data_format = SpectrumDataFormat(DATA[199])
            self.old_dc_count = DATA[200]
            self.old_ref_count = DATA[201]
            self.old_sample_count = DATA[202]
            self.application = DATA[203]

            self.channels = struct.unpack('<H', sub(204, 2))[0]

            self.app_data = sub(206, 128)
            self.gps_data = GPS_DATA(sub(334, 56))

            self.it = struct.unpack('<L', sub(390, 4))[0]
            self.fo = struct.unpack('<h', sub(394, 2))[0]
            self.dcc = struct.unpack('<h', sub(396, 2))[0]

            self.calibration = struct.unpack('<H', sub(398, 2))[0]
            self.instrument_num = struct.unpack('<H', sub(400, 2))[0]

            self.ymin, self.ymax, self.xmin, self.ymax = struct.unpack('<4f', sub(402, 4 * 4))

            self.ip_numbits = struct.unpack('<H', sub(418, 2))[0]
            self.xmode = struct.unpack('<b', sub(420, 1))[0]
            self.flags = struct.unpack('<4b', sub(421, 4))

            self.dc_count, self.ref_count, self.sample_count = struct.unpack('<3H', sub(425, 2 * 3))

            self.instrument = InstrumentType(struct.unpack('<B', sub(431, 1))[0])

            self.bulb = struct.unpack('<L', sub(432, 4))
            self.swir1_gain, self.swir2_gain, self.swir1_offset, self.swir2_offset = struct.unpack('<4H',
                                                                                                   sub(436, 2 * 4))

            self.splice1_wavelength, self.splice2_wavelength = struct.unpack('<2f', sub(444, 2 * 4))

            self.SmartDetectorType = SmartDetectorType(sub(452, 27))
            self.spare = sub(479, 5)

            if self.data_format == SpectrumDataFormat.FLOAT_FORMAT:
                size = 4 * self.channels
                fmt = '<{}f'.format(self.channels)

            elif self.data_format == SpectrumDataFormat.DOUBLE_FORMAT:
                size = 8 * self.channels
                fmt = '<{}d'.format(self.channels)
            elif self.data_format == SpectrumDataFormat.INTEGER_FORMAT:
                size = 4 * self.channels
                fmt = '<{}i'.format(self.channels)
            else:
                raise Exception()

            self.Spectrum = np.array(struct.unpack(fmt, sub(484, size)))

            # reference file header = spectrum data size + 1

            #
            o = 484 + size - 1
            # o = 484 + size
            self.ReferenceFlag = struct.unpack('<?', sub(o + 1, 1))[0]
            if self.ReferenceFlag:
                #           self.ReferenceTime = np.datetime64('1970-01-01') + np.timedelta64(
                #                struct.unpack('<l', DATA[(o + 3):(o + 3 + 8)])[0], 's')
                #           self.SpectrumTime = np.datetime64('1970-01-01') + np.timedelta64(
                #                struct.unpack('<l', DATA[o + 11:o + 11 + 8])[0], 's')

                reftime = struct.unpack('<8B', sub(o + 3, 8))
                spectime = struct.unpack('<8B', sub(o + 11, 8))
                self.SpectrumDescription, slen = n_string(o + 19)

                # reference data
                self.Reference = np.array(struct.unpack(fmt, sub(o + 19 + slen, size)))
            s = ""

        return self


class ASDSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(ASDSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None
        self.mFields: QgsFields = ASD_FIELDS

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(ASDSpectralLibraryIO)

    def supportsMultipleFiles(self) -> bool:
        return True

    def filter(self) -> str:
        return "ASD Binary File (*.asd);;Any file (*.*)"

    def setSource(self, source: str):
        if self.mSource != source:
            self.mSource = source
            self.sigSourceChanged.emit()

    def sourceFields(self) -> QgsFields:
        return QgsFields(self.mFields)

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()

        return context


class ASDSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'ASD Field Spectrometer'

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return ASDSpectralLibraryImportWidget()

    @classmethod
    def readBinaryFile(cls, filePath: str) -> QgsFeature:
        """
        Reads a binary ASD file (*.asd, *.as7)
        :param filePath:
        :return:
        """
        path = pathlib.Path(filePath)
        return ASDBinaryFile(path).asFeature()

    @classmethod
    def readCSVFile(cls, filePath: str) -> typing.List[QgsFeature]:
        """
        Read profiles from a text file
        :param filePath:
        :return: list of QgsFeatures
        """
        profiles = []

        with open(filePath, 'r', encoding='utf-8') as f:
            profiles = []
            lines = f.readlines()
            delimiter = ';'
            if len(lines) >= 2:
                hdrLine = lines[0].strip().split(delimiter)
                if len(hdrLine) >= 2:
                    profileNames = hdrLine[1:]

                    xValues = []
                    DATA = dict()
                    for line in lines[1:]:
                        line = line.split(delimiter)
                        wl = float(line[0])
                        xValues.append(wl)
                        DATA[wl] = [float(v) for v in line[1:]]

                    for i, name in enumerate(profileNames):
                        yValues = [DATA[wl][i] for wl in xValues]
                        xUnit = 'nm'

                        profile = QgsFeature(ASD_FIELDS)
                        spectrum_dict = prepareProfileValueDict(x=xValues, y=yValues, xUnit=xUnit)
                        profile.setAttribute('Spectrum',
                                             encodeProfileValueDict(spectrum_dict, ASD_FIELDS.field('Spectrum')))

                        profiles.append(profile)

        return profiles

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
                    if entry.is_file() and RX_ASDFILE.match(entry.name):
                        sources.append(entry.path)
            elif path.is_file():
                sources.append(path.as_posix())

        # expected_fields = importSettings.get()

        rxCSV = re.compile(r'.*\.(csv|txt)$')
        feedback.setProgress(0)
        n_total = len(sources)
        for i, file in enumerate(sources):
            file = pathlib.Path(file)

            if rxCSV.search(file.name):
                profiles.extend(ASDSpectralLibraryIO.readCSVFile(file))
            else:
                asd: ASDBinaryFile = ASDBinaryFile(file)
                profiles.append(asd.asFeature())
            feedback.setProgress((i + 1) / n_total)
        return profiles
