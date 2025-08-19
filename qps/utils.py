# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/utils.py

    A module for several utilities to be used in other QPS modules
    ---------------------
    Beginning            : 2019-01-11
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
import datetime
import fnmatch
import gc
import importlib
import inspect
import io
import itertools
import json
import math
import os
import re
import shutil
import sys
import traceback
import warnings
import weakref
import zipfile
from collections import defaultdict
from math import floor
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union

import numpy as np
from osgeo import gdal, gdal_array, ogr, osr
from osgeo.ogr import OFSTBoolean, OFSTNone, OFTBinary, OFTDate, OFTDateTime, OFTInteger, OFTInteger64, OFTReal, \
    OFTString, \
    OFTStringList, OFTTime
from osgeo.osr import SpatialReference

from qgis.PyQt import uic
from qgis.PyQt.QtCore import NULL, QByteArray, QDirIterator, QMetaType, QObject, QPoint, QPointF, QRect, Qt, QUrl, \
    QVariant
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QAction, QComboBox, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QMainWindow, \
    QMenu, QToolButton, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement, QDomNode
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsEditorWidgetSetup, \
    QgsFeature, QgsFeatureRequest, QgsFeatureSource, QgsFeedback, QgsField, QgsFields, QgsGeometry, QgsMapLayer, \
    QgsMapLayerProxyModel, QgsMapLayerStore, QgsMapLayerStyle, QgsMapToPixel, QgsMessageOutput, QgsPointXY, \
    QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingFeedback, QgsProject, QgsRaster, \
    QgsRasterBlock, QgsRasterBlockFeedback, QgsRasterDataProvider, QgsRasterIdentifyResult, QgsRasterInterface, \
    QgsRasterLayer, QgsRasterRenderer, QgsRectangle, QgsTask, QgsVector, QgsVectorDataProvider, QgsVectorFileWriter, \
    QgsVectorLayer, QgsWkbTypes
from qgis.core import QgsExpressionContextScope, QgsExpressionContext, QgsFeatureRenderer, QgsSingleSymbolRenderer, \
    QgsMarkerSymbol, QgsExpressionContextUtils, QgsRenderContext, QgsSymbol
from qgis.gui import QgisInterface, QgsDialog, QgsGui, QgsMapCanvas, QgsMapLayerComboBox, QgsMessageViewer
from .qgisenums import QGIS_LAYERFILTER, QGIS_WKBTYPE, QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, \
    QMETATYPE_QBYTEARRAY, QMETATYPE_QCHAR, QMETATYPE_QDATE, QMETATYPE_QDATETIME, QMETATYPE_QSTRING, \
    QMETATYPE_QSTRINGLIST, \
    QMETATYPE_QTIME, \
    QMETATYPE_QVARIANTLIST, \
    QMETATYPE_UINT
from .qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from .unitmodel import datetime64, UnitLookup

QGIS_RESOURCE_WARNINGS = set()

REMOVE_setShortcutVisibleInContextMenu = hasattr(QAction, 'setShortcutVisibleInContextMenu')

jp = os.path.join
dn = os.path.dirname

QGIS2NUMPY_DATA_TYPES = {Qgis.Byte: np.uint8,
                         Qgis.UInt16: np.uint16,
                         Qgis.Int16: np.int16,
                         Qgis.UInt32: np.uint32,
                         Qgis.Int32: np.int32,
                         Qgis.Float32: np.float32,
                         Qgis.Float64: np.float64,
                         Qgis.CFloat32: complex,
                         Qgis.CFloat64: np.complex64,
                         Qgis.ARGB32: np.uint32,
                         Qgis.ARGB32_Premultiplied: np.uint32
                         }

NUMPY2QGIS_DATA_TYPES = {np.uint8: Qgis.Byte,
                         bool: Qgis.Byte,
                         np.uint16: Qgis.UInt16,
                         np.uint32: Qgis.UInt32,
                         np.int16: Qgis.Int16,
                         np.int32: Qgis.Int32,
                         np.float32: Qgis.Float32,
                         np.float64: Qgis.Float64,
                         complex: Qgis.CFloat32,
                         np.complex64: Qgis.CFloat64,
                         }

QGIS_DATATYPE_NAMES = {
    Qgis.Byte: 'Byte',
    Qgis.UInt16: 'UInt16',
    Qgis.Int16: 'Int16',
    Qgis.UInt32: 'UInt32',
    Qgis.Int32: 'Int32',
    Qgis.Float32: 'Float32',
    Qgis.Float64: 'Float64',
    Qgis.CFloat32: 'Complex',
    Qgis.CFloat64: 'Complex64',
    Qgis.ARGB32: 'UInt32',
    Qgis.ARGB32_Premultiplied: 'Int32'}


def rm(p):
    """
    Removes the file or directory `p`
    :param p: path of file or directory to be removed.
    """
    if os.path.isfile(p):
        os.remove(p)
    elif os.path.isdir(p):
        shutil.rmtree(p)


def _geometryIsEmpty(g: QgsGeometry) -> bool:
    if g.isEmpty():
        return True
    if Qgis.versionInt() >= 33000:
        if g.type() in [Qgis.GeometryType.Null,
                        Qgis.GeometryType.Unknown]:
            return True
    else:
        if g.type() in [QgsWkbTypes.NoGeometry,
                        QgsWkbTypes.NullGeometry,
                        QgsWkbTypes.UnknownGeometry
                        ]:
            return True
    return False


def _geometryIsSinglePoint(g: QgsGeometry) -> bool:
    return g.wkbType() in [QGIS_WKBTYPE.Point, QGIS_WKBTYPE.PointM,
                           QGIS_WKBTYPE.PointZM, QGIS_WKBTYPE.Point25D, QGIS_WKBTYPE.PointZ]


def variant_type_to_ogr_field_type(variant_type):
    """
    Reimplementation of QgsOgrUtils::variantTypeToOgrFieldType
    :param variant_type:
    :return:
    """
    ogr_sub_type = OFSTNone
    if variant_type == QMETATYPE_BOOL:
        ogr_type = OFTInteger
        ogr_sub_type = OFSTBoolean

    elif variant_type == QMETATYPE_INT:
        ogr_type = OFTInteger

    elif variant_type == QMetaType.LongLong:
        ogr_type = OFTInteger64

    elif variant_type == QMetaType.Double:
        ogr_type = OFTReal

    elif variant_type in [QMETATYPE_QCHAR, QMETATYPE_QSTRING]:
        ogr_type = OFTString

    elif variant_type == QMETATYPE_QSTRINGLIST:
        ogr_type = OFTStringList

    elif variant_type == QMETATYPE_QBYTEARRAY:
        ogr_type = OFTBinary

    elif variant_type == QMETATYPE_QDATE:
        ogr_type = OFTDate

    elif variant_type == QMETATYPE_QTIME:
        ogr_type = OFTTime

    elif variant_type == QMETATYPE_QDATETIME:
        ogr_type = OFTDateTime

    else:
        ogr_type = OFTString

    return ogr_type, ogr_sub_type


class SignalBlocker(object):
    """
    Signal blocker for arbitrary number of QObjects
    """

    def __init__(self, *objects: QObject):
        self.mObjects = objects
        self.mWasBlocked: List[bool] = []

    def __enter__(self):
        self.mWasBlocked = [obj.blockSignals(True) for obj in self.mObjects]

    def __exit__(self, exc_type, exc_value, tb):
        for obj, wasBlocked in zip(self.mObjects, self.mWasBlocked):
            obj.blockSignals(wasBlocked)


def relativePath(absPath: Path, parentDir: Path) -> Path:
    """
    Returns the path relative to a parent directory
    :param absPath: absolute path to be converted into a relative path
    :param parentDir: the reference directory, from which the relative path will be calculated
                      if both paths are in the same directory, absPath = parentDir / relativePath
    :return: relative path
    """
    if isinstance(absPath, str):
        absPath = Path(absPath)
    if isinstance(parentDir, str):
        parentDir = Path(parentDir)

    assert isinstance(parentDir, Path)
    assert isinstance(absPath, Path)
    n = min(len(parentDir.parts), len(absPath.parts))
    i = 0

    relPath = Path()
    while i < n:
        if parentDir.parts[i] == absPath.parts[i]:
            i += 1
        else:
            break
    if i > 0:
        for _ in range(len(parentDir.parts[i:])):
            relPath = relPath / '..'

    for part in absPath.parts[i:]:
        relPath = relPath / part

    return relPath


def cleanDir(d):
    """
    Remove content from directory 'd'
    :param d: directory to be cleaned.
    """
    assert os.path.isdir(d)
    for root, dirs, files in os.walk(d):
        for p in dirs + files:
            rm(jp(root, p))
        break


# a QPS internal map layer store
QPS_MAPLAYER_STORE = QgsMapLayerStore()
_MAP_LAYER_STORES = [QPS_MAPLAYER_STORE]


def mapLayerStores() -> List[Union[QgsMapLayerStore, QgsProject]]:
    """
    Returns a list of known map layer stores (included QgsProject.instance()
    :return:
    """
    # global _MAP_LAYER_STORES
    return _MAP_LAYER_STORES[:] + [QgsProject.instance()]


def findUpwardPath(basepath, name, is_directory: bool = True) -> Optional[Path]:
    """
    Searches for a file or directory in an upward path of a base path.
    E.g. DIR_REPO = findUpwardPath(__file__, '.git').parent returns the repository directory
         that contains the module referred by __file__

    :param basepath:
    :param name:
    :param is_directory:
    :return:
    """
    tmp = Path(basepath).resolve()
    while tmp != Path(tmp.anchor):
        tmp2 = tmp / name
        if (is_directory and tmp2.is_dir()) or (not is_directory and tmp2.is_file()):
            return tmp2
        else:
            tmp = tmp.parent
    return None


#
def file_search(rootdir,
                pattern,
                recursive: bool = False,
                ignoreCase: bool = False,
                directories: bool = False,
                fullpath: bool = False):
    """
    Searches for files or folders
    :param rootdir: root directory to search in
    :param pattern: wildcard ("my*files.*") or regular expression that describes the file or folder name.
    :param recursive: set True to search recursively.
    :param ignoreCase: set True to ignore character case.
    :param directories: set True to search for directories/folders instead of files.
    :param fullpath: set True if the entire path should be evaluated and not the file name only
    :return: enumerator over file paths
    """
    assert os.path.isdir(rootdir), "Path is not a directory:{}".format(rootdir)
    regType = type(re.compile('.*'))

    with os.scandir(rootdir) as entry_search:
        for entry in entry_search:
            if directories is False:
                if entry.is_file():
                    if fullpath:
                        name = entry.path
                    else:
                        name = os.path.basename(entry.path)
                    if isinstance(pattern, regType):
                        if pattern.search(name):
                            yield entry.path.replace('\\', '/')

                    elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                            or fnmatch.fnmatch(name, pattern):
                        yield entry.path.replace('\\', '/')
                elif entry.is_dir() and recursive is True:
                    for r in file_search(entry.path, pattern, recursive=recursive, directories=directories):
                        yield r
            else:
                if entry.is_dir():
                    if recursive is True:
                        for d in file_search(entry.path, pattern, recursive=recursive, directories=directories):
                            yield d

                    if fullpath:
                        name = entry.path
                    else:
                        name = os.path.basename(entry.path)
                    if isinstance(pattern, regType):
                        if pattern.search(name):
                            yield entry.path.replace('\\', '/')

                    elif (ignoreCase and fnmatch.fnmatch(name, pattern.lower())) \
                            or fnmatch.fnmatch(name, pattern):
                        yield entry.path.replace('\\', '/')


def registerMapLayerStore(store):
    """
    Registers an QgsMapLayerStore or QgsProject to search QgsMapLayers in
    :param store: QgsProject | QgsMapLayerStore
    """
    assert isinstance(store, (QgsProject, QgsMapLayerStore))
    if store not in mapLayerStores():
        _MAP_LAYER_STORES.append(store)


def registeredMapLayers() -> list:
    """
    Returns the QgsMapLayers which are stored in known QgsMapLayerStores
    :return: [list-of-QgsMapLayers]
    """
    layers = []
    for store in mapLayerStores():
        for layer in store.mapLayers().values():
            if layer not in layers:
                layers.append(layer)
    return layers


convertLengthUnit = UnitLookup.convertLengthUnit
convertDateUnit = UnitLookup.convertDateUnit

# contains a lookup for wavelengths in nanometers
LUT_WAVELENGTH = dict({'B': 480,
                       'G': 570,
                       'R': 660,
                       'NIR': 850,
                       'SWIR': 1650,
                       'SWIR1': 1650,
                       'SWIR2': 2150
                       })
WAVELENGTH_DESCRIPTION = {
    'B': f'Visible blue at {LUT_WAVELENGTH["B"]} nm',
    'G': f'Visible green at {LUT_WAVELENGTH["G"]} nm',
    'R': f'Visible red at {LUT_WAVELENGTH["R"]} nm',
    'NIR': f'Near infrared at {LUT_WAVELENGTH["NIR"]} nm',
    'SWIR': f'Shortwave infrared at {LUT_WAVELENGTH["SWIR"]} nm',
    'SWIR1': f'Shortwave infrared at {LUT_WAVELENGTH["SWIR1"]} nm',
    'SWIR2': f'Shortwave infrared at {LUT_WAVELENGTH["SWIR2"]} nm',
}

NEXT_COLOR_HUE_DELTA_CON = 10
NEXT_COLOR_HUE_DELTA_CAT = 100
NEXT_COLOR_DELTA_VALUE = 50


def nextColor(color, mode='cat') -> QColor:
    """
    Returns another color.
    :param color: QColor
    :param mode: str, 'cat' for categorical colors (much difference from 'color')
                      'con' for continuous colors (similar to 'color')
                      'darker' for decreased brightness (if possible)
                      'brighter' for increased brightness (if possible)
    :return: QColor
    """
    assert mode in ['cat', 'con', 'darker', 'brighter']
    assert isinstance(color, QColor)
    hue, sat, value, alpha = color.getHsv()
    if mode == 'cat':
        hue += NEXT_COLOR_HUE_DELTA_CAT
    elif mode == 'con':
        hue += NEXT_COLOR_HUE_DELTA_CON
    elif mode == 'darker':
        value = max(0, value - NEXT_COLOR_DELTA_VALUE)
    elif mode == 'brighter':
        value = max(255, value + NEXT_COLOR_DELTA_VALUE)

    if sat == 0:
        sat = 255
        value = 128
        alpha = 255
        s = ""
    while hue >= 360:
        hue -= 360

    return QColor.fromHsv(hue, sat, value, alpha)


def aggregateArray(aggregation: str, array: np.ndarray, *args, axis: int = None, **kwds) -> np.ndarray:
    aggregation = aggregation.lower()
    if aggregation == 'none':
        return array
    AGGR = {'mean': np.nanmean,
            'median': np.nanmedian,
            'var': np.nanvar,
            'std': np.nanstd,
            'sum': np.nansum,
            'min': np.nanmin,
            'max': np.nanmax,
            'percentile': np.nanpercentile,
            'quantile': np.nanquantile}
    assert aggregation in AGGR.keys(), f'Unknown aggregation "{aggregation}"'

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=RuntimeWarning)
        result = AGGR[aggregation](array, *args, axis=axis, **kwds)

    return result


def noDataValues(dataProvider: Union[QgsRasterLayer, QgsRasterDataProvider]) -> Dict[int, List[Union[int, float]]]:
    """
    Returns all (activated) nodata values
    """
    if isinstance(dataProvider, QgsRasterLayer):
        dataProvider = dataProvider.dataProvider()

    assert isinstance(dataProvider, QgsRasterDataProvider)

    NODATA: Dict[int, List] = dict()
    for b in range(1, dataProvider.bandCount() + 1):
        ndv = []
        if dataProvider.useSourceNoDataValue(b) and dataProvider.sourceHasNoDataValue(b):
            ndv.append(dataProvider.sourceNoDataValue(b))
        ndv.extend(dataProvider.userNoDataValues(b))
        NODATA[b] = ndv

    return NODATA


def findMapLayerStores() -> List[Union[QgsProject, QgsMapLayerStore]]:
    import gc
    yield QgsProject.instance()
    for obj in gc.get_objects():
        if isinstance(obj, QgsMapLayerStore):
            yield obj


def findMapLayer(layer) -> Optional[QgsMapLayer]:
    """
    Returns the first QgsMapLayer out of all layers stored in MAP_LAYER_STORES that matches layer
    :param layer: str layer id or layer name or QgsMapLayer
    :return: QgsMapLayer
    """
    assert isinstance(layer, (QgsMapLayer, str))
    if isinstance(layer, QgsMapLayer):
        return layer

    elif isinstance(layer, str):
        for store in findMapLayerStores():
            lyr = store.mapLayer(layer)
            if isinstance(lyr, QgsMapLayer):
                return lyr
            layers = store.mapLayersByName(layer)
            if len(layers) > 0:
                return layers[0]

    for lyr in gc.get_objects():
        if isinstance(lyr, QgsMapLayer):
            if lyr.id() == layer or lyr.source() == layer:
                return lyr

    return None


