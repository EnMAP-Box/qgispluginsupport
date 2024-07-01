from pathlib import Path
from typing import List, Union
import re

from PyQt5.QtCore import QVariant
from qgis._core import QgsField, QgsFields
from qgis.core import QgsPointXY
from qgis.core import QgsFeature, QgsProcessingFeedback
import os
from qgis.gui import QgsFileWidget
from qps.speclib.core import create_profile_field
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectrallibraryio import SpectralLibraryIO

SVC_FIELDS = QgsFields()
SVC_FIELDS.append(create_profile_field('Reference'))
SVC_FIELDS.append(create_profile_field('Target'))
SVC_FIELDS.append(QgsField('co', QVariant.String))
SVC_FIELDS.append(QgsField('instrument', QVariant.String))
SVC_FIELDS.append(QgsField('units', QVariant.String))


class SVCSigFile(object):

    def __init__(self, path: Union[str, Path]):
        path = Path(path)
        assert path.is_file()
        self.mPath = path

        self.mRADTar = None
        self.mRADRef = None
        self.mREF = None

        self.geo: QgsPointXY = None

        self.mRemoveOverlap: bool = True

        self._readSIGFile(path)

    def _readSIGFile(self, path):
        pass

    def asFeature(self) -> QgsFeature:
        f = QgsFeature(SVC_FIELDS)

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
