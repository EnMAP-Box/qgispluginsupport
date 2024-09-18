import datetime
import json
from typing import Any

from qgis.core import QgsExpressionContext, QgsField, QgsPropertyTransformer
from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QTime
from qps.qgisenums import QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QDATE, QMETATYPE_QDATETIME, \
    QMETATYPE_QSTRING, \
    QMETATYPE_QTIME, QMETATYPE_QVARIANTMAP, QMETATYPE_UINT, \
    QMETATYPE_ULONGLONG

DATE_FORMATS = [Qt.ISODateWithMs, Qt.RFC2822Date, Qt.ISODate, Qt.TextDate]


class GenericPropertyTransformer(QgsPropertyTransformer):
    """
    A transformer to transform any input into values to be stored in a QgsField attribute
    """

    def __init__(self, targetField: QgsField):
        super().__init__()

        self.mIsInt: bool = targetField.isNumeric() and targetField.type() in [
            QMETATYPE_INT, QMETATYPE_UINT, QMETATYPE_ULONGLONG
        ]
        self.mIsFloat: bool = targetField.isNumeric() and targetField.type() in [
            QMETATYPE_DOUBLE
        ]
        self.mField = QgsField(targetField)
        self.mIsJson: bool = targetField.type() == QMETATYPE_QVARIANTMAP
        self.mIsString: bool = targetField.type() == QMETATYPE_QSTRING
        self.mIsDateTime: bool = targetField.type() == QMETATYPE_QDATETIME
        self.mIsDate: bool = targetField.type() == QMETATYPE_QDATE
        self.mIsTime: bool = targetField.type() == QMETATYPE_QTIME
        self.mIsBool: bool = targetField.type() == QMETATYPE_BOOL

    def clone(self) -> 'QgsPropertyTransformer':
        return GenericPropertyTransformer(self.mField)

    def transform(self, context: QgsExpressionContext, value: Any) -> Any:
        if value is None:
            return None

        elif self.mIsFloat:
            return float(value)
        elif self.mIsInt:
            return int(value)
        elif self.mIsJson:
            if isinstance(value, str):
                return json.loads(value)
        elif self.mIsBool:
            return value
        elif self.mIsString:
            return str(value)

        elif self.mIsDate:
            if isinstance(value, QDateTime):
                return value.date()
            elif isinstance(value, datetime.datetime):
                return QDate(value.year, value.month, value.day)
            elif isinstance(value, str):
                for fmt in DATE_FORMATS:
                    try:
                        v = QDate.fromString(value, fmt)
                        return v
                    except Exception as ex:
                        s = ""
                        pass
        elif self.mIsDateTime:
            if isinstance(value, datetime.datetime):
                return QDateTime(value.year, value.month, value.day, value.hour, value.minute, value.second)
            elif isinstance(value, str):
                for fmt in DATE_FORMATS:
                    try:
                        v = QDateTime.fromString(value, fmt)
                        return v
                    except Exception as ex:
                        s = ""
                        pass
        elif self.mIsTime:
            if isinstance(value, QDateTime):
                return value.time()
            elif isinstance(value, datetime.datetime):
                return QTime(value.year, value.month, value.day, value.hour, value.minute, value.second)
            elif isinstance(value, str):
                for fmt in DATE_FORMATS:
                    try:
                        v = QTime.fromString(value, fmt)
                        return v
                    except Exception as ex:
                        s = ""
                        pass

        return value