def gdalFileSize(path) -> int:
    """
    Returns the size of a local gdal readible file (including metadata files etc.)
    :param path: str
    :return: int
    """
    ds = gdal.Open(path)
    if not isinstance(ds, gdal.Dataset):
        return 0
    else:
        size = 0
        for file in ds.GetFileList():
            size += os.stat(file).st_size

            # recursively inspect VRT sources
            if file.endswith('.vrt') and file != path:
                size += gdalFileSize(file)

        return size


def qgisLayerTreeLayers() -> list:
    """
    Returns the layers shown in the QGIS LayerTree
    :return: [list-of-QgsMapLayers]
    """
    iface = qgisAppQgisInterface()
    if isinstance(iface, QgisInterface):
        return [ln.layer() for ln in iface.layerTreeView().layerTreeModel().rootGroup().findLayers()
                if isinstance(ln.layer(), QgsMapLayer)]
    else:
        return []


rx_is_int = re.compile(r'^\s*\d+\s*$')


def stringToType(value: str):
    """
    Converts a string into a matching int, float or string
    """
    if not isinstance(value, str):
        return value

    if rx_is_int.match(value):
        return int(value.strip())
    else:
        try:
            return float(value.strip())
        except ValueError:
            pass
    return value


def toType(t, arg, empty2None=True, empty_values=[None, NULL]):
    """
    Converts lists or single values into type t.

    Examples:
        toType(int, '42') == 42,
        toType(float, ['23.42', '123.4']) == [23.42, 123.4]

    :param empty_values:
    :param t: type
    :param arg: value to convert
    :param empty2None: returns None in case arg is an emptry value (None, '', NoneType, ...)
    :return: arg as type t (or None)
    """
    if isinstance(arg, list):
        return [toType(t, a, empty2None=empty2None, empty_values=empty_values) for a in arg]
    else:

        if empty2None and arg in empty_values:
            return None
        else:
            return t(arg)


def createQgsField(name: str, exampleValue: Any, comment: str = None) -> QgsField:
    """
    Creates a QgsField based on the type properties of a Python-datatype exampleValue
    :param name: field name
    :param exampleValue: value, can be any type
    :param comment: (optional) field comment.
    :return: QgsField
    """
    if isinstance(exampleValue, str):
        return QgsField(name, QMETATYPE_QSTRING, 'varchar', comment=comment)
    elif isinstance(exampleValue, bool):
        return QgsField(name, QMETATYPE_BOOL, 'int', len=1, comment=comment)
    elif isinstance(exampleValue, (int, np.int8, np.int16, np.int32, np.int64)):
        return QgsField(name, QMETATYPE_INT, 'int', comment=comment)
    elif isinstance(exampleValue, (np.uint, np.uint8, np.uint16, np.uint32, np.uint64)):
        return QgsField(name, QMETATYPE_UINT, 'uint', comment=comment)
    elif isinstance(exampleValue, (float, np.double, np.float16, np.float32, np.float64)):
        return QgsField(name, QMETATYPE_DOUBLE, 'double', comment=comment)
    elif isinstance(exampleValue, np.ndarray):
        return QgsField(name, QMETATYPE_QSTRING, 'varchar', comment=comment)
    elif isinstance(exampleValue, np.datetime64):
        return QgsField(name, QMETATYPE_QDATETIME, comment=comment)
    elif isinstance(exampleValue, (bytes, QByteArray)):
        return QgsField(name, QMETATYPE_QBYTEARRAY, 'Binary', comment=comment)
    elif isinstance(exampleValue, list):
        assert len(exampleValue) > 0, 'need at least one value in provided list'
        v = exampleValue[0]
        prototype = createQgsField(name, v)
        subType = prototype.type()
        typeName = prototype.typeName()
        return QgsField(name, QMETATYPE_QVARIANTLIST, typeName, comment=comment, subType=subType)
    elif isinstance(exampleValue, type):
        return createQgsField(name, exampleValue(1), comment=comment)
    else:
        raise NotImplementedError()


def filenameFromString(text: str):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    see https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    :return: path
    """
    if text is None:
        return ''
    isInValid = re.compile(r"[\\/:?\"<>| ,']")

    isValid = re.compile(r"([-_.()]|\d|\D)", re.ASCII + re.IGNORECASE)
    import unicodedata
    cleaned = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore')

    chars = []
    for c in cleaned.decode():
        if isValid.search(c) and not isInValid.search(c):
            chars.append(c)
        else:
            chars.append('_')

    return ''.join(chars)


def value2str(value,
              sep: str = None,
              delimiter: str = ' ',
              empty_values: list = [None, NULL],
              empty_string: str = ''):
    """
    Converts a value into a string
    :param empty_string:
    :param empty_values: Defines a list of values to be represented by the empty_string
    :param sep:
    :param value: any
    :param delimiter: delimiter to be used for list values
    :return:
    """

    if sep is not None:
        delimiter = sep

    if isinstance(value, list):
        value = delimiter.join([str(v) for v in value])
    elif isinstance(value, np.ndarray):
        value = value2str(value.tolist(), delimiter=delimiter, empty_values=empty_values, empty_string=empty_string)
    elif value in empty_values:
        value = empty_string
    else:
        value = str(value)
    return value


def setQgsFieldValue(feature: QgsFeature, field, value):
    """
    Wrties the Python value v into a QgsFeature field, taking care of required conversions
    :param feature: QgsFeature
    :param field: QgsField | field name (str) | field index (int)
    :param value: any python value
    """

    if isinstance(field, int):
        field = feature.fields().at(field)
    elif isinstance(field, str):
        field = feature.fields().at(feature.fieldNameIndex(field))
    assert isinstance(field, QgsField)

    if value is None:
        value = QVariant.NULL
    if field.type() == QMETATYPE_QSTRING:
        value = str(value)
    elif field.type() in [QMETATYPE_INT, QMETATYPE_BOOL]:
        value = int(value)
    elif field.type() in [QMETATYPE_DOUBLE]:
        value = float(value)

    feature.setAttribute(field.name(), value)


def showMessage(message: str, title: str, level):
    """
    Shows a message using the QgsMessageViewer
    :param message: str, message
    :param title: str, title of viewer
    :param level:
    """

    v = QgsMessageViewer()
    v.setTitle(title)

    isHtml = message.startswith('<html>')
    v.setMessage(message, QgsMessageOutput.MessageHtml if isHtml else QgsMessageOutput.MessageText)
    v.showMessage(True)


def gdalDataset(dataset: Union[str, Path, QgsRasterLayer, QgsRasterDataProvider, gdal.Dataset, gdal.Band],
                eAccess: int = gdal.GA_ReadOnly) -> gdal.Dataset:
    """
    Returns a gdal.Dataset object instance
    :param dataset:  path | gdal.Dataset | QgsRasterLayer | QgsRasterDataProvider
    :return: gdal.Dataset
    """
    if isinstance(dataset, gdal.Dataset):
        return dataset
    if isinstance(dataset, gdal.Band):
        return dataset.GetDataset()
    if isinstance(dataset, Path):
        dataset = dataset.as_posix()
    if isinstance(dataset, QgsRasterLayer):
        return gdalDataset(dataset.source(), eAccess=eAccess)
    if isinstance(dataset, QgsRasterDataProvider):
        return gdalDataset(dataset.dataSourceUri(), eAccess=eAccess)
    if isinstance(dataset, str):
        ds = gdal.Open(dataset, eAccess)
        assert isinstance(ds, gdal.Dataset), f'Can not read {dataset} as gdal.Dataset'
        return ds
    else:
        raise NotImplementedError(f'Can not open {dataset} as gdal.Dataset')

    return dataset


def ogrDataSource(data_source, update: int = 0) -> ogr.DataSource:
    """
    Returns an OGR DataSource instance
    :param data_source: ogr.DataSource | str | Path | QgsVectorLayer
    :return: ogr.Datasource
    """
    if isinstance(data_source, ogr.DataSource):
        return data_source

    if isinstance(data_source, QgsVectorLayer):
        dpn = data_source.dataProvider().name()
        uri = None
        if dpn not in ['ogr']:
            context = QgsProcessingContext()
            feedback = QgsProcessingFeedback()
            alg: QgsProcessingAlgorithm = QgsApplication.processingRegistry().algorithmById(
                'native:savefeatures').create({})
            parameters = dict(DATASOURCE_OPTIONS='',
                              INPUT=data_source.source(),
                              LAYER_NAME='',
                              LAYER_OPTIONS='',
                              OUTPUT='TEMPORARY_OUTPUT'
                              )

            assert alg.prepareAlgorithm(parameters, context, feedback), feedback.textLog()

            results = alg.processAlgorithm(parameters, context, feedback)
            print(results)
            if not results:
                raise Exception(f'Unable to convert {dpn} to temporary ogr format')
            else:
                uri = results['OUTPUT']
        else:
            uri = data_source.source().split('|')[0]
        if uri is None:
            raise Exception(f'Unsupported vector data provider: {dpn}')
        return ogrDataSource(uri)

    if isinstance(data_source, Path):
        data_source = data_source.as_posix()

    if isinstance(data_source, str):
        data_source = ogr.Open(data_source, update=update)

    assert isinstance(data_source, ogr.DataSource), 'Can not read {} as ogr.DataSource'.format(data_source)
    return data_source


def optimize_block_size(ds: gdal.Dataset,
                        nb: int = None,
                        cache: int = 5 * 2 ** 20  # defaults: 5 megabytes
                        ) -> Tuple[int, int]:
    """
    Calculates a block_size for fast raster access given a defined cache size in bytes.
    :param ds: gdal.Dataset
    :param nb: number of bands to read, defaults to total number of bands = ds.RasterCount
    :param cache: maximum number of bytes to load with one block. defaults to 5 MB.
    :return:
    """
    ds = gdalDataset(ds)
    assert isinstance(ds, gdal.Dataset)
    if nb is None:
        nb = ds.RasterCount
    block_size = ds.GetRasterBand(1).GetBlockSize()
    # bytes per value
    bpv = gdal_array.flip_code(ds.GetRasterBand(1).DataType)(0).itemsize

    # bytes per profile
    bpp = nb * bpv

    size = block_size[0] * block_size[1] * bpp
    if size > cache:
        # todo: reduce block sizes
        pass
    elif size < cache:
        # increase
        if block_size[0] >= ds.RasterXSize:
            bbl = ds.RasterXSize * bpp
            nl = min(int(cache / bbl), ds.RasterYSize)
            block_size = [ds.RasterXSize, nl]
        elif block_size[1] >= ds.RasterYSize:
            bbs = ds.RasterYSize * bpp
            ns = min(int(cache / bbs), ds.RasterXSize)
            block_size = [ns, ds.RasterYSize]

    return block_size


def fid2pixelindices(raster: gdal.Dataset,
                     vector: ogr.DataSource,
                     layer: Union[int, str] = 0,
                     all_touched: bool = True,
                     raster_fids: Union[str, Path] = None) -> Tuple[np.ndarray, int]:
    """
    Returns vector feature pixel positions.

    :param raster: gdal.Dataset | QgsRasterLayer or path to
    :param vector: ogr.DataSource | QgsVectorLayer or path to
    :param layer: optional, layer name (str) or index (0), defaults to first layer (index = 0)
    :param all_touched: optional, set FALSE to return pixels entirely covered only
    :return: np.ndarray, int no data value
    """
    raster: gdal.Dataset = gdalDataset(raster)
    vector: ogr.DataSource = ogrDataSource(vector)

    if isinstance(layer, str):
        layernames = [vector.GetLayer(i).GetName() for i in range(vector.GetLayerCount())]
        if layer in layernames:
            layer = layernames.index(layer)
        else:
            raise Exception(f'Invalid layer name "{layer}". Possible values: {",".join(layernames)}')

    assert isinstance(layer, int)
    assert layer >= 0
    assert layer < vector.GetLayerCount()
    layer: ogr.Layer = vector.GetLayerByIndex(layer)
    all_fids = [f.GetFID() for f in layer]
    if len(all_fids) == 0:
        eType = gdal.GDT_Byte
        no_data = 0
    else:
        fid_min = min(all_fids)
        fid_max = max(all_fids)
        fid_array = np.asarray([fid_min, fid_max])
        eType = gdal_array.flip_code(fid_array.dtype)
        if fid_min > 0:
            no_data = 0
        elif fid_min == 0:
            no_data = fid_max + 1
        else:
            no_data = fid_min - 1

    if eType is None:
        eType = gdal.GDT_Float64

    dsMEM: gdal.Dataset = gdal.GetDriverByName('MEM') \
        .Create('', raster.RasterXSize, raster.RasterYSize, 1, eType=eType)
    dsMEM.SetGeoTransform(raster.GetGeoTransform())
    dsMEM.SetProjection(raster.GetProjection())
    band: gdal.Band = dsMEM.GetRasterBand(1)
    band.Fill(no_data)
    band.SetNoDataValue(no_data)
    dsMEM.FlushCache()

    # print(f'Rasterize FIDs of {layer.GetDescription()}...')

    drvMem: ogr.Driver = ogr.GetDriverByName('Memory')
    dsMem: ogr.DataSource = drvMem.CreateDataSource('')
    lyrMem: ogr.Layer = dsMem.CreateLayer(layer.GetName(),
                                          srs=layer.GetSpatialRef(),
                                          geom_type=layer.GetGeomType())
    assert ogr.OGRERR_NONE == lyrMem.CreateField(ogr.FieldDefn('FID_BURN', ogr.OFTInteger64))
    ldef: ogr.FeatureDefn = lyrMem.GetLayerDefn()
    # ldef.AddFieldDefn(ogr.FieldDefn('FID_BURN', ogr.OFTInteger64))
    dsMem.FlushCache()

    for f in layer:
        assert isinstance(f, ogr.Feature)
        # Create the feature and set values
        fMem: ogr.Feature = ogr.Feature(ldef)
        fMem.SetGeometry(f.GetGeometryRef())
        fMem.SetField("FID_BURN", f.GetFID())

        lyrMem.CreateFeature(fMem)
    lyrMem.ResetReading()

    all_touched = 'TRUE' if all_touched else 'FALSE'

    result = gdal.RasterizeLayer(dsMEM, [1], lyrMem,
                                 options=['ALL_TOUCHED={}'.format(all_touched),
                                          'ATTRIBUTE={}'.format('FID_BURN')])
    assert result == ogr.OGRERR_NONE, f'Failed to rasterize vector layer {vector.GetDescription()}'

    fidArray: np.ndarray = dsMEM.ReadAsArray()
    if eType == gdal.GDT_Float64:
        fidArray = fidArray.astype(np.int64)
    if raster_fids is not None:
        raster_fids = Path(raster_fids)
        drvTIFF: gdal.Driver = gdal.GetDriverByName('GTiff')
        drvTIFF.CreateCopy(raster_fids.as_posix(), dsMEM)

    return fidArray, int(no_data)


def qgsVectorLayer(source) -> QgsVectorLayer:
    """
    Returns a QgsVectorLayer from different source types
    :param source: QgsVectorLayer | ogr.DataSource | file path
    :return: QgsVectorLayer
    :rtype: QgsVectorLayer
    """
    if isinstance(source, QgsVectorLayer):
        return source
    if isinstance(source, Path):
        return QgsVectorLayer(source.as_posix())
    if isinstance(source, str):
        return QgsVectorLayer(source)
    if isinstance(source, ogr.DataSource):
        return QgsVectorLayer(source.GetDescription())
    if isinstance(source, QUrl):
        return qgsVectorLayer(Path(source.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)).resolve())

    raise Exception('Unable to transform {} into QgsVectorLayer'.format(source))


DEFAULT_RENDERER = QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({'name': 'square', 'color': 'white'}))


def featureSymbolScope(feature: QgsFeature,
                       renderer: Optional[QgsFeatureRenderer] = None,
                       context: Optional[QgsExpressionContext] = None,
                       default_color: Union[None, str, QColor] = None) -> QgsExpressionContextScope:
    """
    Returns a QgsExpressionContextScope with variables 'symbol_color' and 'symbol_angle'.
    """
    assert isinstance(feature, QgsFeature)
    feature = QgsFeature(feature)
    if not feature.hasGeometry():
        symbolScope = QgsExpressionContextScope()
        default_color = QColor(default_color) if default_color else QColor('grey')
        symbolScope.setVariable('symbol_color', default_color)
        symbolScope.setVariable('symbol_angle', 0)
        return symbolScope

    if renderer is None:
        renderer = DEFAULT_RENDERER

    renderer = renderer.clone()
    if context is None:
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
    else:
        context = QgsExpressionContext(context)

    context.setFeature(feature)

    renderContext = QgsRenderContext()
    renderContext.setExpressionContext(context)

    renderer.startRender(renderContext, feature.fields())

    symbol = renderer.symbolForFeature(feature, renderContext)
    if isinstance(symbol, QgsSymbol):
        symbolScope = QgsExpressionContextScope(symbol.symbolRenderContext().expressionContextScope())
    else:
        symbolScope = QgsExpressionContextScope()
        symbolScope.setVariable('symbol_color', QColor('grey'))
        symbolScope.setVariable('symbol_angle', 0)
    renderer.stopRender(renderContext)
    return symbolScope


def qgsRasterLayer(source) -> QgsRasterLayer:
    """
    Returns a QgsRasterLayer from different source types
    :param source: QgsRasterLayer | gdal.Dataset | file path
    :return: QgsRasterLayer
    :rtype: QgsRasterLayer
    """
    if isinstance(source, QgsRasterLayer):
        return source
    if isinstance(source, Path):
        return QgsRasterLayer(source.as_posix())
    if isinstance(source, str):
        return QgsRasterLayer(source)
    if isinstance(source, gdal.Dataset):
        return QgsRasterLayer(source.GetDescription())
    if isinstance(source, QUrl):
        return qgsRasterLayer(Path(source.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)).resolve())

    raise Exception('Unable to transform {} into QgsRasterLayer'.format(source))


def xy_pair_matrix(pairs: List[Union[Tuple[np.ndarray, np.ndarray], Dict]]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Takes arbitrary number of (x, y) pairs of 1D lists or numpy arrays.
    Returns:
      result1: 1D numpy array of all unique x values (sorted by first occurrence)
      result2: 2D numpy array (len(result1), n_pairs) containing y values matched to x,
               np.nan fills if x doesn't exist in the pair.
    """
    # Normalize input into a list of (x, y) numpy arrays
    pairs2 = []
    x_order = {}
    counter = 0
    for pair in pairs:
        if isinstance(pair, dict):
            x, y = np.asarray(pair['x']), np.asarray(pair['y'])
        else:
            x, y = np.asarray(pair[0]), np.asarray(pair[1])
        assert len(x) == len(y), f'Input arrays must be of the same length: {len(x)} != {len(y)}'
        pairs2.append((x, y))

        # preserve order of first occurrence
        for xi in x:
            if xi not in x_order:
                x_order[xi] = counter
                counter += 1

    # unique x values, ordered by first occurrence
    x_values = np.array(sorted(x_order, key=x_order.get))

    # map from x to row index
    x_to_idx = {x: i for i, x in enumerate(x_values)}

    n_pairs = len(pairs2)
    Y_VALUES = np.full((len(x_values), n_pairs), np.nan)

    # fill matrix
    for j, (xvec, yvec) in enumerate(pairs2):
        idxs = [x_to_idx[x] for x in xvec]
        Y_VALUES[idxs, j] = yvec

    return x_values, Y_VALUES


