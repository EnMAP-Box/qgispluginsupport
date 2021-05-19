# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/__init__.py

    A python module to handle and visualize SpectralLibraries in QGIS
    ---------------------
    Beginning            : 2018-12-17
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import enum
import pathlib

from qgis.core import QgsSettings, QgsCoordinateReferenceSystem, QgsField, QgsFields
from qgis.PyQt.QtCore import NULL, QVariant
from osgeo import ogr
EDITOR_WIDGET_REGISTRY_KEY = 'SpectralProfile'

SPECLIB_EPSG_CODE = 4326
SPECLIB_CRS = QgsCoordinateReferenceSystem('EPSG:{}'.format(SPECLIB_EPSG_CODE))

EMPTY_VALUES = [None, NULL, QVariant(), '', 'None']

FIELD_VALUES = 'profiles'
FIELD_NAME = 'name'
FIELD_FID = 'fid'


def ogrStandardFields() -> list:
    """Returns the minimum set of fields a Spectral Library should contains"""
    fields = [
        ogr.FieldDefn(FIELD_FID, ogr.OFTInteger),
        ogr.FieldDefn(FIELD_NAME, ogr.OFTString),
        ogr.FieldDefn('source', ogr.OFTString),
        ogr.FieldDefn(FIELD_VALUES, ogr.OFTBinary),
    ]
    return fields


def createStandardFields() -> QgsFields:
    fields = QgsFields()
    for f in ogrStandardFields():
        assert isinstance(f, ogr.FieldDefn)
        name = f.GetName()
        ogrType = f.GetType()
        if ogrType == ogr.OFTString:
            a, b = QVariant.String, 'varchar'
        elif ogrType in [ogr.OFTInteger, ogr.OFTInteger64]:
            a, b = QVariant.Int, 'int'
        elif ogrType in [ogr.OFTReal]:
            a, b = QVariant.Double, 'double'
        elif ogrType in [ogr.OFTBinary]:
            a, b = QVariant.ByteArray, 'Binary'
        else:
            raise NotImplementedError()

        fields.append(QgsField(name, a, b))

    return fields


class SpectralLibrarySettingsKey:
    BACKGROUND_COLOR = 'BACKGROUND_COLOR'
    FOREGROUND_COLOR = 'FOREGROUND_COLOR'
    INFO_COLOR = 'INFO_COLOR'
    CROSSHAIR_COLOR= 'CROSSHAIR_COLOR'
    SELECTION_COLOR = 'SELECTION_COLOR'
    TEMPORARY_COLOR = 'TEMPORARY_COLOR'

def speclibSettings() -> QgsSettings:
    """
    Returns SpectralLibrary relevant QSettings
    :return: QSettings
    """
    return QgsSettings('HUB', 'speclib')


try:
    from ..speclib.io.envi import EnviSpectralLibraryIO
except:
    pass


def speclibUiPath(name: str) -> str:
    """
    Returns the path to a spectral library *.ui file
    :param name: name
    :type name: str
    :return: absolute path to *.ui file
    :rtype: str
    """
    path = pathlib.Path(__file__).parent / 'ui' / name
    assert path.is_file(), f'File does not exist: {path}'
    return path.as_posix()