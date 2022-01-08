# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    setup.py

    This file is required to allow QPS being installed via pip, e.g. like:
    # python3 -m pip install --user git+https://bitbucket.org/jakimowb/qgispluginsupport.git@develop#egg=qps
    ---------------------
    Beginning            : 2019-12-18
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
from setuptools import setup, find_packages
from qps import __version__

setup(name='qps',
      version=__version__,
      description='QPS - QGIS Plugin Support. Tools and helpers to develop QGIS Plugins for remote sensing applications',
      author='Benjamin Jakimow    ',
      author_email='benjamin.jakimow@geo.hu-berlin.de',
      packages=find_packages(),
      url='https://bitbucket.org/jakimowb/qgispluginsupport',
      long_description=open('README.md').read(),
      include_package_data=True,
      dependency_links=['git+https://bitbucket.org/jakimowb/qgispluginsupport.git@develop#egg=qps']
      )

# python3 -m pip install --user https://bitbucket.org/jakimowb/bit-flag-renderer/get/master.zip#egg=qps
# python3 -m pip install --user git+https://bitbucket.org/jakimowb/qgispluginsupport.git@develop#egg=qps