def qgsFields(source: Union[List[QgsField], QgsFeature, QgsFields, QgsVectorLayer]) -> QgsFields:
    """
    Returns the QgsFields of its inputs
    :return: QgsFields
    """
    if isinstance(source, list):
        fields = QgsFields()
        for f in source:
            assert isinstance(f, QgsField)
            fields.append(f)
        return fields

    if isinstance(source, QgsFields):
        return source
    elif isinstance(source, (QgsFeature, QgsVectorLayer)):
        return source.fields()
    return None


def qgsField(layer_fields: Union[QgsFields, QgsVectorLayer, QgsFeature],
             field: Union[QgsField, str, int]) -> QgsField:
    """
    Returns the QgsField relating to the input value in "field"
    :param layer_fields: QgsVectorLayer | QgsFields
    :param field: QgsField | str or int index of field in layer_fields
    :return: QgsField or None, if not found
    """
    if isinstance(layer_fields, QgsVectorLayer):
        layer_fields = layer_fields.fields()
    elif isinstance(layer_fields, QgsFeature):
        layer_fields = layer_fields.fields()

    assert isinstance(layer_fields, QgsFields)

    if isinstance(field, QgsField):
        return qgsField(layer_fields, layer_fields.lookupField(field.name()))
    elif isinstance(field, str):
        return qgsField(layer_fields, layer_fields.lookupField(field))
    elif isinstance(field, int):
        if 0 <= field < layer_fields.count():
            return layer_fields.at(field)
    return None


def findTypeFromString(value: str):
    """
    Returns a fitting basic python data type of a string value, i.e.
    :param value: string
    :return: type out of [str, int or float]
    """
    for t in (int, float, str):
        try:
            _ = t(value)
        except ValueError:
            continue
        return t

    # every value can be converted into a string
    return str


def setComboboxValue(cb: QComboBox, text: str):
    """
    :param cb:
    :param text:
    :return:
    """
    assert isinstance(cb, QComboBox)
    currentIndex = cb.currentIndex()
    idx = -1
    if text is None:
        text = ''
    text = text.strip()
    for i in range(cb.count()):
        v = str(cb.itemText(i)).strip()
        if v == text:
            idx = i
            break
    if not idx >= 0:
        pass

    if idx >= 0:
        cb.setCurrentIndex(idx)
    else:
        print('ComboBox index not found for "{}"'.format(text))


def qgsRasterLayers(sources) -> Iterator[QgsRasterLayer]:
    """
    Like qgsRasterLayer, but on multiple inputs and with extraction of sub-layers
    :param sources:
    :return:
    """
    if not isinstance(sources, list):
        sources = [sources]
    assert isinstance(sources, list)

    for source in sources:
        lyr: QgsRasterLayer = qgsRasterLayer(source)
        if lyr.isValid():
            yield lyr
        for lyr in qgsRasterLayers(lyr.subLayers()):
            yield lyr


def qgsMapLayer(value: Any) -> QgsMapLayer:
    """
    Tries to convert the input into a QgsMapLayer
    :param value: any
    :return: QgsMapLayer or None
    """
    if isinstance(value, QgsMapLayer):
        return value
    try:
        lyr = qgsRasterLayer(value)
        if isinstance(lyr, QgsRasterLayer):
            return lyr
    except Exception:
        pass

    try:
        lyr = qgsVectorLayer(value)
        if isinstance(lyr, QgsVectorLayer):
            return lyr
    except Exception:
        pass

    return None


UI_STORE: Dict[Path, str] = dict()


def loadUi(uifile: Union[str, Path],
           baseinstance=None,
           resource_suffix: str = '_rc',
           remove_resource_references: bool = True,
           no_caching: bool = False,
           loadUiType: bool = False,
           package: str = ''
           ):
    """
    :param uifile: path to *.ui file
    :param resource_suffix: suffix used for python-compiled *.qrc files. E.g. `_rc` if images.qrc is
    compiled to images_rc.py
    :param remove_resource_references: removes all *.qrc references from the *.ui xml. In this case resources need to be
    loaded externally. See qps.resources for examples.
    :param no_caching: if True, will read the *.ui for each new call
    :param loadUiType: if True, returns the output of `uic.loadUi(...)` instead of `uic.loadUiType(...)`
    :param baseinstance: argument to `uic.loadUi(...)`
    :param package: argument to `uic.loadUi(...)`
    :return:
    """
    if baseinstance is not None:
        assert isinstance(baseinstance, QWidget)

    uifile = Path(uifile).resolve()
    # global UI_STORE
    assert uifile.is_file(), '*.ui file does not exist: {}'.format(uifile)
    if no_caching or uifile not in UI_STORE.keys():
        from .resources import REGEX_QGIS_IMAGES_QRC

        with open(uifile, 'r', encoding='utf-8') as f:
            txt = f.read()

        dirUi: Path = uifile.parent

        locations = []

        # replace local path to QGIS repository images with that used in the QGIS Application
        txt = re.sub(r'resource="[^":]*/QGIS[^\/"]*[\/]images[\/]images\.qrc"', 'resource=":/images/images.qrc"', txt)

        for m in re.findall(r'(<include location="(.*\.qrc)"/>)', txt):
            locations.append(m)

        missing = []
        for t in locations:
            line, path = t
            if REGEX_QGIS_IMAGES_QRC.search(path):
                continue
            if not os.path.isabs(path):
                p = (dirUi / Path(path)).resolve()
            else:
                p = Path(path)

            if not p.is_file():
                missing.append(t)

        if len(missing) > 0:
            print('{}\nrefers to {} none-existing resource (*.qrc) file(s):'.format(uifile, len(missing)))
            for i, t in enumerate(missing):
                line, path = t
                print('{}: "{}"'.format(i + 1, path), file=sys.stderr)

        doc = QDomDocument()
        doc.setContent(txt)

        if REMOVE_setShortcutVisibleInContextMenu and 'shortcutVisibleInContextMenu' in txt:
            toRemove = []
            actions = doc.elementsByTagName('action')
            for iAction in range(actions.count()):
                properties = actions.item(iAction).toElement().elementsByTagName('property')
                for iProperty in range(properties.count()):
                    prop = properties.item(iProperty).toElement()
                    if prop.attribute('name') == 'shortcutVisibleInContextMenu':
                        toRemove.append(prop)
            for prop in toRemove:
                prop.parentNode().removeChild(prop)
            del toRemove

        # we need the absolute position of qps
        # e.g. within my/package/externals/qps
        # of as top-level qps
        try:
            from .. import qps
        except ImportError:
            qps = __import__('qps')
        except ValueError:
            qps = __import__('qps')

        elem = doc.elementsByTagName('customwidget')
        for child in [elem.item(i) for i in range(elem.count())]:
            child = child.toElement()

            cClass = child.firstChildElement('class').firstChild()
            cHeader = child.firstChildElement('header').firstChild()
            cExtends = child.firstChildElement('extends').firstChild()

            sClass = str(cClass.nodeValue())
            sExtends = str(cHeader.nodeValue())
            if False:
                if sClass.startswith('Qgs'):
                    cHeader.setNodeValue('qgis.gui')
            if True:
                # replace 'qps' package location with local absolute position
                if sExtends.startswith('qps.'):
                    cHeader.setNodeValue(re.sub(r'^qps\.', qps.__spec__.name + '.', sExtends))

        if remove_resource_references:
            # remove resource file locations to avoid import errors.
            elems = doc.elementsByTagName('include')
            for i in range(elems.count()):
                node = elems.item(i).toElement()
                attribute = node.attribute('location')
                if len(attribute) > 0 and attribute.endswith('.qrc'):
                    node.parentNode().removeChild(node)

            # remove iconset resource names, e.g.<iconset resource="../qpsresources.qrc">
            elems = doc.elementsByTagName('iconset')
            for i in range(elems.count()):
                node = elems.item(i).toElement()
                attribute = node.attribute('resource')
                if len(attribute) > 0:
                    node.removeAttribute('resource')
        UI_STORE[uifile] = doc.toString()

    buffer = io.StringIO()  # buffer to store ui XML
    buffer.write(UI_STORE[uifile])
    buffer.flush()
    buffer.seek(0)

    if not loadUiType:
        return uic.loadUi(buffer, baseinstance=baseinstance, package=package, resource_suffix=resource_suffix)
    else:
        return uic.loadUiType(buffer, resource_suffix=resource_suffix)


def loadUIFormClass(pathUi: str, from_imports=False, resourceSuffix: str = '', fixQGISRessourceFileReferences=True,
                    _modifiedui=None):
    """
    Backport, deprecated
    """
    info = ''.join(traceback.format_stack()) + '\nUse loadUi(... , loadUiType=True) instead.'
    warnings.warn(info, DeprecationWarning)
    return loadUi(pathUi, resource_suffix=resourceSuffix, loadUiType=True)[0]


def typecheck(variable, type_):
    """
    Checks for `variable` if it is an instance of type `type_`.
    In case `variable` is a list, all list elements will be checked.
    :param variable:
    :type variable:
    :param type_:
    :type type_:
    :return:
    :rtype:
    """
    if isinstance(type_, list):
        for i in range(len(type_)):
            typecheck(variable[i], type_[i])
    else:
        assert isinstance(variable, type_)


# thanks to https://gis.stackexchange.com/questions/75533/how-to-apply-band-settings-using-gdal-python-bindings
def read_vsimem(fn):
    """
    Reads VSIMEM path as string
    :param fn: vsimem path (str)
    :return: result of gdal.VSIFReadL(1, vsileng, vsifile)
    """
    vsifile = gdal.VSIFOpenL(fn, 'r')
    gdal.VSIFSeekL(vsifile, 0, 2)
    vsileng = gdal.VSIFTellL(vsifile)
    gdal.VSIFSeekL(vsifile, 0, 0)
    return gdal.VSIFReadL(1, vsileng, vsifile)


def writeAsVectorFormat(layer: QgsVectorLayer,
                        path: Union[str, Path],
                        options: QgsVectorFileWriter.SaveVectorOptions = None,
                        feedback: QgsFeedback = None,
                        field_value_converter: Optional[
                            QgsVectorFileWriter.FieldValueConverter] = None) -> QgsVectorLayer:
    """
    Writes any vector layer into another format. E.g. to store in-memory vector layers persistently
    :param field_value_converter:
    :param layer: QgsVectorLayer
    :param path: path to store the vector file.
    :param options: optional, QgsVectorFileWriter.SaveVectorOptions
    :param feedback: QgsFeedback
    :return: QgsVectorLayer
    """
    path = Path(path)
    assert isinstance(layer, QgsVectorLayer)
    assert layer.isValid()

    if not isinstance(options, QgsVectorFileWriter.SaveVectorOptions):

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.fileEncoding = 'UTF-8'

        parts = os.path.splitext(path.name)

        if len(parts) == 2:
            driver_name = QgsVectorFileWriter.driverForExtension(parts[1])
            options.driverName = driver_name
            options.layerOptions = QgsVectorFileWriter.defaultLayerOptions(options.driverName)
            options.datasourceOptions = QgsVectorFileWriter.defaultDatasetOptions(options.driverName)
            options.includeConstraints = True
            options.layerMetadata = layer.metadata()

    if isinstance(field_value_converter, QgsVectorFileWriter.FieldValueConverter):
        options.fieldValueConverter = field_value_converter
    if not isinstance(options.fieldValueConverter, QgsVectorFileWriter.FieldValueConverter):
        from .fieldvalueconverter import GenericFieldValueConverter
        srcFields = layer.fields()

        dstFields = GenericFieldValueConverter.compatibleTargetFields(srcFields, options.driverName)

        converter = GenericFieldValueConverter(srcFields, dstFields)
        options.fieldValueConverter = converter

    err, errMsg, fn_new, lyrname_new = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        path.as_posix(),
        QgsProject.instance().transformContext(),
        options,
    )
    assert err == QgsVectorFileWriter.NoError, errMsg

    # assert r
    # save styling

    lyr2 = QgsVectorLayer(path.as_posix(), layer.name())
    assert lyr2.isValid()

    style = QgsMapLayerStyle()
    style.readFromLayer(layer)
    style.writeToLayer(lyr2)

    path_qlr = path.parent / re.sub(r'\.[^.]+$', '.qml', path.name)
    # msg, success = layer.saveNamedStyle(pathQlr.as_posix())
    msg, success = lyr2.saveNamedStyle(path_qlr.as_posix())
    assert success, 'Failed to save style:' + msg

    return lyr2


def write_vsimem(fn: str, data: str):
    """
    Writes data to vsimem path
    :param fn: vsimem path (str)
    :param data: string to write
    :return: result of gdal.VSIFCloseL(vsifile)
    """
    '''Write GDAL vsimem files'''
    vsifile = gdal.VSIFOpenL(fn, 'w')
    size = len(data)
    gdal.VSIFWriteL(data, 1, size, vsifile)
    return gdal.VSIFCloseL(vsifile)


class KeepRefs(object):
    __refs__ = defaultdict(list)

    def __init__(self):
        self.__refs__[self.__class__].append(weakref.ref(self))

    @classmethod
    def instances(cls):
        for inst_ref in cls.__refs__[cls]:
            inst = inst_ref()
            if inst is not None:
                yield inst


def appendItemsToMenu(menu, itemsToAdd):
    """
    Appends items to QMenu "menu"
    :param menu: the QMenu to be extended
    :param itemsToAdd: QMenu or [list-of-QActions-or-QMenus]
    :return: menu
    """
    assert isinstance(menu, QMenu)
    if isinstance(itemsToAdd, QMenu):
        itemsToAdd = itemsToAdd.children()[1:]
    if not isinstance(itemsToAdd, list):
        itemsToAdd = [itemsToAdd]

    for item in itemsToAdd:
        if isinstance(item, QAction):
            item.setParent(menu)
            menu.addAction(item)
            s = ""
        elif isinstance(item, QMenu):
            # item.setParent(menu)
            sub = menu.addMenu(item.title())
            sub.setIcon(item.icon())
            appendItemsToMenu(sub, item.children()[1:])
        else:
            s = ""
    return menu


