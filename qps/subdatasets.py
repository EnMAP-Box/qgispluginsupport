# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/subdatasets.py

    A module to manage GDAL Datasource subdataset
    ---------------------
    Beginning            : 2020-04-09
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
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import datetime
import re
import sys
import typing
from typing import List, Dict, Tuple

from qgis.PyQt.QtCore import QItemSelectionModel
from qgis.PyQt.QtWidgets import QTableView, QPushButton

from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, QModelIndex, QAbstractTableModel, QSortFilterProxyModel
from qgis.PyQt.QtWidgets import QDialogButtonBox, QDialog
from qgis.core import QgsProviderSublayerTask, QgsProviderSublayerDetails, QgsProviderSublayerModel, \
    QgsProviderSublayerProxyModel
from qgis.core import QgsTaskManager, QgsApplication, QgsTask
from . import DIR_UI_FILES
from .utils import loadUi


class SubDatasetLoadingTask(QgsTask):
    def __init__(self,
                 files: typing.List[str],
                 description: str = "Collect subdata sets",
                 callback=None,
                 progress_interval: int = 1):

        super().__init__(description=description)
        self.mFiles: List[str] = [str(f) for f in files]
        self.mCallback = callback
        self.mMessages: Dict[str, str] = dict()
        self.mTimeOutSec = progress_interval
        self.mSubDataSets: Dict[str, List[QgsProviderSublayerDetails]] = dict()

    def results(self) -> Dict[str, List[QgsProviderSublayerDetails]]:
        return self.mSubDataSets.copy()

    def messages(self) -> Dict[str, str]:
        return self.mMessages.copy()

    def run(self):
        n = len(self.mFiles)
        t0 = datetime.datetime.now()

        for i, path in enumerate(self.mFiles):
            assert isinstance(path, str)

            try:
                task = QgsProviderSublayerTask(path)
                task.run()
                self.mSubDataSets[path] = task.results()
            except Exception as ex:
                self.mMessages[path] = str(ex)

            if self.isCanceled():
                return False

            dt = datetime.datetime.now() - t0
            if dt.seconds > self.mTimeOutSec:
                self.setProgress(100 * (i + 1) / n)

        self.setProgress(100 * (i + 1) / n)
        return True

    def finished(self, result):

        if self.mCallback is not None:
            self.mCallback(result, self)


class DatasetTableModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mColumnNames = ['Dataset', '#']
        self.mColumnToolTip = ['Dataset location',
                               'Number of Sublayers']
        self.mDatasetInfos: typing.List[Tuple[str, List[QgsProviderSublayerDetails]]] = []

    def clear(self):
        self.beginResetModel()
        self.mDatasetInfos.clear()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mDatasetInfos)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 1
        return len(self.mColumnNames)

    def allSublayerDetails(self) -> List[QgsProviderSublayerDetails]:

        return [d for t in self.mDatasetInfos for d in t[1]]

    def uniqueSublayerDetails(self) -> List[QgsProviderSublayerDetails]:
        """
        Returns a unique set of subset details
        """
        all_details = self.allSublayerDetails()

        RESULTS = dict()
        for d in self.allSublayerDetails():
            t = self.sublayerDetailKey(d)
            if t not in RESULTS.keys():
                RESULTS[t] = d
        return list(RESULTS.values())

    def sublayerDetailKey(self, detail: QgsProviderSublayerDetails) -> Tuple[int, str, str, str]:
        return (detail.wkbType(), detail.providerKey(), detail.name(), detail.description())

    def similarSublayerDetails(self, referenceDetails: List[QgsProviderSublayerDetails]):
        """
        Returns all sublayer details that are similar to those in referenceDetails.
        """

        requested_settings = set([self.sublayerDetailKey(d) for d in referenceDetails])

        return [d for d in self.allSublayerDetails() if self.sublayerDetailKey(d) in requested_settings]

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames[col]
            if role == Qt.ToolTipRole:
                return self.mColumnToolTip[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col + 1
        return None

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        sds = self.mDatasetInfos[row]
        return self.createIndex(row, column, sds)

    def addDatasetInfos(self, infos: List[Tuple[str, List[QgsProviderSublayerDetails]]]):

        # remove existing sources, might have been updated
        sources = [d[0] for d in infos]
        to_remove = [d for d in self.mDatasetInfos if d[0] in sources]

        if len(to_remove) > 0:
            for d in to_remove:
                if d in self.mDatasetInfos:
                    c = self.mDatasetInfos.index(d)
                    self.beginRemoveRows(QModelIndex(), c, c)
                    self.mDatasetInfos.remove(d)
                    self.endRemoveRows()

        if len(infos) > 0:
            r0 = self.rowCount()
            r1 = r0 + len(infos) - 1
            self.beginInsertRows(QModelIndex(), r0, r1)
            self.mDatasetInfos.extend(infos)
            self.endInsertRows()

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        info = self.mDatasetInfos[index.row()]
        src, details = info
        src: str
        details: List[QgsProviderSublayerDetails]

        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return src
            if col == 1:
                return len(details)

        if role == Qt.ToolTipRole:
            tt = [src]

            tt.append('\n  ' + '\n  '.join([d.description() for d in details]))
            return '\n'.join(tt)

        if role == Qt.UserRole:
            return info

        return None


class SubDatasetSelectionDialog(QDialog):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(DIR_UI_FILES / 'subdatasetselectiondialog.ui', self)

        self.fileWidget.fileChanged.connect(self.onFilesChanged)
        self.mTasks = dict()

        self.datasetModel = DatasetTableModel()
        self.datasetFilterModel = QSortFilterProxyModel()
        self.datasetFilterModel.setSourceModel(self.datasetModel)
        self.datasetFilterModel.setFilterKeyColumn(0)

        self.subDatasetModel = QgsProviderSublayerModel()
        self.subDatasetFilterModel = QgsProviderSublayerProxyModel()
        self.subDatasetFilterModel.setSourceModel(self.subDatasetModel)

        self.tvSubDatasets: QTableView
        self.tvDatasets.setModel(self.datasetFilterModel)

        self.tvSubDatasets: QTableView
        self.tvSubDatasets.setModel(self.subDatasetFilterModel)
        smodel: QItemSelectionModel = self.tvSubDatasets.selectionModel()
        smodel.selectionChanged.connect(self.validate)

        self.btnSelectAll: QPushButton
        self.btnDeselectAll: QPushButton
        self.btnSelectAll.clicked.connect(self.tvSubDatasets.selectAll)
        self.btnDeselectAll.clicked.connect(smodel.clearSelection)

        self.tbFilterDatasets.valueChanged.connect(self.datasetFilterModel.setFilterWildcard)
        self.tbFilterSubDatasets.valueChanged.connect(self.subDatasetFilterModel.setFilterString)
        self.validate()

    def showMultiFiles(self, b: bool):

        self.frameFiles.setVisible(b)
        self.gbFiles.setVisible(b)

    def onSubsetDataChanged(self, i1, i2, roles):
        if Qt.CheckStateRole in roles:
            self.validate()

    def setFiles(self, files: typing.List[str]):
        assert isinstance(files, list)
        fileString = ' '.join(['"{}"'.format(f) for f in files])
        self.fileWidget.setFilePath(fileString)

    def setSubDatasetDetails(self, details: List[QgsProviderSublayerDetails]):
        """
        Allows to set SubDatasetDetails directly
        """
        self.fileWidget.setFilePath('')
        self.subDatasetModel.setSublayerDetails([])
        self.datasetModel.clear()

        self.addDatasetInfos([('dummy', details)])

    def onFilesChanged(self, files: str):
        files = re.split(r'["\n]', files)
        files = [f.strip() for f in files]
        files = [f for f in files if len(f) > 0]

        self.subDatasetModel.setSublayerDetails([])
        self.datasetModel.clear()

        if len(files) == 0:
            self.setInfo('Please define input files.')
            return

        tm = QgsApplication.taskManager()
        assert isinstance(tm, QgsTaskManager)
        qgsTask = SubDatasetLoadingTask(files, description='Search Subdatasets', callback=self.onCompleted)
        self.startTask(qgsTask)

    def addDatasetInfos(self, infos: List[Tuple[str, List[QgsProviderSublayerDetails]]]):

        infos = [i for i in infos if len(i[1]) > 0]

        self.datasetModel.addDatasetInfos(infos)
        details = self.datasetModel.uniqueSublayerDetails()
        self.subDatasetModel.setSublayerDetails(details)

    def startTask(self, qgsTask: QgsTask):
        self.setCursor(Qt.WaitCursor)
        self.fileWidget.setEnabled(False)
        self.fileWidget.lineEdit().setShowSpinner(True)
        tid = id(qgsTask)
        qgsTask.progressChanged.connect(lambda p: self.setInfo('Read {:0.2f} %'.format(p)))
        qgsTask.taskCompleted.connect(lambda *args, t=tid: self.onRemoveTask(t))
        qgsTask.taskTerminated.connect(lambda *args, t=tid: self.onRemoveTask(t))

        self.mTasks[tid] = qgsTask
        tm = QgsApplication.taskManager()
        assert isinstance(tm, QgsTaskManager)
        tm.addTask(qgsTask)

    def setDefaultRoot(self, root: str):
        self.fileWidget.setDefaultRoot(root)

    def defaultRoot(self) -> str:
        return self.fileWidget.defaultRoot()

    def onCompleted(self, result: bool, task: QgsTask):
        if isinstance(task, SubDatasetLoadingTask) and not sip.isdeleted(task):
            infos = [(k, details) for k, details in task.results().items()]

            self.addDatasetInfos(infos)

            self.onRemoveTask(id(task))

    def onTaskMessage(self, msg: str, is_error: bool):
        if is_error:
            print(msg, file=sys.stderr)
        self.setInfo(msg)

    def setInfo(self, text: str):
        self.tbInfo.setText(text)

    def onRemoveTask(self, tid):
        self.setCursor(Qt.ArrowCursor)
        self.fileWidget.setEnabled(True)
        self.fileWidget.lineEdit().setShowSpinner(False)
        if isinstance(tid, QgsTask):
            tid = id(tid)
        if tid in self.mTasks.keys():
            del self.mTasks[tid]

    def validate(self):

        rows = self.tvSubDatasets.selectionModel().selectedRows()

        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(len(rows) > 0)

    def selectedSublayerDetails(self) -> typing.List[QgsProviderSublayerDetails]:
        """
        Returns the selected QgsProviderSublayerDetails from all input sources
        """

        selectedRows = self.tvSubDatasets.selectionModel().selectedRows()
        referenceRows = [self.tvSubDatasets.model().mapToSource(idx) for idx in selectedRows]

        referenceDetails = self.subDatasetModel.sublayerDetails()
        referenceDetails = [referenceDetails[idx.row()] for idx in referenceRows]

        return self.datasetModel.similarSublayerDetails(referenceDetails)

    def setFileFilter(self, filter: str):
        """
        Sets the file filter
        :param filter:
        """
        self.fileWidget.setFilter(filter)
