# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    runfirst.py

    run this script to set up the QPS repository.
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
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib
import site


def setupRepository():
    """
    Initializes the QPS repository after it has been clones
    """
    dir_repo = pathlib.Path(__file__).parent.resolve()
    site.addsitedir(dir_repo.as_posix())

    from qps.resources import compileResourceFiles

    path_images = dir_repo / 'qgisresources' / 'images_rc.py'
    if not path_images.is_file():
        from scripts.install_testdata import install_qgisresources
        install_qgisresources()

    make_qrc = False
    try:
        import os.path
        import qps.qpsresources
        assert qps.qpsresouces is not None
        path_qrc = dir_repo / 'qps' / 'qpsresources.qrc'
        path_py = dir_repo / 'qps' / 'qpsresources.py'

        if not path_py.is_file() or os.path.getmtime(path_py) < os.path.getmtime(path_qrc):
            make_qrc = True

    except (ImportError, ModuleNotFoundError):
        # compile resources
        make_qrc = True

    if make_qrc:
        print('Need to create qpsresources.py')
        print('Start *.qrc search  in {}'.format(dir_repo))
        compileResourceFiles(dir_repo.as_posix())
    else:
        print('qpsresources.py exists and is up-to-date')


if __name__ == "__main__":
    setupRepository()
