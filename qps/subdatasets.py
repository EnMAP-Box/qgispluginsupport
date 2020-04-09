import typing
import re
import sys
import sip
import pathlib
import collections
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from osgeo import gdal
from .utils import loadUi
from . import DIR_UI_FILES

# read https://gdal.org/user/raster_data_model.html#subdatasets-domain



class SubDatasetDescription(object):
    def __init__(self, name: str, checked: bool = False):
        assert isinstance(name, str)
        self.name: str = name
        self.checked: bool = checked

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, SubDatasetDescription):
            return False
        return self.name == other.name

class SubDatasetInfo(object):

    @staticmethod
    def fromRaster(obj):
        if isinstance(obj, pathlib.Path):
            obj = str(obj)
        if isinstance(obj, str):
            try:
                obj = gdal.Open(obj)
            except:
                pass
        if isinstance(obj, gdal.Dataset):
            subs = obj.GetSubDatasets()
            if isinstance(subs, list) and len(subs) > 0:
                return SubDatasetInfo(obj.GetDescription(), subs)

        return None

    def __init__(self, file: str, subs: typing.List[typing.Tuple[str, str]]):

        assert isinstance(file, str)
        assert isinstance(subs, list) and len(subs) > 0

        self.mReferenceFile: str = str(file)
        self.mSubDescriptions: typing.List[str] = [s[1] for s in subs]
        self.mSubNames: typing.List[str] = [s[0] for s in subs]

    def reference_file(self) -> str:
        return self.mReferenceFile

    def subset_descriptions(self) -> typing.List[SubDatasetDescription]:
        return [SubDatasetDescription(d) for d in self.mSubDescriptions[:]]

    def subset_names(self) -> typing.List[str]:
        return self.mSubNames[:]

    def contains_name(self, name: str) -> bool:
        return name in self.mSubNames

    def contains_description(self, description: str) -> bool:
        return description in self.mSubDescriptions

    def __eq__(self, other):
        """
        Two subset infos are equal if they have the same subset description
        """
        if not isinstance(other, SubDatasetInfo):
            return False
        return self.mSubDescriptions == other.mSubDescriptions

class SubDatasetLoadingTask(QgsTask):

    sigFoundSubDataSets = pyqtSignal(list)
    sigMessage = pyqtSignal(str, bool)

    def __init__(self,
                 files: typing.List[str],
                 description: str = "Collect subdata sets",
                 callback = None,
                 block_size : int = 10):

        super().__init__(description=description)
        self.mFiles = files
        self.mCallback = callback
        self.mSubDataSets = collections.OrderedDict()
        self.mResultBlockSize = block_size

    def subDataSets(self) -> collections.OrderedDict:
        return self.mSubDataSets.copy()

    def run(self):
        result_block = []
        for i, path in enumerate(self.mFiles):
            assert isinstance(path, str)
            try:
                info = SubDatasetInfo.fromRaster(path)
                if isinstance(info, SubDatasetInfo):
                    result_block.append(info)
            except Exception as ex:
                self.sigMessage.emit(str(ex), True)
            self.progressChanged.emit(i+1)

            if len(result_block) >= self.mResultBlockSize:
                self.sigFoundSubDataSets.emit(result_block[:])
                result_block.clear()
            if self.isCanceled():
                return False
            self.setProgress(i+1)

        if len(result_block) > 0:
            self.sigFoundSubDataSets.emit(result_block[:])
        return True

    def finished(self, result):

        if self.mCallback is not None:
            self.mCallback(result, self)

class SubDatasetDescriptionModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mSubDatasetDescriptions: typing.List[SubDatasetDescription] = []
        self.mColumnNames = ['Subsets']

    def clear(self):
        self.beginResetModel()
        self.mSubDatasetDescriptions.clear()
        self.endResetModel()

    def addSubDatasetDescriptions(self, descriptions: typing.List[SubDatasetDescription]):
        if not isinstance(descriptions, list):
            descriptions = [descriptions]
        for d in descriptions:
            assert isinstance(d, SubDatasetDescription)

        to_add = []
        [to_add.append(d) for d in descriptions if d not in self.mSubDatasetDescriptions
         and d not in to_add]

        if len(to_add) > 0:
            r0 = self.rowCount()
            r1 = r0 + len(to_add) - 1
            self.beginInsertRows(QModelIndex(), r0, r1)
            self.mSubDatasetDescriptions.extend(to_add)
            self.endInsertRows()

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mSubDatasetDescriptions)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mColumnNames)

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColumnNames[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col + 1
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        descr = self.mSubDatasetDescriptions[index.row()]
        assert isinstance(descr, SubDatasetDescription)
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return descr.name
        if role == Qt.ToolTipRole:
            if col == 0:
                return descr.name
        if role == Qt.CheckStateRole:
            if col == 0:
                return Qt.Checked if descr.checked else Qt.Unchecked
        if role == Qt.UserRole:
            return descr

        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return None

        descr = self.mSubDatasetDescriptions[index.row()]
        assert isinstance(descr, SubDatasetDescription)

        b = False
        if role == Qt.CheckStateRole:
            descr.checked = True if value == Qt.Checked else False
            b = True

        if b:
            self.dataChanged.emit(index, index, [role])
        return b

    def subDatasetDescriptions(self, checked: bool =None) -> typing.List[SubDatasetDescription]:
        subs = self.mSubDatasetDescriptions[:]
        if isinstance(checked, bool):
            subs = [s for s in subs if s.checked == checked]
        return subs

class DataSetTableModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mColumnNames = ['Dataset', '#']
        self.mColumnToolTip = ['Dataset location',
                               'Number of Subdatasets']
        self.mSubDatasetInfos: typing.List[SubDatasetInfo] = []

    def clear(self):
        self.beginResetModel()
        self.mSubDatasetInfos.clear()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.mSubDatasetInfos)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 1
        return len(self.mColumnNames)

    def subDatasets(self, description_filter: typing.List[SubDatasetDescription] = []) -> typing.List[str]:
        results = []
        if len(description_filter) > 0:
            for d in description_filter:
                assert isinstance(d, SubDatasetDescription)
            for info in self.mSubDatasetInfos:
                results.extend([n for (n, d) in zip(info.subset_names(), info.subset_descriptions())
                                if d in description_filter])
        else:
            for info in self.mSubDatasetInfos:
                results.extend(info.subset_names())
        return results

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
        sds = self.mSubDatasetInfos[row]
        return self.createIndex(row, column, sds)

    def addSubDatasetInfos(self, infos: typing.List[SubDatasetInfo]):
        if not isinstance(infos, list):
            infos = [infos]
        for i in infos:
            assert isinstance(i, SubDatasetInfo)

        # remove existing
        to_add = []
        for i in infos:
            if i not in to_add and i not in self.mSubDatasetInfos:
                to_add.append(i)

        if len(to_add) > 0:
            r0 = self.rowCount()
            r1 = r0 + len(to_add) - 1
            self.beginInsertRows(QModelIndex(), r0, r1)
            self.mSubDatasetInfos.extend(to_add)
            self.endInsertRows()

    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        info = self.mSubDatasetInfos[index.row()]
        assert isinstance(info, SubDatasetInfo)
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return info.reference_file()
            if col == 1:
                return len(info.mSubNames)

        if role == Qt.ToolTipRole:
            tt = [info.reference_file()]
            tt.append('Subdatasets:')
            tt.append('\t'+'\n\t'.join(info.subset_names()))
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

        self.datasetModel = DataSetTableModel()
        self.datasetFilterModel = QSortFilterProxyModel()
        self.datasetFilterModel.setSourceModel(self.datasetModel)
        self.datasetFilterModel.setFilterKeyColumn(0)

        self.subDatasetModel = SubDatasetDescriptionModel()
        self.subDatasetFilterModel = QSortFilterProxyModel()
        self.subDatasetFilterModel.setSourceModel(self.subDatasetModel)
        self.subDatasetFilterModel.setFilterKeyColumn(0)
        self.subDatasetModel.dataChanged.connect(self.onSubsetDataChanged)

        self.tvDatasets.setModel(self.datasetFilterModel)
        self.tvSubDatasets.setModel(self.subDatasetFilterModel)

        self.tbFilterDatasets.valueChanged.connect(self.datasetFilterModel.setFilterWildcard)
        self.tbFilterSubDatasets.valueChanged.connect(self.subDatasetFilterModel.setFilterWildcard)
        self.validate()

    def onSubsetDataChanged(self, i1, i2, roles):
        if Qt.CheckStateRole in roles:
            self.validate()

    def setFiles(self, files: typing.List[str]):
        assert isinstance(files, list)
        fileString = ' '.join(['"{}"'.format(f) for f in files])
        self.fileWidget.setFilePath(fileString)

    def onFilesChanged(self, files: str):
        files = re.split(r'["\n]', files)
        files = [f.strip() for f in files]
        files = [f for f in files if len(f) > 0]

        self.subDatasetModel.clear()
        self.datasetModel.clear()

        if len(files) == 0:
            self.setInfo('Please define input files.')
            return

        tm = QgsApplication.taskManager()
        assert isinstance(tm, QgsTaskManager)
        qgsTask = SubDatasetLoadingTask(files, description='Search Subdatasets', callback=self.onCompleted)
        qgsTask.sigFoundSubDataSets.connect(self.add_subdatasetinfos)
        self.startTask(qgsTask)

    def add_subdatasetinfos(self, infos: typing.List[SubDatasetInfo]):
        self.datasetModel.addSubDatasetInfos(infos)
        descriptions = []
        [descriptions.extend(i.subset_descriptions()) for i in infos]
        self.subDatasetModel.addSubDatasetDescriptions(descriptions)

    def startTask(self, qgsTask:QgsTask):
        tid = id(qgsTask)
        qgsTask.progressChanged.connect(lambda p: self.setInfo('Loaded {:0.2f} %'.format(p)))
        qgsTask.taskCompleted.connect(lambda *args, t=tid: self.onRemoveTask(t))
        qgsTask.taskTerminated.connect(lambda *args, t=tid: self.onRemoveTask(t))
        qgsTask.sigMessage.connect(self.onTaskMessage)
        self.mTasks[tid] = qgsTask
        tm = QgsApplication.taskManager()
        assert isinstance(tm, QgsTaskManager)
        tm.addTask(qgsTask)

    def onCompleted(self, result: bool, task: QgsTask):
        if isinstance(task, SubDatasetLoadingTask) and not sip.isdeleted(task):
            self.onRemoveTask(id(task))

    def onTaskMessage(self, msg: str, is_error:bool):
        if is_error:
            print(msg, file=sys.stderr)
        self.setInfo(msg)

    def setInfo(self, text: str):
        self.tbInfo.setText(text)

    def onRemoveTask(self, tid):
        if isinstance(tid, QgsTask):
            tid = id(tid)
        if tid in self.mTasks.keys():
            del self.mTasks[tid]

    def validate(self):

        selected = len(self.subDatasetModel.subDatasetDescriptions()) > 0
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(selected)

    def selectedSubDatasets(self) -> typing.List[str]:
        """
        Returns the subdataset strings that can be used as input to QgsRasterLayers or gdal.Open()
        """
        description_filter = self.subDatasetModel.subDatasetDescriptions(checked=True)
        return self.datasetModel.subDatasets(description_filter)

    def setFileFilter(self, filter: str):
        """
        Sets the file filter
        :param filter:
        """
        self.fileWidget.setFilter(filter)
