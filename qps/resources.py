
import sys, os, pathlib, typing
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtCore import *


def initQtResources(roots:list=[]):
    """
    Searches recursively for `*_rc.py` files and loads them into the QApplications resources system
    :param roots: list of root folders to search within
    :type roots:
    :return:
    :rtype:
    """

    if len(roots) == 0:
        p = pathlib.Path(__file__).parent
        roots.append(p.parent)

    rc_files = []
    for rootDir in roots:
        for r, dirs, files in os.walk(rootDir):
            root = pathlib.Path(r)
            for f in files:
                if f.endswith('_rc.py'):
                    path = root / f
                    if path not in rc_files:
                        rc_files.append(path)

    for path in rc_files:
        print('load {}'.format(path))
        initResourceFile(path)


def initResourceFile(path):
    """
    Loads a '*_rc.py' file into the QApplication's resource system
    """
    if not isinstance(path, pathlib.Path):
        path = pathlib.Path(path)
    f = path.name
    name = f[:-3]
    add_path = path.parent.as_posix() not in sys.path
    if add_path:
        sys.path.append(path.parent.as_posix())
    try:
        __import__(name)
        # spec = importlib.util.spec_from_file_location(name, path)
        #rcModule = importlib.util.module_from_spec(spec)
        #spec.loader.exec_module(rcModule)
        #rcModule.qInitResources()

    except Exception as ex:
        print(ex, file=sys.stderr)

    if add_path:
        sys.path.remove(path.parent.as_posix())

def findQGISResourceFiles():
    """
    Tries to find a folder 'qgisresources'.
    See snippets/create_qgisresourcefilearchive.py to create the 'qgisresources' folder.
    """
    results = []
    root = None
    if 'QPS_QGIS_RESOURCES' in os.environ.keys():
        root = os.environ.keys()
    else:
        d = pathlib.Path(__file__)

        while d != pathlib.Path('.'):
            if (d / 'qgisresources').is_dir():
                root = (d / 'qgisresources')
                break
            else:
                d = d.parent
            if len(d.parts) == 1:
                break

    if isinstance(root, pathlib.Path):
        for root, dirs, files in os.walk(root):
            for rc_file_name in [f for f in files if f.endswith('_rc.py')]:
                path = pathlib.Path(root) / rc_file_name
                if path.is_file():
                    results.append(path)
    return results


def scanResources(path=':')->str:
    """Recursively returns file paths in directory"""
    D = QDirIterator(path)
    while D.hasNext():
        entry = D.next()
        if D.fileInfo().isDir():
            yield from scanResources(path=entry)
        elif D.fileInfo().isFile():
            yield D.filePath()

def printResources():
    print('Available resources:')
    res = sorted(list(scanResources()))
    for r in res:
        print(r)



def showResources()->QWidget:
    """
    A simple way to list available Qt resources
    :return:
    :rtype:
    """
    needQApp = not isinstance(QApplication.instance(), QApplication)
    if needQApp:
        app = QApplication([])
    scrollArea = QScrollArea()

    widget = QFrame()
    grid = QGridLayout()
    iconSize = QSize(25, 25)
    row = 0
    for resourcePath in scanResources(':'):
        labelText = QLabel(resourcePath)
        labelText.setTextInteractionFlags(Qt.TextSelectableByMouse)
        labelIcon = QLabel()
        icon = QIcon(resourcePath)
        assert not icon.isNull()

        labelIcon.setPixmap(icon.pixmap(iconSize))

        grid.addWidget(labelText, row, 0)
        grid.addWidget(labelIcon, row, 1)
        row += 1

    widget.setLayout(grid)
    widget.setMinimumSize(widget.sizeHint())
    scrollArea.setWidget(widget)
    scrollArea.show()
    if needQApp:
        QApplication.instance().exec_()
    return scrollArea



