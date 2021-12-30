import pathlib

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QDialog, QTreeView, QDialogButtonBox, QPushButton

from qgis._gui import QgsFilterLineEdit, QgsProcessingToolboxTreeView, QgsProcessingToolboxProxyModel

from qgis.PyQt.QtCore import Qt
from qgis._core import QgsProcessingAlgorithm
from qps.utils import loadUi


class ProcessingAlgorithmDialog(QDialog):


    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        path_ui = pathlib.Path(__file__).parent / 'processingalgorithmdialog.ui'
        loadUi(path_ui, self)
        self.mTreeViewAlgorithms: QgsProcessingToolboxTreeView
        self.mAlgorithmModel: QgsProcessingToolboxProxyModel = QgsProcessingToolboxProxyModel()
        self.mAlgorithmModel.setRecursiveFilteringEnabled(True)
        self.mAlgorithmModel.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.mTreeViewAlgorithms.header().setVisible(False)
        self.mTreeViewAlgorithms.setDragDropMode(QTreeView.DragOnly)
        self.mTreeViewAlgorithms.setDropIndicatorShown(False)
        self.mTreeViewAlgorithms.setToolboxProxyModel(self.mAlgorithmModel)
        self.mTreeViewAlgorithms.selectionModel().selectionChanged.connect(self.onAlgorithmTreeSelectionChanged)
        # self.mTreeViewAlgorithms.selectionModel().currentChanged.connect(self.onAlgorithmTreeSelectionChanged)

        self.mSelectedAlgorithm: QgsProcessingAlgorithm = None

        self.tbAlgorithmFilter: QgsFilterLineEdit
        self.tbAlgorithmFilter.textChanged.connect(self.setAlgorithmFilter)

        # btnOk: QPushButton = self.buttonBox.button(QDialogButtonBox.Ok)
        # btnCancel: QPushButton = self.buttonBox.button(QDialogButtonBox.Cancel)

        self.onAlgorithmTreeSelectionChanged(None, None)

    def setAlgorithmModel(self, model: QgsProcessingToolboxProxyModel):
        assert isinstance(model, QgsProcessingToolboxProxyModel)
        self.mTreeViewAlgorithms.selectionModel().selectionChanged.disconnect(self.onAlgorithmTreeSelectionChanged)
        self.mTreeViewAlgorithms.setToolboxProxyModel(model)
        self.mTreeViewAlgorithms.selectionModel().selectionChanged.connect(self.onAlgorithmTreeSelectionChanged)
        self.mAlgorithmModel = model

    def algorithm(self) -> QgsProcessingAlgorithm:
        return self.mSelectedAlgorithm

    def setAlgorithmFilter(self, pattern: str):
        self.mTreeViewAlgorithms.setFilterString(pattern)

    def onAlgorithmTreeSelectionChanged(self, selected, deselected):

        self.mSelectedAlgorithm = self.mTreeViewAlgorithms.selectedAlgorithm()
        b = isinstance(self.mSelectedAlgorithm, QgsProcessingAlgorithm)

        btnOk = self.buttonBox.button(QDialogButtonBox.Ok)
        btnOk.setEnabled(b)

