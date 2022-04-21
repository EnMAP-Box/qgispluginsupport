# -*- coding: utf-8 -*-

"""
***************************************************************************
    deploy.py
    Script to deploy a QGIS Python Plugin
    ---------------------
    Date                 : August 2017
    Copyright            : (C) 2017 by Benjamin Jakimow
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
import os.path
import pathlib
import re
import typing
from os import getenv
import platform
from qgis.PyQt.QtCore import QStandardPaths, QSettings
from qgis.core import QgsApplication

from qgis.core import QgsUserProfileManager


def userProfileManager() -> QgsUserProfileManager:
    globalsettingsfile = None
    configLocalStorageLocation = None

    if globalsettingsfile is None:
        globalsettingsfile: str = getenv("QGIS_GLOBAL_SETTINGS_FILE")

    if globalsettingsfile is None:
        startupPaths = QStandardPaths.locateAll(QStandardPaths.AppDataLocation, "qgis_global_settings.ini")
        if startupPaths:
            globalsettingsfile = startupPaths[0]

    if globalsettingsfile is None:
        default_globalsettingsfile = QgsApplication.resolvePkgPath() + "/resources/qgis_global_settings.ini"
        if os.path.isfile(default_globalsettingsfile):
            globalsettingsfile = default_globalsettingsfile

    if configLocalStorageLocation is None:
        if globalsettingsfile is not None:
            globalSettings = QSettings(globalsettingsfile, QSettings.IniFormat)
            if globalSettings.contains("core/profilesPath"):
                configLocalStorageLocation = globalSettings.value("core/profilesPath", "")

    if configLocalStorageLocation is None:
        home = pathlib.Path('~').expanduser()
        basePath = None
        if platform.system() == 'Windows':
            basePath = home / 'AppData/Roaming/QGIS/QGIS3'

        if basePath is None:
            raise NotImplementedError(f'No QGIS basePath for {platform.system()}')

        configLocalStorageLocation = basePath.as_posix()

    rootProfileFolder = QgsUserProfileManager.resolveProfilesFolder(configLocalStorageLocation)
    return QgsUserProfileManager(rootProfileFolder)


class QGISMetadataFileWriter(object):
    """
    A class to store and write the QGIS plugin metadata.txt
    For details see:
    https://docs.qgis.org/3.16/en/docs/pyqgis_developer_cookbook/plugins/plugins.html#plugin-metadata-table
    """

    def __init__(self):
        self.mName = ''
        self.mDescription = ''
        self.mVersion = ''
        self.mQgisMinimumVersion = '3.8'
        self.mQgisMaximumVersion = '3.99'
        self.mAuthor = ''
        self.mAbout = ''
        self.mEmail = ''
        self.mHomepage = ''
        self.mIcon = ''
        self.mTracker = ''
        self.mRepository = ''
        self.mIsExperimental = ''
        self.mHasProcessingProvider: bool = False
        self.mTags: typing.List[str] = []
        self.mCategory: str = ''
        self.mChangelog: str = ''
        self.mPlugin_dependencies: typing.List[str] = []

    def validate(self) -> bool:
        return True

    def formatTag(self, tag: str, value, sep: str = ', '):
        s = f'{tag}='
        if isinstance(value, list):
            s += f'{sep}'.join(value)
        else:
            s += f'{value}'
        return s

    def metadataString(self) -> str:
        assert self.validate()

        lines = ['[general]']
        lines.append(self.formatTag('name', self.mName))
        lines.append(self.formatTag('author', self.mAuthor))
        if self.mEmail:
            lines.append(self.formatTag('email', self.mEmail))

        lines.append(self.formatTag('description', self.mDescription))
        lines.append(self.formatTag('version', self.mVersion))

        lines.append(self.formatTag('qgisMinimumVersion', self.mQgisMinimumVersion))
        lines.append(self.formatTag('qgisMaximumVersion', self.mQgisMaximumVersion))
        lines.append(self.formatTag('about', re.sub('\n', '', self.mAbout)))

        lines.append(self.formatTag('icon', self.mIcon))
        lines.append(self.formatTag('tags', self.mTags))
        lines.append(self.formatTag('category', self.mRepository))

        if self.mHasProcessingProvider:
            lines.append('hasProcessingProvider=yes')
        else:
            lines.append('hasProcessingProvider=no')
        lines.append(self.formatTag('homepage', self.mHomepage))

        if self.mTracker:
            lines.append(self.formatTag('tracker', self.mTracker))

        if self.mRepository:
            lines.append(self.formatTag('repository', self.mRepository))

        if isinstance(self.mIsExperimental, bool):
            lines.append(self.formatTag('experimental', self.mIsExperimental))

        if len(self.mPlugin_dependencies) > 0:
            lines.append(self.formatTag('plugin_dependencies', self.mPlugin_dependencies))
        # lines.append('deprecated={}'.format(self.mIsDeprecated))
        lines.append('')
        lines.append(self.formatTag('changelog', self.mChangelog))

        return '\n'.join(lines)

    """
    [general]
    name=dummy
    description=dummy
    version=dummy
    qgisMinimumVersion=dummy
    qgisMaximumVersion=dummy
    author=dummy
    about=dummy
    email=dummy
    icon=dummy
    homepage=dummy
    tracker=dummy
    repository=dummy
    experimental=False
    deprecated=False
    tags=remote sensing, raster, time series, data cube, landsat, sentinel
    category=Raster
    """

    def writeMetadataTxt(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.metadataString())
