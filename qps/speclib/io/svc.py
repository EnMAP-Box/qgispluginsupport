import datetime
import os
import re
from datetime import timezone, timedelta
from pathlib import Path
from typing import List, Match, Optional, Union

import numpy as np

from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.core import QgsEditorWidgetSetup, QgsExpressionContext, QgsFeature, QgsField, QgsFields, QgsPointXY, \
    QgsProcessingFeedback, QgsVectorLayer
from qgis.gui import QgsFileWidget
from ..core.spectrallibraryio import SpectralLibraryImportWidget, SpectralLibraryIO
from ..core.spectralprofile import prepareProfileValueDict, SpectralProfileFileReader
from ...qgisenums import QMETATYPE_QDATETIME, QMETATYPE_QSTRING

# GPS Longitude  DDDmm.mmmmC
# GPS Latitude  DDmm.mmmmC
# GPS Time  HHmmSS.SSS

# Precompiled regular expressions for performance
rxSIGFile = re.compile(r'\.sig$')
rxGPSLongitude = re.compile(r'(?P<deg>\d{3})(?P<min>\d{2}.\d+)(?P<quad>[EW])')
rxGPSLatitude = re.compile(r'(?P<deg>\d{2})(?P<min>\d{2}.\d+)(?P<quad>[NS])')
rxGPSTime = re.compile(r'(?P<hh>\d{2})(?P<mm>\d{2})(?P<sec>\d{2}(\.\d+)?)')
rx_decimal_sep = re.compile(r'temp= \d+([,.])\d+,')
rx_sig_file = re.compile(r'\.sig$')
rx_comment_block = re.compile(r'/[*]{3}.*[*]{3}/', re.DOTALL)
rx_metadata = re.compile(r'^(?P<tag>[^=]+)=(?P<val>.*)', re.MULTILINE)
rx_data_block = re.compile(r'^data=(?P<data>.*)', re.MULTILINE | re.DOTALL)
rx_moc_suffix = re.compile(r'_moc$')


def toQDateTime(value) -> QDateTime:
    if isinstance(value, str):
        return QDateTime.fromString(value, Qt.ISODate)
    elif isinstance(value, datetime.datetime):
        return QDateTime.fromString(value.isoformat(), Qt.ISODate)
    raise NotImplementedError()


def gpsTime(date: datetime.datetime, gpstime_string: str) -> Optional[datetime.datetime]:
    if not isinstance(date, datetime.datetime):
        return None
    m = rxGPSTime.match(gpstime_string)

    if not m:
        return None

    dtg = datetime.datetime(year=date.year,
                            month=date.month,
                            day=date.day,
                            hour=int(m.group('hh')),
                            minute=int(m.group('mm')),
                            second=int(float(m.group('sec'))),
                            tzinfo=timezone(timedelta(0)),  # UTC
                            )

    return dtg


def match_to_coordinate(matchLon: Match, matchLat: Match) -> QgsPointXY:
    y = float(matchLat.group('deg')) + float(matchLat.group('min')) / 60
    x = float(matchLon.group('deg')) + float(matchLon.group('min')) / 60

    if matchLon.group('quad') == 'W':
        x *= -1

    if matchLat.group('quad') == 'S':
        y *= -1

    return QgsPointXY(x, y)