def allSubclasses(cls):
    """
    Returns all subclasses of class 'cls'
    Thx to: http://stackoverflow.com/questions/3862310/how-can-i-find-all-subclasses-of-a-class-given-its-name
    :param cls:
    :return:
    """
    return cls.__subclasses__() + [g for s in cls.__subclasses__()
                                   for g in allSubclasses(s)]


def copyEditorWidgetSetup(vectorLayer: QgsVectorLayer, fields: Union[QgsFields, QgsVectorLayer, List[QgsField]]):
    """
    :param fields:
    :type fields:
    :return:
    :rtype:
    """
    """Copies the editor widget setup from another vector layer or list of QgsField"""
    fields = qgsFields(fields)

    for fSrc in fields:
        idx = vectorLayer.fields().indexOf(fSrc.name())

        if idx == -1:
            # profile_field name does not exist
            continue
        fDst = vectorLayer.fields().at(idx)
        assert isinstance(fDst, QgsField)

        setup = fSrc.editorWidgetSetup()
        if QgsGui.instance().editorWidgetRegistry().factory(setup.type()).supportsField(vectorLayer, idx):
            vectorLayer.setEditorWidgetSetup(idx, setup)
        else:
            s = ""
    vectorLayer.updatedFields.emit()


def compare_dicts(d1, d2, path=""):
    """
    Compares two dictionaries recursively and prints their differences.
    """
    for key in d1.keys() | d2.keys():  # Union of keys from both dicts
        current_path = f"{path}.{key}" if path else key

        if key not in d1:
            print(f"Added: {current_path} = {d2[key]}")
        elif key not in d2:
            print(f"Removed: {current_path} = {d1[key]}")
        else:
            val1 = d1[key]
            val2 = d2[key]

            if isinstance(val1, dict) and isinstance(val2, dict):
                compare_dicts(val1, val2, current_path)
            elif isinstance(val1, list) and isinstance(val2, list):
                if len(val1) != len(val2):
                    print(f'# Changed lists: {current_path}')
                else:
                    for i, (v1, v2) in enumerate(zip(val1, val2)):
                        if v1 != v2:
                            cpath = f'{current_path}[{i}]'
                            if isinstance(v1, dict):
                                compare_dicts(v1, v2)
                            else:
                                print(f'# Changed {cpath} {v1} -> {v2}')

            elif val1 != val2:
                print(f"# Changed: {current_path}: {val1} -> {val2}")


def check_package(name, package=None, stop_on_error=False):
    try:
        importlib.import_module(name, package)
    except Exception as e:
        if stop_on_error:
            raise Exception('Unable to import package/module "{}"'.format(name))
        return False
    return True


def qgsFieldAttributes2List(attributes: List[Any]) -> List[Any]:
    """Returns a list of attributes with None instead of NULL or QVariant.NULL"""
    r = QVariant(None)
    return [None if v == r else v for v in attributes]


def qgsFields2str(qgsFields: QgsFields) -> str:
    """Converts the QgsFields definition into a pickable string"""
    infos = []
    for field in qgsFields:
        assert isinstance(field, QgsField)
        # info = [field.name(), field.type(), field.typeName(), field.length(), field.precision(),
        # field.comment(), field.subType()]
        info = dict(name=field.name(),
                    type=field.type(),
                    typeName=field.typeName(),
                    length=field.length(),
                    precission=field.precision(),
                    comment=field.comment(),
                    subType=field.subType(),
                    editorWidget=field.editorWidgetSetup().type())
        infos.append(info)
    return json.dumps(infos)


def str2QgsFields(fieldString: str) -> QgsFields:
    """Converts the string from qgsFields2str into a QgsFields collection"""
    fields = QgsFields()

    infos = json.loads(fieldString)
    assert isinstance(infos, list)
    for info in infos:
        field = QgsField(name=info['name'],
                         type=info['type'],
                         typeName=info['typeName'],
                         len=info['length'],
                         prec=info['precission'],
                         comment=info['comment'],
                         subType=info['subType']
                         )
        field.setEditorWidgetSetup(QgsEditorWidgetSetup(info['editorWidget'], {}))
        fields.append(field)
    return fields


def as_py_value(value, datatype: Qgis.DataType):
    """
    Converts values into a corresponding python_type
    :param value:
    :param datatype:
    :return:
    """
    if value in [None, QVariant()]:
        return None
    if datatype in [Qgis.Byte, Qgis.Int16, Qgis.Int32, Qgis.UInt16, Qgis.UInt32]:
        return int(value)
    elif datatype in [Qgis.Float32, Qgis.Float64, Qgis.CFloat32, Qgis.CFloat64]:
        return float(value)
    return value


def zipdir(pathDir, pathZip):
    """
    :param pathDir: directory to compress
    :param pathZip: path to new zipfile
    """
    # thx to https://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory
    """
    import zipfile
    assert os.path.isdir(pathDir)
    zipf = zipfile.ZipFile(pathZip, 'w', zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(pathDir):
        for file in files:
            zipf.write(os.path.join(root, file))
    zipf.close()
    """
    relroot = os.path.abspath(os.path.join(pathDir, os.pardir))
    with zipfile.ZipFile(pathZip, "w", zipfile.ZIP_DEFLATED) as zip:
        for root, dirs, files in os.walk(pathDir):
            # add directory (needed for empty dirs)
            zip.write(root, os.path.relpath(root, relroot))
            for file in files:
                filename = os.path.join(root, file)
                if os.path.isfile(filename):  # regular files only
                    arcname = os.path.join(os.path.relpath(root, relroot), file)
                    zip.write(filename, arcname)


def scanResources(path=':') -> Iterator[str]:
    """
    Returns all resource-paths of the Qt Resource system
    :param path:
    :type path:
    :return:
    :rtype:
    """
    D = QDirIterator(path)
    while D.hasNext():
        entry = D.next()
        if D.fileInfo().isDir():
            yield from scanResources(path=entry)
        elif D.fileInfo().isFile():
            yield D.filePath()


def displayBandNames(rasterSource, bands=None, leadingBandNumber=True):
    """
    Returns a list of readable band names from a raster source.
    Will use "Band 1"  ff no band name is defined.
    :param rasterSource: QgsRasterLayer | gdal.DataSource | str
    :param bands:
    :return:
    """

    if isinstance(rasterSource, str):
        return displayBandNames(QgsRasterLayer(rasterSource), bands=bands, leadingBandNumber=leadingBandNumber)
    if isinstance(rasterSource, QgsRasterLayer):
        if not rasterSource.isValid():
            return None
        else:
            return displayBandNames(rasterSource.dataProvider(), bands=bands, leadingBandNumber=leadingBandNumber)
    if isinstance(rasterSource, gdal.Dataset):
        # use gdal.Band.GetDescription() for band name
        results = []
        if bands is None:
            bands = range(1, rasterSource.RasterCount + 1)
        for band in bands:
            b = rasterSource.GetRasterBand(band)
            name = b.GetDescription()
            if len(name) == 0:
                name = 'Band {}'.format(band)
            if leadingBandNumber:
                name = '{}:{}'.format(band, name)
            results.append(name)
        return results
    if isinstance(rasterSource, QgsRasterDataProvider):
        if rasterSource.name() == 'gdal':
            ds = gdal.Open(rasterSource.dataSourceUri())
            return displayBandNames(ds, bands=bands, leadingBandNumber=leadingBandNumber)
        else:
            # in case of WMS and other data providers use QgsRasterRendererWidget::displayBandName
            results = []
            if bands is None:
                bands = range(1, rasterSource.bandCount() + 1)
            for band in bands:
                name = rasterSource.generateBandName(band)
                colorInterp = '{}'.format(rasterSource.colorInterpretationName(band))
                if colorInterp != 'Undefined':
                    name += '({})'.format(colorInterp)
                if leadingBandNumber:
                    name = '{}:{}'.format(band, name)
                results.append(name)

            return results

    return None


def rendererXML(renderer: QgsRasterRenderer, root: str = 'root') -> QDomDocument:
    doc = QDomDocument()
    root = doc.createElement(root)
    renderer.writeXml(doc, root)
    doc.appendChild(root)
    return doc


def equalRasterRenderer(renderer1: QgsRasterRenderer, renderer2: QgsRasterRenderer) -> bool:
    if renderer1 == renderer2:
        return True
    if renderer1.type() != renderer2.type():
        return False

    # same type? go into the details
    xml1 = rendererXML(renderer1)
    xml2 = rendererXML(renderer2)
    return xml1.toByteArray() == xml2.toByteArray()


def defaultBands(dataset) -> List[int]:
    """
    Returns a list of 3 default bands.
    Band numbers start counting with 1
    :param dataset:
    :return:
    """
    if isinstance(dataset, str):
        return defaultBands(gdal.Open(dataset))
    elif isinstance(dataset, QgsRasterDataProvider):
        return defaultBands(dataset.dataSourceUri())
    elif isinstance(dataset, QgsRasterLayer) and \
            isinstance(dataset.dataProvider(), QgsRasterDataProvider) and \
            dataset.dataProvider().name() == 'gdal':
        return defaultBands(dataset.source())
    elif isinstance(dataset, gdal.Dataset):

        # check ENVI style metadata default band definition
        for k in ['default_bands', 'default bands']:
            db = dataset.GetMetadataItem(k, str('ENVI'))
            if db is not None:
                db = [int(n) for n in re.findall(r'\d+', db)]
                return db

        db = [0, 0, 0]
        cis = [gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand]
        for b in range(dataset.RasterCount):
            band = dataset.GetRasterBand(b + 1)
            assert isinstance(band, gdal.Band)
            ci = band.GetColorInterpretation()
            if ci in cis:
                db[cis.index(ci)] = b + 1
        if 0 not in db:
            return db

        rl = QgsRasterLayer(dataset.GetDescription())
        defaultRenderer = rl.renderer()
        if isinstance(defaultRenderer, QgsRasterRenderer):
            db = defaultRenderer.usesBands()
            if len(db) == 0:
                return [1, 2, 3]
            if len(db) > 3:
                db = db[0:3]
        return db

    else:
        return [1, 1, 1]


def bandClosestToWavelength(dataset, wl, wl_unit: str = 'nm') -> int:
    """
    Returns the band index of an image raster closest to wavelength `wl`.
    :param dataset: str | gdal.Dataset
    :param wl: wavelength to search the closed band for
    :param wl_unit: unit of wavelength. Default = nm
    :return: band index (starting with 0) | defaults to 0, e.g. if wavelength information is not provided
    """
    if isinstance(wl, str):
        assert wl.upper() in LUT_WAVELENGTH.keys(), wl
        return bandClosestToWavelength(dataset, LUT_WAVELENGTH[wl.upper()], wl_unit='nm')
    else:
        try:
            wl = float(wl)
            ds_wl, ds_wlu = parseWavelength(dataset)

            if ds_wl is None or ds_wlu is None:
                return 0

            if ds_wlu != wl_unit:
                wl = UnitLookup.convertLengthUnit(wl, wl_unit, ds_wlu)
            return int(np.argmin(np.abs(ds_wl - wl)))
        except Exception:
            pass
    return 0


def parseBadBandList(dataset) -> List[int]:
    """
    Returns the bad-band-list if it is specified explicitly
    :param dataset:
    :type dataset:
    :return: list of booleans. True = valid band, False = excluded / bad band
    :rtype:
    """
    bbl = None

    sp = QgsRasterLayerSpectralProperties.fromRasterLayer(dataset)
    bbl = sp.badBands()
    return bbl

    try:
        dataset = gdalDataset(dataset)
    except Exception:
        return None
        pass

    if not isinstance(dataset, gdal.Dataset):
        return None

    # 1. search for ENVI style definition of band band list
    bblStr1 = dataset.GetMetadataItem('bbl')
    bblStr2 = dataset.GetMetadataItem('bbl', 'ENVI')

    for bblStr in [bblStr1, bblStr2]:
        if isinstance(bblStr, str) and len(bblStr) > 0:
            parts = bblStr.split(',')
            if len(parts) == dataset.RasterCount:
                bbl = [int(p) for p in parts]

    return bbl


def parseFWHM(dataset) -> np.ndarray:
    """
    Returns the full width half maximum
    :param dataset:
    :return:
    """
    sp = QgsRasterLayerSpectralProperties.fromRasterLayer(dataset)
    fwhm = sp.fwhm()
    for v in fwhm:
        if v is not None:
            return np.asarray(fwhm)
    else:
        return None

    try:
        dataset = gdalDataset(dataset)
    except Exception:
        return None

    key_positions = [('fwhm', None),
                     ('fwhm', 'ENVI')]

    if isinstance(dataset, gdal.Dataset):
        for key, domain in key_positions:
            values = dataset.GetMetadataItem(key, domain)
            if isinstance(values, str):
                values = re.sub('[{}]', '', values).strip()
                try:
                    values = np.fromstring(values, sep=',', count=dataset.RasterCount)
                    if len(values) == dataset.RasterCount:
                        return values
                except Exception:
                    pass

        # search band by band
        values = []
        for b in range(dataset.RasterCount):
            band: gdal.Band = dataset.GetRasterBand(b + 1)
            for key, domain in key_positions:
                value = dataset.GetMetadataItem(key, domain)
                if value not in ['', None]:
                    values.append(value)
                    break
        if len(values) == dataset.RasterCount:
            return np.asarray(values)
    return None


def checkWavelength(key: str, values: str, expected: int = 1) -> np.ndarray:
    wl: np.ndarray = None
    if re.search(r'^(center[ _]*)?wavelengths?$', key, re.I):
        # remove trailing / ending { } and whitespace
        values = re.sub('[{}]', '', values).strip()
        if ',' not in values:
            sep = ' '
        else:
            sep = ','
        try:
            wl = np.asarray(values.split(sep), dtype=float)
            if len(wl) != expected:
                wl = None
            # wl = np.fromstring(values, count=expected, sep=sep)
        except ValueError as exV:
            pass
        except Exception as ex:
            pass
    return wl


def checkWavelengthUnit(key: str, value: str) -> str:
    wlu: str = None
    value = value.strip()
    if re.search(r'^wavelength[ _]?units?', key, re.I):
        # metric length units
        wlu = UnitLookup.baseUnit(value)

        if wlu is not None:
            return wlu

        if re.search(r'^Wavenumber$', value, re.I):
            wlu = '-'
        elif re.search(r'^GHz$', value, re.I):
            wlu = 'GHz'
        elif re.search(r'^MHz$', value, re.I):
            wlu = 'MHz'
        # date / time units
        elif re.search(r'^(Date|DTG|Date[_ ]?Time[_ ]?Group|Date[_ ]?Stamp|Time[_ ]?Stamp)$', value, re.I):
            wlu = 'DateTime'
        elif re.search(r'^Decimal[_ ]?Years?$', value, re.I):
            wlu = 'DecimalYear'
        elif re.search(r'^(Seconds?|s|secs?)$', value, re.I):
            wlu = 's'
        elif re.search(r'^Index$', value, re.I):
            wlu = None
        else:
            wlu = None
    return wlu


