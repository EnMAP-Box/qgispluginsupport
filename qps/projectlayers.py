from typing import List, Optional

from qgis.PyQt.QtCore import QAbstractTableModel, QSortFilterProxyModel, QItemSelection, QItemSelectionModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QTableView, QDialogButtonBox, QVBoxLayout
from qgis.core import QgsProject, QgsMapLayer, QgsIconUtils
from qgis.gui import QgsFilterLineEdit


class SelectProjectLayersDialog(QDialog):

    def __init__(self, *args, project=None, **kwds):

        super().__init__(*args, **kwds)
        self.setWindowTitle('Select Project Layers')
        if project is None:
            project = QgsProject.instance()
        else:
            assert isinstance(project, QgsProject)
        self.mModel = ProjectLayerTableModel()
        self.mProxyModel = QSortFilterProxyModel()
        self.mProxyModel.setSourceModel(self.mModel)
        self.mProxyModel.setDynamicSortFilter(True)
        self.mProxyModel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.mProxyModel.setFilterKeyColumn(-1)

        self.tableView = QTableView()
        self.tableView.setModel(self.mProxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tableView.selectionModel().selectionChanged.connect(self.validate)

        # self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        self.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.accept)
        self.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Reset).clicked.connect(self.clearSelection)
        self.buttonBox.button(QDialogButtonBox.Reset).setText('Clear Selection')
        self.setProject(project)
        self.tbFilter = QgsFilterLineEdit()
        self.tbFilter.setPlaceholderText('Filter Layers')
        self.tbFilter.textChanged.connect(self.mProxyModel.setFilterFixedString)
        layout = QVBoxLayout()
        layout.addWidget(self.tbFilter)
        layout.addWidget(self.tableView)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)

        self.validate()

    def validate(self):

        selection = self.tableView.selectionModel().selection()
        b = selection.count() > 0
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(b)
        self.buttonBox.button(QDialogButtonBox.Reset).setEnabled(b)

    def clearSelection(self):
        self.tableView.clearSelection()

    def onFilterChanged(self):
        text = self.tbFilter.text()
        self.mProxyModel.setFilterFixedString(text)

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)

    def project(self) -> QgsProject:
        return self.mModel.project()

    def setSelectedLayers(self, layers: List[QgsMapLayer]):

        m = self.tableView.model()
        to_select = QItemSelection()
        for r in range(m.rowCount()):
            idx0 = m.index(r, 0)
            lyr = m.data(idx0, Qt.ItemDataRole.UserRole)
            if isinstance(lyr, QgsMapLayer) and lyr in layers:
                to_select.select(idx0, m.index(r, m.columnCount() - 1))
        self.tableView.selectionModel().select(to_select, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        s = ""

    def selectedLayers(self) -> List[QgsMapLayer]:
        """
        Returns the selected layers.
        :return:
        """
        layers = []
        selection = self.tableView.selectionModel().selection()
        for idx in selection.indexes():
            lyr = self.tableView.model().data(idx, Qt.ItemDataRole.UserRole)
            if isinstance(lyr, QgsMapLayer) and lyr.isValid() and lyr not in layers:
                layers.append(lyr)
        return layers


class ProjectLayerTableModel(QAbstractTableModel):
    cName = 0
    cSource = 1
    cID = 2
    cType = 3
    cProject = 4

    def __init__(self, *args, project: Optional[QgsProject] = None, **kwds):
        super().__init__(*args, **kwds)
        self.mProject = QgsProject.instance()
        self.setProject(project)

        self.mColumNames = {self.cName: 'Name',
                            self.cType: 'Type',
                            self.cID: 'ID',
                            self.cSource: 'Source',
                            self.cProject: 'Project'}
        self.mColumnTooltips = {self.cName: 'Layer name',
                                self.cType: 'Layer type',
                                self.cID: 'Layer ID',
                                self.cSource: 'Layer source',
                                self.cProject: 'Parent project of map layer'}

    def setProject(self, project):

        if project is None:
            project = QgsProject.instance()
        else:
            assert isinstance(project, QgsProject)

        if self.mProject == project:
            return

        if isinstance(self.mProject, QgsProject):
            # disconnect from project
            pass

        self.beginResetModel()
        project.aboutToBeCleared.connect(self.beginResetModel)
        project.cleared.connect(self.endResetModel)

        project.layersWillBeRemoved.connect(self.beginResetModel)
        project.layersRemoved.connect(self.endResetModel)
        project.layersAdded.connect(self._reset)

        self.mProject = project
        self.endResetModel()

    def _reset(self):

        self.beginResetModel()
        self.endResetModel()

    def project(self) -> QgsProject:
        return self.mProject

    def rowCount(self, parent=None):
        return len(self.mProject.mapLayers())

    def columnCount(self, parent=None):
        return len(self.mColumNames)

    def headerData(self, section, orientation, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.mColumNames[section]
            # elif orientation == Qt.Vertical:
            #    return section + 1
        return None

    def data(self, index, role=None):

        r = index.row()
        c = index.column()
        lyr = list(self.mProject.mapLayers().values())[r]

        if isinstance(lyr, QgsMapLayer) and lyr.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                if c == self.cName:
                    return lyr.name()
                elif c == self.cType:
                    return lyr.__class__.__name__
                elif c == self.cID:
                    return lyr.id()
                elif c == self.cSource:
                    return lyr.source()
                elif c == self.cProject:
                    p = lyr.project()
                    if p == QgsProject.instance():
                        return 'QGIS'
                    if isinstance(p, QgsProject):
                        return p.title()
                    else:
                        return None

            if role == Qt.ItemDataRole.ToolTipRole:
                if c == self.cName:
                    tt = (f'Layer: {lyr.name()}<br> '
                          f'Type: {lyr.__class__.__name__}<br> '
                          f'ID: {lyr.id()}<br> '
                          f'Source: {lyr.source()}')
                    return tt
                elif c == self.cType:
                    return lyr.__class__.__name__
                elif c == self.cID:
                    return lyr.id()
                elif c == self.cSource:
                    return lyr.source()

            if role == Qt.ItemDataRole.DecorationRole:
                if c == self.cName:
                    return QgsIconUtils.iconForLayer(lyr)

            if role == Qt.ItemDataRole.UserRole:
                return lyr

        return None
