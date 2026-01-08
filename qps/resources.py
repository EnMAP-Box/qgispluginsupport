# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/resources.py

    A module to manage Qt/PyQt resources
    ---------------------
    Beginning            : 2019-02-18
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
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

from qgis.PyQt.QtCore import QAbstractTableModel, QDirIterator, QFile, QModelIndex, QRegExp, QSortFilterProxyModel, Qt, \
    QTextStream
from qgis.PyQt.QtGui import QContextMenuEvent, QIcon, QPixmap
from qgis.PyQt.QtSvg import QGraphicsSvgItem
from qgis.PyQt.QtWidgets import QAction, QApplication, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel, \
    QLineEdit, QMenu, QTableView, QTextBrowser, QToolButton, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement

if __name__ == '__main__' and __package__ is None:
    # fix for "ImportError: attempted relative import with no known parent package"
    file = Path(__file__).resolve()
    parent, top = file.parent, file.parents[1]
    sys.path.append(str(top))
    try:
        from qps.utils import file_search, findUpwardPath, loadUi
    finally:
        sys.path.remove(str(top))
else:
    from .utils import file_search, findUpwardPath, loadUi

REGEX_FILEXTENSION_IMAGE = re.compile(r'\.([^.]+)$')
REGEX_QGIS_IMAGES_QRC = re.compile(r'.*QGIS[^\/]*[\/]images[\/]images\.qrc$')


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values


def compileResourceFiles(dirRoot: Union[str, Path],
                         targetDir: Optional[Union[str, Path]] = None,
                         suffix: str = '_rc.py',
                         skip_qgis_images: bool = True,
                         compressLevel=19,
                         compressThreshold=100,
                         qt_version: str = None,
                         ):
    """
    Searches for *.ui files and compiles the *.qrc files they use.
    :param compressLevel:
    :param compressThreshold:
    :param suffix:
    :param skip_qgis_images:
    :type skip_qgis_images: bool, if True (default), qrc paths to the qgis images.qrc will be skipped
    :param dirRoot: str, root directory, in which to search for *.qrc files or a list of *.ui file paths.
    :param targetDir: str, output directory to write the compiled *.py files to.
           Defaults to the *.qrc's directory
    """
    # find ui files
    dirRoot = Path(dirRoot)
    assert dirRoot.is_dir(), '"dirRoot" is not a directory: {}'.format(dirRoot)
    dirRoot = dirRoot.resolve()

    ui_files = list(file_search(dirRoot, '*.ui', recursive=True))

    qrc_files = []
    qrc_files_skipped = []
    doc = QDomDocument()

    for ui_file in ui_files:
        ui_dir = Path(ui_file).parent
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                location = attr['location']
                qrc_path = (ui_dir / Path(location)).resolve()
                if not qrc_path.exists():
                    if REGEX_QGIS_IMAGES_QRC.match(qrc_path.as_posix()) and skip_qgis_images:
                        continue
                    info = ['Broken *.qrc location in {}'.format(ui_file),
                            ' `location="{}"`'.format(location)]
                    print('\n'.join(info), file=sys.stderr)
                    continue

                elif not qrc_path.as_posix().startswith(dirRoot.as_posix()):
                    # skip resource files out of the root directory
                    if qrc_path not in qrc_files_skipped:
                        qrc_files_skipped.append(qrc_path)

                    continue
                elif qrc_path not in qrc_files:
                    qrc_files.append(qrc_path)

    for file in file_search(dirRoot, '*.qrc', recursive=True):
        file = Path(file)
        if file not in qrc_files:
            qrc_files.append(file)

    if len(qrc_files) == 0:
        print('Did not find any *.qrc files in {}'.format(dirRoot), file=sys.stderr)
        return

    print('Compile {} *.qrc files:'.format(len(qrc_files)))
    targetDirOutputNames = []
    for qrcFile in qrc_files:
        assert isinstance(qrcFile, Path)
        # in case of similar base names, use different output names
        # e.g. make
        #  src/images.qrc
        #  src/sub/images.qrc
        # to
        #  targetDir/images_rc.py
        #  targetDir/images2_rc.py
        bn = os.path.splitext(qrcFile.name)[0]
        s = suffix
        i = 1
        outName = '{}{}'.format(bn, s)
        while outName in targetDirOutputNames:
            i += 1
            s = '{}{}'.format(i, suffix)
            outName = '{}{}'.format(bn, s)

        compileResourceFile(qrcFile,
                            targetDir=targetDir,
                            suffix=s,
                            compressLevel=compressLevel,
                            compressThreshold=compressThreshold,
                            qt_version=qt_version)
        targetDirOutputNames.append(outName)

    if len(qrc_files_skipped) > 0:
        print('Skipped *.qrc files (out of root directory):')
        for qrcFile in qrc_files_skipped:
            print(qrcFile.as_posix())