def parseWavelength(dataset) -> Tuple[np.ndarray, str]:
    """
    Returns the wavelength + wavelength unit of a raster
    :param dataset:
    :return: (wl, wl_u) or (None, None), if not existing
    """

    sp = QgsRasterLayerSpectralProperties.fromRasterLayer(dataset)
    wl = np.asarray(sp.wavelengths())
    wlu = sp.wavelengthUnits()
    if len(wl) > 0 and len(wlu) > 0:
        return wl, wlu[0]
    else:
        return None, None

    # try to get wavelength from provider

    if isinstance(dataset, QgsRasterLayer):

        # temporary workaround, as it uses none-QGIS API
        # will re replaces with future QEP specification of remote-sensing specific raster metadata
        provider: QgsRasterDataProvider = dataset.dataProvider()

        # note that wavelength() is only available for custom provider like EE
        if hasattr(provider, 'wavelength'):
            wl = np.array([provider.wavelength(bandNo) for bandNo in range(1, provider.bandCount() + 1)])
            wlu = 'Nanometers'
            return wl, wlu

    def sort_domains(domains) -> List[str]:
        if not isinstance(domains, list):
            domains = []
        return sorted(domains, key=lambda n: n != ['ENVI'])

    try:
        dataset = gdalDataset(dataset)
    except Exception:
        return None, None

    if isinstance(dataset, gdal.Dataset):
        # 1. check on raster level
        for domain in sort_domains(dataset.GetMetadataDomainList()):
            # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html for supported wavelength units

            mdDict = dataset.GetMetadata_Dict(domain)

            domainWLU: str = None
            domainWL: np.ndarray = None
            # search domain
            for key, values in mdDict.items():
                if domainWL is None:
                    domainWL = checkWavelength(key, values, expected=dataset.RasterCount)
                if domainWLU is None:
                    domainWLU = checkWavelengthUnit(key, values)

            if isinstance(domainWL, np.ndarray) and isinstance(domainWLU, str):
                if domain == 'FORCE' and domainWLU == 'DecimalYear':
                    # make decimal-year values leap-year sensitive
                    domainWL = convertDateUnit(datetime64(domainWL, dpy=365), 'DecimalYear')

                if len(domainWL) > dataset.RasterCount:
                    domainWL = domainWL[0:dataset.RasterCount]

                return domainWL, domainWLU

        # 2. check on band level. collect wl from each single band
        # first domain that defines wl and wlu is prototype domain for all other bands

        wl = []  # list of wavelength values
        wlu: str = None  # wavelength unit string
        wlDomain: str = None  # the domain in which the WL and WLU are defined
        wlKey: str = None  # key that stores the wavelength value
        wluKey: str = None  # key that stores the wavelength unit

        for b in range(dataset.RasterCount):
            band: gdal.Band = dataset.GetRasterBand(b + 1)
            if b == 0:
                for domain in sort_domains(band.GetMetadataDomainList()):
                    # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html for supported wavelength units
                    domainWL = domainWLU = None

                    mdDict = band.GetMetadata_Dict(domain)

                    for key, values in mdDict.items():
                        if domainWLU is None:
                            domainWLU = checkWavelengthUnit(key, values)
                            if domainWLU:
                                wluKey = key

                        if domainWL is None:
                            domainWL = checkWavelength(key, values, expected=1)
                            if isinstance(domainWL, np.ndarray):
                                wlKey = key

                    if isinstance(domainWL, np.ndarray) and isinstance(domainWLU, str):
                        wlDomain = domain
                        wlu = domainWLU
                        wl.append(domainWL[0])

                if len(wl) == 0:
                    # we did not found a WL + WLU for the 1st band. stop searching and return
                    return None, None
            else:
                bandWLU = checkWavelengthUnit(wluKey, band.GetMetadataItem(wluKey, wlDomain))
                bandWL = checkWavelength(wlKey, band.GetMetadataItem(wlKey, wlDomain), expected=1)

                if bandWLU != wlu or bandWL is None:
                    print(f'{dataset.GetDescription()}: inconsistent use of metadata key {wluKey} per band')
                    return None, None
                wl.append(bandWL[0])

        if len(wl) == 0:
            return None, None

        wl = np.asarray(wl)
        if domain == 'FORCE' and wlu == 'DecimalYear':
            # make decimal-year values leap-year sensitive
            wl = UnitLookup.convertDateUnit(datetime64(wl, dpy=365), 'DecimalYear')

        return wl, wlu
    else:
        return None, None


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def qgisToNumpyDataType(t: Qgis.DataType) -> np.dtype:
    return QGIS2NUMPY_DATA_TYPES.get(t, None)


def numpyToQgisDataType(t) -> Qgis.DataType:
    if isinstance(t, np.dtype):
        t = t.type
    return NUMPY2QGIS_DATA_TYPES.get(t, Qgis.DataType.UnknownDataType)


def qgisAppQgisInterface() -> QgisInterface:
    """
    Returns the QgisInterface of the QgisApp in case everything was started from within the QGIS Main Application
    :return: QgisInterface | None in case the qgis.utils.iface points to another
             QgisInterface (e.g. the EnMAP-Box itself)
    """
    try:
        import qgis.utils
        if not isinstance(qgis.utils.iface, QgisInterface):
            return None
        mainWindow = qgis.utils.iface.mainWindow()
        if not isinstance(mainWindow, QMainWindow) or mainWindow.objectName() != 'QgisApp':
            return None
        return qgis.utils.iface
    except ImportError:
        return None


def chunks(iterable, size=10):
    """
    Returns list or generator output as chunks
    Example taken from: https://stackoverflow.com/a/24527424
    :param iterable:
    :param size:
    :return:
    """
    iterator = iter(iterable)
    for first in iterator:
        yield itertools.chain([first], itertools.islice(iterator, size - 1))


def nodeXmlString(node: QDomElement, indent: int = 1) -> str:
    """
    Represent the QDomElement as string
    :param node: QDomElement
    :param indent:
    :return: str
    """
    if isinstance(node, QDomDocument):
        node = node.documentElement()
    assert isinstance(node, QDomElement)
    doc = QDomDocument()
    doc.createElement('root')  # curious, we just need to create it, without adding as child
    doc.appendChild(node.cloneNode(True).toElement())
    return doc.toString(indent=indent)


def getDOMAttributes(elem) -> dict:
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[attr.nodeName()] = attr.nodeValue()
    return values


def fileSizeString(num, suffix='B', div=1000) -> str:
    """
    Returns a human-readable file size string.
    thanks to Fred Cirera
    http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    :param num: number in bytes
    :param suffix: 'B' for bytes by default.
    :param div: divisor of num, 1000 by default.
    :return: the file size string
    """
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < div:
            return "{:3.1f}{}{}".format(num, unit, suffix)
        num /= div
    return "{:.1f} {}{}".format(num, unit, suffix)


def geo2pxF(geo: QgsPointXY, gt: Union[list, np.ndarray, tuple]) -> QPointF:
    """
    Returns the pixel position related to a Geo-Coordinate in floating point precision.
    :param geo: Geo-Coordinate as QgsPoint
    :param gt: GDAL Geo-Transformation tuple, as described in https://gdal.org/user/raster_data_model.html
    :return: pixel position as QPointF
    """
    assert isinstance(geo, QgsPointXY)
    # see https://gdal.org/user/raster_data_model.html#affine-geotransform
    px = (geo.x() - gt[0]) / gt[1]  # x pixel
    py = (geo.y() - gt[3]) / gt[5]  # y pixel
    return QPointF(px, py)


def geo2px(geo: QgsPointXY, gt: Union[list, np.ndarray, tuple]) -> QPoint:
    """
    Returns the pixel position related to a Geo-Coordinate as integer number.
    Floating-point coordinate are cast to integer coordinate, e.g. the pixel
    coordinate (0.815, 23.42) is returned as (0,23)
    :param geo: Geo-Coordinate as QgsPointXY
    :param gt: GDAL Geo-Transformation tuple, as described in
               https://gdal.org/user/raster_data_model.html#affine-geotransform or
          gdal.Dataset or QgsRasterLayer
    :return: pixel position as QPpint
    """

    if isinstance(gt, QgsRasterLayer):
        return geo2px(geo, layerGeoTransform(gt))
    elif isinstance(gt, gdal.Dataset):
        return geo2px(gt.GetGeoTransform())
    else:
        px = geo2pxF(geo, gt)
        return QPoint(int(px.x()), int(px.y()))


def check_vsimem() -> bool:
    """
    Checks if the gdal/ogr vsimem is available to the QGIS API
    (might be not the case for QGIS
    :return: bool
    """
    result = False
    try:
        from osgeo import gdal
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer
        import uuid
        # create an 2x2x1 in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        assert isinstance(driver, gdal.Driver)
        path = f'/vsimem/inmemorytestraster.{uuid.uuid4()}.tif'

        dataSet: gdal.Dataset = driver.Create(path, 2, 2, bands=1, eType=gdal.GDT_Byte)
        assert isinstance(dataSet, gdal.Dataset)
        drv: gdal.Driver = dataSet.GetDriver()
        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        assert isinstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        assert isinstance(layer, QgsRasterLayer)
        result = layer.isValid()
        del layer
        drv.Delete(path)

    except Exception as ex:
        return False
    return result


def layerGeoTransform(rasterLayer: QgsRasterLayer) -> Tuple[float, float, float, float, float, float]:
    """
    Returns the geo-transform vector from a QgsRasterLayer.
    See https://gdal.org/user/raster_data_model.html
    :param rasterLayer: QgsRasterLayer
    :return: [array]
    """
    assert isinstance(rasterLayer, QgsRasterLayer)
    ext = rasterLayer.extent()
    x0 = ext.xMinimum()
    y0 = ext.yMaximum()

    gt = (x0, rasterLayer.rasterUnitsPerPixelX(), 0, y0,
          0, -1 * rasterLayer.rasterUnitsPerPixelY())
    return gt


def osrSpatialReference(input) -> osr.SpatialReference:
    """
    Returns the input as osr.SpatialReference
    :param input: any
    :return: osr.SpatialReference
    """
    srs: osr.SpatialReference = osr.SpatialReference()
    if isinstance(input, osr.SpatialReference):
        return input
    if isinstance(input, gdal.Dataset):
        return input.GetSpatialRef()
    if isinstance(input, ogr.Layer):
        return input.GetSpatialRef()
    if isinstance(input, ogr.DataSource):
        return osrSpatialReference(input.GetLayer(0))
    if isinstance(input, gdal.Band):
        return osrSpatialReference(input.GetDataset())
    if isinstance(input, QgsMapLayer):
        return osrSpatialReference(input.crs())

    if isinstance(input, QgsCoordinateReferenceSystem):
        srs.ImportFromWkt(input.toWkt())
    elif isinstance(input, str):
        wkt = osr.GetUserInputAsWKT(input)
        if isinstance(wkt, str):
            srs.ImportFromWkt(wkt)
    else:
        raise Exception(f'Unable to convert {str(input)} to osr.SpatialReference')

    return srs


def px2geocoordinatesV2(layer: QgsRasterLayer,
                        xcoordinates: np.ndarray = None,
                        ycoordinates: np.ndarray = None,
                        subpixel_pos: float = 0.5,
                        subpixel_pos_x: float = None,
                        subpixel_pos_y: float = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns the pixel centers as coordinate in a raster layer's CRS
    :param layer: QgsRasterLayer
    :param px: QPoint pixel position (0,0) = 1st pixel
    :return: geo_x, geo_y numpy arrays
    """
    assert isinstance(layer, QgsRasterLayer) and layer.isValid()
    # assert 0 <= px.x() < layer.width()
    # assert 0 <= px.y() < layer.height()
    assert 0 <= subpixel_pos <= 1.0

    if xcoordinates is None:
        xcoordinates = np.arange(layer.width())

    if ycoordinates is None:
        ycoordinates = np.arange(layer.height())

    if subpixel_pos_x is None:
        subpixel_pos_x = subpixel_pos

    if subpixel_pos_y is None:
        subpixel_pos_y = subpixel_pos

    assert 0 <= subpixel_pos_x <= 1.0
    assert 0 <= subpixel_pos_y <= 1.0

    ext: QgsRectangle = layer.extent()

    resX = layer.extent().width() / layer.width()
    resY = layer.extent().height() / layer.height()

    geo_x = ext.xMinimum() + (xcoordinates + subpixel_pos_x) * resX
    geo_y = ext.yMaximum() - (ycoordinates + subpixel_pos_y) * resY

    return geo_x, geo_y


def px2geocoordinates(raster, target_srs=None, pxCenter: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns the pixel positions as geo-coordinates
    :param pxCenter: bool, set True to return coordinates in pixel center
    :param raster: any, must be readable as gdal.Dataset
    :param target_srs: any, must be convertable to osr.SpatialReference
    :return:
    """
    # returns pixel coordinates in arrays with the x and y pixel coodinates in target_srs

    raster: gdal.Dataset = gdalDataset(raster)
    if target_srs:
        target_srs = osrSpatialReference(target_srs)
    else:
        target_srs = osrSpatialReference(raster)

    gt = raster.GetGeoTransform()
    indices = np.indices((raster.RasterYSize, raster.RasterXSize))
    if pxCenter:
        indices = indices + 0.5

    geo_x = gt[0] + indices[1, :, :] * gt[1] + indices[1, :, :] * gt[2]
    geo_y = gt[3] + indices[0, :, :] * gt[4] + indices[0, :, :] * gt[5]

    if not target_srs.IsSame(raster.GetSpatialRef()):
        drv = gdal.GetDriverByName('MEM')
        dsMEM: gdal.Dataset = drv.Create('', raster.RasterXSize, raster.RasterYSize, 3, gdal.GDT_Float64)
        dsMEM.GetRasterBand(1).WriteArray(geo_x)
        dsMEM.GetRasterBand(2).WriteArray(geo_y)

        transformer = gdal.Transformer(None, None, [f'SRC_SRS={raster.GetSpatialRef().ExportToProj4()}',
                                                    f'DST_SRS={target_srs.ExportToProj4()}'])
        status = transformer.TransformGeolocations(dsMEM.GetRasterBand(1),
                                                   dsMEM.GetRasterBand(2),
                                                   dsMEM.GetRasterBand(3))
        if status != ogr.OGRERR_NONE:
            raise Exception(f'Error transforming coordinates: {gdal.GetLastErrorMsg()}')

        geo_x = dsMEM.GetRasterBand(1).ReadAsArray()
        geo_y = dsMEM.GetRasterBand(2).ReadAsArray()
        del dsMEM

    return geo_x, geo_y


def px2geo(px: QPoint, gt, pxCenter: bool = True) -> QgsPointXY:
    """
    Converts a pixel coordinate into a geo-coordinate
    :param px: QPoint() with pixel coordinates
    :param gt: geo-transformation
    :param pxCenter: True (default) to return geo-coordinate of pixel center,
                     False to return the pixel's upper-left edge.
    :return:
    """

    # see https://gdal.org/user/raster_data_model.html

    gx = gt[0] + px.x() * gt[1] + px.y() * gt[2]
    gy = gt[3] + px.x() * gt[4] + px.y() * gt[5]

    if pxCenter:
        p2 = px2geo(QPoint(int(px.x() + 1), int(px.y() + 1)), gt, pxCenter=False)

        gx = 0.5 * (gx + p2.x())
        gy = 0.5 * (gy + p2.y())

    return QgsPointXY(gx, gy)


class HashablePointF(QPointF):
    """
        A QPointF that can be hashed, e.g. to be used in a set
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def __hash__(self):
        return hash((self.x(), self.y()))

    def __eq__(self, other):
        return self.x() == other.x() and self.y() == other.y()


class HashablePoint(QPoint):
    """
    A QPoint that can be hashed, e.g. to be used in a set
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def __hash__(self):
        return hash((self.x(), self.y()))

    def __eq__(self, other):
        return self.x() == other.x() and self.y() == other.y()


class HashableRectangle(QgsRectangle):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def __hash__(self):
        return hash((self.xMinimum(), self.yMinimum(), self.xMaximum(), self.yMaximum()))


class HashableRect(QRect):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def __hash__(self):
        return hash((self.x(), self.y(), self.width(), self.height()))


def rasterLayerMapToPixel(layer: QgsRasterLayer) -> QgsMapToPixel:
    assert isinstance(layer, QgsRasterLayer)
    c = layer.extent().center()

    m2p = QgsMapToPixel(layer.rasterUnitsPerPixelX(),
                        c.x(), c.y(),
                        layer.width(), layer.height(),
                        0)
    return m2p


class SpatialPoint(QgsPointXY):
    """
    Object to keep QgsPoint and QgsCoordinateReferenceSystem together
    """

    @staticmethod
    def readXml(node: QDomNode):
        node_crs = node.firstChildElement('SpatialPointCrs')
        crs = QgsCoordinateReferenceSystem()
        if not node_crs.isNull():
            crs.readXml(node_crs)
        point = QgsGeometry.fromWkt(node.firstChildElement('SpatialPoint').text()).asPoint()
        return SpatialPoint(crs, point)

    @staticmethod
    def fromMapCanvasCenter(mapCanvas: QgsMapLayer):
        assert isinstance(mapCanvas, QgsMapCanvas)
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialPoint(crs, mapCanvas.center())

    @staticmethod
    def fromMapLayerCenter(mapLayer: QgsMapLayer):
        assert isinstance(mapLayer, QgsMapLayer) and mapLayer.isValid()
        crs = mapLayer.crs()
        return SpatialPoint(crs, mapLayer.extent().center())

    @staticmethod
    def fromSpatialExtent(spatialExtent):
        assert isinstance(spatialExtent, SpatialExtent)
        crs = spatialExtent.crs()
        return SpatialPoint(crs, spatialExtent.center())

    @staticmethod
    def fromPixelPosition(rasterLayer: QgsRasterLayer,
                          x: Union[int, float, QPoint, QPointF], y: Optional[Union[int, float]] = None):
        """
        Returns the coordinate of pixel at position x,y (upper left). Use x+0.5, y+0.5 for pixel center coordinate.
        :param rasterLayer:
        :param x:
        :param y:
        :return:
        """
        assert isinstance(rasterLayer, QgsRasterLayer)
        if isinstance(x, (QPoint, QPointF)):
            y = x.y()
            x = x.x()
        assert isinstance(x, (int, float))
        assert isinstance(y, (int, float))

        mapUnitsPerPixel = rasterLayer.rasterUnitsPerPixelX()
        ext = rasterLayer.extent()
        center = ext.center()
        rotation = 0
        m2p = QgsMapToPixel(mapUnitsPerPixel,
                            center.x(),
                            center.y(),
                            rasterLayer.width(),
                            rasterLayer.height(),
                            rotation)

        geoPt = m2p.toMapCoordinatesF(x, y)
        return SpatialPoint(rasterLayer.crs(), geoPt)

    def __init__(self, crs, *args):
        if isinstance(crs, SpatialPoint):
            crs, args = crs.crs(), [crs]

        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialPoint, self).__init__(*args)
        self.mCrs = crs

    def __hash__(self):
        return hash(str(self))

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def toPixel(self, layer: QgsRasterLayer) -> QPoint:
        assert isinstance(layer, QgsRasterLayer)

        pt = self.toCrs(layer.crs())
        if not isinstance(pt, SpatialPoint):
            return None

        c = layer.extent().center()
        m2p = QgsMapToPixel(layer.rasterUnitsPerPixelX(),
                            c.x(), c.y(),
                            layer.width(),
                            layer.height(),
                            0)

        px = m2p.transform(pt)

        return QPoint(math.floor(px.x()), math.floor(px.y()))

    def toPixelPosition(self, rasterDataSource, allowOutOfRaster=False) -> QPoint:
        """
        Returns the pixel position of this SpatialPoint within the rasterDataSource
        :param rasterDataSource: gdal.Dataset
        :param allowOutOfRaster: set True to return out-of-raster pixel positions, e.g. QPoint(-1,0)
        :return: the pixel position as QPoint
        """
        lyr: QgsRasterLayer = qgsRasterLayer(rasterDataSource)
        if not lyr.isValid():
            return None

        geoPt = self.toCrs(lyr.crs())
        if not isinstance(geoPt, SpatialPoint):
            return None

        mapUnitsPerPixel = lyr.rasterUnitsPerPixelX()
        center = lyr.extent().center()
        rotation = 0
        m2p = QgsMapToPixel(mapUnitsPerPixel,
                            center.x(),
                            center.y(),
                            lyr.width(),
                            lyr.height(),
                            rotation)
        pxPt: QgsPointXY = m2p.transform(geoPt)
        pxPt: QPoint = QPoint(int(pxPt.x()), int(pxPt.y()))
        if (not allowOutOfRaster) and not (0 <= pxPt.x() < lyr.width() and 0 <= pxPt.y() < lyr.height()):
            return None
        else:
            return pxPt

    def writeXml(self, node: QDomNode, doc: QDomDocument):
        node_geom = doc.createElement('SpatialPoint')
        node_geom.appendChild(doc.createTextNode(self.asWkt()))
        node_crs = doc.createElement('SpatialPointCrs')
        self.crs().writeXml(node_crs, doc)
        node.appendChild(node_geom)
        node.appendChild(node_crs)

    def toCrs(self, crs) -> Optional['SpatialPoint']:
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        pt = QgsPointXY(self)

        if self.mCrs != crs:
            pt = saveTransform(pt, self.mCrs, crs)

        return SpatialPoint(crs, pt) if pt else None

    def __reduce_ex__(self, protocol):
        return self.__class__, (self.crs().toWkt(), self.x(), self.y()), {}

    def __eq__(self, other):
        if not isinstance(other, SpatialPoint):
            return False
        b = self.x() == other.x() \
            and self.y() == other.y() \
            and self.crs() == other.crs()
        return b

    def __copy__(self):
        return SpatialPoint(self.crs(), self.x(), self.y())

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return '{} {} {}'.format(self.x(), self.y(), self.crs().authid())


