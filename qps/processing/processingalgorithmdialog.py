import pathlib

from qgis.PyQt.QtCore import pyqtSignal, QModelIndex
from qgis.PyQt.QtWidgets import QDialog, QTreeView, QDialogButtonBox, QPushButton

from qgis.gui import QgsFilterLineEdit, QgsProcessingToolboxTreeView, QgsProcessingToolboxProxyModel

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProcessingAlgorithm
from ..utils import loadUi


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
        self.mTreeViewAlgorithms.doubleClicked.connect(self.onDoubleClicked)
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
        self.tbAlgorithmFilter.setText(model.filterString())

    def algorithm(self) -> QgsProcessingAlgorithm:
        return self.mSelectedAlgorithm

    def setAlgorithmFilter(self, pattern: str):
        self.mTreeViewAlgorithms.setFilterString(pattern)

    def onDoubleClicked(self, index: QModelIndex):
        alg = self.mTreeViewAlgorithms.algorithmForIndex(index)
        if isinstance(alg, QgsProcessingAlgorithm):
            self.mSelectedAlgorithm = alg
            self.setResult(QDialog.Accepted)
            self.buttonBox.button(QDialogButtonBox.Ok).click()

    def onAlgorithmTreeSelectionChanged(self, selected, deselected):
        self.mSelectedAlgorithm = self.mTreeViewAlgorithms.selectedAlgorithm()
        b = isinstance(self.mSelectedAlgorithm, QgsProcessingAlgorithm)

        btnOk = self.buttonBox.button(QDialogButtonBox.Ok)
        btnOk.setEnabled(b)
