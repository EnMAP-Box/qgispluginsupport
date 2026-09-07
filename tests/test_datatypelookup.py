# -*- coding: utf-8 -*-
"""
***************************************************************************
    tests/datatypeconverter.py

    Unit tests for DataTypeConverter
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

import unittest

import numpy as np
from qgis.PyQt.QtCore import QMetaType
from qgis.core import Qgis

from qps.datatypelookup import DataTypeLookup


class TestDataTypeLookup(unittest.TestCase):

    def test_toNumpy_QgisDataType(self):
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Byte), np.uint8)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Int8), np.int8)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.UInt16), np.uint16)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Int16), np.int16)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.UInt32), np.uint32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Int32), np.int32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Float32), np.float32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Float64), np.float64)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CInt16), np.int16)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CInt32), np.int32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CFloat32), np.complex64)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CFloat64), np.complex128)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.ARGB32), np.uint32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.ARGB32_Premultiplied), np.uint32)

    def test_toNumpy_QMetaType(self):
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.Bool), np.uint8)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.Int), np.int32)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.UInt), np.uint32)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.Double), np.float64)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.Short), np.int16)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.Float), np.float32)
        self.assertEqual(DataTypeLookup.toNumpy(QMetaType.Type.QString), np.uint8)

    def test_toNumpy_str(self):
        # Test string types
        self.assertEqual(DataTypeLookup.toNumpy(str), np.dtype('U'))
        self.assertEqual(DataTypeLookup.toNumpy(np.str_), np.dtype('U'))

    def test_toNumpy_numpy(self):
        self.assertEqual(DataTypeLookup.toNumpy(np.uint8), np.uint8)
        self.assertEqual(DataTypeLookup.toNumpy(np.uint16), np.uint16)
        self.assertEqual(DataTypeLookup.toNumpy(np.int32), np.int32)
        self.assertEqual(DataTypeLookup.toNumpy(np.float32), np.float32)
        self.assertEqual(DataTypeLookup.toNumpy(np.float64), np.float64)

    def test_toNumpy_python_type(self):
        self.assertEqual(DataTypeLookup.toNumpy(int), np.dtype(int))
        self.assertEqual(DataTypeLookup.toNumpy(float), np.dtype(float))
        self.assertEqual(DataTypeLookup.toNumpy(bool), np.dtype(bool))
        self.assertEqual(DataTypeLookup.toNumpy(str), np.dtype('U'))

    def test_toNumpy_numpy_str(self):
        # Test numpy string dtypes
        self.assertEqual(DataTypeLookup.toNumpy(np.str_), np.dtype('U'))
        self.assertEqual(DataTypeLookup.toNumpy(np.dtype('str')), np.dtype('U'))
        self.assertEqual(DataTypeLookup.toNumpy(np.dtype('U')), np.dtype('U'))

    def test_toQgisDataType_numpy(self):
        self.assertEqual(DataTypeLookup.toQgisDataType(np.uint8), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.uint16), Qgis.DataType.UInt16)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.int8), Qgis.DataType.Int8)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.int16), Qgis.DataType.Int16)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.uint32), Qgis.DataType.UInt32)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.int32), Qgis.DataType.Int32)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.float32), Qgis.DataType.Float32)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.float64), Qgis.DataType.Float64)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.complex64), Qgis.DataType.CFloat32)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.complex128), Qgis.DataType.CFloat64)
        self.assertEqual(DataTypeLookup.toQgisDataType(bool), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.dtype('bool')), Qgis.DataType.Byte)

    def test_toQgisDataType_str(self):
        # Test string types
        self.assertEqual(DataTypeLookup.toQgisDataType(str), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.str_), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.dtype('U')), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.dtype('str')), Qgis.DataType.Byte)

    def test_toQgisDataType_QMetaType(self):
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.Bool), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.Int), Qgis.DataType.Int32)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.UInt), Qgis.DataType.UInt32)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.Double), Qgis.DataType.Float64)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.Short), Qgis.DataType.Int16)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.Float), Qgis.DataType.Float32)
        self.assertEqual(DataTypeLookup.toQgisDataType(QMetaType.Type.QString), Qgis.DataType.Byte)

    def test_toQgisDataType_QgisDataType(self):
        self.assertEqual(DataTypeLookup.toQgisDataType(Qgis.DataType.Byte), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(Qgis.DataType.Float64), Qgis.DataType.Float64)

    def test_toQMetaType_QgisDataType(self):
        self.assertEqual(DataTypeLookup.toQMetaType(Qgis.DataType.Byte), QMetaType.Type.Bool)
        self.assertEqual(DataTypeLookup.toQMetaType(Qgis.DataType.Int16), QMetaType.Type.Short)
        self.assertEqual(DataTypeLookup.toQMetaType(Qgis.DataType.UInt32), QMetaType.Type.UInt)
        self.assertEqual(DataTypeLookup.toQMetaType(Qgis.DataType.Float32), QMetaType.Type.Float)
        self.assertEqual(DataTypeLookup.toQMetaType(Qgis.DataType.Float64), QMetaType.Type.Double)

    def test_toQMetaType_numpy(self):
        self.assertEqual(DataTypeLookup.toQMetaType(np.uint8), QMetaType.Type.Bool)
        self.assertEqual(DataTypeLookup.toQMetaType(np.int32), QMetaType.Type.Int)
        self.assertEqual(DataTypeLookup.toQMetaType(np.float64), QMetaType.Type.Double)
        self.assertEqual(DataTypeLookup.toQMetaType(np.int16), QMetaType.Type.Short)
        self.assertEqual(DataTypeLookup.toQMetaType(np.float32), QMetaType.Type.Float)

    def test_toQMetaType_str(self):
        # Test string types
        self.assertEqual(DataTypeLookup.toQMetaType(str), QMetaType.Type.QString)
        self.assertEqual(DataTypeLookup.toQMetaType(np.str_), QMetaType.Type.QString)
        self.assertEqual(DataTypeLookup.toQMetaType(np.dtype('U')), QMetaType.Type.QString)
        self.assertEqual(DataTypeLookup.toQMetaType(np.dtype('str')), QMetaType.Type.QString)

    def test_roundtrip(self):
        qgis_types = [
            Qgis.DataType.Byte,
            Qgis.DataType.Int8,
            Qgis.DataType.UInt16,
            Qgis.DataType.Int16,
            Qgis.DataType.UInt32,
            Qgis.DataType.Int32,
            Qgis.DataType.Float32,
            Qgis.DataType.Float64,
            Qgis.DataType.CFloat32,
            Qgis.DataType.CFloat64,
        ]

        for qgis_type in qgis_types:
            numpy_dtype = DataTypeLookup.toNumpy(qgis_type)
            qgis_type_back = DataTypeLookup.toQgisDataType(numpy_dtype)
            self.assertEqual(qgis_type, qgis_type_back)

    def test_special_types(self):
        # ARGB32 and ARGB32_Premultiplied are special color formats
        # They map to uint32 and int32 respectively
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.ARGB32), np.uint32)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.ARGB32_Premultiplied), np.uint32)

        # CInt16 and CInt32 are complex integer types with no direct numpy equivalent
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CInt16), np.int16)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.CInt32), np.int32)

    def test_roundtrip_numpy(self):
        numpy_types = [
            np.uint8,
            np.uint16,
            np.int16,
            np.int32,
            np.float32,
            np.float64,
            np.complex64,
            np.complex128,
        ]

        for numpy_dtype in numpy_types:
            qgis_type = DataTypeLookup.toQgisDataType(numpy_dtype)
            numpy_dtype_back = DataTypeLookup.toNumpy(qgis_type)
            self.assertEqual(numpy_dtype, numpy_dtype_back)

    def test_bool_conversion(self):
        self.assertEqual(DataTypeLookup.toQgisDataType(bool), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.bool_), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType(np.dtype('bool')), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toNumpy(Qgis.DataType.Byte), np.uint8)

    def test_roundtrip_qmetatype(self):
        qmeta_types = [
            QMetaType.Type.Bool,
            QMetaType.Type.Int,
            QMetaType.Type.UInt,
            QMetaType.Type.Double,
            QMetaType.Type.Short,
            QMetaType.Type.Float,
        ]

        for qmeta_type in qmeta_types:
            qgis_type = DataTypeLookup.toQgisDataType(qmeta_type)
            qmeta_type_back = DataTypeLookup.toQMetaType(qgis_type)
            self.assertEqual(qmeta_type, qmeta_type_back)

    def test_toQgisDataType_string(self):
        self.assertEqual(DataTypeLookup.toQgisDataType('bool'), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType('int'), Qgis.DataType.Int32)
        self.assertEqual(DataTypeLookup.toQgisDataType('float'), Qgis.DataType.Float64)
        self.assertEqual(DataTypeLookup.toQgisDataType('uint8'), Qgis.DataType.Byte)
        self.assertEqual(DataTypeLookup.toQgisDataType('uint16'), Qgis.DataType.UInt16)
        self.assertEqual(DataTypeLookup.toQgisDataType('int16'), Qgis.DataType.Int16)
        self.assertEqual(DataTypeLookup.toQgisDataType('int32'), Qgis.DataType.Int32)
        self.assertEqual(DataTypeLookup.toQgisDataType('float32'), Qgis.DataType.Float32)
        self.assertEqual(DataTypeLookup.toQgisDataType('float64'), Qgis.DataType.Float64)

    def test_toQMetaType_string(self):
        self.assertEqual(DataTypeLookup.toQMetaType('bool'), QMetaType.Type.Bool)
        self.assertEqual(DataTypeLookup.toQMetaType('int'), QMetaType.Type.Int)
        self.assertEqual(DataTypeLookup.toQMetaType('float'), QMetaType.Type.Double)
        self.assertEqual(DataTypeLookup.toQMetaType('short'), QMetaType.Type.Short)
        self.assertEqual(DataTypeLookup.toQMetaType('long'), QMetaType.Type.Long)
        self.assertEqual(DataTypeLookup.toQMetaType('longlong'), QMetaType.Type.LongLong)
        self.assertEqual(DataTypeLookup.toQMetaType('double'), QMetaType.Type.Double)
        self.assertEqual(DataTypeLookup.toQMetaType('qstring'), QMetaType.Type.QString)
        self.assertEqual(DataTypeLookup.toQMetaType('qbytearray'), QMetaType.Type.QByteArray)

    def test_invalid_type(self):
        with self.assertRaises(ValueError):
            DataTypeLookup.toNumpy("invalid")
        with self.assertRaises(ValueError):
            DataTypeLookup.toQgisDataType("invalid")
        with self.assertRaises(ValueError):
            DataTypeLookup.toQMetaType("invalid")


if __name__ == '__main__':
    unittest.main()