def px2spatialPoint(rasterInterface: Union[QgsRasterInterface, QgsRasterLayer],
                    px: QPoint,
                    subpixel_pos: float = 0.5,
                    subpixel_pos_x: float = None,
                    subpixel_pos_y: float = None) -> SpatialPoint:
    """
    Returns the pixel center as coordinate in a raster layer's CRS
    :param rasterInterface: QgsRasterLayer
    :param px: QPoint pixel position (0,0) = 1st pixel
    :return: SpatialPoint
    """
    if isinstance(rasterInterface, QgsRasterLayer):
        assert rasterInterface.isValid()
        rasterInterface = rasterInterface.dataProvider()

    assert isinstance(rasterInterface, QgsRasterInterface)

    # assert 0 <= px.x() < layer.width()
    # assert 0 <= px.y() < layer.height()
    assert 0 <= subpixel_pos <= 1.0

    if subpixel_pos_x is None:
        subpixel_pos_x = subpixel_pos

    if subpixel_pos_y is None:
        subpixel_pos_y = subpixel_pos

    assert 0 <= subpixel_pos_x <= 1.0
    assert 0 <= subpixel_pos_y <= 1.0

    ext: QgsRectangle = rasterInterface.extent()

    resX = rasterInterface.extent().width() / rasterInterface.xSize()
    resY = rasterInterface.extent().height() / rasterInterface.ySize()

    return SpatialPoint(rasterInterface.crs(),
                        ext.xMinimum() + (px.x() + subpixel_pos_x) * resX,
                        ext.yMaximum() - (px.y() + subpixel_pos_y) * resY)


def spatialPoint2px(layer: QgsRasterLayer, spatialPoint: Union[QgsPointXY, SpatialPoint]) -> Optional[QPoint]:
    """
    Converts a spatial point into a raster pixel coordinate
    :param layer:
    :param spatialPoint:
    :return:

    """
    if isinstance(spatialPoint, SpatialPoint):
        spatialPoint = spatialPoint.toCrs(layer.crs())
    assert isinstance(spatialPoint, QgsPointXY)
    assert isinstance(layer, QgsRasterLayer)
    ext = layer.extent()
    if layer.width() == 0 or layer.height() == 0:
        return None
    resX = layer.extent().width() / layer.width()
    resY = layer.extent().height() / layer.height()

    x = math.floor((spatialPoint.x() - ext.xMinimum()) / resX)
    y = math.floor((ext.yMaximum() - spatialPoint.y()) / resY)

    return QPoint(x, y)


def rasterBlockArray(block: QgsRasterBlock, masked: bool = False) -> Union[np.ndarray, np.ma.MaskedArray]:
    """
    Returns the content of a QgsRasterBlock as 2D numpy array
    :param block: QgsRasterBlock, the block to read values
    :param masked: bool: set True to return values in a numpy.ma.MaskedArray where mask = True if
                         block values area considered to be a no-data value

    :return: numpy.ndarray or numpy.ma.MaskedArray
    """
    dtype = QGIS2NUMPY_DATA_TYPES[block.dataType()]
    array = np.frombuffer(block.data(), dtype=dtype).reshape(block.height(), block.width())
    if masked:
        mask = np.zeros(array.shape, dtype=bool)
        if block.hasNoData():
            for col in range(block.width()):
                for row in range(block.height()):
                    mask[row, col] = block.isNoData(row, col)
        array: np.ma.MaskedArray = np.ma.array(array, mask=mask)
    return array


def featureBoundingBox(features) -> QgsRectangle:
    retval = QgsRectangle()
    retval.setNull()

    for feature in features:
        feature: QgsFeature
        if not feature.hasGeometry():
            continue
        r = feature.geometry().boundingBox()
        retval.combineExtentWith(r)
    if retval.width() == 0.0 or retval.height() == 0.0:
        if retval.xMinimum() == 0 and retval.yMinimum() == 0 and retval.xMaximum() == 0 and retval.yMaximum() == 0:
            retval.set(-1.0, -1.0, 1.0, 1.0)
    return retval


def findParent(qObject: QObject, parentType, checkInstance: bool = False):
    """

    Parameters
    ----------
    qObject
    parentType
    checkInstance

    Returns
    -------

    """
    parent = qObject.parent()
    if checkInstance:
        while parent is not None and not isinstance(parent, parentType):
            parent = parent.parent()
    else:
        while parent is not None and parent.__class__.__name__ != parentType.__name__:
            parent = parent.parent()
    return parent


def iconForFieldType(field: Union[QgsField, QgsVectorDataProvider.NativeType]) -> QIcon:
    """
    Returns an icon for field types, including own defined
    :return:
    """

    if isinstance(field, QgsVectorDataProvider.NativeType):
        field = QgsField(name='dummy',
                         type=field.mType,
                         typeName=field.mTypeName,
                         len=field.mMaxLen,
                         prec=field.mMaxPrec,
                         subType=field.mSubType)

    assert isinstance(field, QgsField)
    return QgsFields.iconForFieldType(field.type())


def createCRSTransform(src: QgsCoordinateReferenceSystem, dst: QgsCoordinateReferenceSystem):
    """

    :param src:
    :param dst:
    :return:
    """
    assert isinstance(src, QgsCoordinateReferenceSystem)
    assert isinstance(dst, QgsCoordinateReferenceSystem)
    t = QgsCoordinateTransform()
    t.setSourceCrs(src)
    t.setDestinationCrs(dst)
    return t


def saveTransform(geom: Union[QgsPointXY, QgsRectangle, Tuple[np.ndarray, np.ndarray]],
                  crs1: QgsCoordinateReferenceSystem,
                  crs2: QgsCoordinateReferenceSystem) -> Union[QgsPointXY, QgsRectangle]:
    """
    Transforms geometries from into another QgsCoordinateReferenceSystem
    :param geom: QgsGeometry
    :param crs1:
    :param crs2:
    :return:
    """
    assert isinstance(crs1, QgsCoordinateReferenceSystem)
    assert isinstance(crs2, QgsCoordinateReferenceSystem)

    transform = QgsCoordinateTransform(crs1, crs2, QgsProject.instance())

    result = None
    if isinstance(geom, QgsRectangle):
        if geom.isNull() or not geom.isFinite():
            return None

        try:
            rect = transform.transformBoundingBox(geom)
            result = SpatialExtent(crs2, rect)
        except Exception as ex:
            print(f'Can not transform from {crs1.description()} to {crs2.description()} '
                  f'on rectangle {geom}.\n{ex}')

    elif isinstance(geom, QgsPointXY):

        try:
            pt = transform.transform(geom)
            result = SpatialPoint(crs2, pt)
        except Exception as ex:
            print(f'Can not transform from {crs1.description()} to {crs2.description()} '
                  f'on QgsPointXY {geom}\n{ex}')

    elif isinstance(geom, tuple):

        xcoords, ycoords = geom
        shape = xcoords.shape
        assert xcoords.shape == ycoords.shape
        n = np.prod(xcoords.shape)
        results = [transform.transform(QgsPointXY(x, y))
                   for x, y in zip(xcoords.flatten(), ycoords.flatten())]
        xresults = np.asarray([r.x() for r in results])
        yresults = np.asarray([r.y() for r in results])

        result = (xresults.reshape(shape), yresults.reshape(shape))
    return result


def snapGeoCoordinates(coordinates: List[Union[QgsPointXY, QPointF]],
                       m2p: Union[QgsRasterLayer, QgsMapToPixel]) -> List[QgsPointXY]:
    if isinstance(m2p, QgsRasterLayer):
        c = m2p.extent().center()
        raster = QgsMapToPixel(m2p.rasterUnitsPerPixelX(),
                               c.x(), c.y(),
                               m2p.width(), m2p.height(),
                               0,
                               )
    assert isinstance(m2p, QgsMapToPixel)
    d = QgsVector(0.5 * m2p.mapUnitsPerPixel(),
                  -0.5 * m2p.mapUnitsPerPixel())
    snapped = []
    for c in coordinates:
        px = m2p.transform(c)
        geo = m2p.toMapCoordinates(int(px.x()), int(px.y())) + d
        snapped.append(geo)
    return snapped


def scaledUnitString(num: float,
                     infix: str = ' ',
                     suffix: str = 'B',
                     largest_si_prefix: str = None,
                     div: float = 1000):
    """
    Returns a human-readable file size string.
    thanks to Fred Cirera
    http://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    :param infix:
    :param num: number in bytes
    :param suffix: 'B' for bytes by default.
    :param div: divisor of num, 1000 by default.
    :return: the file size string
    """
    si_prefixes = ['', 'k', 'M', 'G', 'T', 'P', 'E', 'Z']
    if largest_si_prefix is None:
        largest_si_prefix = si_prefixes[-1]
    for si_prefix in si_prefixes:
        if abs(num) < div or si_prefix == largest_si_prefix:
            return "{:3.1f}{}{}{}".format(num, infix, si_prefix, suffix)
        num /= div
    return "{:.1f}{}{}{}".format(num, infix, si_prefix, suffix)


