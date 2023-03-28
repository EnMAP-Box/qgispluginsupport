# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/csvdata.py

    Input/Output of spectral library data from/to CSV files.
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
import json

from qgis.core import QgsVectorFileWriter
from .. import FIELD_VALUES

# max size a CSV file can have, in MBytes
MAX_CSV_SIZE = 5


class CSVWriterFieldValueConverter(QgsVectorFileWriter.FieldValueConverter):
    """
    A QgsVectorFileWriter.FieldValueConverter to converts SpectralLibrary values into strings
    """

    def __init__(self, speclib):
        super(CSVWriterFieldValueConverter, self).__init__()
        self.mSpeclib = speclib
        self.mNames = self.mSpeclib.fields().names()
        self.mCharactersToReplace = '\t'
        self.mReplacement = ' '

    def setSeparatorCharactersToReplace(self, charactersToReplace, replacement: str = ' '):
        """
        Specifies characters that need to be masked in string, i.e. the separator, to not violate the CSV structure.
        :param charactersToReplace: str | list of strings
        :param replacement: str, Tabulator by default
        """
        if isinstance(charactersToReplace, str):
            charactersToReplace = [charactersToReplace]
        assert replacement not in charactersToReplace
        self.mCharactersToReplace = charactersToReplace
        self.mReplacement = replacement

    def clone(self):
        c = CSVWriterFieldValueConverter(self.mSpeclib)
        c.setSeparatorCharactersToReplace(self.mCharactersToReplace, replacement=self.mReplacement)
        return c

    def convert(self, i, value):
        name = self.mNames[i]
        if name.startswith(FIELD_VALUES):
            return json.loads(value)
        else:
            v = str(value)
            for c in self.mCharactersToReplace:
                v = v.replace(c, self.mReplacement)
            return v

    def fieldDefinition(self, field):
        return field
