# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/datatypeconverter.py

    A module for converting datatype descriptions between Qgis.DataType, numpy and QMetaType
    ---------------------
    Beginning            : 2026-09-03
    Copyright            : (C) 2026 by Benjamin Jakimow
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
from typing import Union

import numpy as np
from qgis.PyQt.QtCore import QMetaType
from qgis.core import Qgis

NUMPY_STRING_MAPPING = {
    'bool': bool,
    'int': int,
    'int8': np.int8,
    'int16': np.int16,
    'int32': np.int32,
    'int64': np.int64,
    'uint8': np.uint8,
    'uint16': np.uint16,
    'uint32': np.uint32,
    'uint64': np.uint64,
    'float': float,
    'float16': np.float16,
    'float32': np.float32,
    'float64': np.float64,
    'complex': complex,
    'complex64': np.complex64,
    'complex128': np.complex128,
    'long': int,
    'longlong': int,
    'ulong': int,
    'ulonglong': int,
}

QMETATYPE_STRING_MAPPING = {
    'bool': QMetaType.Type.Bool,
    'int': QMetaType.Type.Int,
    'uint': QMetaType.Type.UInt,
    'long': QMetaType.Type.Long,
    'longlong': QMetaType.Type.LongLong,
    'ulong': QMetaType.Type.ULong,
    'ulonglong': QMetaType.Type.ULongLong,
    'float': QMetaType.Type.Double,
    'double': QMetaType.Type.Double,
    'short': QMetaType.Type.Short,
    'uchar': QMetaType.Type.UChar,
    'char': QMetaType.Type.Char,
    'qchar': QMetaType.Type.QChar,
    'qstring': QMetaType.Type.QString,
    'qbytearray': QMetaType.Type.QByteArray,
    'qdate': QMetaType.Type.QDate,
    'qtime': QMetaType.Type.QTime,
    'qdatetime': QMetaType.Type.QDateTime,
    'quuid': QMetaType.Type.QUuid,
    'qurl': QMetaType.Type.QUrl,
    'qcolor': QMetaType.Type.QColor,
    'qvariant': QMetaType.Type.QVariant,
}


