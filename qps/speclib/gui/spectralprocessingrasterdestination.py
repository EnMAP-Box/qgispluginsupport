import os
import re
from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QButtonGroup
from qgis.PyQt.QtWidgets import QLabel, QWidget
from qgis.PyQt.QtWidgets import QRadioButton, QLineEdit, QHBoxLayout, QVBoxLayout
from qgis.core import (
    QgsFields,
    QgsProcessing,
)
from qgis.gui import QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingGui
from qgis.gui import QgsFieldComboBox


class SpectralProcessingDestinationFieldWidget(QWidget):
    """
    A widget that allows users to specify a destination field either by:
    1. Entering a field name directly in a text box
    2. Selecting an existing field from a combo box

    The two options are toggled using radio buttons.
    Radio buttons are displayed in one row, and the input widget (QLineEdit or QComboBox)
    is displayed in a second row.
    """

    sigValueChanged = pyqtSignal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.mUseTextBox = True  # True = text box, False = combo box

        # Create radio buttons
        self.rbNewField = QRadioButton("Create new Field")
        self.rbExistingField = QRadioButton("Update existing Field")
        self.btnGroup = QButtonGroup(self)
        self.btnGroup.addButton(self.rbNewField)
        self.btnGroup.addButton(self.rbExistingField)

        # Group the radio buttons
        self.rbNewField.setChecked(True)

        # Create text box
        self.tbNewFieldName = QLineEdit()
        self.tbNewFieldName.setPlaceholderText("Enter field name...")
        self.tbNewFieldName.textChanged.connect(self.onFieldChanged)
        self.tbNewFieldName_tt = 'Name of new field to store calculated values'
        # Create combo box
        self.cbFields = QgsFieldComboBox()
        self.cbFields.setEditable(False)
        self.cbFields.hide()  # Hidden by default
        self.cbFields.fieldChanged.connect(self.onFieldChanged)

        # Radio button connections
        self.rbNewField.toggled.connect(self.onRadioButtonToggled)
        self.rbExistingField.toggled.connect(self.onRadioButtonToggled)

        # Radio button layout (row 1) - horizontal layout for radio buttons
        rbLayout = QHBoxLayout()
        rbLayout.setContentsMargins(0, 0, 0, 0)
        rbLayout.setSpacing(5)
        rbLayout.addWidget(self.rbNewField)
        rbLayout.addWidget(self.rbExistingField)
        rbLayout.addStretch(1)

        # Input widget layout (row 2) - contains either QLineEdit or QComboBox
        inputLayout = QHBoxLayout()
        inputLayout.setContentsMargins(0, 0, 0, 0)
        inputLayout.setSpacing(5)
        inputLayout.addWidget(self.tbNewFieldName)
        inputLayout.addWidget(self.cbFields)

        # Hide combo box by default (text box mode is active)
        self.cbFields.hide()

        # Main layout with two rows: radio buttons in row 1, input widget in row 2
        mainLayout = QVBoxLayout()
        # mainLayout.addStretch(1)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(5)
        mainLayout.addLayout(rbLayout)
        mainLayout.addLayout(inputLayout)
        mainLayout.addStretch(1)

        self.setLayout(mainLayout)

    def onRadioButtonToggled(self, checked: bool):
        """Handle radio button toggles"""
        if self.rbNewField.isChecked():
            self.tbNewFieldName.setVisible(True)
            self.cbFields.setVisible(False)
        else:
            self.tbNewFieldName.setVisible(False)
            self.cbFields.setVisible(True)

        self.validate()

    def onFieldChanged(self, text: str):
        """Handle text changes in the text box"""
        self.validate()

    def validate(self):
        """Update the text field color based on whether the text matches an existing field"""
        text = self.tbNewFieldName.text()
        field_names = self.cbFields.fields().names() if self.cbFields.fields().count() > 0 else []

        err = None
        if text == '':
            err = None
        elif text in field_names:
            # Text matches an existing field - show in red
            err = f'Field "{text}" already exists'
        elif not self.isSafeFieldName(text):
            err = f'Field name "{text}" contains invalid characters'

        if err:
            self.tbNewFieldName.setStyleSheet("color: red;")
            self.tbNewFieldName.setToolTip(err)
        else:
            # Text is a new field - show in default color
            self.tbNewFieldName.setStyleSheet("")
            self.tbNewFieldName.setToolTip(self.tbNewFieldName_tt)

    rx_safe_fieldname = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')

    def isSafeFieldName(self, name: str):
        """
        Returns True if the name is a valid field name
        :param name: str
        :return: bool
        """
        return bool(self.rx_safe_fieldname.match(name))

    def onComboBoxChanged(self, text: str):
        """Handle text changes in the combo box"""
        self.sigValueChanged.emit()

    def setFields(self, fields: QgsFields):
        """
        Sets the values of the combo box to show existing field names.

        :param fields: QgsFields object containing field definitions
        """
        self.cbFields.setFields(fields)

    def setValue(self, value: str):
        """
        Sets the widget value.
        If value matches a field in the combo box, selects it.
        Otherwise, sets it as text in the text box.
        """
        # Find if value exists in combo box
        idx = self.cbFields.findText(value)
        if idx >= 0:
            # Value exists in combo - select combo mode
            self.rbExistingField.setChecked(True)
            self.cbFields.setCurrentIndex(idx)
        else:
            # Value doesn't exist - use text box
            self.rbNewField.setChecked(True)
            self.tbNewFieldName.setText(value)

    def value(self) -> str | None:
        """Returns the current value based on selected mode"""
        if self.rbNewField.isChecked():
            return self.tbNewFieldName.text()
        else:
            return self.cbFields.currentText()