def compileResourceFile(pathQrc,
                        targetDir=None,
                        suffix: str = '_rc.py',
                        compressLevel=7,
                        compressThreshold=100,
                        qt_version: str = None):
    """
    Compiles a *.qrc file
    :param pathQrc: path to *.qrc file
    :param targetDir:
    :param suffix: suffix to add to the output file name. defaults to '*._rc.py'
    :param compressLevel:
    :param compressThreshold:
    :param qt_version: set major PyQt version to compile the resource file for. Defaults to the Qt version of the
                       qgis.PyQt.QtCore module of the running python
    :return:
    """
    if qt_version is None:
        from qgis.PyQt.QtCore import QT_VERSION_STR
        qt_version = QT_VERSION_STR[0]
    else:
        # qt_version = os.environ.get('QT_VERSION', '5')
        qt_version = str(qt_version)

    assert qt_version in ['5', '6'], 'Unsupported PyQt version: {}'.format(qt_version)

    if not isinstance(pathQrc, Path):
        pathQrc = Path(pathQrc)

    assert isinstance(pathQrc, Path)
    assert pathQrc.name.endswith('.qrc')
    print('Compile {}...'.format(pathQrc))
    if targetDir is None:
        targetDir = pathQrc.parent
    elif not isinstance(targetDir, Path):
        targetDir = Path(targetDir)

    assert isinstance(targetDir, Path)
    targetDir = targetDir.resolve()

    cwd = Path(pathQrc).parent

    pathPy = targetDir / (os.path.splitext(pathQrc.name)[0] + suffix)

    last_cwd = os.getcwd()
    os.chdir(cwd)

    # print(cmd)
    if True:
        if qt_version == '5':
            rcc_exe = 'pyrcc5'
        elif qt_version == '6':
            rcc_exe = 'pyside6-rcc'
        else:
            raise RuntimeError('Unsupported PyQt version: {}'.format(qt_version))
        assert shutil.which(rcc_exe), f'Unable to find {rcc_exe}'
        cmd = [rcc_exe, str(pathQrc), '-o', str(pathPy)]
        cmd.extend(['-compress', str(compressLevel),
                    '-threshold', str(compressThreshold)])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Resource compilation failed: {result.stderr}")

        s = ""
    elif False:
        import qgis.PyQt.pyrcc_main
        last_level = PyQt5.pyrcc_main.compressLevel
        last_threshold = PyQt5.pyrcc_main.compressThreshold

        # increase compression level and move to *.qrc's directory
        PyQt5.pyrcc_main.compressLevel = compressLevel
        PyQt5.pyrcc_main.compressThreshold = compressThreshold

        assert PyQt5.pyrcc_main.processResourceFile([pathQrc.name], pathPy.as_posix(), False)

        # restore previous settings
        PyQt5.pyrcc_main.compressLevel = last_level
        PyQt5.pyrcc_main.compressThreshold = last_threshold
    else:
        cmd = 'pyrcc5 -compress {} -o {} {}'.format(compressLevel, pathPy, pathQrc)
        cmd2 = 'pyrcc5 -no-compress -o {} {}'.format(pathPy.as_posix(), pathQrc.name)

        print(cmd2)
        os.system(cmd2)

    os.chdir(last_cwd)


