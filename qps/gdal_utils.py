"""
A set of tools that help to operate on GDAL API only.
"""
from typing import Dict

from osgeo import gdal


class GDALConfigChanges(object):
    """
    Can be used to modify the GDAL configuration for a local context only.
    See https://github.com/EnMAP-Box/enmap-box/issues/1214
    """

    def __init__(self, changes: Dict[str, str]):

        self._changes = changes.copy()
        self._original = {}

    def __enter__(self):
        for key, value in self._changes.items():
            self._original[key] = gdal.GetConfigOption(key)
            gdal.SetConfigOption(key, value)

    def __exit__(self, exc_type, exc_val, exc_tb):

        for key, value in self._original.items():
            gdal.SetConfigOption(key, value)
