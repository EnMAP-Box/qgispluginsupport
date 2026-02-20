from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QTextBrowser, QToolButton, QWidget
from qgis.core import QgsVectorLayer
from qgis.gui import QgsCodeEditorPython, QgsFeaturePickerWidget
from ..utils import loadUi


class PythonCodeDialog(QDialog):
    """
    A dialog to modify python expressions. Changing the python code triggers
    the validationRequest(result:dict) signal.
    The signals' dictionary can be used to validate the python code externally
    and return informations to be shown in the dialog (see validation_request_dictionary)

    input: expression - the python expression to validate
    return values:
    error: str - an error message
    preview_text: str - the text to be shown in the preview text field
    preview_tooltip: str - a tooltip
    """

    VALKEY_CODE = 'expression'
    VALKEY_FEATURE = 'feature'
    VALKEY_ERROR = 'error'
    VALKEY_PREVIEW_TEXT = 'preview_text'
    VALKEY_PREVIEW_TOOLTIP = 'preview_tooltip'

    validationRequest = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        path_ui = Path(__file__).parent / 'pythoncodeeditordialog.ui'
        loadUi(path_ui, self)
        self.setWindowTitle("Edit Python Expression")

        editor: QgsCodeEditorPython = self.mCodeEditor
        editor.textChanged.connect(self.updatePreview)

        featurePicker: QgsFeaturePickerWidget = self.mFeaturePickerWidget
        featurePicker.featureChanged.connect(self.updatePreview)

        self.buttonBox().accepted.connect(self.accept)
        self.buttonBox().rejected.connect(self.reject)

    def featurePickerWidget(self) -> QgsFeaturePickerWidget:
        return self.mFeaturePickerWidget

    def updatePreview(self):
        """
        Collects the code text and the feature instance.
        Emits the validationRequest to validate the expression.
        """
        d = {
            self.VALKEY_FEATURE: self.featurePickerWidget().feature(),
            self.VALKEY_CODE: self.code(),
            self.VALKEY_PREVIEW_TEXT: None,
            self.VALKEY_PREVIEW_TOOLTIP: None
        }

        self.validationRequest.emit(d)

        text = d.get(self.VALKEY_PREVIEW_TEXT, '')
        tt = d.get(self.VALKEY_PREVIEW_TOOLTIP, '')

        if isinstance(text, str):
            self.tbPreview.setText(text)

        if isinstance(tt, str):
            self.tbPreview.setToolTip(tt)

    def setLayer(self, layer: QgsVectorLayer):
        self.mFeaturePickerWidget.setLayer(layer)

    def setPreviewText(self, text: str):
        self.tbPreview.setText(text)

    def previewText(self) -> str:
        return self.tbPreview.toPlainText()

    def helpTextBrowser(self) -> QTextBrowser:
        return self.mHelpTextBrowser

    def setHelpText(self, text: Optional[str]):
        """
        Sets the HTML text shown in the help text browser.
        If None or empty, the help text browser is hidden.
        :param text: str or None
        """
        self.helpTextBrowser().setHtml(text)
        self.mHelpTextBrowser.setVisible(text not in [None, ''])

    def setCode(self, code: str):
        self.codeEditor().setText(code)

    def code(self) -> str:
        return self.codeEditor().text()

    def codeEditor(self) -> QgsCodeEditorPython:
        return self.mCodeEditor

    def buttonBox(self) -> QDialogButtonBox:
        return self.mButtonBox


class PythonCodeWidget(QWidget):
    """
    A widget that shows a python expression.
    Shows a button to open a PythonExpressionDialog to modify the expression.
    """
    codeChanged = pyqtSignal(str)
    validationRequest = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Python Expression')
        # Create main components
        self.lineEdit = QLineEdit(self)
        self.editButton = QToolButton(self)
        self.editButton.setIcon(QIcon(":/images/themes/default/mIconPythonFile.svg"))

        self.mDialogHelpText = 'Enter Python code.'
        # Layout for the main widget
        layout = QHBoxLayout(self)
        layout.addWidget(self.lineEdit)
        layout.addWidget(self.editButton)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        # Connect button click to open the dialog
        self.editButton.clicked.connect(self.openCodeDialog)

        # Signal to track changes in the QLineEdit
        self.lineEdit.textChanged.connect(self.onCodeChanged)
        self.lineEdit.textEdited.connect(lambda: self.doValidationRequest())

        self.mLayer: Optional[QgsVectorLayer] = None
        self.mValidationError: Optional[str] = None

    def setDialogHelpText(self, text: str):
        self.mDialogHelpText = text

    def openCodeDialog(self):
        """Opens a dialog with QgsCodeEditorPython to edit the expression."""
        dialog = PythonCodeDialog(self)
        dialog.validationRequest.connect(self.doValidationRequest)
        dialog.setWindowTitle("Edit Python Expression")
        dialog.setCode(self.code())
        dialog.setHelpText(self.mDialogHelpText)
        # Connect dialog buttons
        buttonBox = dialog.buttonBox()
        buttonBox.accepted.connect(lambda d=dialog: self.applyExpression(d))
        buttonBox.rejected.connect(dialog.reject)

        if self.mLayer:
            dialog.setLayer(self.mLayer)

        dialog.exec_()

    def doValidationRequest(self, data: dict = None):
        if data is None:
            data = {
                PythonCodeDialog.VALKEY_CODE: self.code(),
                PythonCodeDialog.VALKEY_PREVIEW_TEXT: None,
                PythonCodeDialog.VALKEY_PREVIEW_TOOLTIP: None
            }
            if isinstance(self.mLayer, QgsVectorLayer):
                for f in self.mLayer.getFeatures():
                    data[PythonCodeDialog.VALKEY_FEATURE] = f
                    break

        try:
            self.validationRequest.emit(data)
        except Exception as ex:
            data[PythonCodeDialog.VALKEY_ERROR] = str(ex)

        self.mValidationError = data.get('error', None)

        if isinstance(self.mValidationError, str):
            self.lineEdit.setStyleSheet('color:red;')
        else:
            self.lineEdit.setStyleSheet('')

    def applyExpression(self, dialog: PythonCodeDialog):
        """Applies the expression from the code editor to the line edit."""

        self.lineEdit.setText(dialog.code())
        dialog.accept()

    def onCodeChanged(self, text):
        """Emit signal when the expression changes."""
        self.codeChanged.emit(text)
        self.doValidationRequest()

    def setLayer(self, layer: QgsVectorLayer):
        assert isinstance(layer, QgsVectorLayer) and layer.isValid()
        self.mLayer = layer

    def layer(self) -> Optional[QgsVectorLayer]:
        return self.mLayer

    def code(self):
        """Returns the current expression in the QLineEdit."""
        return self.lineEdit.text()

    def setCode(self, expression):
        """Sets the expression in the QLineEdit."""
        self.lineEdit.setText(expression)

        self.doValidationRequest()

    def isValid(self) -> bool:
        return self.mValidationError in [None, '']

    def validationError(self) -> Optional[str]:
        return self.mValidationError
