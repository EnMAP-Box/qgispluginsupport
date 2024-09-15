import os
import re
from pathlib import Path
from typing import List, Match, Optional, Union

import numpy as np

from qgis.core import QgsFeature, QgsField, QgsFields, QgsGeometry, QgsPointXY, QgsProcessingFeedback
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QVariant
from ..core import create_profile_field
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectrallibraryio import SpectralLibraryIO
from ..core.spectralprofile import AbstractSpectralProfileFile, prepareProfileValueDict, ProfileEncoding

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


class SVCSigFile(AbstractSpectralProfileFile):
    SVC_FIELDS = QgsFields()
    SVC_FIELDS.append(create_profile_field('reference', encoding=ProfileEncoding.Dict))
    SVC_FIELDS.append(create_profile_field('target', encoding=ProfileEncoding.Dict))
    SVC_FIELDS.append(create_profile_field('reflectance', encoding=ProfileEncoding.Dict))
    SVC_FIELDS.append(QgsField('timeR', QVariant.DateTime))
    SVC_FIELDS.append(QgsField('timeT', QVariant.DateTime))
    SVC_FIELDS.append(QgsField('json_data', QVariant.Map))

    def __init__(self, path: Union[str, Path]):
        super().__init__(path)

        self.profileT = None
        self.profileR = None
        self.profileRefl = None
        self.mRADRef = None
        self.mREF = None
        self.data: dict = {}
        self.coordT: Optional[QgsPointXY] = None
        self.coordR: Optional[QgsPointXY] = None
        self.mRemoveOverlap: bool = True

        self._readSIGFile(path)

    def _readSIGFile(self, path):
        with open(path) as f:
            lines = f.read()
            lines = re.sub('/[*]{3}.*[*]{3}/', '', lines)

            # find regular - one-line tags
            for match in re.finditer(r'^(?P<tag>[^=]+)=(?P<val>.*)', lines, re.M):
                tag = match.group('tag').strip()
                val = match.group('val').strip()
                self.data[tag] = val

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
            self.profileR = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 1])
            if nCols > 2:
                self.profileT = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 2])
            if nCols > 3:
                self.profileRefl = prepareProfileValueDict(x=wl, xUnit='nm', y=data[:, 3], yUnit='%')

            rx_coord_parts = re.compile(r'(?P<deg>\d{2})(?P<min>(\d|\.)+)(?P<direction>[ENSW])')
            # get coordinates
            if 'longitude' in self.data:
                longitudes = rxGPSLongitude.finditer(self.data['longitude'])
                latitudes = rxGPSLatitude.finditer(self.data['latitude'])
                coordinates = [match_to_coordinate(lat, lon) for lon, lat in zip(longitudes, latitudes)]

                if len(coordinates) == 2:
                    self.coordR = coordinates[0]
                    self.coordT = coordinates[1]
                elif len(coordinates) == 1:
                    self.coordT = coordinates[0]

    def asMap(self) -> dict:
        attributes = {'json_data': self.data}

        if self.profileR:
            attributes['reference'] = self.profileR

        if self.profileT:
            attributes['target'] = self.profileT

        if self.profileRefl:
            attributes['reflectance'] = self.profileR

        return attributes

    def asFeature(self) -> QgsFeature:

        f = QgsFeature(self.SVC_FIELDS)
        attributes = self.asMap()
        SpectralLibraryUtils.setAttributeMap(f, attributes)

        if self.coordT:
            f.setGeometry(QgsGeometry.fromPointXY(self.coordT))
        elif self.coordR:
            f.setGeometry(QgsGeometry.fromPointXY(self.coordT))

        return f


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

        # expected_fields = importSettings.get()

        rxCSV = re.compile(r'.*\.(csv|txt)$')
        feedback.setProgress(0)
        n_total = len(sources)
        profiles: List[QgsFeature] = []
        for i, file in enumerate(sources):
            file = Path(file)

            if rxCSV.search(file.name):
                pass
                # profiles.extend(ASDSpectralLibraryIO.readCSVFile(file))
            else:
                sig: SVCSigFile = SVCSigFile(file)
                profiles.append(sig.asFeature())
            feedback.setProgress(int((i + 1) / n_total))
        return profiles
