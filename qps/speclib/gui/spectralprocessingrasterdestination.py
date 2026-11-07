import os
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QLabel, QComboBox, QWidget
from qgis.core import (
    QgsFields,
    QgsProcessing,
    QgsProcessingParameterDefinition,
)
from qgis.gui import QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingGui


class SpectralProcessingRasterDestination(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.WidgetType.Standard,
                 parent: QObject = None):
        self.mLabel: Optional[QLabel] = None
        self.mFieldComboBox: Optional[QComboBox] = None
        self.mFieldName: Optional[str] = None
        self.mFields: QgsFields = QgsFields()
        super(SpectralProcessingRasterDestination, self).__init__(parameter, dialogType, parent)

    def setFields(self, fields: QgsFields):
        self.mFields = fields
        # self.mFieldComboBox.setFields(fields)

    def createLabel(self) -> QLabel:
        label = QLabel(f'<html> <img src=":/qps/ui/icons/field_from_raster.svg"/>   '
                       f'{self.parameterDefinition().description()}</html>')
        label.setToolTip('An existing or new field to write raster values into')
        self.mLabel = label
        return label

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def createWrappedWidget(self, context) -> QWidget:

        if not isinstance(self.mFieldComboBox, QComboBox):
            self.mFieldComboBox = self.createWidget()
            self.mFieldComboBox.setObjectName(self.parameterDefinition().name())
        return self.mFieldComboBox

    def createWrappedLabel(self) -> Optional[QLabel]:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()

        return self.mLabel

    def createWidget(self):
        cb = QComboBox()
        cb.setEditable(True)
        for f in self.mFields:
            cb.addItem(f.name(), f)
        is_optional = self.parameterDefinition().flags() & QgsProcessingParameterDefinition.Flag.FlagOptional
        if is_optional:
            pass
        cb.currentTextChanged.connect(self.setValue)
        self.mFieldComboBox = cb
        return cb

    def setValue(self, value):

        old = self.mFieldName
        if isinstance(value, str):
            self.mFieldName = value

        if old != self.mFieldName:
            self.widgetValueHasChanged.emit(self)

    def setWidgetValue(self, value, context):
        if isinstance(self.mFieldComboBox, QComboBox) and isinstance(self.mFields, QgsFields):
            if isinstance(value, str):
                value2 = self.pathToFieldName(value)
                for i in range(self.mFieldComboBox.count()):
                    field = self.mFieldComboBox.itemData(i)
                    if field.name() == value or field.name() == value2:
                        self.mFieldComboBox.setCurrentIndex(i)
                        return
                # not found. set text for new field
                self.mFieldComboBox.setCurrentText(value2)

    @classmethod
    def pathToFieldName(cls, path: str) -> str:
        name = Path(path).stem
        prefix = f'{QgsProcessing.TEMPORARY_OUTPUT}_'
        name = name.replace(prefix, '')
        return name

    def widgetValue(self):
        """
        Returns a temporary file paths for the selected field
        Use SpectralProcessingRasterDestination.pathToFieldName(path) to return the original field name
        :return:
        """
        if isinstance(self.mFieldComboBox, QComboBox):
            field_name = self.mFieldComboBox.currentText()
            bn, ext = os.path.splitext(field_name)
            if ext == '':
                ext = self.parameterDefinition().defaultFileExtension()
                field_name = f'{bn}.{ext}'
            return f'{QgsProcessing.TEMPORARY_OUTPUT}_{field_name}'
        return None
