# This script shows information on the current python installation
import importlib.util
import os
import sys


def section(title):
    print(f'\n### {title} ###')


section('SYSTEM')
print(f'Version: {sys.version}')
print(f'Exec: {sys.executable}')
print(f'Platform: {sys.platform}')
print(f'Prefix: {sys.prefix}')
print(f'Version: {sys.version_info}')

try:
    from qgis.core import Qgis

    print(f'QGIS: {Qgis.version()}')
except Exception as ex:
    print(f'QGIS: not available!: {ex}')

section('PACKAGES')
to_test = ['numpy', 'scipy', 'osgeo.gdal', 'colorama', 'qps', 'sklearn', 'pytest']

for p in sorted(to_test):
    b = importlib.util.find_spec(p) is not None
    print(f'{p} {b}')

section('PYTHONPATH')
for p in sorted(sys.path):
    print(p)

section('ENVIRONMENT')
for p in sorted(os.environ):
    print(f'{p}={os.environ[p]}')