class SpatialExtent(QgsRectangle):
    """
    Object that combines a QgsRectangle and QgsCoordinateReferenceSystem
    """

    @staticmethod
    def readXml(node: QDomNode):
        node_crs = node.firstChildElement('SpatialExtentCrs')
        crs = QgsCoordinateReferenceSystem()
        if not node_crs.isNull():
            crs.readXml(node_crs)
        rectangle = QgsRectangle.fromWkt(node.firstChildElement('SpatialExtent').text())
        return SpatialExtent(crs, rectangle)

    @staticmethod
    def fromMapCanvas(mapCanvas, fullExtent: bool = False):
        assert isinstance(mapCanvas, QgsMapCanvas)

        if fullExtent:
            extent = mapCanvas.fullExtent()
        else:
            extent = mapCanvas.extent()
        crs = mapCanvas.mapSettings().destinationCrs()
        return SpatialExtent(crs, extent)

    @staticmethod
    def world():
        crs = QgsCoordinateReferenceSystem('EPSG:4326')
        ext = QgsRectangle(-180, -90, 180, 90)
        return SpatialExtent(crs, ext)

    @staticmethod
    def fromRasterSource(pathSrc):
        ds = gdalDataset(pathSrc)
        assert isinstance(ds, gdal.Dataset)
        ns, nl = ds.RasterXSize, ds.RasterYSize
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        xValues = []
        yValues = []
        for x in [0, ns]:
            for y in [0, nl]:
                px = px2geo(QPoint(x, y), gt, pxCenter=False)
                xValues.append(px.x())
                yValues.append(px.y())

        return SpatialExtent(crs, min(xValues), min(yValues),
                             max(xValues), max(yValues))

    @staticmethod
    def fromLayer(mapLayer):
        assert isinstance(mapLayer, QgsMapLayer)
        extent = mapLayer.extent()
        crs = mapLayer.crs()
        return SpatialExtent(crs, extent)

    def __init__(self, crs, *args):

        if isinstance(crs, SpatialExtent):
            crs, args = crs.crs(), [crs]
        if not isinstance(crs, QgsCoordinateReferenceSystem):
            crs = QgsCoordinateReferenceSystem(crs)
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        super(SpatialExtent, self).__init__(*args)
        self.mCrs = crs

    def setCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        self.mCrs = crs

    def crs(self):
        return self.mCrs

    def writeXml(self, node: QDomNode, doc: QDomDocument):
        node_geom = doc.createElement('SpatialExtent')
        node_geom.appendChild(doc.createTextNode(self.asWktPolygon()))
        node_crs = doc.createElement('SpatialExtentCrs')
        self.crs().writeXml(node_crs, doc)
        # if QgsCoordinateReferenceSystem(self.crs().authid()) == self.crs():
        #    node_crs.appendChild(doc.createTextNode(self.crs().authid()))
        # else:
        #    node_crs.appendChild(doc.createTextNode(self.crs().toWkt()))
        node.appendChild(node_geom)
        node.appendChild(node_crs)

    def toCrs(self, crs):
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        box = QgsRectangle(self)
        if self.mCrs != crs:
            box = saveTransform(box, self.mCrs, crs)
        return SpatialExtent(crs, box) if box else None

    def spatialCenter(self):
        return SpatialPoint(self.crs(), self.center())

    def combineExtentWith(self, *args):
        if args is None:
            return
        elif isinstance(args[0], SpatialExtent):
            extent2 = args[0].toCrs(self.crs())
            self.combineExtentWith(QgsRectangle(extent2))
        else:
            super(SpatialExtent, self).combineExtentWith(*args)

        return self

    def setCenter(self, centerPoint, crs=None):
        """
        Shift the center of this rectange
        :param centerPoint:
        :param crs:
        :return:
        """
        if crs and crs != self.crs():
            trans = QgsCoordinateTransform(crs, self.crs())
            centerPoint = trans.transform(centerPoint)

        delta = centerPoint - self.center()
        self.setXMaximum(self.xMaximum() + delta.x())
        self.setXMinimum(self.xMinimum() + delta.x())
        self.setYMaximum(self.yMaximum() + delta.y())
        self.setYMinimum(self.yMinimum() + delta.y())

        return self

    def __cmp__(self, other):
        if other is None:
            return 1
        s = ""

    def upperRightPt(self) -> QgsPointXY:
        """
        Returns the upper-right coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperRight())

    def upperLeftPt(self) -> QgsPointXY:
        """
        Returns the upper-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.upperLeft())

    def lowerRightPt(self) -> QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerRight())

    def lowerLeftPt(self) -> QgsPointXY:
        """
        Returns the lower-left coordinate as QgsPointXY.
        :return: QgsPointXY
        """
        return QgsPointXY(*self.lowerLeft())

    def upperRight(self) -> tuple:
        """
        Returns the upper-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMaximum()

    def upperLeft(self) -> tuple:
        """
        Returns the upper-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMaximum()

    def lowerRight(self) -> tuple:
        """
        Returns the lower-right coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMaximum(), self.yMinimum()

    def lowerLeft(self) -> tuple:
        """
        Returns the lower-left coordinate as tuple (x,y)
        :return: tuple (x,y)
        """
        return self.xMinimum(), self.yMinimum()

    def __eq__(self, other) -> bool:
        """
        Checks for equality
        :param other: SpatialExtent
        :return: bool
        """
        if not isinstance(other, SpatialExtent):
            return False
        else:
            return self.toString() == other.toString()

    def __sub__(self, other):
        raise NotImplementedError()

    def __mul__(self, other):
        raise NotImplementedError()

    def __copy__(self):
        return SpatialExtent(self.crs(), QgsRectangle(self))

    def __reduce__(self):

        return self.__class__, ('',), self.__getstate__()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('mCrs')
        state['_crs_'] = self.crs().toWkt()
        state['_xmin_'] = self.xMinimum()
        state['_xmax_'] = self.xMaximum()
        state['_ymin_'] = self.yMinimum()
        state['_ymax_'] = self.yMaximum()
        return state

    def __setstate__(self, state):
        self.setCrs(QgsCoordinateReferenceSystem(state.pop('_crs_')))
        self.setXMinimum(state.pop('_xmin_'))
        self.setXMaximum(state.pop('_xmax_'))
        self.setYMinimum(state.pop('_ymin_'))
        self.setYMaximum(state.pop('_ymax_'))
        self.__dict__.update(state)

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return self.__repr__()

    def __repr__(self) -> str:
        """
        Returns a representation string
        :return: str
        """

        return '{} {} {}'.format(self.upperLeft(), self.lowerRight(), self.crs().authid())


class MapGeometryToPixel(object):
    """
    A class to return the covered pixel indices related to a vector geometry
    """

    @staticmethod
    def fromRaster(raster):
        raster = qgsRasterLayer(raster)
        assert isinstance(raster, QgsRasterLayer)
        center = raster.extent().center()
        m2p = QgsMapToPixel(raster.rasterUnitsPerPixelX(),
                            center.x(),
                            center.y(),
                            raster.width(),
                            raster.height(),
                            0
                            )
        return MapGeometryToPixel(m2p, crs=raster.crs())

    @staticmethod
    def fromExtent(extent: QgsRectangle,
                   ns: int, nl: int,
                   mapUnitsPerPixel: float = None,
                   crs: QgsCoordinateReferenceSystem = None):
        if mapUnitsPerPixel is None:
            mapUnitsPerPixel = extent.width() / ns
        center = extent.center()
        m2p = QgsMapToPixel(mapUnitsPerPixel,
                            center.x(), center.y(),
                            ns, nl, 0
                            )
        return MapGeometryToPixel(m2p, crs=crs)

    def __init__(self,
                 m2p: QgsMapToPixel,
                 crs: QgsCoordinateReferenceSystem = None):
        assert m2p.isValid()
        self.m2p = m2p

        ul = m2p.toMapCoordinatesF(0, 0)

        self.xMin = ul.x()
        self.yMax = ul.y()
        self.crs = crs
        self.srs = None

        # t: QTransform = self.m2p.transform()
        self.rsMEM: gdal.Dataset = None
        self.bandMEM: gdal.Band = None
        self.vsMem: ogr.DataSource = None
        self.srs: osr.SpatialReference = None
        self.wkbTypeLayers: Dict[int, ogr.Layer] = dict()

    def nSamples(self) -> int:
        return self.m2p.mapWidth()

    def nLines(self) -> int:
        return self.m2p.mapHeight()

    def pixelWidth(self) -> float:
        return self.m2p.mapUnitsPerPixel()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wkbTypeLayers.clear()
        del self.vsMem
        del self.rsMEM

    def px2geo(self, x: int, y: int) -> QgsPointXY:
        return self.m2p.toMapCoordinatesF(x, y)

    def px2geoList(self, xvalues, yvalues) -> List[QgsPointXY]:
        return [self.px2geo(x, y) for x, y in zip(xvalues, yvalues)]

    def px2geoArrays(self, xvalues, yvalues) -> Tuple[np.ndarray, np.ndarray]:
        geo = self.px2geoList(xvalues, yvalues)
        px_x = np.asarray([g.x() for g in geo])
        px_y = np.asarray([g.y() for g in geo])
        return px_x, px_y

    def geo2px(self, x: float, y: float) -> QPoint:
        return self.m2p.transform(x, y)

    def geo2pxList(self, xvalues, yvalues) -> List[QPoint]:
        return [self.geo2px(x, y) for x, y in zip(xvalues, yvalues)]

    def memoryLayerBand(self, qgsGeometry: QgsGeometry) -> Tuple[gdal.Band, ogr.Layer]:
        if not isinstance(self.srs, SpatialReference) and \
                isinstance(self.crs, QgsCoordinateReferenceSystem):
            self.srs = SpatialReference(self.crs.toWkt())

        if not isinstance(self.rsMEM, gdal.Dataset):
            self.rsMEM: gdal.Dataset = (gdal.GetDriverByName('MEM')
                                        .Create('', self.nSamples(), self.nLines(), 1, gdal.GDT_Byte))
            # ul = self.px2geo(0, 0)
            t, success = self.m2p.transform().inverted()
            assert success, 'Matrix is not invertible'
            self.rsMEM.SetGeoTransform((t.m31(), t.m11(), t.m12(),
                                        t.m32(), t.m21(), t.m22()))
            #  self.rsMEM.SetGeoTransform((ul.x(), self.pixelWidth(), 0,
            #                              ul.y(), 0, -self.pixelWidth()))

            if isinstance(self.srs, SpatialReference):
                self.rsMEM.SetSpatialRef(self.srs)
            self.bandMEM: gdal.Band = self.rsMEM.GetRasterBand(1)

        if not isinstance(self.vsMem, ogr.DataSource):
            self.vsMem: ogr.DataSource = ogr.GetDriverByName('Memory').CreateDataSource('')

        g = ogr.CreateGeometryFromWkb(qgsGeometry.asWkb())
        geom_type = g.GetGeometryType()
        key = f'geomType_{geom_type}'
        if key not in self.wkbTypeLayers:
            lyr: ogr.Layer = self.vsMem.CreateLayer(key, srs=self.srs, geom_type=geom_type)

            lyr.CreateField(ogr.FieldDefn('FID_BURN', ogr.OFTInteger))
            self.wkbTypeLayers[key] = lyr

        return self.bandMEM, self.wkbTypeLayers[key]

    def geometryPixelPositions(self,
                               g: Union[QgsGeometry, QgsFeature],
                               all_touched: bool = True,
                               burn_points: bool = False,
                               ) -> Tuple[np.ndarray, np.ndarray]:
        #  rasterizes the feature geometry and returns the pixel positions
        if isinstance(g, QgsFeature):
            if g.hasGeometry():
                g = g.geometry()

        if not isinstance(g, QgsGeometry) or _geometryIsEmpty(g):
            return None, None

        if g.wkbType() == QGIS_WKBTYPE.Point and not burn_points:
            g = QgsGeometry(g)
            g.mapToPixel(self.m2p)
            px_x = []
            px_y = []
            for point in g.constParts():
                x, y = int(point.x()), int(point.y())
                if 0 <= x < self.m2p.mapWidth() and 0 <= y < self.m2p.mapHeight():
                    px_x.append(x)
                    px_y.append(y)
                else:
                    s = ""
            if len(px_x) > 0:
                return np.asarray(px_y), np.asarray(px_x)
            else:
                return None, None
        else:
            bandMEM, lyr = self.memoryLayerBand(g)
            bandMEM: gdal.Band
            lyr: ogr.Layer
            dsMEM: gdal.Dataset = bandMEM.GetDataset()
            ogrFeature = ogr.Feature(lyr.GetLayerDefn())
            ogrFeature.SetFID(1)
            ogrFeature.SetField("FID_BURN", 1)
            ogrFeature.SetGeometryDirectly(ogr.CreateGeometryFromWkb(g.asWkb()))
            assert ogrFeature.geometry().IsValid()

            assert ogr.OGRERR_NONE == self._clearAndInsert(lyr, ogrFeature)
            assert lyr.GetFeatureCount() == 1
            lyr.ResetReading()
            bandMEM.Fill(0)  # ensure that no FIDs are left from previous writes
            assert gdal.CPLE_None == gdal.RasterizeLayer(dsMEM, [1], lyr,
                                                         options=['ALL_TOUCHED={}'.format(all_touched).upper(),
                                                                  'ATTRIBUTE={}'.format('FID_BURN')]
                                                         )
            is_fid = dsMEM.ReadAsArray() == 1
            px_y, px_x = np.where(is_fid)
            if len(px_y) > 0:
                return px_y, px_x
            else:
                return None, None

    def _clearAndInsert(self, lyr: ogr.Layer, ogrFeature: ogr.Feature):
        for feature in lyr:
            lyr.DeleteFeature(feature.GetFID())
        return lyr.CreateFeature(ogrFeature)


class ExtentTileIterator(object):
    """
    An iterator over tiles
    """

    def __init__(self,
                 extent: Union[QgsRectangle, QgsMapLayer],
                 raster: QgsRasterLayer = None,
                 tileSize: float = None,
                 tileSizeX: float = None,
                 tileSizeY: float = None):

        if isinstance(extent, QgsMapLayer):
            extent = extent.extent()

        if isinstance(tileSize, (int, float)):
            tileSizeX = tileSizeY = tileSize

        if isinstance(raster, QgsRasterLayer):
            # get extent and tile size from raster
            tileSizeX = raster.dataProvider().xBlockSize() * raster.rasterUnitsPerPixelX()
            tileSizeY = raster.dataProvider().yBlockSize() * raster.rasterUnitsPerPixelY()
            extent = raster.extent()

        assert isinstance(extent, QgsRectangle) and not extent.isEmpty()
        if tileSizeX < 0 or tileSizeX > extent.width():
            tileSizeX = extent.width()

        if tileSizeY < 0 or tileSizeY > extent.height():
            tileSizeY = extent.width()

        assert 0 < tileSizeX
        assert 0 < tileSizeY

        self.mExtent = extent
        self.mTileSizeX = tileSizeX
        self.mTileSizeY = tileSizeY

        self.mXmin: float = self.mExtent.xMinimum()
        self.mYmax: float = self.mExtent.yMaximum()
        self.mXmax = self.mYmin = -1
        self.n = 0

        self.nTotal = math.ceil(self.mExtent.width() / tileSizeX) * math.ceil(self.mExtent.height() / tileSizeY)

    def resetReading(self):
        self.mXmin = self.mExtent.xMinimum()
        self.mYmax = self.mExtent.yMaximum()
        self.mXmax = self.mYmin = -1
        self.n = 0

    def __iter__(self):
        return self

    def __next__(self):

        if self.mXmin >= self.mExtent.xMaximum():
            # got next block line
            self.mXmin = self.mExtent.xMinimum()
            self.mYmax -= self.mTileSizeY

        if self.mYmax <= self.mExtent.yMinimum():
            raise StopIteration()

        self.mXmax = min(self.mExtent.xMaximum(), self.mXmin + self.mTileSizeX)
        self.mYmin = max(self.mExtent.yMinimum(), self.mYmax - self.mTileSizeY)
        self.n += 1
        rect = QgsRectangle(QgsPointXY(self.mXmin, self.mYmax),
                            QgsPointXY(self.mXmax, self.mYmin))
        self.mXmin += self.mTileSizeX
        return rect


def rasterizeFeatures(featureSource: QgsFeatureSource,
                      rasterLayer: QgsRasterLayer,
                      request: QgsFeatureRequest = QgsFeatureRequest(),
                      all_touched: bool = True,
                      pixel_metadata: bool = True,
                      blockSize: int = 0,
                      feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> \
        Iterator[Tuple[QgsFeature, np.ndarray, Dict[str, Any]]]:
    transform = QgsCoordinateTransform()
    transform.setSourceCrs(featureSource.crs())
    transform.setDestinationCrs(rasterLayer.crs())

    extF = transform.transformBoundingBox(featureSource.sourceExtent())
    extR = rasterLayer.extent()
    extI = extF.intersect(extR)

    # snap to raster grid

    if extI.isEmpty():
        s = ""
    dp: QgsRasterDataProvider = rasterLayer.dataProvider()

    c: QgsPointXY = rasterLayer.extent().center()
    M2P = QgsMapToPixel(rasterLayer.rasterUnitsPerPixelX(),
                        c.x(), c.y(),
                        rasterLayer.width(),
                        rasterLayer.height(), 0)

    half_pixel = QgsVector(0.5 * M2P.mapUnitsPerPixel(),
                           -0.5 * M2P.mapUnitsPerPixel())

    if blockSize:
        tileSizeX = blockSize * rasterLayer.rasterUnitsPerPixelX()
        tileSizeY = blockSize * rasterLayer.rasterUnitsPerPixelY()
    else:
        tileSizeX = dp.xBlockSize() * rasterLayer.rasterUnitsPerPixelX()
        tileSizeY = dp.yBlockSize() * rasterLayer.rasterUnitsPerPixelY()

    tileIterator = ExtentTileIterator(extI, tileSizeX=tileSizeX, tileSizeY=tileSizeY)

    Tile2Features: Dict[int, List[int]] = dict()

    class FeatureData(object):

        def __init__(self, fid: int):
            self.fid = fid
            self.tiles: List[int] = []
            self.arrays: List[np.ndarray] = []
            self.px: List[QPoint] = []
            self.geo: List[QgsPointXY] = []

    FEATURE_DATA: Dict[int, FeatureData] = dict()
    # Feat2Tile: Dict[int, List[int]] = dict()
    # Feat2Data: Dict[int, List] = dict()
    # Feat2MD: Dict[int, Dict] = dict()

    for tid, tileExt in enumerate(tileIterator):
        tileRequest = QgsFeatureRequest(request)
        tileRequest.setDestinationCrs(dp.crs(), QgsProject.instance().transformContext())
        tileRequest.setFilterRect(tileExt)
        tileRequest.setInvalidGeometryCheck(QgsFeatureRequest.InvalidGeometryCheck.GeometrySkipInvalid)

        Tile2Features[tid] = []
        for feature in featureSource.getFeatures(tileRequest):
            fid = feature.id()
            # create lookup between tile and feature ids
            Tile2Features[tid].append(fid)
            # create a FeatureData container to store temporary data
            # for each in-completed feature
            fd = FEATURE_DATA.get(fid, FeatureData(fid))
            fd.tiles.append(tid)
            FEATURE_DATA[fid] = fd

    tileIterator.resetReading()

    def removeTileID(fid: int, tid: int):
        # may happen in case of multi-point/line/polygon geometries
        featureData = FEATURE_DATA[fid]
        featureData.tiles.remove(tid)
        Tile2Features[tid].remove(fid)

        if len(Tile2Features[tid]) == 0:
            Tile2Features.pop(tid)

        if len(featureData.tiles) == 0:
            FEATURE_DATA.pop(fid)
            if len(featureData.arrays) > 0:
                featureProfiles = np.concatenate(featureData.arrays, axis=1)
                # concatenate other metadata
                featureMetadata = {'px': featureData.px,
                                   'geo': featureData.geo}

                return feature, featureProfiles, featureMetadata

        return None

    for tid, tileExt in enumerate(tileIterator):
        fids = Tile2Features[tid][:]
        if fids is None:
            # no features intersect with this tile
            continue

        array: np.ndarray = rasterArray(dp, tileExt)
        if not isinstance(array, np.ndarray):
            # no intersecting raster pixels
            # e.g. if the tile covers only the 2nd half of a pixel, but not it's center.
            for fid in fids:
                r = removeTileID(fid, tid)
                if r:
                    yield r
        else:

            nb, nl, ns = array.shape
            MG2PX = MapGeometryToPixel.fromExtent(tileExt,
                                                  ns, nl,
                                                  mapUnitsPerPixel=rasterLayer.rasterUnitsPerPixelX(),
                                                  crs=dp.crs())

            tileRequest = QgsFeatureRequest(request)
            tileRequest.setDestinationCrs(dp.crs(), QgsProject.instance().transformContext())
            tileRequest.setFilterRect(tileExt)
            tileRequest.setInvalidGeometryCheck(QgsFeatureRequest.InvalidGeometryCheck.GeometrySkipInvalid)
            tileRequest.setFilterFids(fids)

            for feature in featureSource.getFeatures(tileRequest):
                fid = feature.id()

                # pixel coordinates of tile subset / in array
                iy, ix = MG2PX.geometryPixelPositions(feature.geometry(),
                                                      burn_points=True,
                                                      all_touched=all_touched)

                if iy is None:
                    # no pixels covered by this feature
                    r = removeTileID(fid, tid)
                    if r:
                        yield r
                    continue

                profileData = array[:, iy, ix]

                featData: FeatureData = FEATURE_DATA[fid]
                featData.arrays.append(profileData)

                if pixel_metadata:
                    # geo-coordinates
                    geo_coordinates = MG2PX.px2geoList(ix, iy)

                    # pixel coordinates within pixel grid of total raster layer
                    px_coordinates = [M2P.transform(p).toQPointF().toPoint() for p in geo_coordinates]
                    geo_snapped = [M2P.toMapCoordinates(px.x(), px.y()) + half_pixel
                                   for px in px_coordinates]

                    # snap coordinates
                    featData.geo.extend(geo_snapped)
                    featData.px.extend(px_coordinates)

                r = removeTileID(fid, tid)
                if r:
                    yield r

        feedback.setProgress(int((tid + 1.0) * 100. / tileIterator.nTotal))

    assert len(FEATURE_DATA) == 0
    for k in list(Tile2Features.keys()):
        if len(Tile2Features[k]) == 0:
            del Tile2Features[k]
    assert len(Tile2Features) == 0


def rasterLayerArray(*args, **kwds):
    warnings.warn(
        DeprecationWarning('Use rasterArray() instead, which supports QgsRasterLayers and QgsRasterInterfaces'))
    return rasterArray(*args, **kwds)


def rasterArray(rasterInterface: Union[QgsRasterInterface, str, QgsRasterLayer],
                rect: Union[QRect, QgsRasterInterface, QgsRectangle, SpatialExtent] = None,
                ul: Union[SpatialPoint, QPoint] = None,
                lr: Union[SpatialPoint, QPoint] = None,
                bands: Union[str, int, List[int]] = None) -> Optional[np.ndarray]:
    """
    Returns the raster values of a QgsRasterLayer or QgsRasterInterface as 3D numpy array of shape (bands, height, width)
    :param rasterInterface: QgsRasterLayer, QgsRasterInterface or str to load a QgsRasterLayer from
    :param rect: Subset to be returned.
                 QRect for subset in pixel coordinates,
                 QgsRectangle for geo-coordinates in raster CRS,
                 SpatialExtent for geo-coordinates with CRS different to the raster CRS (will be transformed)
    :param ul: upper-left corner,
               can be a geo-coordinate (SpatialPoint, QgsPointXY) or pixel-coordinate (QPoint)
               defaults to raster layers upper-left corner
    :param lr: lower-right corner,
               can be a geo-coordinate (SpatialPoint, QgsPointXY) or pixel-coordinate (QPoint)
               default to raster layers lower-right corner
    :param bands: list of bands to return the pixel valuse for.
                  defaults to "all". 1st band = [1]
    :return: numpy.ndarray

    """
    if not isinstance(rasterInterface, QgsRasterInterface):
        rlayer = qgsRasterLayer(rasterInterface)
        assert isinstance(rlayer, QgsRasterLayer) and rlayer.isValid()
        rasterInterface = rlayer.dataProvider()
    assert isinstance(rasterInterface, QgsRasterInterface)

    ext = rasterInterface.extent()
    resX = ext.width() / rasterInterface.xSize()
    resY = ext.height() / rasterInterface.ySize()

    if rect:
        if isinstance(rect, SpatialExtent):
            rect = rect.toCrs(rasterInterface.crs())

        if isinstance(rect, QgsRectangle):
            ul = SpatialPoint(rasterInterface.crs(), rect.xMinimum(), rect.yMaximum())
            lr = SpatialPoint(rasterInterface.crs(), rect.xMaximum(), rect.yMinimum())
        elif isinstance(rect, QRect):
            ul = QPoint(rect.x(), rect.y())
            lr = QPoint(rect.x() + rect.width() - 1,
                        rect.y() + rect.height() - 1)
        elif isinstance(rect, SpatialPoint):
            ul = lr = rect
        elif isinstance(rect, QgsPointXY):
            ul = lr = SpatialPoint(rasterInterface.crs(), rect.x(), rect.y())
        else:
            raise NotImplementedError()

    if not isinstance(ul, SpatialPoint):
        if isinstance(ul, QPoint):
            ul = px2spatialPoint(rasterInterface, ul, subpixel_pos=0.0)
        elif isinstance(ul, QgsPointXY):
            ul = SpatialPoint(rasterInterface.crs(), ul.x(), ul.y())
        elif ul is None:
            ul = SpatialPoint(rasterInterface.crs(), ext.xMinimum(), ext.yMaximum())

    assert isinstance(ul, SpatialPoint)
    ul = ul.toCrs(rasterInterface.crs())

    if not isinstance(lr, SpatialPoint):
        if isinstance(lr, QPoint):
            lr = px2spatialPoint(rasterInterface, lr, subpixel_pos=1.0)
        elif isinstance(lr, QgsPointXY):
            lr = SpatialPoint(rasterInterface.crs(), lr.x(), lr.y())
        elif lr is None:
            lr = SpatialPoint(rasterInterface.crs(), ext.xMaximum(), ext.yMinimum())

    assert isinstance(lr, SpatialPoint)
    lr = lr.toCrs(rasterInterface.crs())

    assert isinstance(lr, SpatialPoint)

    if bands in [None, 'all', '*']:
        bands = list(range(1, rasterInterface.bandCount() + 1))

    boundingBox: QgsRectangle = QgsRectangle(ul, lr)
    # npx = width_px * height_px

    dp = rasterInterface

    result_array: np.ndarray = None
    bands = sorted(set(bands))
    nb = len(bands)
    assert nb > 0
    feedback = QgsRasterBlockFeedback()

    if not boundingBox.isNull() and boundingBox.isEmpty():
        # single point -> return single profile.
        # Use identify, which is faster for single pixels
        ires: QgsRasterIdentifyResult = dp.identify(boundingBox.center(),
                                                    QgsRaster.IdentifyFormatValue).results()

        arr = np.asarray([ires[b] for b in bands]).reshape((len(bands), 1, 1))
        return arr.astype(QGIS2NUMPY_DATA_TYPES.get(dp.dataType(1), arr.dtype))
    else:

        if isinstance(rect, QRect):
            width_px = rect.width()
            height_px = rect.height()
        else:
            # ensure that we always get all pixels whose center coordinate is within the extent

            M2P = QgsMapToPixel(resX, dp.extent().center().x(),
                                dp.extent().center().y(),
                                dp.xSize(), dp.ySize(), 0)

            width_px = int(round(boundingBox.width() / resX))
            height_px = int(round(boundingBox.height() / resY))

            ul = M2P.transform(QgsPointXY(boundingBox.xMinimum(), boundingBox.yMaximum()))
            lr = M2P.transform(QgsPointXY(boundingBox.xMaximum(), boundingBox.yMinimum()))

            xl, xr = floor(ul.x() - 0.5), floor(lr.x() - 0.5)
            yt, yb = floor(ul.y() - 0.5), floor(lr.y() - 0.5)

            if xr - xl <= 0 or yb - yt <= 0:
                return None
            w_px = xr - xl
            h_px = yb - yt
            # we want all pixel indices
            width_px = w_px
            height_px = h_px

        for i, band in enumerate(bands):
            band_block: QgsRasterBlock = dp.block(band, boundingBox, width_px, height_px, feedback=feedback)
            if not (isinstance(band_block, QgsRasterBlock) and band_block.isValid()):
                return None

            assert isinstance(band_block, QgsRasterBlock)
            band_array = rasterBlockArray(band_block)
            assert band_array.shape == (height_px, width_px)
            if i == 0:
                result_array = np.empty((nb, height_px, width_px), dtype=band_array.dtype)
            result_array[i, :, :] = band_array

        return result_array


def setToolButtonDefaultActionMenu(toolButton: QToolButton, actions: list):
    if isinstance(toolButton, QAction):
        for btn in toolButton.parent().findChildren(QToolButton):
            assert isinstance(btn, QToolButton)
            if btn.defaultAction() == toolButton:
                toolButton = btn
                break

    assert isinstance(toolButton, QToolButton)
    toolButton.setPopupMode(QToolButton.MenuButtonPopup)
    menu = QMenu(toolButton)
    for i, a in enumerate(actions):
        assert isinstance(a, QAction)
        a.setParent(menu)
        menu.addAction(a)
        if i == 0:
            toolButton.setDefaultAction(a)

    menu.triggered.connect(toolButton.setDefaultAction)
    toolButton.setMenu(menu)


class SelectMapLayerDialog(QgsDialog):

    def __init__(self, *args, **kwds):
        super().__init__(*args, buttons=QDialogButtonBox.Cancel | QDialogButtonBox.Ok, **kwds)
        self.setWindowTitle('Select Layer')
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.mBox = QgsMapLayerComboBox(parent=self)
        self.mLabel = QLabel('Layer', parent=self)
        self.hl = QHBoxLayout()
        self.hl.addWidget(self.mLabel)
        self.hl.addWidget(self.mBox)
        self.hl.setStretchFactor(self.mBox, 2)
        self.layout().insertLayout(0, self.hl)

    def setProject(self, project: QgsProject):
        if hasattr(self.mBox, 'setProject') and callable(self.mBox.objectName):
            # https://github.com/qgis/QGIS/pull/46706
            self.mBox.setProject(project)

    def mapLayerComboBox(self) -> QgsMapLayerComboBox:
        return self.mBox

    def layer(self) -> QgsMapLayer:
        return self.mBox.currentLayer()


class SelectMapLayersDialog(QgsDialog):
    class LayerDescription(object):

        def __init__(self, info: str, filters: QGIS_LAYERFILTER, allowEmptyLayer=False):
            self.labelText = info
            self.filters = filters
            self.allowEmptyLayer = allowEmptyLayer

    def __init__(self, *args, layerDescriptions: list = None, **kwds):
        super(SelectMapLayersDialog, self).__init__(buttons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.setWindowTitle('Select layer(s)')

        gl = QGridLayout()
        assert isinstance(gl, QGridLayout)
        self.mGrid = gl
        gl.setSpacing(6)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 1)
        self.layout().addLayout(gl)

        self.mMapLayerBoxes = []

        self.buttonBox().button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

    def selectMapLayer(self, i, layer):
        """
        Selects the QgsMapLayer layer in QgsMapLayerComboBox.
        :param i: int
        :param layer: QgsMapLayer.
        """
        if isinstance(i, QgsMapLayerComboBox):
            i = self.mMapLayerBoxes.index(i)
        box = self.mMapLayerBoxes[i]
        assert isinstance(layer, QgsMapLayer)
        assert isinstance(box, QgsMapLayerComboBox)
        QgsProject.instance().addMapLayer(layer)

        for i in range(box.count()):
            boxLayer = box.layer(i)
            if isinstance(boxLayer, QgsMapLayer) and boxLayer == layer:
                box.setCurrentIndex(i)
                break

    def exec_(self):

        if len(self.mMapLayerBoxes) == 0:
            self.addLayerDescription('Map Layer', QgsMapLayerProxyModel.All)
        super(SelectMapLayersDialog, self).exec_()

    def addLayerDescription(self, info: str,
                            filters: QGIS_LAYERFILTER,
                            allowEmptyLayer=False,
                            layerDescription=None) -> QgsMapLayerComboBox:
        """
        Adds a map layer description
        :param info:  text
        :param filters: map layer filters
        :param allowEmptyLayer: bool
        :param layerDescription: SelectMapLayersDialog.LayerDescription (overwrites the other attributes)
        :return: the QgsMapLayerComboBox that relates to this layer description
        """

        if not isinstance(layerDescription, SelectMapLayersDialog.LayerDescription):
            layerDescription = SelectMapLayersDialog.LayerDescription(info, filters, allowEmptyLayer=allowEmptyLayer)

        assert isinstance(layerDescription, SelectMapLayersDialog.LayerDescription)
        i = self.mGrid.rowCount()

        layerbox = QgsMapLayerComboBox(self)
        layerbox.setFilters(layerDescription.filters)
        self.mMapLayerBoxes.append(layerbox)
        self.mGrid.addWidget(QLabel(layerDescription.labelText, self), i, 0)
        self.mGrid.addWidget(layerbox, i, 1)

        return layerbox

    def mapLayers(self) -> list:
        """
        Returns the user's list of map layers
        :return: [list-of-QgsMapLayers]
        """
        return [b.currentLayer() for b in self.mMapLayerBoxes]


class QgsTaskMock(QgsTask):
    """
    A mocked QgsTask
    """

    def __init__(self):
        super(QgsTaskMock, self).__init__()


class FeatureReferenceIterator(object):
    """
    Iterator for QgsFeatures that uses the 1st feature as a reference
    """

    def __init__(self, features: Iterable[QgsFeature]):

        self.mNextFeatureIndex = -1
        self.mReferenceFeature = None
        if isinstance(features, QgsVectorLayer):
            self.mFeatureIterator = features.getFeatures()
        else:
            self.mFeatureIterator = iter(features)
        try:
            self.mReferenceFeature = self.mFeatureIterator.__next__()
            self.mNextFeatureIndex += 1
        except StopIteration:
            pass

    def referenceFeature(self) -> QgsFeature:
        return self.mReferenceFeature

    def __str__(self):
        return 'FeaturePreviewIterator'

    def __iter__(self):
        return self

    def __next__(self):
        self.mNextFeatureIndex += 1
        if self.mNextFeatureIndex == 0:
            raise StopIteration
        elif self.mNextFeatureIndex == 1:
            return self.referenceFeature()
        else:
            return self.mFeatureIterator.__next__()


def printCaller(prefix: str = None,
                suffix: str = None,
                dt: Union[datetime.datetime, datetime.timedelta] = None) -> datetime.datetime:
    """
    prints out the current code location in calling method
    :param prefix: prefix text
    :param suffix: suffix text
    """
    now = datetime.datetime.now()
    if not os.environ.get('DEBUG', '').lower() in ['1', 'true']:
        return now

    curFrame = inspect.currentframe()
    outerFrames = inspect.getouterframes(curFrame)
    FOI = outerFrames[1]
    stack = inspect.stack()
    stack_class = stack[1][0].f_locals["self"].__class__.__name__
    stack_method = stack[1][0].f_code.co_name
    info = f'{stack_class}.{FOI.function}: {os.path.basename(FOI.filename)}:{FOI.lineno}'

    prefix = f'{prefix}:' if prefix else ''
    suffix = f':{suffix}' if suffix else ''

    if isinstance(dt, datetime.datetime):
        dt = now - dt

    if isinstance(dt, datetime.timedelta):
        suffix += ' {:0.2f} s'.format(dt.total_seconds())
    print(f'#{prefix}{info}{suffix}', flush=True)

    return now


def create_picture_viewer_config(relative: bool = False,
                                 px_width: int = 300,
                                 px_height: int = 0, ) -> dict:
    """
    Creates the config dictionary to set a QgsEditorWidgetSetup of type ExternalResource
    to become a picture viewer
    :param relative: use path as relative to layer sources
    :param px_width: minimum width in pixel to display the picture (0 = flexible)
    :param px_height: minimum height in pixel to display the picture (0 = flexible)
    :return: dict
    """
    if relative:
        relativeStorage = 2
        propertyRootPath = {
            'active': True,
            'expression': "layer_property(@layer, 'path')",
            'type': 3, }
    else:
        # use absolute path
        relativeStorage = 0
        propertyRootPath = {'active': False,
                            'val': None,
                            'type': 1, }

    config = {'DocumentViewer': 1,
              'DocumentViewerHeight': px_height,
              'DocumentViewerWidth': px_width,  # 300 pixel width
              'FileWidget': True,
              'FileWidgetButton': False,
              'FileWidgetFilter': '',
              'PropertyCollection': {
                  'name': NULL,
                  'type': 'collection',
                  'properties': {
                      'propertyRootPath': propertyRootPath,

                  }},
              'RelativeStorage': relativeStorage,
              'StorageAuthConfigId': None,
              'StorageMode': 0,
              'StorageType': None
              }

    return config