class SpectralProcessingRasterDestination(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.WidgetType.Standard,
                 parent: QObject | None = None):
        self.mLabel: Optional[QLabel] = None
        self.mDestinationFieldWidget: Optional[SpectralProcessingDestinationFieldWidget] = None
        self.mFieldName: Optional[str] = None
        self.mFields: QgsFields = QgsFields()
        super(SpectralProcessingRasterDestination, self).__init__(parameter, dialogType, parent)

    def setFields(self, fields: QgsFields):
        self.mFields = fields
        if self.mDestinationFieldWidget:
            self.mDestinationFieldWidget.setFields(fields)

    def createLabel(self) -> QLabel:
        label = QLabel(f'<html> <img src=":/qps/ui/icons/field_from_raster.svg"/>   '
                       f'{self.parameterDefinition().description()}</html>')
        label.setToolTip('An existing or new vector field to write created raster values to')
        self.mLabel = label
        return label

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def createWrappedWidget(self, context) -> QWidget:

        if not isinstance(self.mDestinationFieldWidget, SpectralProcessingDestinationFieldWidget):
            self.mDestinationFieldWidget = self.createWidget()
            self.mDestinationFieldWidget.setObjectName(self.parameterDefinition().name())
        return self.mDestinationFieldWidget

    def createWrappedLabel(self) -> Optional[QLabel]:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()

        return self.mLabel

    def createWidget(self):
        widget = SpectralProcessingDestinationFieldWidget()
        widget.setFields(self.mFields)
        # widget.sigFieldChanged.connect(self.onWidgetValueChanged)
        widget.setValue(self.parameterDefinition().defaultValueForGui())
        self.mDestinationFieldWidget = widget
        return widget

    def setWidgetValue(self, value, context):
        if isinstance(self.mDestinationFieldWidget, SpectralProcessingDestinationFieldWidget):
            self.mDestinationFieldWidget.setValue(value)
            # if isinstance(value, str):
            #     value2 = self.pathToFieldName(value)
            #     self.mDestinationFieldWidget.setValue(value2)

    @classmethod
    def pathToFieldName(cls, path: str) -> str:
        fn = Path(path).stem
        prefix = f'{QgsProcessing.TEMPORARY_OUTPUT}_'
        fn = fn.replace(prefix, '')
        return fn

    def widgetValue(self):
        """
        Returns a temporary file paths for the selected field
        Use SpectralProcessingRasterDestination.pathToFieldName(path) to return the original field name
        :return:
        """
        if isinstance(self.mDestinationFieldWidget, SpectralProcessingDestinationFieldWidget):
            # return self.mDestinationFieldWidget.value()
            field_name = self.mDestinationFieldWidget.value()
            if field_name is None or len(field_name) == 0:
                return None
            fn, ext = os.path.splitext(field_name)
            if ext == '':
                ext = self.parameterDefinition().defaultFileExtension()
            return f'{QgsProcessing.TEMPORARY_OUTPUT}_{fn}.{ext}'
        return None
