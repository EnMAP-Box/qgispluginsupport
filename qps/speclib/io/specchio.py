# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/specchia.py

    Input/Output of SPECCHIO spectral library data
    ---------------------
    Beginning            : 2019-08-23
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import collections
import re
from pathlib import Path
from typing import Optional, Union, List, Dict

import numpy as np
from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsFeature, QgsField, QgsFields, QgsProcessingFeedback, QgsFeatureIterator

from .. import FIELD_NAME
from ..core.spectralprofile import (
    SpectralProfileFileReader, SpectralProfileFileWriter,
    ProfileEncoding, encodeProfileValueDict, prepareProfileValueDict, create_profile_field
)
from ...utils import findTypeFromString


class SPECCHIOReader(SpectralProfileFileReader):
    """
    File Reader for SPECCHIO spectral library files.
    See https://ecosis.org for details.
    """

    def __init__(self, path: Union[str, Path], **kwds):
        super().__init__(path, **kwds)
        self._profiles: Optional[List[Dict]] = None
        self._metadataKeys: List[str] = []
        self._numericKeys: List[str] = []

    @classmethod
    def id(cls) -> str:
        return 'specchio'

    @classmethod
    def shortHelp(cls) -> str:
        return 'SPECCHIO text file format'

    @classmethod
    def canReadFile(cls, path: Union[str, Path]) -> bool:
        path = Path(path)
        if not path.is_file():
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    values = line.split(',')
                    if len(values) < 2:
                        continue
                    if re.search(r'^\d+(\.\d+)?.+$', values[0]):
                        return True
        except Exception:
            return False
        return False

    def _readProfiles(self) -> List[Dict]:
        """
        Reads spectral profiles from the SPECCHIO file
        :return: list of profile dictionaries
        """
        if self._profiles is not None:
            return self._profiles

        profiles = []
        DATA = collections.OrderedDict()
        regNumber = re.compile(r'^\d+(\.\d+)?$')

        delimiter = ','
        with open(self.path(), 'r', encoding='utf-8') as f:
            lines = f.readlines()

            for i, line in enumerate(lines):
                line = line.strip()
                if len(line) == 0:
                    continue

                values = line.split(delimiter)
                if len(values) < 2:
                    continue

                try:
                    mdKey = values.pop(0).strip()
                    if not isinstance(mdKey, str):
                        raise AssertionError
                    if len(values) == 0:
                        continue

                    t = findTypeFromString(values[0])
                    values = [t(v) for v in values if len(v) > 0]
                    if len(values) > 0:
                        DATA[mdKey] = values
                except Exception as ex:
                    print(ex)
                    print('Line {}:{}'.format(i + 1, line))

            numericValueKeys = []
            metadataKeys = []
            for k in DATA.keys():
                if regNumber.search(k):
                    numericValueKeys.append(k)
                else:
                    metadataKeys.append(k)

            # sort by wavelength
            numericValueKeys = np.asarray(numericValueKeys, dtype=str)
            xValues = np.asarray(numericValueKeys, dtype=float)
            s = np.argsort(xValues)
            numericValueKeys = numericValueKeys[s]
            xValues = xValues[s]

            nProfiles = len(DATA[numericValueKeys[0]])

            for i in range(nProfiles):
                profile = {'y': [float(DATA[k][i]) for k in numericValueKeys]}
                profile['x'] = xValues
                profile['xUnit'] = 'nm'

                # add metadata
                profile['metadata'] = {}
                for k in metadataKeys:
                    mdValues = DATA[k]
                    if len(mdValues) > i:
                        profile['metadata'][k] = mdValues[i]

                # add name
                if FIELD_NAME in metadataKeys:
                    profile['name'] = DATA[FIELD_NAME][i]
                else:
                    profile['name'] = '{}:{}'.format(self.path().stem, i + 1)

                profiles.append(profile)

        self._profiles = profiles
        self._metadataKeys = metadataKeys
        self._numericKeys = numericValueKeys

        return profiles

    def metadataKeys(self) -> List[str]:
        self._readProfiles()
        return self._metadataKeys

    def numericKeys(self) -> List[str]:
        self._readProfiles()
        return self._numericKeys

    def asFeatures(self) -> List[QgsFeature]:
        """
        Returns the file content as QgsFeatures
        :return: list of QgsFeature
        """
        profiles = self._readProfiles()
        features = []

        pfield = create_profile_field('profile', encoding=ProfileEncoding.Text)
        fields = QgsFields()
        fields.append(QgsField(FIELD_NAME, QMetaType.Type.QString))
        fields.append(pfield)

        for metaKey in self._metadataKeys:
            if metaKey not in fields.names():
                fields.append(QgsField(metaKey, QMetaType.Type.QVariant))

        for profile in profiles:
            f = QgsFeature(fields)
            f.setAttribute(FIELD_NAME, profile.get('name', ''))

            # encode profile values
            y = profile.get('y', [])
            x = profile.get('x', list(range(len(y))))
            xUnit = profile.get('xUnit', 'nm')

            pdict = prepareProfileValueDict(x=x, y=y, xUnit=xUnit)
            profile_str = encodeProfileValueDict(pdict, encoding=ProfileEncoding.Dict)

            f.setAttribute(pfield.name(), profile_str)

            # add metadata
            for metaKey in self._metadataKeys:
                if metaKey in profile.get('metadata', {}):
                    f.setAttribute(metaKey, profile['metadata'][metaKey])

            features.append(f)

        return features


class SPECCHIOWriter(SpectralProfileFileWriter):
    """
    Writer for SPECCHIO spectral library files.
    See https://ecosis.org for details.
    """

    def __init__(self, *args, delimiter: str = ',', **kwds):
        super().__init__(*args, **kwds)
        self.mDelimiter = delimiter

    @classmethod
    def id(cls) -> str:
        return 'specchio'

    @classmethod
    def filterString(cls) -> str:
        return "SPECCHIO CSV files (*.csv);;All files (*.*)"

    def writeFeatures(
        self,
        path: Union[str, Path], features: List[QgsFeature],
        field_names=None,
        feedback: Optional[QgsProcessingFeedback] = None
    ) -> List[Path]:
        """
        Writes the features to a SPECCHIO CSV file
        :param field_names:
        :param path: path to write
        :param features: list of features to write
        :param feedback: QgsProcessingFeedback
        :return: list of written file paths
        """
        path = Path(path)

        if feedback is None:
            feedback = QgsProcessingFeedback()

        if isinstance(features, (list, tuple)) and len(features) == 0:
            feedback.pushInfo('No features to write')
            return []

        if isinstance(features, QgsFeatureIterator):
            features = list(features)

        # Get the profile field
        if len(features) == 0:
            feedback.pushInfo('No profile features found')
            return []

        profile_field_names = features[0]
        if len(profile_field_names) == 0:
            feedback.pushInfo('No profile field found')
            return []

        if field_names is None:
            field_names = profile_field_names
        else:
            for f in field_names:
                if f not in profile_field_names:
                    feedback.pushInfo(f'Profile field {f} not found')
                    return []

        writtenFiles = []

        raise NotImplementedError('todo: write SPECCHIO csv files')
        return writtenFiles