class DataTypeLookup:
    """
    Static class to convert between Qgis.DataType, numpy dtypes, and QMetaType.
    
    Examples:
        >>> DataTypeLookup.toNumpy(Qgis.DataType.UInt16)
        <class 'numpy.uint16'>
        >>> DataTypeLookup.toQgisDataType(np.float64)
        <Qgis.DataType.Float64: 6>
        >>> DataTypeLookup.toQgisDataType(QMetaType.Double)
        <Qgis.DataType.Float64: 6>
    """

    QGIS2NUMPY_DATA_TYPES = {
        Qgis.DataType.Byte: np.uint8,
        Qgis.DataType.Int8: np.int8,
        Qgis.DataType.UInt16: np.uint16,
        Qgis.DataType.Int16: np.int16,
        Qgis.DataType.UInt32: np.uint32,
        Qgis.DataType.Int32: np.int32,
        Qgis.DataType.Float32: np.float32,
        Qgis.DataType.Float64: np.float64,
        Qgis.DataType.CInt16: np.int16,
        Qgis.DataType.CInt32: np.int32,
        Qgis.DataType.CFloat32: np.complex64,
        Qgis.DataType.CFloat64: np.complex128,
        Qgis.DataType.ARGB32: np.uint32,
        Qgis.DataType.ARGB32_Premultiplied: np.uint32,
    }

    NUMPY2QGIS_DATA_TYPES = {
        np.uint8: Qgis.DataType.Byte,
        np.uint16: Qgis.DataType.UInt16,
        np.uint32: Qgis.DataType.UInt32,
        np.uint64: Qgis.DataType.UInt32,
        np.int8: Qgis.DataType.Int8,
        np.int16: Qgis.DataType.Int16,
        np.int32: Qgis.DataType.Int32,
        np.int64: Qgis.DataType.Int32,
        np.float16: Qgis.DataType.Float32,
        np.float32: Qgis.DataType.Float32,
        np.float64: Qgis.DataType.Float64,
        np.complex64: Qgis.DataType.CFloat32,
        np.complex128: Qgis.DataType.CFloat64,
        bool: Qgis.DataType.Byte,
    }

    QGIS2QMETATYPE_DATA_TYPES = {
        Qgis.DataType.Byte: QMetaType.Type.Bool,
        Qgis.DataType.UInt16: QMetaType.Type.UInt,
        Qgis.DataType.Int16: QMetaType.Type.Short,
        Qgis.DataType.UInt32: QMetaType.Type.UInt,
        Qgis.DataType.Int32: QMetaType.Type.Int,
        Qgis.DataType.Float32: QMetaType.Type.Float,
        Qgis.DataType.Float64: QMetaType.Type.Double,
        Qgis.DataType.CFloat32: QMetaType.Type.QString,
        Qgis.DataType.CFloat64: QMetaType.Type.QString,
        Qgis.DataType.ARGB32: QMetaType.Type.UInt,
        Qgis.DataType.ARGB32_Premultiplied: QMetaType.Type.Int,
    }

    QMETATYPE2QGIS_DATA_TYPES = {
        QMetaType.Type.Bool: Qgis.DataType.Byte,
        QMetaType.Type.Int: Qgis.DataType.Int32,
        QMetaType.Type.UInt: Qgis.DataType.UInt32,
        QMetaType.Type.Long: Qgis.DataType.Int32,
        QMetaType.Type.LongLong: Qgis.DataType.Int32,
        QMetaType.Type.ULong: Qgis.DataType.UInt32,
        QMetaType.Type.ULongLong: Qgis.DataType.UInt32,
        QMetaType.Type.Short: Qgis.DataType.Int16,
        QMetaType.Type.Double: Qgis.DataType.Float64,
        QMetaType.Type.Float: Qgis.DataType.Float32,
        QMetaType.Type.QChar: Qgis.DataType.Byte,
        QMetaType.Type.QString: Qgis.DataType.Byte,
        QMetaType.Type.QByteArray: Qgis.DataType.Byte,
        QMetaType.Type.QDate: Qgis.DataType.Byte,
        QMetaType.Type.QTime: Qgis.DataType.Byte,
        QMetaType.Type.QDateTime: Qgis.DataType.Byte,
        QMetaType.Type.QUuid: Qgis.DataType.Byte,
        QMetaType.Type.QUrl: Qgis.DataType.Byte,
        QMetaType.Type.QColor: Qgis.DataType.Byte,
        QMetaType.Type.QVariant: Qgis.DataType.Byte,
        QMetaType.Type.QChar: Qgis.DataType.Byte,
    }

    @classmethod
    def toNumpy(cls, datatype: Union[Qgis.DataType, QMetaType.Type, np.dtype, type, str]) -> np.dtype:
        """
        Converts a datatype to numpy dtype.
        
        :param datatype: Qgis.DataType, QMetaType.Type, numpy dtype, Python type, or string representation
        :return: numpy dtype
        """
        if isinstance(datatype, str):
            if datatype in NUMPY_STRING_MAPPING:
                return NUMPY_STRING_MAPPING[datatype]
            try:
                return np.dtype(datatype)
            except (TypeError, ValueError):
                pass

        if isinstance(datatype, np.dtype):
            return datatype
        elif isinstance(datatype, type):
            try:
                return np.dtype(datatype)
            except (TypeError, ValueError):
                pass

        if isinstance(datatype, Qgis.DataType):
            if datatype in cls.QGIS2NUMPY_DATA_TYPES:
                return cls.QGIS2NUMPY_DATA_TYPES[datatype]
        elif isinstance(datatype, QMetaType.Type):
            if datatype in cls.QMETATYPE2QGIS_DATA_TYPES:
                qgis_type = cls.QMETATYPE2QGIS_DATA_TYPES[datatype]
                return cls.QGIS2NUMPY_DATA_TYPES.get(qgis_type, np.uint8)

        raise ValueError(f'Unable to convert {datatype} to numpy dtype')

    @classmethod
    def toQgisDataType(cls, datatype: Union[Qgis.DataType, QMetaType.Type, np.dtype, type, str]) -> Qgis.DataType:
        """
        Converts a datatype to Qgis.DataType.
        
        :param datatype: Qgis.DataType, QMetaType.Type, numpy dtype, Python type, or string representation
        :return: Qgis.DataType
        """
        if isinstance(datatype, str):
            if datatype in NUMPY_STRING_MAPPING:
                numpy_dtype = NUMPY_STRING_MAPPING[datatype]
                return cls.toQgisDataType(numpy_dtype)
            try:
                numpy_dtype = np.dtype(datatype)
                return cls.toQgisDataType(numpy_dtype)
            except (TypeError, ValueError):
                pass

        if isinstance(datatype, Qgis.DataType):
            return datatype

        if isinstance(datatype, QMetaType.Type):
            if datatype in cls.QMETATYPE2QGIS_DATA_TYPES:
                return cls.QMETATYPE2QGIS_DATA_TYPES[datatype]

        if isinstance(datatype, np.dtype):
            dtype = datatype
            # Check for string dtypes first
            if dtype.kind in ['U', 'S', 'O']:  # Unicode, bytes, object (string-like)
                return Qgis.DataType.Byte
            dtype_type = dtype.type if hasattr(dtype, 'type') else dtype
            for np_type, qgis_type in cls.NUMPY2QGIS_DATA_TYPES.items():
                try:
                    if np.issubdtype(dtype_type, np_type) or dtype_type == np_type:
                        return qgis_type
                except (TypeError, ValueError):
                    if dtype_type == np_type:
                        return qgis_type
        elif isinstance(datatype, type):
            # Handle str and numpy.str_ types
            if datatype in (str, np.str_):
                return Qgis.DataType.Byte
            for np_type, qgis_type in cls.NUMPY2QGIS_DATA_TYPES.items():
                try:
                    if np.issubdtype(datatype, np_type) or datatype == np_type:
                        return qgis_type
                except (TypeError, ValueError):
                    if datatype == np_type:
                        return qgis_type

        raise ValueError(f'Unable to convert {datatype} to Qgis.DataType')

    @classmethod
    def toQMetaType(cls, datatype: Union[Qgis.DataType, QMetaType.Type, np.dtype, type, str]) -> QMetaType.Type:
        """
        Converts a datatype to QMetaType.Type.
        
        :param datatype: Qgis.DataType, QMetaType.Type, numpy dtype, Python type, or string representation
        :return: QMetaType.Type
        """
        if isinstance(datatype, str):
            if datatype in QMETATYPE_STRING_MAPPING:
                return QMETATYPE_STRING_MAPPING[datatype]
            if datatype in NUMPY_STRING_MAPPING:
                numpy_dtype = NUMPY_STRING_MAPPING[datatype]
                qgis_type = cls.toQgisDataType(numpy_dtype)
                return cls.QGIS2QMETATYPE_DATA_TYPES.get(qgis_type, QMetaType.Type.QString)
            try:
                numpy_dtype = np.dtype(datatype)
                qgis_type = cls.toQgisDataType(numpy_dtype)
                return cls.QGIS2QMETATYPE_DATA_TYPES.get(qgis_type, QMetaType.Type.QString)
            except (TypeError, ValueError):
                pass

        if isinstance(datatype, QMetaType.Type):
            return datatype

        if isinstance(datatype, Qgis.DataType):
            if datatype in cls.QGIS2QMETATYPE_DATA_TYPES:
                return cls.QGIS2QMETATYPE_DATA_TYPES[datatype]

        if isinstance(datatype, np.dtype):
            numpy_dtype = datatype
        elif isinstance(datatype, type):
            try:
                numpy_dtype = np.dtype(datatype)
            except (TypeError, ValueError):
                numpy_dtype = None
        else:
            numpy_dtype = None

        if numpy_dtype is not None:
            # Check for string dtypes first
            if numpy_dtype.kind in ['U', 'S', 'O']:  # Unicode, bytes, object (string-like)
                return QMetaType.Type.QString
            qgis_type = cls.toQgisDataType(numpy_dtype)
            if qgis_type in cls.QGIS2QMETATYPE_DATA_TYPES:
                return cls.QGIS2QMETATYPE_DATA_TYPES[qgis_type]

        raise ValueError(f'Unable to convert {datatype} to QMetaType.Type')
