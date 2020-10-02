# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    runfirst.py

    run this script to setup the QPS repository.
    It compiles *.svg icons into corresponding *_rc.py files
    that make icons available to the Qt resource system.
    ---------------------
    Beginning            : 2019-01-24
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
import pathlib
import site


def setupRepository():
    DIR_REPO = pathlib.Path(__file__).parent.resolve()
    site.addsitedir(DIR_REPO)

    from qps.resources import compileResourceFiles

    path_images = DIR_REPO / 'qgisresources' / 'images_rc.py'
    if not path_images.is_file():
        from scripts.install_testdata import install_qgisresources
        install_qgisresources()

    makeQrc = False
    try:
        import os.path
        import qps.qpsresources

        pathQrc = DIR_REPO / 'qps' / 'qpsresources.qrc'
        pathPy = DIR_REPO / 'qps' / 'qpsresources.py'

        if not pathPy.is_file() or os.path.getmtime(pathPy) < os.path.getmtime(pathQrc):
            makeQrc = True

    except Exception as ex:
        # compile resources
        makeQrc = True

    if makeQrc:
        print('Need to create qpsresources.py')
        print('Start *.qrc search  in {}'.format(DIR_REPO))
        compileResourceFiles(DIR_REPO)
    else:
        print('qpsresources.py exists and is up-to-date')


if __name__ == "__main__":
    setupRepository()
