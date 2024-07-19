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

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib

from qgis.core import QgsCoordinateReferenceSystem, QgsField, QgsFields, QgsSettings
from qgis.PyQt.QtCore import NULL, QMetaType, QVariant
from qgis.PyQt.QtWidgets import QWidget

EDITOR_WIDGET_REGISTRY_KEY = 'SpectralProfile'
# EDITOR_WIDGET_REGISTRY_NAME = 'Spectral Profile'

SPECLIB_EPSG_CODE = 4326

EMPTY_VALUES = [None, NULL, QVariant(), '', 'None']

FIELD_VALUES = 'profiles'
FIELD_NAME = 'name'
FIELD_FID = 'fid'


def defaultSpeclibCrs() -> QgsCoordinateReferenceSystem:
    crs = QgsCoordinateReferenceSystem()
    assert crs.createFromString(f'EPSG:{SPECLIB_EPSG_CODE}'), f'Unable to create CRS for input "{SPECLIB_EPSG_CODE}"'
    return crs


def createStandardFields() -> QgsFields:
    from .core import create_profile_field
    fields = QgsFields()
    fields.append(create_profile_field('profiles'))
    fields.append(QgsField('name', QMetaType.QString))
    return fields


class SpectralLibrarySettingsKey:
    BACKGROUND_COLOR = 'BACKGROUND_COLOR'
    FOREGROUND_COLOR = 'FOREGROUND_COLOR'
    INFO_COLOR = 'INFO_COLOR'
    CROSSHAIR_COLOR = 'CROSSHAIR_COLOR'
    SELECTION_COLOR = 'SELECTION_COLOR'
    TEMPORARY_COLOR = 'TEMPORARY_COLOR'


def speclibSettings() -> QgsSettings:
    """
    Returns SpectralLibrary relevant QSettings
    :return: QSettings
    """
    return QgsSettings('EnMAP', 'speclib')


def speclibUiPath(name: str) -> str:
    """
    Returns the path to a spectral library *.ui file
    :param name: name
    :type name: str
    :return: absolute path to *.ui file
    :rtype: str
    """

    if isinstance(name, QWidget):
        name = name.__class__.__name__.lower() + '.ui'

    path = pathlib.Path(__file__).parent / 'ui' / name
    assert path.is_file(), f'File does not exist: {path}'
    return path.as_posix()