def compileQGISResourceFiles(qgis_repo: Union[str, Path, None], target: str = None):
    """
    Searches for *.qrc files in the QGIS repository and compiles them to <target>

    :param qgis_repo: str, path to local QGIS repository.
    :param target: str, path to directory that contains the compiled QGIS resources. By default it will be
            `<REPOSITORY_ROOT>/qgisresources`.
    """

    if qgis_repo is None:
        for k in ['QGIS_REPO', 'QGIS_REPOSITORY']:
            if k in os.environ.keys():
                qgis_repo = Path(os.environ[k])
                break
    else:
        qgis_repo = Path(qgis_repo)
    if qgis_repo is None:
        print('QGIS_REPO location undefined', file=sys.stderr)
        return

    if not isinstance(qgis_repo, Path):
        qgis_repo = Path(qgis_repo)
    assert isinstance(qgis_repo, Path)
    assert qgis_repo.is_dir()
    assert (qgis_repo / 'images' / 'images.qrc').is_file(), '{} is not the QGIS repository root'.format(
        qgis_repo.as_posix())

    if target is None:
        DIR_REPO = findUpwardPath(__file__, '.git')
        target = DIR_REPO / 'qgisresources'

    if not isinstance(target, Path):
        target = Path(target)

    os.makedirs(target, exist_ok=True)
    compileResourceFiles(qgis_repo / 'src', targetDir=target, skip_qgis_images=False)
    compileResourceFiles(qgis_repo / 'images', targetDir=target, skip_qgis_images=False)


def initQtResources(roots: Union[None, str, Path, list] = None):
    """
    Searches recursively for `*_rc.py` files and loads them into the QApplications resources system
    :param roots: list of root folders to search within
    :type roots:
    :return:
    :rtype:
    """
    if roots is None:
        roots = []
    elif not isinstance(roots, list):
        roots = [roots]

    if len(roots) == 0:
        p = Path(__file__).parent
        roots.append(p.parent)

    rc_files = []
    for rootDir in roots:
        for r, dirs, files in os.walk(rootDir):
            root = Path(r)
            for f in files:
                if f.endswith('_rc.py'):
                    path = root / f
                    if path not in rc_files:
                        rc_files.append(path)

    for path in rc_files:
        print('load {}'.format(path))
        initResourceFile(path)


def initResourceFile(path: Union[str, Path]):
    """
    Loads a '*_rc.py' file into the QApplication's resource system
    """
    if not isinstance(path, Path):
        path = Path(path)
    f = path.name
    name = f[:-3]
    add_path = path.parent.as_posix() not in sys.path
    if add_path:
        sys.path.append(path.parent.as_posix())
    try:
        rcModule = __import__(name)
        # spec = importlib.util.spec_from_file_location(name, path)
        # rcModule = importlib.util.module_from_spec(spec)
        # spec.loader.exec_module(rcModule)
        # rcModule.qInitResources()
        rcModule.qInitResources()
        s = ""

    except Exception as ex:
        print(ex, file=sys.stderr)

    if add_path:
        sys.path.remove(path.parent.as_posix())


def findQGISResourceFiles() -> List[Path]:
    """
    Tries to find a folder 'qgisresources'.
    See snippets/create_qgisresourcefilearchive.py to create the 'qgisresources' folder.
    """
    results = []
    root = None
    if 'QPS_QGIS_RESOURCES' in os.environ.keys():
        root = os.environ.keys()
    else:
        d = Path(__file__)

        while d != Path('.'):
            if (d / 'qgisresources').is_dir():
                root = (d / 'qgisresources')
                break
            else:
                d = d.parent
            if len(d.parts) == 1:
                break

    if isinstance(root, Path):
        for root, dirs, files in os.walk(root):
            for rc_file_name in [f for f in files if f.endswith('_rc.py')]:
                path = Path(root) / rc_file_name
                if path.is_file():
                    results.append(path)
    return results


def scanResources(path=':') -> Generator[str, None, None]:
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

    def columnNames(self) -> List[str]:
        return [self.cnUri, self.cnIcon]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.columnNames()[section]

        if role == Qt.TextAlignmentRole and orientation == Qt.Vertical:
            return Qt.AlignRight

        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = ...) -> Any:
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
            if cn == self.cnUri:
                return uri

        if role == Qt.UserRole:
            return uri

        return None