class SVCSigFile(SpectralProfileFileReader):

    def __init__(self, path: Union[str, Path]):
        super().__init__(path)

        self.mRemoveOverlap: bool = True
        self.mPicture: Optional[Path] = None
        self.mGpsTimeR: Optional[datetime.datetime] = None
        self.mGpsTimeT: Optional[datetime.datetime] = None
        self._readSIGFile(path)

    def _parse_coordinates(self) -> None:
        """Parse coordinate information from metadata using precompiled regex"""
        if 'longitude' in self.mMetadata and 'latitude' in self.mMetadata:
            longitudes = rxGPSLongitude.finditer(self.mMetadata['longitude'])
            latitudes = rxGPSLatitude.finditer(self.mMetadata['latitude'])
            coordinates = [match_to_coordinate(lon, lat) for lon, lat in zip(longitudes, latitudes)]

            if len(coordinates) == 2:
                self.mReferenceCoordinate = coordinates[0]
                self.mTargetCoordinate = coordinates[1]
            elif len(coordinates) == 1:
                self.mTargetCoordinate = coordinates[0]

    def _parse_times(self) -> None:
        """Parse time information from metadata efficiently"""
        if 'time' in self.mMetadata:
            # Parse regular timestamps
            t1, t2 = [t.strip() for t in self.mMetadata['time'].split(',')]
            self.mReferenceTime = self._readDateTime(t1)
            self.mTargetTime = self._readDateTime(t2)

            # Parse GPS times if available
            if 'gpstime' in self.mMetadata:
                gpsR, gpsT = [t.strip() for t in self.mMetadata['gpstime'].split(',')]

                # Only calculate GPS times if we have reference times
                if self.mReferenceTime:
                    self.mGpsTimeR = gpsTime(self.mReferenceTime, gpsR)
                if self.mTargetTime:
                    self.mGpsTimeT = gpsTime(self.mTargetTime, gpsT)

    def picturePath(self) -> Optional[Path]:
        return self.mPicture

    def standardFields(self) -> QgsFields:

        fields = super().standardFields()

        gpsTimeTField = QgsField('gpsTimeT', type=QMETATYPE_QDATETIME)
        gpsTimeRField = QgsField('gpsTimeR', type=QMETATYPE_QDATETIME)

        pictureField = QgsField(self.KEY_Picture, type=QMETATYPE_QSTRING)

        # setup attachment widget
        config = {'DocumentViewer': 1,
                  'DocumentViewerHeight': 0,
                  'DocumentViewerWidth': 0,
                  'FileWidget': True,
                  'FileWidgetButton': True,
                  'FileWidgetFilter': '',
                  'PropertyCollection': {'name': None,
                                         'properties': {},
                                         'type': 'collection'},
                  'RelativeStorage': 0,
                  'StorageAuthConfigId': None,
                  'StorageMode': 0,
                  'StorageType': None}
        setup = QgsEditorWidgetSetup('ExternalResource', config)
        pictureField.setEditorWidgetSetup(setup)
        fields.append(gpsTimeRField)
        fields.append(gpsTimeTField)
        fields.append(pictureField)
        return fields

    def asMap(self) -> dict:

        data = super().asMap()
        if isinstance(self.mPicture, Path):
            data[self.KEY_Picture] = self.mPicture.as_posix()
        if self.mGpsTimeR:
            data['gpsTimeR'] = toQDateTime(self.mGpsTimeR)
        if self.mGpsTimeT:
            data['gpsTimeT'] = toQDateTime(self.mGpsTimeT)
        return data

    @staticmethod
    def _readDateTime(text: str) -> datetime.datetime:
        text = text.strip()

        # test for ISO
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            pass

        # test non-ISO formats
        formats = [
            '%m/%d/%Y %H:%M:%S%p',  # 5/27/2025 9:39:32AM
            '%m/%d/%Y %H:%M:%S %p',  # 5/27/2025 9:39:32 AM
            '%m/%d/%Y %H:%M:%S',  # 5/27/2025 9:39:32
            '%d/%m/%Y %H:%M:%S',  # 27/05/2025 09:39:32
            '%d.%m.%Y %H:%M:%S',  # 27.05.2025 09:39:32
        ]

        for fmt in formats:
            try:
                return datetime.datetime.strptime(text, fmt)
            except ValueError:
                continue

        raise ValueError(f'Unable to extract datetime from {text}')

    def _readSIGFile(self, path):
        """Parse SIG file using precompiled regular expressions for improved performance"""
        path: Path = Path(path)
        with open(path) as f:
            lines = f.read()

        # Remove comment blocks

        lines = rx_comment_block.sub('', lines)
        decimal_separator = rx_decimal_sep.search(lines).group(1)

        # Extract decimal separator

        # Extract metadata tags
        for match in rx_metadata.finditer(lines):
            tag = match.group('tag').strip()
            val = match.group('val').strip()
            self.mMetadata[tag] = val

        # Extract data block
        match = rx_data_block.search(lines.strip())
        if not match:
            raise ValueError(f"Could not find data block in {path}")

        data = match.group('data').strip()
        data = data.replace(decimal_separator, '.')
        dataLines = data.split('\n')
        nRows = len(dataLines)
        data = data.split()
        nCols = int(len(data) / nRows)
        data = np.asarray([float(d) for d in data]).reshape((nRows, nCols))

        # Process wavelength data
        wl = data[:, 0]
        if np.all(wl == 0):
            wl = None  # no wl defined. use band numbers only

        # Create profile value dictionaries
        self.mReference = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 1])
        if nCols > 2:
            self.mTarget = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 2])
        if nCols > 3:
            self.mReflectance = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 3], yUnit='%')

        # Process coordinates if available
        self._parse_coordinates()

        # Process time information
        self._parse_times()

        # Find associated image files
        stem = rx_moc_suffix.sub('', path.stem)
        for ext in ['.jpg', '.png']:
            path_img = path.parent / f'{stem}.sig{ext}'
            if path_img.is_file():
                self.mPicture = path_img
                break


class SVCSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(SVCSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: Optional[QgsVectorLayer] = None

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(SVCSpectralLibraryIO)

    def supportsMultipleFiles(self) -> bool:
        return True

    def filter(self) -> str:
        return "Spectra Vista Coorporation SVC) File (*.sig);;Any file (*.*)"

    def setSource(self, source: str):
        if self.mSource != source:
            self.mSource = source
            self.sigSourceChanged.emit()

    def sourceFields(self) -> QgsFields:
        return QgsFields(SpectralProfileFileReader.standardFields())

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext()

        return context


class SVCSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def formatName(self) -> str:
        return 'SVC Spectrometer'

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return SVCSpectralLibraryImportWidget()

    @classmethod
    def importProfiles(cls,
                       path: Union[str, Path],
                       importSettings: Optional[dict] = None,
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:

        sources = []
        if isinstance(path, str):
            sources = QgsFileWidget.splitFilePaths(path)
        elif isinstance(path, Path):
            if path.is_dir():
                for entry in os.scandir(path):
                    if entry.is_file() and rxSIGFile.match(entry.name):
                        sources.append(entry.path)
            elif path.is_file():
                sources.append(path.as_posix())

        feedback.setProgress(0)
        n_total = len(sources)
        profiles: List[QgsFeature] = []
        for i, file in enumerate(sources):
            file = Path(file)
            if file.name.endswith('.sig'):
                sig: SVCSigFile = SVCSigFile(file)
                profiles.append(sig.asFeature())
            feedback.setProgress(int((i + 1) / n_total))
        return profiles

    @classmethod
    def filter(self) -> str:

        return "SVC Signature File (*.sig);;Any file (*.*)"
