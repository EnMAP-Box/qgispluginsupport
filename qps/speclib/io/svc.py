import datetime
import os
import re
from pathlib import Path
from typing import List, Match, Optional, Union

import numpy as np
from qgis.core import QgsFeature, QgsField, QgsFields, QgsPointXY, QgsProcessingFeedback
from qgis.gui import QgsFileWidget

from ..core.spectrallibraryio import SpectralLibraryIO
from ..core.spectralprofile import prepareProfileValueDict, SpectralProfileFileReader
from ...qgisenums import QMETATYPE_QSTRING

# GPS Longitude  DDDmm.mmmmC
# GPS Latitude  DDmm.mmmmC
# GPS Time  HHmmSS.SSS

rxGPSLongitude = re.compile(r'(?P<deg>\d{3})(?P<min>\d{2}.\d+)(?P<quad>[EW])')
rxGPSLatitude = re.compile(r'(?P<deg>\d{2})(?P<min>\d{2}.\d+)(?P<quad>[NS])')


def match_to_coordinate(matchLat: Match, matchLon: Match) -> QgsPointXY:
    y = float(matchLat.group('deg')) + float(matchLat.group('min')) / 60
    x = float(matchLon.group('deg')) + float(matchLon.group('min')) / 60

    if matchLon.group('quad') == 'W':
        y *= -1

    if matchLat.group('quad') == 'S':
        x *= -1

    return QgsPointXY(x, y)


class SVCSigFile(SpectralProfileFileReader):
    KEY_Picture = 'picture'

    def __init__(self, path: Union[str, Path]):
        super().__init__(path)

        self.mRemoveOverlap: bool = True
        self.mPicture: Optional[Path] = None
        self._readSIGFile(path)

    def picturePath(self) -> Path:
        return self.mPicture

    def standardFields(self) -> QgsFields:

        fields = super().standardFields()

        pictureField = QgsField(self.KEY_Picture, type=QMETATYPE_QSTRING)

        # setup attachment widget

        # setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
        # field.setEditorWidgetSetup(setup)

        fields.append(pictureField)
        return fields

    def asMap(self) -> dict:

        data = super().asMap()
        if isinstance(self.mPicture, Path):
            data[self.KEY_Picture] = self.mPicture.as_posix()
        return data

    def _readSIGFile(self, path):
        path: Path = Path(path)
        with open(path) as f:
            lines = f.read()
            lines = re.sub('/[*]{3}.*[*]{3}/', '', lines)

            # find regular - one-line tags
            for match in re.finditer(r'^(?P<tag>[^=]+)=(?P<val>.*)', lines, re.M):
                tag = match.group('tag').strip()
                val = match.group('val').strip()
                self.mMetadata[tag] = val

            # find data
            match = re.search(r'^data=\n(?P<data>.*)', lines.strip(), re.M | re.DOTALL)
            data = match.group('data').strip()
            dataLines = data.split('\n')
            nRows = len(dataLines)
            data = data.split()
            nCols = int(len(data) / nRows)
            data = np.asarray([float(d) for d in data]).reshape((nRows, nCols))
            wl = data[:, 0]

            # get profiles
            self.mReference = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 1])
            if nCols > 2:
                self.mTarget = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 2])
            if nCols > 3:
                self.mReflectance = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 3], yUnit='%')

            rx_coord_parts = re.compile(r'(?P<deg>\d{2})(?P<min>(\d|\.)+)(?P<direction>[ENSW])')
            # get coordinates
            if 'longitude' in self.mMetadata:
                longitudes = rxGPSLongitude.finditer(self.mMetadata['longitude'])
                latitudes = rxGPSLatitude.finditer(self.mMetadata['latitude'])
                coordinates = [match_to_coordinate(lat, lon) for lon, lat in zip(longitudes, latitudes)]

                if len(coordinates) == 2:
                    self.mReferenceCoordinate = coordinates[0]
                    self.mTargetCoordinate = coordinates[1]
                elif len(coordinates) == 1:
                    self.mTargetCoordinate = coordinates[0]

            if 'time' in self.mMetadata:
                t1, t2 = self.mMetadata['time'].split(',')
                self.mReferenceTime = datetime.datetime.strptime(t1.strip(), '%d/%m/%Y %H:%M:%S%p')
                self.mTargetTime = datetime.datetime.strptime(t2.strip(), '%d/%m/%Y %H:%M:%S%p')

            for ext in ['.jpg', '.png']:
                path_img = path.parent / (path.name + ext)
                if path_img.is_file():
                    self.mPicture = path_img
                    break


RX_SIG_FILE = re.compile(r'\.sig$')


class SVCSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def formatName(self) -> str:
        return 'SVC'

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

        return "Spectra Vista Corporation (SVC) Signature File (*.sig);;Any file (*.*)"
