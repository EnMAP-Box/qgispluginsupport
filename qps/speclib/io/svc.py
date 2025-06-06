import datetime
import os
import re
import typing
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

rxGPSLongitude = re.compile(r'(?P<deg>\d{3})(?P<min>\d{2}.\d+)(?P<quad>[EW])')
rxGPSLatitude = re.compile(r'(?P<deg>\d{2})(?P<min>\d{2}.\d+)(?P<quad>[NS])')

rxGPSTime = re.compile(r'(?P<hh>\d{2})(?P<mm>\d{2})(?P<sec>\d{2}(\.\d+)?)')


def toQDateTime(value) -> QDateTime:
    if isinstance(value, str):
        return QDateTime.fromString(value, Qt.ISODate)
    elif isinstance(value, datetime.datetime):
        return QDateTime.fromString(value.isoformat(), Qt.ISODate)
    raise NotImplementedError()


def gpsTime(date: datetime.datetime, gpstime_string: str) -> datetime.datetime:
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


rx_decimal_sep = re.compile(r'integration= \d+([,.])\d+')

rx_sig_file = re.compile(r'\.sig$')


class SVCSigFile(SpectralProfileFileReader):

    def __init__(self, path: Union[str, Path]):
        super().__init__(path)

        self.mRemoveOverlap: bool = True
        self.mPicture: Optional[Path] = None
        self.mGpsTimeR: Optional[datetime.datetime] = None
        self.mGpsTimeT: Optional[datetime.datetime] = None
        self._readSIGFile(path)

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

    @classmethod
    def _readDateTime(cls, text: str) -> datetime.datetime:
        text = text.strip()

        # test for ISO
        try:
            dtg = datetime.datetime.fromisoformat(text)
            return dtg
        except ValueError as ex:
            s = ""

        # test non-ISO formats
        formats = [
            '%m/%d/%Y %H:%M:%S%p',  # 5/27/2025 9:39:32AM
            '%m/%d/%Y %H:%M:%S %p',  # 5/27/2025 9:39:32 AM
            '%m/%d/%Y %H:%M:%S',  # 5/27/2025 9:39:32
            '%d.%m.%Y %H:%M:%S',  # 27.05.2025 09:39:32
        ]

        for fmt in formats:
            try:
                dtg = datetime.datetime.strptime(text, fmt)
                return dtg
            except ValueError:
                s = ""
                pass

        raise Exception(f'Unable to extract datetime from {text}')

    def _readSIGFile(self, path):
        path: Path = Path(path)
        with open(path) as f:
            lines = f.read()

            decimal_separator = '.'

            match_decimal_sep = rx_decimal_sep.search(lines)
            if isinstance(match_decimal_sep, typing.Match):
                decimal_separator = match_decimal_sep.group(1)

            lines = re.sub('/[*]{3}.*[*]{3}/', '', lines)

            # find regular - one-line tags
            for match in re.finditer(r'^(?P<tag>[^=]+)=(?P<val>.*)', lines, re.M):
                tag = match.group('tag').strip()
                val = match.group('val').strip()
                self.mMetadata[tag] = val

            # find data
            match = re.search(r'^data=(?P<data>.*)', lines.strip(), re.M | re.DOTALL)
            data = match.group('data').strip()
            data = data.replace(decimal_separator, '.')
            dataLines = data.split('\n')
            nRows = len(dataLines)
            data = data.split()
            nCols = int(len(data) / nRows)
            data = np.asarray([float(d) for d in data]).reshape((nRows, nCols))
            wl = data[:, 0]
            if np.all(wl == 0):
                wl = None  # no wl defined. use band numbers only
            # get profiles
            self.mReference = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 1])
            if nCols > 2:
                self.mTarget = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 2])
            if nCols > 3:
                self.mReflectance = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 3], yUnit='%')

            rx_coord_parts = re.compile(r'(?P<deg>\d{2})(?P<min>(\d|\.)+)(?P<direction>[ENSW])')

            if 'integration' in self.mMetadata:
                s = ""

            # get coordinates
            if 'longitude' in self.mMetadata:
                longitudes = rxGPSLongitude.finditer(self.mMetadata['longitude'])
                latitudes = rxGPSLatitude.finditer(self.mMetadata['latitude'])
                coordinates = [match_to_coordinate(lon, lat) for lon, lat in zip(longitudes, latitudes)]

                if len(coordinates) == 2:
                    self.mReferenceCoordinate = coordinates[0]
                    self.mTargetCoordinate = coordinates[1]
                elif len(coordinates) == 1:
                    self.mTargetCoordinate = coordinates[0]

            if 'time' in self.mMetadata:
                t1, t2 = self.mMetadata['time'].split(',')
                self.mReferenceTime = self._readDateTime(t1)
                self.mTargetTime = self._readDateTime(t2)

            if 'gpstime' in self.mMetadata:
                gpsR, gpsT = [t.strip() for t in self.mMetadata['gpstime'].split(',')]

                self.mGpsTimeR = gpsTime(self.mReferenceTime, gpsR)
                self.mGpsTimeT = gpsTime(self.mTargetTime, gpsT)

                s = ""
                # HHMMSS.SSS
                # gps1 = datetime.datetime.strptime(gps1.strip(), '%H%M%S.%f')
                # gps2 = datetime.datetime.strptime(gps2.strip(), '%H%H%S.%f')

                # g = datetime.datetime(year=1980, month=1, day=1)
                # gt1, gt2 = g + timedelta(seconds=gps1), g + timedelta(seconds=gps2)

            stem = re.sub(r'_moc$', '', path.stem)

            for ext in ['.jpg', '.png']:
                path_img = path.parent / f'{stem}.sig{ext}'
                if path_img.is_file():
                    self.mPicture = path_img
                    break


RX_SIG_FILE = re.compile(r'\.sig$')


class SVCSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(SVCSpectralLibraryImportWidget, self).__init__(*args, **kwds)

        self.mSource: QgsVectorLayer = None

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
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:

        if isinstance(path, str):
            sources = QgsFileWidget.splitFilePaths(path)
        elif isinstance(path, Path):
            sources = []
            if path.is_dir():
                for entry in os.scandir(path):
                    if entry.is_file() and RX_SIG_FILE.match(entry.name):
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
