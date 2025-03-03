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
import os
import collections
import re
import sys
import io

from qgis.core import QgsVectorLayer, QgsFeature
from qgis.core import QgsProcessingFeedback
import numpy as np
from qgis.PyQt.QtWidgets import QMenu, QFileDialog
from ..core import is_spectral_library
from ..core.spectrallibrary import SpectralSetting, SpectralLibraryUtils
from ..core.spectrallibraryio import SpectralLibraryIO
from .. import FIELD_VALUES, FIELD_NAME, FIELD_FID, createStandardFields
from ...utils import findTypeFromString, createQgsField


class SPECCHIOSpectralLibraryIO(SpectralLibraryIO):
    """
    I/O Interface for the SPECCHIO spectral library .
    See https://ecosis.org for details.
    """

    @classmethod
    def canRead(cls, path) -> bool:
        """
        Returns true if it can read the source defined by path
        :param path: source uri
        :return: True, if source is readable.
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if re.search(r'^\d+(\.\d+)?.+', line):
                        return True
        except Exception as ex:
            return False
        return False

    @classmethod
    def readFrom(cls, path: str,
                 wlu='nm',
                 delimiter=',',
                 feedback: QgsProcessingFeedback = None):
        """
         Returns the SpectralLibrary read from "path"
        :param path:
        :type path:
        :param wlu:
        :type wlu:
        :param delimiter:
        :type delimiter:
        :param feedback:
        :type feedback:
        :return:
        :rtype:
        """
        sl = SpectralLibraryUtils.createSpectralLibrary()
        sl.startEditing()
        sl.addMissingFields(createStandardFields())
        sl.commitChanges(stopEditing=False)
        bn = os.path.basename(path)
        delimiter = ','
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            DATA = collections.OrderedDict()
            regNumber = re.compile(r'^\d+(\.\d+)?$')
            nProfiles = 0
            for i, line in enumerate(lines):

                assert isinstance(line, str)
                line = line.strip()
                if len(line) == 0:
                    continue

                values = line.split(delimiter)
                if len(values) < 2:
                    continue

                try:
                    mdKey = values.pop(0).strip()
                    assert isinstance(mdKey, str)
                    if len(values) == 0:
                        continue

                    t = findTypeFromString(values[0])
                    values = [t(v) for v in values if len(v) > 0]
                    if len(values) > 0:
                        DATA[mdKey] = values
                    else:
                        s = ""
                except Exception as ex:
                    print(ex, file=sys.stderr)
                    print('Line {}:{}'.format(i + 1, line), file=sys.stderr)

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

            sl.beginEditCommand('Set metadata columns')
            for k in metadataKeys:
                if k in sl.fields().names():
                    continue

                qgsField = createQgsField(k, DATA[k][0])
                assert sl.addAttribute(qgsField)

            sl.endEditCommand()
            sl.commitChanges(stopEditing=False)

            profiles = []
            for i in range(nProfiles):
                profile = QgsFeature(fields=sl.fields())
                # add profile name
                if FIELD_NAME in metadataKeys:
                    profile.setAttribute(FIELD_NAME, DATA[FIELD_NAME][i])
                else:
                    profile.setAttribute(FIELD_NAME, '{}:{}'.format(bn, i + 1))

                # add profile values
                yValues = [float(DATA[k][i]) for k in numericValueKeys]
                profile.setValues(x=xValues, y=yValues, xUnit=wlu)

                # add profile metadata
                for k in metadataKeys:
                    mdValues = DATA[k]
                    if len(mdValues) > i:
                        profile.setAttribute(k, mdValues[i])

                profiles.append(profile)

            sl.addProfiles(profiles, addMissingFields=True)
        sl.commitChanges()
        return sl

    @classmethod
    def write(cls, speclib: QgsVectorLayer, path: str, feedback: QgsProcessingFeedback = None,
              delimiter: str = ',') -> list:
        """
        Writes the SpectralLibrary to path and returns a list of written files
        that can be used to open the spectral library with readFrom(...)
        :param speclib: SpectralLibrary
        :param path: str, path to library source
        :return: [str-list-of-written-files]
        """
        assert is_spectral_library(speclib)
        basePath, ext = os.path.splitext(path)

        writtenFiles = []
        # fieldNames = [n for n in speclib.fields().names() if n not in [FIELD_VALUES, FIELD_FID]]
        groups = speclib.groupBySpectralProperties()
        for i, setting in enumerate(groups.keys()):
            # in-memory text buffer
            setting: SpectralSetting
            stream = io.StringIO()
            xValues, _, _ = setting.x(), setting.xUnit(), setting.yUnit()
            profiles = groups[setting]
            if i == 0:
                path = basePath + ext
            else:
                path = basePath + '{}{}'.format(i + 1, ext)

            # write metadata
            for fn in speclib.fields().names():
                assert isinstance(fn, str)
                if fn in [FIELD_FID, FIELD_VALUES]:
                    continue
                line = [fn]
                for p in profiles:
                    assert isinstance(p, QgsFeature)
                    line.append(str(p.attribute(fn)))
                stream.write(delimiter.join(line) + '\n')
            #
            line = ['wavelength unit']
            for p in profiles:
                line.append(str(p.xUnit()))
            stream.write(delimiter.join(line) + '\n')

            # write values
            for i, xValue in enumerate(xValues):
                line = [str(xValue)]
                for p in profiles:
                    assert isinstance(p, QgsFeature)
                    yValue = p.values()['y'][i]
                    line.append(str(yValue))
                stream.write(delimiter.join(line) + '\n')

            lines = stream.getvalue().replace('\r', '')

            with open(path, 'w', encoding='utf-8') as f:
                f.write(lines)
                writtenFiles.append(path)

        return writtenFiles

    @classmethod
    def addExportActions(cls, spectralLibrary: QgsVectorLayer, menu: QMenu) -> list:

        def write(speclib: QgsVectorLayer):
            path, filter = QFileDialog.getSaveFileName(caption='Write SPECCHIO CSV Spectral Library ',
                                                       filter='Textfile (*.csv)')
            if isinstance(path, str) and len(path) > 0:
                SPECCHIOSpectralLibraryIO.write(spectralLibrary, path)

        m = menu.addAction('SPECCHIO')
        m.setToolTip('Exports the profiles into the SPECCIO text file format.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: write(sl))

    @classmethod
    def addImportActions(cls, spectralLibrary: QgsVectorLayer, menu: QMenu) -> list:

        def read(speclib: QgsVectorLayer):

            path, filter = QFileDialog.getOpenFileName(caption='Read SPECCHIO CSV File',
                                                       filter='All type (*.*);;Text files (*.txt);; CSV (*.csv)')
            if os.path.isfile(path):

                sl = SPECCHIOSpectralLibraryIO.readFrom(path)
                if is_spectral_library(sl):
                    speclib.startEditing()
                    speclib.beginEditCommand('Add profiles from {}'.format(path))
                    speclib.addSpeclib(sl, True)
                    speclib.endEditCommand()
                    speclib.commitChanges()

        m = menu.addAction('SPECCHIO')
        m.setToolTip('Adds profiles stored in an SPECCHIO csv text file.')
        m.triggered.connect(lambda *args, sl=spectralLibrary: read(sl))
