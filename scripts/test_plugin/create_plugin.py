# -*- coding: utf-8 -*-

"""
***************************************************************************
    create_plugin.py
    Script to build qgispluginsupport as QGIS plugin. Basically just for testing
    ---------------------
    Date                 : Nov 2024
    Copyright            : (C) 2024 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.
                 *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming

import argparse
import datetime
import os
import pathlib
import re
import shutil
import site
import textwrap
from pathlib import Path
from typing import Iterator, Optional, Union

import markdown

from qps.make.deploy import QGISMetadataFileWriter, userProfileManager
from qps.utils import zipdir
from qgis.core import QgsUserProfile, QgsUserProfileManager

site.addsitedir(pathlib.Path(__file__).parents[2])
from qps import DIR_QPS

DIR_TEST_PLUGIN = Path(__file__).parent
DIR_REPO = DIR_QPS.parent
print('DIR_REPO={}'.format(DIR_REPO))

########## Config Section

MD = QGISMetadataFileWriter()
MD.mName = 'qgispluginsupport'
MD.mDescription = 'just testing. if this has been released to the QGIS plugin support is has been a failure!'
MD.mTags = ['remote sensing', 'raster', 'time series', 'landsat', 'sentinel']
MD.mCategory = 'Analysis'
MD.mAuthor = 'Benjamin Jakimow'
MD.mIcon = ''
MD.mHomepage = 'no homepage'
MD.mAbout = ''
MD.mTracker = 'qps tracker'
MD.mRepository = 'pqs repo'
MD.mQgisMinimumVersion = '3.34'
MD.mEmail = 'benjamin.jakimow@geo.hu-berlin.de'
MD.mIsExperimental = True


########## End of config section


def scantree(path, pattern=re.compile(r'.$')) -> Iterator[pathlib.Path]:
    """
    Recursively returns file paths in directory
    :param path: root directory to search in
    :param pattern: str with required file ending, e.g. ".py" to search for *.py files
    :return: pathlib.Path
    """
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path, pattern=pattern)
        elif entry.is_file and pattern.search(entry.path):
            yield pathlib.Path(entry.path)


def create_plugin(create_zip: bool = True,
                  copy_to_profile: bool = False,
                  build_name: str = None) -> Optional[pathlib.Path]:
    assert (DIR_REPO / '.git').is_dir()

    # BUILD_NAME = '{}.{}.{}'.format(__version__, timestamp, currentBranch)
    # BUILD_NAME = re.sub(r'[:-]', '', BUILD_NAME)
    # BUILD_NAME = re.sub(r'[\\/]', '_', BUILD_NAME)
    # PLUGIN_DIR = DIR_DEPLOY / 'timeseriesviewerplugin'

    DIR_DEPLOY_LOCAL = DIR_REPO / 'deploy'

    if build_name is None:
        dtg = datetime.datetime.now()
        BUILD_NAME = re.sub(r'[- :]', '_', f'qps_{dtg}')
    else:
        BUILD_NAME = build_name

    PLUGIN_DIR = DIR_DEPLOY_LOCAL / 'qgispluginsupport'
    PLUGIN_ZIP = DIR_DEPLOY_LOCAL / 'qgispluginsupport.{}.zip'.format(BUILD_NAME)

    if PLUGIN_DIR.is_dir():
        shutil.rmtree(PLUGIN_DIR)
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    PATH_METADATAFILE = PLUGIN_DIR / 'metadata.txt'
    MD.mVersion = BUILD_NAME
    MD.mAbout = 'nothing to report here'
    MD.writeMetadataTxt(PATH_METADATAFILE)

    # 1. (re)-compile all resource files

    # copy python and other resource files
    pattern = re.compile(r'\.(py|svg|png|txt|ui|tif|qml|md|js|css|json)$')
    files = list(scantree(DIR_REPO / 'qps', pattern=pattern))

    for fileSrc in files:
        assert fileSrc.is_file()
        fileDst = PLUGIN_DIR / fileSrc.relative_to(DIR_REPO)
        os.makedirs(fileDst.parent, exist_ok=True)
        shutil.copy(fileSrc, fileDst.parent)

    # copy __init__
    shutil.copy(DIR_TEST_PLUGIN / '__init__.py', PLUGIN_DIR / '__init__.py')
    # update metadata version

    f = open(DIR_REPO / 'qps' / '__init__.py')
    lines = f.read()
    f.close()
    # lines = re.sub(r'(__version__\W*=\W*)([^\n]+)', r'__version__ = "{}"\n'.format(BUILD_NAME), lines)
    f = open(PLUGIN_DIR / 'qps' / '__init__.py', 'w')
    f.write(lines)
    f.flush()
    f.close()

    # Copy to other deploy directory
    if copy_to_profile:
        profileManager: QgsUserProfileManager = userProfileManager()
        assert len(profileManager.allProfiles()) > 0
        if isinstance(copy_to_profile, str):
            profileName = copy_to_profile
        else:
            profileName = profileManager.lastProfileName()
        assert profileManager.profileExists(profileName), \
            f'QGIS profiles "{profileName}" does not exist in {profileManager.allProfiles()}'

        profileManager.setActiveUserProfile(profileName)
        profile: QgsUserProfile = profileManager.userProfile()

        DIR_QGIS_USERPROFILE = pathlib.Path(profile.folder())
        if DIR_QGIS_USERPROFILE:
            os.makedirs(DIR_QGIS_USERPROFILE, exist_ok=True)
            if not DIR_QGIS_USERPROFILE.is_dir():
                raise f'QGIS profile directory "{profile.name()}" does not exists: {DIR_QGIS_USERPROFILE}'

            QGIS_PROFILE_DEPLOY = DIR_QGIS_USERPROFILE / 'python' / 'plugins' / PLUGIN_DIR.name
            # just in case the <profile>/python/plugins folder has not been created before
            os.makedirs(DIR_QGIS_USERPROFILE.parent, exist_ok=True)
            if QGIS_PROFILE_DEPLOY.is_dir():
                print(f'Copy plugin to {QGIS_PROFILE_DEPLOY}...')
                shutil.rmtree(QGIS_PROFILE_DEPLOY)
            shutil.copytree(PLUGIN_DIR, QGIS_PROFILE_DEPLOY)

    # 5. create a zip
    # Create a zip
    if create_zip:
        print('Create zipfile...')
        zipdir(PLUGIN_DIR, PLUGIN_ZIP)

        # 7. install the zip file into the local QGIS instance. You will need to restart QGIS!

    print('Finished')
    return PLUGIN_ZIP.as_posix()


def markdown2html(path: Union[str, pathlib.Path]) -> str:
    path_md = pathlib.Path(path)
    with open(path_md, 'r', encoding='utf-8') as f:
        md = f.read()
    return markdown.markdown(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create QPS Test Plugin')

    parser.add_argument('-b', '--build-name',
                        required=False,
                        default=None,
                        help=textwrap.dedent("""
                            The build name in "timeseriesviewerplugin.<build name>.zip"
                            Defaults:
                                <version> in case of a release.* branch
                                <version>.<timestamp>.<branch name> in case of any other branch.
                            """
                                             ))

    parser.add_argument('-p', '--profile',
                        nargs='?',
                        const=True,
                        default=False,
                        help=textwrap.dedent("""
                                Install the plugin into a QGIS user profile.
                                Requires that QGIS is closed. Use:
                                -p or --profile for installation into the active user profile
                                --profile=myProfile for installation install it into profile "myProfile"
                                """)
                        )
    args = parser.parse_args()

    path = create_plugin(build_name=args.build_name,
                         copy_to_profile=args.profile)
    print('QPS ZIP={}'.format(path))