class ResourceTableView(QTableView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

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

        pathUi = Path(__file__).parent / 'ui' / 'qpsresourcebrowser.ui'
        loadUi(pathUi, self)
        self.setWindowTitle('QPS Resource Browser')
        self.actionReload: QAction
        self.optionUseRegex: QAction
        self.tbFilter: QLineEdit
        self.tableView: ResourceTableView
        self.btnUseRegex: QToolButton
        self.btnCaseSensitive: QToolButton
        self.btnReload: QToolButton
        self.preview: QLabel

        self.graphicsView: QGraphicsView
        self.graphicsScene = QGraphicsScene()
        self.graphicsView.setScene(self.graphicsScene)

        self.textBrowser: QTextBrowser

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
        self.btnCaseSensitive.setDefaultAction(self.optionCaseSensitive)
        self.actionReload.triggered.connect(self.resourceModel.reloadResources)

        self.optionCaseSensitive.toggled.connect(self.updateFilter)
        self.optionUseRegex.toggled.connect(self.updateFilter)
        self.tbFilter.textChanged.connect(self.updateFilter)

    def updateFilter(self):

        txt = self.tbFilter.text()

        expr = QRegExp(txt)

        if self.optionUseRegex.isChecked():
            expr.setPatternSyntax(QRegExp.RegExp)
        else:
            expr.setPatternSyntax(QRegExp.Wildcard)

        if self.optionCaseSensitive.isChecked():
            expr.setCaseSensitivity(Qt.CaseSensitive)
        else:
            expr.setCaseSensitivity(Qt.CaseInsensitive)

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

    def updatePreview(self, uri: str):

        hasImage = False
        hasText = False
        self.textBrowser.clear()
        self.graphicsScene.clear()

        if isinstance(uri, str) and '.' in uri:
            ext = os.path.splitext(uri)[1]

            item = None
            if ext == '.svg':
                item = QGraphicsSvgItem(uri)
            else:
                pm = QPixmap(uri)
                if not pm.isNull():
                    item = QGraphicsPixmapItem(pm)

            if item:
                hasImage = True
                self.graphicsScene.addItem(item)
                self.graphicsView.fitInView(item, Qt.KeepAspectRatio)

            if re.search(r'\.(svg|html|xml|txt)$', uri, re.I) is not None:
                file = QFile(uri)
                if file.open(QFile.ReadOnly | QFile.Text):
                    stream = QTextStream(file)
                    stream.setAutoDetectUnicode(True)
                    txt = stream.readAll()
                    self.textBrowser.setPlainText(txt)
                    hasText = True
                    file.close()

        self.tabWidget.setTabEnabled(self.tabWidget.indexOf(self.pageImage), hasImage)
        self.tabWidget.setTabEnabled(self.tabWidget.indexOf(self.pageText), hasText)

    def useFilterRegex(self) -> bool:
        return self.optionUseRegex.isChecked()


def showResources() -> ResourceBrowser:
    """
    A simple way to list available Qt resources
    :return:
    :rtype:
    """
    needQApp = not isinstance(QApplication.instance(), QApplication)
    if needQApp:
        app = QApplication([])
    browser = ResourceBrowser()
    browser.show()
    if needQApp:
        QApplication.instance().exec_()
    return browser


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='QPS Qt Resources')
    subparsers = parser.add_subparsers(dest='command', help='sub-command help')

    # compile command
    parser_compile = subparsers.add_parser('compile', help='compile qrc files')
    parser_compile.add_argument('path', type=str, help='path to *.qrc file or directory containing *.qrc files')
    parser_compile.add_argument('--target', type=str, default=None, help='target directory')
    parser_compile.add_argument('--qt-version', type=str, default=None,
                                help='Qt version to compile for. Can be 5 or 6. Defaults to the version of '
                                     'QGIS Python API')
    # browse command
    parser_browse = subparsers.add_parser('browse', help='open the ResourceBrowser')

    args = parser.parse_args()

    if args.command == 'compile':
        path = Path(args.path)
        if path.is_file():
            compileResourceFile(path, targetDir=args.target, qt_version=args.qt_version)
        elif path.is_dir():
            compileResourceFiles(path, targetDir=args.target, qt_version=args.qt_version)
        else:
            print(f"Path not found: {args.path}", file=sys.stderr)

    elif args.command == 'browse':
        initQtResources()
        showResources()
    else:
        parser.print_help()