class ResourceTableModel(QAbstractTableModel):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

        self.cnUri = 'Path'
        self.cnIcon = 'Resource'

        self.RESOURCES = []

        self.reloadResources()

    def reloadResources(self):

        self.beginResetModel()
        self.RESOURCES.clear()
        self.RESOURCES.extend(list(scanResources()))
        self.endResetModel()

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return 2

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.RESOURCES)

    def columnNames(self)->typing.List[str]:
        return [self.cnUri, self.cnIcon]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.columnNames()[section]

        return super().headerData(section, orientation, role)


    def data(self, index: QModelIndex, role: int = ...) -> typing.Any:
        if not index.isValid():
            return None

        uri = self.RESOURCES[index.row()]
        cn = self.columnNames()[index.column()]

        if role == Qt.DisplayRole:
            if cn == self.cnUri:
                return uri
            else:
                return os.path.basename(uri)
        if role == Qt.DecorationRole:
            if cn == self.cnIcon:
                return QIcon(uri)

        if role == Qt.ToolTipRole:
            return uri

        if role == Qt.UserRole:
            return uri

        return None


class ResourceTableView(QTableView):

    def __init__(self, *args, **kwds):
        super().__init__(*args ,**kwds)


    def contextMenuEvent(self, event: QContextMenuEvent) -> None:

        idx = self.indexAt(event.pos())
        if isinstance(idx, QModelIndex) and idx.isValid():

            uri = idx.data(Qt.UserRole)
            m = QMenu()
            a = m.addAction('Copy Name')
            a.triggered.connect(lambda *args, n=os.path.basename(uri): QApplication.clipboard().setText(n))
            a = m.addAction('Copy Path')
            a.triggered.connect(lambda *args, n=uri: QApplication.clipboard().setText(n))
            a = m.addAction('Copy Icon')
            a.triggered.connect(lambda *args, n=uri: QApplication.clipboard().setPixmap(QPixmap(n)))

            m.exec_(event.globalPos())

        pass


class ResourceBrowser(QWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


        from qps.utils import loadUi
        pathUi = pathlib.Path(__file__).parent / 'ui' / 'qpsresourcebrowser.ui'
        loadUi(pathUi, self)
        self.setWindowTitle('QPS Resource Browser')
        self.actionReload: QAction
        self.optionUseRegex: QAction
        self.tbFilter: QLineEdit
        self.tableView: ResourceTableView
        self.btnUseRegex: QToolButton
        self.btnReload: QToolButton
        self.preview: QLabel

        self.resourceModel: ResourceTableModel = ResourceTableModel()
        self.resourceProxyModel = QSortFilterProxyModel()
        self.resourceProxyModel.setFilterKeyColumn(0)
        self.resourceProxyModel.setFilterRole(Qt.UserRole)
        self.resourceProxyModel.setSourceModel(self.resourceModel)

        self.tableView.setSortingEnabled(True)
        self.tableView.setModel(self.resourceProxyModel)
        self.tableView.selectionModel().selectionChanged.connect(self.onSelectionChanged)

        self.btnReload.setDefaultAction(self.actionReload)
        self.btnUseRegex.setDefaultAction(self.optionUseRegex)

        self.optionUseRegex.toggled.connect(self.updateFilter)
        self.tbFilter.textChanged.connect(self.updateFilter)

    def updateFilter(self):

        txt = self.tbFilter.text()

        expr = QRegExp(txt)

        if self.optionUseRegex.isChecked():
            expr.setPatternSyntax(QRegExp.RegExp)
        else:
            expr.setPatternSyntax(QRegExp.Wildcard)
        if expr.isValid():
            self.resourceProxyModel.setFilterRegExp(expr)
            self.info.setText('')
        else:
            self.resourceProxyModel.setFilterRegExp(None)
            self.info.setText(expr.errorString())



    def onSelectionChanged(self, selected, deselected):

        selectedIdx = selected.indexes()
        if len(selectedIdx) == 0:
            self.updatePreview(None)
        else:
            idx1 = selectedIdx[0]
            assert isinstance(idx1, QModelIndex)

            uri = idx1.data(Qt.UserRole)
            self.updatePreview(uri)

    def updatePreview(self, uri:str):

        l = self.preview
        assert isinstance(l, QLabel)

        if uri is None:
            pm = QPixmap()
        else:
            pm = QPixmap(uri)
            pm = pm.scaled(l.width(), l.height(), Qt.KeepAspectRatio)
        l.setPixmap(pm)


    def useFilterRegex(self)->bool:
        return self.optionUseRegex.isChecked()

