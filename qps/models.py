# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/models.py

    Basic QAbstractItem models to handle and visualize data
    ---------------------
    Beginning            : 2019-01-11
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
import copy
import enum
import inspect
import re
import types
from typing import List, Iterator, Type, Union, Tuple, Dict, Pattern

import numpy as np

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QModelIndex, QAbstractItemModel, pyqtSignal, Qt, QObject, QAbstractListModel, QSize, \
    pyqtBoundSignal
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtGui import QIcon, QContextMenuEvent
from qgis.PyQt.QtWidgets import QComboBox, QTreeView, QMenu
from qgis.PyQt.QtWidgets import QStyleOptionViewItem
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QTableView
from qgis.core import QgsSettings
from qgis.gui import QgsColorButton, QgsSpinBox, QgsDoubleSpinBox


def currentComboBoxValue(comboBox):
    assert isinstance(comboBox, QComboBox)
    if isinstance(comboBox.model(), OptionListModel):
        o = comboBox.currentData(Qt.UserRole)
        assert isinstance(o, Option)
        return o.mValue
    else:
        return comboBox.currentData()


def setCurrentComboBoxValue(comboBox, value):
    """
    Sets a QComboBox to the value `value`, if it exists in the underlying item list
    :param comboBox: QComboBox
    :param value: any type
    :return: True | False
    """
    assert isinstance(comboBox, QComboBox)
    model = comboBox.model()
    if not isinstance(model, OptionListModel):
        i = comboBox.findData(value, role=Qt.DisplayRole)
        if i == -1:
            i = comboBox.findData(value, role=Qt.UserRole)
        if i == -1:
            for r in range(model.rowCount(QModelIndex())):
                idx = model.index(r, 0)
                displayData = model.data(idx, role=Qt.Unchecked)
                userData = model.data(idx, role=Qt.UserRole)
                if displayData == value or (userData is not None and userData == value):
                    i = r
                    break
        if i != -1:
            comboBox.setCurrentIndex(i)
            return True
    else:
        if not isinstance(value, Option):
            value = Option(value)
        for i in range(comboBox.count()):
            option = comboBox.itemData(i, role=Qt.UserRole)
            if option == value:
                comboBox.setCurrentIndex(i)
                return True
    return False


class Option(object):
    """
    Represents an option
    """

    def __init__(self, value, name=None, toolTip='', icon=QIcon()):
        self.mValue = value
        if name is None:
            name = str(value)
        self.mName = name
        self.mTooltip = toolTip
        self.mIcon = icon

    def __repr__(self):
        return f'Option(name={self.mName} value={self.mValue}) id {id(self)}'

    def value(self) -> object:
        """
        Returns the option value
        :return: object
        """
        return self.mValue

    def name(self) -> str:
        """
        Returns the option name
        :return: str
        """
        return self.mName

    def toolTip(self) -> str:
        """
        Returns the option tooltip.
        :return: str
        """
        return self.mTooltip

    def icon(self) -> QIcon:
        """
        Returns an option icon
        :return: QIcon
        """
        return self.mIcon

    def __eq__(self, other):
        if not isinstance(other, Option):
            return False
        else:
            return other.mValue == self.mValue


class OptionListModel(QAbstractListModel):
    def __init__(self, options=None, parent=None):
        super(OptionListModel, self).__init__(parent)

        self.mOptions: List[Option] = []

        self.insertOptions(options)

    def __len__(self):
        return len(self.mOptions)

    def __iter__(self):
        return iter(self.mOptions)

    def __getitem__(self, slice):
        return self.mOptions[slice]

    def addOption(self, option):
        self.insertOptions([option])

    def addOptions(self, options):
        assert isinstance(options, list)
        self.insertOptions(options)

    sigOptionsInserted = pyqtSignal(list)

    def insertOptions(self, options, i=None):
        if options is None:
            return
        elif isinstance(options, enum.Enum):
            options = [Option(e.value, name=str(e.name)) for e in options]
        if not isinstance(options, list):
            options = [options]
        assert isinstance(options, list)

        options = [self.o2o(o) for o in options]

        options = [o for o in options if o not in self.mOptions]

        n_options = len(options)
        if n_options > 0:
            if i is None:
                i = len(self.mOptions)
            self.beginInsertRows(QModelIndex(), i, i + len(options) - 1)
            for o in options:
                self.mOptions.insert(i, o)
                i += 1
            self.endInsertRows()

            self.sigOptionsInserted.emit(options)

    def findOption(self, value) -> Option:
        """
        Returns the option with value "value"
        :param value:
        :return:
        """
        if isinstance(value, Option):
            if value in self.mOptions:
                return self.mOptions[self.mOptions.index(value)]
        for o in self:
            if o.mValue == value:
                return o
        return None

    def o2o(self, value):
        if not isinstance(value, Option):
            value = Option(value, '{}'.format(value))
        return value

    def options(self) -> List[Option]:
        """
        :return: [list-of-Options]
        """
        return self.mOptions[:]

    def optionValues(self) -> list:
        """
        :return: [list-str-of-Option-Values]
        """
        return [o.value() for o in self.options()]

    sigOptionsRemoved = pyqtSignal(list)

    def removeOptions(self, options):
        """
        Removes a list of options from this Options list.
        :param options: [list-of-Options]
        """
        options = [self.o2o(o) for o in options]
        options = [o for o in options if o in self.mOptions]
        removed = []
        for o in options:
            row = self.mOptions.index(o)
            self.beginRemoveRows(QModelIndex(), row, row)
            o2 = self.mOptions[row]
            self.mOptions.remove(o2)
            removed.append(o2)
            self.endRemoveRows()

        if len(removed) > 0:
            self.sigOptionsRemoved.emit(removed)

    def clear(self):
        self.removeOptions(self.mOptions)

    def rowCount(self, parent=None, *args, **kwargs) -> int:
        return len(self.mOptions)

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 1

    def idx2option(self, index):
        if index.isValid():
            return self.mOptions[index.row()]
        return None

    def option2idx(self, option):
        if isinstance(option, Option):
            option = option.mValue

        idx = self.createIndex(None, -1, 0)
        for i, o in enumerate(self.mOptions):
            assert isinstance(o, Option)
            if o.mValue == option:
                idx.setRow(i)
                break
        return idx

    def optionNames(self):
        return [o.mName for o in self.mOptions]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if (index.row() >= len(self.mOptions)) or (index.row() < 0):
            return None
        option = self.idx2option(index)
        if not isinstance(option, Option):
            s = ""
        result = None
        if role == Qt.DisplayRole:
            result = '{}'.format(option.mName)
        elif role == Qt.ToolTipRole:
            result = '{}'.format(option.mName if option.mTooltip is None else option.mTooltip)
        elif role == Qt.DecorationRole:
            result = QIcon(option.mIcon)
        elif role == Qt.UserRole:
            result = option
        return result


class TreeNode(QObject):
    beginAddChildNodes = pyqtSignal(object, int, int)
    endAddChildNodes = pyqtSignal(object, int, int)
    beginRemoveChildNodes = pyqtSignal(object, int, int)
    endRemoveChildNodes = pyqtSignal(object, int, int)
    sigUpdated = pyqtSignal(object)

    def __init__(self,
                 name: str = None,
                 value: any = None,
                 values=None,
                 icon: QIcon = None,
                 toolTip: str = None,
                 statusTip: str = None,
                 **kwds):

        super().__init__()

        self.mParentNode: TreeNode = None
        self.mChildren: List[TreeNode] = []
        self.mName: str = name
        self.mValues: list = []
        self.mIcon: QIcon = None
        self.mToolTip: str = None
        self.mCheckState: Qt.CheckState = Qt.Unchecked
        self.mCheckable: bool = False
        self.mStatusTip: str = ''

        if name:
            self.setName(name)
        if value is not None:
            self.setValue(value)
        if icon:
            self.setIcon(icon)
        if toolTip:
            self.setToolTip(toolTip)
        if statusTip:
            self.setStatusTip(statusTip)

        if values is not None:
            self.setValues(values)

    def populateContextMenu(self, menu: QMenu):
        """
        Overwrite to provide a TreeNode specific context menu
        :param menu:
        :return:
        """
        pass

    def __iter__(self):
        return iter(self.mChildren)

    def __repr__(self):
        return f'{super().__repr__()}"{self.name()}"'

    def __len__(self):
        return len(self.mChildren)

    def __contains__(self, item):
        return item in self.mChildren

    def __getitem__(self, slice):
        return self.mChildren[slice]

    def depth(self) -> int:
        d = 0
        parent = self.parentNode()
        while isinstance(parent, TreeNode):
            d += 1
            parent = parent.parentNode()
        return d

    def columnCount(self) -> int:
        """
        A node has at least one column for its name
        :return:
        :rtype:
        """
        return len(self.mValues) + 1

    def expanded(self) -> bool:
        return self.mExpanded is True

    def setStatusTip(self, statusTip: str):
        """
        Sets the nodes's status tip to the string specified by statusTip.
        :param statusTip: str
        """
        assert isinstance(statusTip, str)
        self.mStatusTip = statusTip

    def statusTip(self) -> str:
        """
        Returns the nodes's status tip.
        :return: str
        """
        return self.mStatusTip

    def setCheckState(self, checkState):
        assert isinstance(checkState, (int, Qt.CheckState))
        self.mCheckState = checkState
        self.sigUpdated.emit(self)

    def canFetchMore(self) -> bool:
        """
        To be overwritten by TreeNodes that can fetch data.
        Need to implement .fetch() as well
        :return:
        """
        return False

    def fetch(self):
        """
        To be overwritten by TreeNodes that allow to fetch data.
        :return:
        """
        pass

    def checkState(self) -> Qt.CheckState:
        return self.mCheckState

    def checked(self) -> bool:
        return self.isCheckable() and self.mCheckState == Qt.Checked

    def isCheckable(self) -> bool:
        return self.mCheckable is True

    def setCheckable(self, b: bool):
        assert isinstance(b, bool)
        self.mCheckable = b

    def clone(self, parent=None):

        n = TreeNode(parent)
        n.mName = self.mName
        n.mValues = copy.copy(self.mValues[:])
        n.mIcon = QIcon(self.mIcon)
        n.mToolTip = self.mToolTip

        for childNode in self.mChildren:
            assert isinstance(childNode, TreeNode)
            childNode.clone(parent=n)
        return n

    def nodeIndex(self) -> int:
        p = self.parentNode()
        if isinstance(p, TreeNode):
            return p.mChildren.index(self)
        else:
            None

    def next(self):
        p = self.parentNode()
        if isinstance(p, TreeNode):
            i = p.mChildren.index(self)
            if i < len(p.mChildren) - 1:
                return p.mChildren[i + 1]
        return None

    def previous(self):
        p = self.parentNode()
        if isinstance(p, TreeNode):
            i = p.mChildren.index(self)
            if i > 0:
                return p.mChildren[i - 1]
        return None

    def detach(self):
        """
        Detaches this TreeNode from its parent TreeNode
        :return:
        """
        p = self.parent()
        if isinstance(p, TreeNode):
            p.removeChildNodes(self)

    def hasChildren(self) -> bool:
        return len(self.mChildren) > 0

    def appendChildNodes(self, child_nodes):
        self.insertChildNodes(len(self.mChildren), child_nodes)

    def insertChildNodes(self, index: int, child_nodes):
        assert index <= len(self.mChildren)
        if isinstance(child_nodes, TreeNode):
            child_nodes = [child_nodes]
        assert isinstance(child_nodes, list)
        unique = []
        for n in child_nodes:
            if n not in unique and n not in self.mChildren:
                unique.append(n)

        child_nodes = unique

        n_nodes = len(child_nodes)
        if n_nodes == 0:
            return
        idxLast = index + n_nodes - 1

        self.beginAddChildNodes.emit(self, index, idxLast)

        for i, node in enumerate(child_nodes):
            assert isinstance(node, TreeNode)

            # connect node signals
            node.beginAddChildNodes.connect(self.beginAddChildNodes)
            node.endAddChildNodes.connect(self.endAddChildNodes)

            node.beginRemoveChildNodes.connect(self.beginRemoveChildNodes)
            node.endRemoveChildNodes.connect(self.endRemoveChildNodes)

            node.sigUpdated.connect(self.sigUpdated)
            node.setParentNode(self)
            self.mChildren.insert(index + i, node)

        self.endAddChildNodes.emit(self, index, idxLast)
        s = ""

    def removeAllChildNodes(self):
        self.removeChildNodes(self.childNodes())

    def removeChildNodes(self, child_nodes):
        """
        Removes child-nodes
        :param child_nodes:
        :type child_nodes:
        :return:
        :rtype:
        """
        if isinstance(child_nodes, TreeNode):
            child_nodes = [child_nodes]
        child_nodes: List[TreeNode]
        for node in child_nodes:
            assert isinstance(node, TreeNode)
            assert node in self.mChildren
            assert node.parentNode() == self

        child_nodes = sorted(child_nodes, key=lambda node: node.nodeIndex())
        removed = []
        while len(child_nodes) > 0:
            # find neighbored nodes to remove
            nextNode = child_nodes[0]
            toRemove = []
            while isinstance(nextNode, TreeNode) and nextNode in child_nodes:
                toRemove.append(nextNode)
                nextNode = nextNode.next()

            first = toRemove[0].nodeIndex()
            last = toRemove[-1].nodeIndex()

            self.beginRemoveChildNodes.emit(self, first, last)

            for node in reversed(toRemove):
                # disconnect node signals
                node.beginAddChildNodes.disconnect(self.beginAddChildNodes)
                node.endAddChildNodes.disconnect(self.endAddChildNodes)
                node.beginRemoveChildNodes.disconnect(self.beginRemoveChildNodes)
                node.endRemoveChildNodes.disconnect(self.endRemoveChildNodes)
                node.sigUpdated.disconnect(self.sigUpdated)

                self.mChildren.remove(node)

                node.setParentNode(None)

                child_nodes.remove(node)
                removed.append(node)

            self.endRemoveChildNodes.emit(self, first, last)
            s = ""

    def setToolTip(self, toolTip: str):
        """
        Sets the tooltip
        :param toolTip: str
        """
        self.mToolTip = toolTip

    def toolTip(self) -> str:
        """
        Returns a tooltip
        :return: str
        """
        return self.mToolTip

    def setParentNode(self, node: 'TreeNode'):
        self.mParentNode: TreeNode = node
        # self.setParent(node)

    def parentNode(self) -> 'TreeNode':
        return self.mParentNode

    def parentNodes(self) -> List['TreeNode']:
        """
        Returns all parent nodes
        """
        nodes = []
        p = self.mParentNode
        while isinstance(p, TreeNode):
            nodes.append(p)
            p = p.parentNode()
        return nodes

    def rootNode(self) -> 'TreeNode':
        p = self.mParentNode
        while isinstance(p, TreeNode) and isinstance(p.parentNode(), TreeNode):
            p = p.parentNode()

        return p

    def setIcon(self, icon: QIcon):
        """
        Sets the TreeNode icon
        :param icon: QIcon
        """
        if icon != self.mIcon:
            self.mIcon = icon
            self.sigUpdated.emit(self)

    def icon(self) -> QIcon:
        """
        Returns the TreeNode icon
        :return: QIcon
        """
        return self.mIcon

    def setName(self, name: str):
        """
        Sets the TreeNodes name
        :param name: str
        """
        if name != self.mName:
            self.mName = str(name)
            self.sigUpdated.emit(self)

    def name(self) -> str:
        """
        Returns the TreeNodes name
        :return: str
        """
        return self.mName

    def setValue(self, value):
        """
        Same as setValues([value])
        :param value: any
        """
        if value is None:
            self.setValues(None)
        else:
            self.setValues([value])

    def setValues(self, values: list):
        """
        Sets the values show by this TreeNode
        :param values: [list-of-values]
        """
        if not isinstance(values, list):
            values = [values]

        if self.mValues != values:
            self.mValues.clear()
            self.mValues.extend(values)
            self.sigUpdated.emit(self)

    def values(self) -> list:
        """
        Returns the list of values
        :return:
        """
        return self.mValues[:]

    def value(self):
        """
        Returns the first value of all defined values or None, if no values are defined.
        :return:
        """
        if len(self.mValues) > 0:
            return self.mValues[0]
        else:
            return None

    def childCount(self) -> int:
        """Returns the number of child nodes"""
        return len(self.mChildren)

    def childNodes(self) -> List['TreeNode']:
        """
        Returns the child nodes
        :return: [list-of-TreeNodes]
        """
        return self.mChildren[:]

    def findParentNode(self, nodeType) -> Type['TreeNode']:
        """
        Returns the next upper TreeNode of type "nodeType"
        :param nodeType:
        :return: TreeNode of type "nodeType" or None
        """

        parent = self.parentNode()
        if not isinstance(parent, TreeNode):
            return None
        elif isinstance(parent, nodeType):
            return parent
        else:
            return parent.findParentNode(nodeType)

    def findChildNodes(self, type, recursive: bool = True):
        """
        Returns a list of child nodes with node-type `type`.
        :param type: node-class
        :param recursive: if True (default), will search for nodes of type `type` also in child and child-child nodes.
        :return: [list-of-TreeNodes]
        """
        results = []
        for node in self.mChildren:
            if isinstance(node, type):
                results.append(node)
            if recursive:
                results.extend(node.findChildNodes(type, recursive=True))
        return results


class OptionTreeNode(TreeNode):

    def __init__(self, optionModel: OptionListModel, *args, option: Option = None, **kwds):
        super().__init__(*args, **kwds)

        assert isinstance(optionModel, OptionListModel)
        self.mOptionModel = optionModel
        self.mOption: Option = None
        if option is None and len(optionModel) > 0:
            option = optionModel[0]
        self.setOption(option)

    def optionModel(self) -> OptionListModel:
        return self.mOptionModel

    def setOption(self, option: Option):
        assert option in self.mOptionModel
        self.mOption = option
        self.setValue(option.name())

    def option(self) -> Option:
        return self.mOption

    def options(self) -> List[Option]:
        return self.mOptionModel.options()


class NumpyArrayIterator(object):
    """
    Iterator for numpy.ndArrays
    """

    def __init__(self, array: np.ndarray):
        assert isinstance(array, np.ndarray)
        self.mArray = array
        self.mIndex = -1
        self.mMax = array.shape[0]

    def __str__(self):
        return 'NumpyArrayIterator'

    def __iter__(self):
        return self

    def __next__(self):
        self.mIndex += 1
        if self.mIndex < self.mArray.shape[0]:
            if self.mArray.ndim > 1:
                return self.mIndex, self.mArray[self.mIndex, :]
            else:
                return self.mIndex, self.mArray[self.mIndex]
        else:
            raise StopIteration


class PyObjectTreeNode(TreeNode):

    def __init__(self, *args, obj=None, **kwds):
        super().__init__(*args, **kwds)

        self.mPyObject = obj
        self.mFetchIterator = None
        self.mIsFetched: bool = False

        # end-nodes which cannot be fetched deeper
        if isinstance(obj, (int, float, str)):
            self.setValue(obj)
            self.mIsFetched = True

        else:
            max_line_width = 128
            subnodes = []
            if isinstance(obj, np.ndarray):
                subnodes.append(TreeNode('min', value=obj.min()))
                subnodes.append(TreeNode('max', value=obj.max()))
                subnodes.append(TreeNode('shape', value=obj.shape))
                subnodes.append(TreeNode('dtype', value=obj.dtype))
                subnodes.append(TreeNode('size', value=obj.size))
                # value = np.array2string(obj, max_line_width=max_line_width)
                value = str(obj)
            elif isinstance(obj, (bytearray, bytes)):
                value = str(obj)
            else:
                value = str(obj)

            value = value.strip()
            if len(value) > max_line_width:
                value = value[0:max_line_width - 3] + '...' + value[-3:]
            self.setValue(value)
            self.setToolTip(f'{self.name()} {value}')
            if len(subnodes) > 0:
                self.appendChildNodes(subnodes)

    def canFetchMore(self) -> bool:
        return not self.mIsFetched

    @staticmethod
    def valueAndTooltip(obj) -> Tuple[str, str]:
        pass

    def hasChildren(self) -> bool:
        return self.canFetchMore() or len(self.mChildren) > 0

    def fetch(self):
        FETCH_SIZE = 10
        # print(f'Fetch {self}: "{self.name()}"...')

        if self.mFetchIterator is None:
            if isinstance(self.mPyObject, (list, tuple)):
                self.mFetchIterator = enumerate(self.mPyObject)
            elif isinstance(self.mPyObject, np.ndarray):
                # self.mFetchIterator = iter(self.mPyObject[:,])
                self.mFetchIterator = iter({'array': NumpyArrayIterator(self.mPyObject),
                                            # 'internals': iter(self.mPyObject)
                                            }.items())
            elif isinstance(self.mPyObject, NumpyArrayIterator):
                self.mFetchIterator = self.mPyObject
            elif isinstance(self.mPyObject, dict):
                self.mFetchIterator = iter(self.mPyObject.items())
            elif isinstance(self.mPyObject, object):
                self.mFetchIterator = iter(sorted(inspect.getmembers(self.mPyObject)))
            elif isinstance(iter(self.mPyObject), Iterator):
                self.mFetchIterator = self.mPyObject
            else:
                self.mIsFetched = True
                return

        newNodes: List[PyObjectTreeNode] = []

        i = 0
        try:
            while i < FETCH_SIZE:
                k, v = self.mFetchIterator.__next__()

                if isinstance(k, str) and k.startswith('__'):
                    continue
                if isinstance(v, (types.BuiltinFunctionType,
                                  pyqtSignal,
                                  pyqtBoundSignal,
                                  sip.wrappertype)
                              ) or \
                        inspect.isfunction(v) or \
                        inspect.ismethod(v):
                    continue

                # create a new node
                # this allows to create a new node even of inherited classes
                newNodes.append(self.__class__(name=str(k), obj=v))
                i += 1

        except StopIteration:
            self.mIsFetched = True

        if len(newNodes) > 0:
            self.appendChildNodes(newNodes)


class TreeModel(QAbstractItemModel):
    """
    A QAbstractItemModel implementation to be used in QTreeViews
    """

    def __init__(self, parent: QObject = None, rootNode: TreeNode = None):
        super().__init__(parent)

        self.mRootNode: TreeNode
        if isinstance(rootNode, TreeNode):
            self.mRootNode = rootNode
        else:
            self.mRootNode = TreeNode(name='<root node>')

        self.mRootNode.setParent(self)

        # monitors the number of being/end blocks for removing / inserting rows
        self.mCNT_REMOVE = 0
        self.mCNT_INSERT = 0

        self.mRootNode.setValues(['Name', 'Value'])
        self.mRootNode.beginAddChildNodes.connect(self.beginInsertNodes)
        self.mRootNode.endAddChildNodes.connect(self.endInsertNodes)
        self.mRootNode.beginRemoveChildNodes.connect(self.beginRemoveNodes)
        self.mRootNode.endRemoveChildNodes.connect(self.endRemoveNodes)
        self.mRootNode.sigUpdated.connect(self.onNodeUpdated)

    def setColumnNames(self, names):
        assert isinstance(names, list)
        self.mRootNode.setValues(names)

    def __contains__(self, item):
        return item in self.mRootNode

    def __getitem__(self, slice):
        return self.mRootNode[slice]

    def rootNode(self) -> TreeNode:
        """
        Returns the (invisible) root node
        :return: TreeNode
        """
        return self.mRootNode

    def setupNodeConnections(self, node: TreeNode):
        assert isinstance(node, TreeNode)

    def beginInsertNodes(self, node: TreeNode, first: int, last: int):
        parent = self.node2idx(node)
        if node == self.mRootNode or parent.isValid():
            self.beginInsertRows(parent, first, last)
        else:
            s = ""

    def endInsertNodes(self, node: TreeNode, first: int, last: int):
        self.endInsertRows()
        s = ""
        # self.mCNT_INSERT -= 1
        # parent = self.node2idx(node)
        # idx1 = self.index(first, 0, parent)
        # idx2 = self.index(last, 0, parent)
        # self.dataChanged.emit(idx1, idx2)

    def maxColumnCount(self, index: QModelIndex) -> int:
        assert isinstance(index, QModelIndex)
        cnt = self.columnCount(index)
        for row in range(self.rowCount(index)):
            idx = self.index(row, 0, index)
            cnt = max(cnt, self.maxColumnCount(idx))
        return cnt

    def beginRemoveNodes(self, node: TreeNode, first: int, last: int):
        parent = self.node2idx(node)
        if node == self.mRootNode or parent.isValid():
            self.beginRemoveRows(parent, first, last)
        # self.mCNT_REMOVE += 1
        # idxNode = self.node2idx(node)
        # self.beginRemoveRows(idxNode, first, last)

    def endRemoveNodes(self, node: TreeNode, first: int, last: int):
        self.endRemoveRows()
        # self.mCNT_REMOVE -= 1

    def onNodeUpdated(self, node: TreeNode):

        # if self.mCNT_REMOVE > 0:
        #    # do not emit dataChanged while being in begin/end removeRows!
        #    return
        # if self.mCNT_INSERT > 0:
        #    # do not emit dataChanged while being in begin/end addRows!
        #    return

        idx = self.node2idx(node)
        idx2 = self.index(idx.row(), node.columnCount() - 1, parent=idx.parent())
        self.dataChanged.emit(idx, idx2)
        s = ""

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self.mRootNode.values()):
                return self.mRootNode.values()[section]
            else:
                return f'Column {section + 1}'
        return None

    def parent(self, index: QModelIndex) -> QModelIndex:
        """
        Returns the parent index of a QModelIndex `index`
        :param index: QModelIndex
        :return: QModelIndex
        """
        if not index.isValid():
            return QModelIndex()

        childNode: TreeNode = index.internalPointer()
        parentNode: TreeNode = childNode.parentNode()

        if parentNode == self.rootNode() or parentNode is None:
            return QModelIndex()

        else:
            idx = self.node2idx(parentNode)
            if idx.column() != 0:
                s = ""
            return self.createIndex(idx.row(), idx.column(), parentNode)
        s = ""

    def rowCount(self, parent: QModelIndex = None) -> int:
        """
        Return the row-count, i.e. number of child node for a TreeNode at index `index`.
        :param index: QModelIndex
        :return: int
        """
        if parent is None:
            parent = QModelIndex()

        if not parent.isValid():
            return self.mRootNode.childCount()
        else:
            if parent.column() > 0:
                return 0
            else:
                node: TreeNode = parent.internalPointer()
                if isinstance(node, PyObjectTreeNode):
                    s = ""
                return node.childCount()

    def hasChildren(self, parent: QModelIndex = None) -> bool:
        """
        Returns True if a TreeNode at index `index` has child nodes.
        :param index: QModelIndex
        :return: bool
        """
        if parent is None:
            parent = QModelIndex()

        if parent.isValid():
            node = parent.internalPointer()
        else:
            node = self.rootNode()
        return node.hasChildren()

    def columnNames(self) -> list:
        """
        Returns the column names
        :return: [list-of-string]
        """
        return self.mColumnNames[:]

    def printModel(self,
                   index: Union[QModelIndex, TreeNode],
                   prefix: str = '',
                   depth: int = 1):
        """
        Prints the model oder a sub-node specified by index. Usable for debugging.
        :param index: QModelIndex or TreeNode
        :type index:
        :param prefix:
        :type prefix:
        :param depth: depth to which sub-nodes should be print
        """
        if depth == -1:
            return
        if index is None:
            index = QModelIndex()
        if isinstance(index, TreeNode):
            index = self.node2idx(index)
        print(f'{prefix} {self.data(index, role=Qt.DisplayRole)}')
        depth = depth - 1
        for r in range(self.rowCount(index)):
            idx = self.index(r, 0, parent=index)
            self.printModel(idx, prefix=f'{prefix}-', depth=depth)

    def span(self, idx) -> QSize():

        return super(TreeModel, self).span(idx)

    def canFetchMore(self, parent: QModelIndex) -> bool:

        if not parent.isValid() or parent.column() > 0:
            return False

        node = parent.internalPointer()

        if isinstance(node, PyObjectTreeNode):
            s = ""
        if isinstance(node, TreeNode):
            return node.canFetchMore()
        else:
            return False

    def fetchMore(self, index: QModelIndex):
        """
        Fetches node content, if implemented with TreeNode.fetch()
        :param index:
        :return:
        """
        node = index.internalPointer()
        if isinstance(node, TreeNode):
            node.fetch()

    def columnCount(self, parent: QModelIndex = None) -> int:
        """
        Returns the number of columns
        :param index: QModelIndex
        :return:
        """
        return len(self.mRootNode.values())

        """
        if not isinstance(parent, QModelIndex):
            parent = QModelIndex()
        if not parent.isValid():
            return len(self.rootNode().values())

        parentNode: TreeNode = parent.internalPointer()
        assert isinstance(parentNode, TreeNode)

        return parentNode.columnCount()
        """

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        """
        Returns the QModelIndex
        :param row: int
        :param column: int
        :param parent: QModelIndex
        :return: QModelIndex
        """
        if parent is None:
            parent = QModelIndex()

        if not parent.isValid():

            parentNode: TreeNode = self.mRootNode
        else:
            parentNode: TreeNode = parent.internalPointer()

        if parentNode.childCount() > 0:
            if row < len(parentNode.mChildren):
                return self.createIndex(row, column, parentNode.mChildren[row])
            else:
                return QModelIndex()
        else:
            return QModelIndex()

    def findParentNode(self, node: TreeNode, nodeType) -> TreeNode:
        """
        finds the next parent TreeNode of type `parentNodeType`
        :param node: TreeNode
        :param parentNodeType: cls
        :return: TreeNode instance
        """
        assert isinstance(node, TreeNode)
        return node.findParentNode(nodeType)

    def indexes2nodes(self, indexes: list):
        """
        Returns the TreeNodes related to a list of QModelIndexes
        :param indexes: [list-of-QModelIndex]
        :return: [list-of-TreeNodes]
        """
        assert isinstance(indexes, list)
        nodes = []
        for idx in indexes:
            n = self.idx2node(idx)
            if n not in nodes:
                nodes.append(n)
        return nodes

    def removeNodes(self, nodes):
        """
        Removes nodes from the model
        :param nodes:
        :type nodes:
        :return:
        :rtype:
        """
        if isinstance(nodes, TreeNode):
            nodes = [nodes]

        for n in nodes:
            assert isinstance(n, TreeNode)
            idx = self.node2idx(n)
            if idx.isValid():
                n.parentNode().removeChildNodes(n)

    def nodes2indexes(self, nodes: list):
        """
        Converts a list of TreeNodes into the corresponding list of QModelIndexes
        Set indexes2nodes
        :param nodes: [list-of-TreeNodes]
        :return: [list-of-QModelIndex]
        """
        return [self.node2idx(n) for n in nodes]

    def expandNode(self, node, expand=True, recursive=True):
        assert isinstance(node, TreeNode)
        if False and isinstance(self.mTreeView, QTreeView):
            idx = self.node2idx(node)
            self.mTreeView.setExpanded(idx, expand)

            if recursive:
                for n in node.childNodes():
                    self.expandNode(n, expand=expand, recursive=recursive)

    def idx2node(self, index: QModelIndex) -> TreeNode:
        """
        Returns the TreeNode related to a valid QModelIndex `index`.
        :param index: QModelIndex
        :return: TreeNode
        """

        if not index.isValid():
            return None

        node = index.internalPointer()
        assert isinstance(node, TreeNode)
        return node

    def node2idx(self, node: TreeNode) -> QModelIndex:
        """
        Returns a TreeNode's QModelIndex
        :param node: TreeNode
        :return: QModelIndex
        """
        parentNode = node.parentNode()
        if not isinstance(node, TreeNode) or parentNode is None:
            return QModelIndex()

        parentIndex = self.node2idx(parentNode)
        row = parentNode.mChildren.index(node)
        return self.index(row, 0, parent=parentIndex)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        """

        :param index: QModelIndex
        :param role: Qt.ItemRole
        :return: object
        """
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            if role == Qt.UserRole:
                return self.rootNode()
            else:
                return None

        node = index.internalPointer()
        assert isinstance(node, TreeNode)

        if role == Qt.UserRole:
            return node

        col = index.column()

        if col == 0:
            if role in [Qt.DisplayRole, Qt.EditRole]:
                return node.name()
            if role == Qt.DecorationRole:
                return node.icon()
            if role == Qt.ToolTipRole:
                return node.toolTip()
            if role == Qt.CheckStateRole and node.isCheckable():
                return node.checkState()

        if col > 0:
            # first column is for the node name, other columns are for node values
            i = col - 1

            if len(node.values()) > i:

                if role == Qt.DisplayRole:
                    return str(node.values()[i])
                if role == Qt.EditRole:
                    return node.values()[i]
                if role == Qt.ToolTipRole:
                    tt = [f'{v}' for i, v in enumerate(node.values())]
                    tt = re.split('\n', '\n'.join(tt))
                    if len(tt) > 24:
                        tt = tt[0:23] + ['...'] + tt[23:24]
                    tt = '<br>'.join(tt)
                    return tt
        return None

    def flags(self, index):
        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


class TreeView(QTreeView):
    """
    A basic QAbstractItemView implementation to realize TreeModels.
    """
    populateContextMenu = pyqtSignal(QMenu)

    def __init__(self, *args, **kwds):
        super(TreeView, self).__init__(*args, **kwds)

        self.mAutoExpansionDepth: int = 1
        self.mModel = None
        self.mNodeExpansion: Dict[str, bool] = dict()
        self.mAutoFirstColumnSpan: bool = True

    def setAutoFirstColumnSpan(self, b: bool):
        assert isinstance(b, bool)
        self.mAutoFirstColumnSpan = b

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        menu.setToolTipsVisible(True)
        nodes = self.selectedNodes()
        if len(nodes) == 1:
            node: TreeNode = nodes[0]
            node.populateContextMenu(menu)
        self.populateContextMenu.emit(menu)

        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

    def setAutoExpansionDepth(self, depth: int):
        """
        Sets the depth until which new TreeNodes will be opened
        0 = Top nodes not expanded
        1 = Top nodes expanded
        2 = Top and Subnodes expanded
        :param depth: int
        """
        assert isinstance(depth, int)
        self.mAutoExpansionDepth = depth

    def expandSelectedNodes(self, expand: bool):
        indices = self.selectedIndexes()
        if len(indices) == 0:
            self.selectAll()
            indices += self.selectedIndexes()
            # treeView.clearSelection()
        for idx in indices:
            self.setExpanded(idx, expand)

    def updateNodeExpansion(self,
                            restore: bool,
                            index: QModelIndex = None,
                            prefix='') -> Dict[str, bool]:
        """
        Allows to save and restore the state of node expansion
        :param restore: bool, set True to save the state, False to restore it
        :param index: QModelIndex()
        :param prefix: string to identify the parent nodes
        :return: Dict[str, bool] that stores the node expansion states
        """
        assert isinstance(restore, bool)

        if not isinstance(index, QModelIndex):
            index = QModelIndex()
        if False and not (restore or index.isValid()):
            self.mNodeExpansion.clear()

        model: QAbstractItemModel = self.model()
        if isinstance(model, QAbstractItemModel):
            rows = model.rowCount(index)
            if rows > 0:
                nodeName = f'{prefix}:{model.data(index, role=Qt.DisplayRole)}'
                nodeDepth: int = self.nodeDepth(index)

                if restore:
                    # restore expansion state, if stored in mNodeExpansion
                    self.setExpanded(index, self.mNodeExpansion.get(nodeName, nodeDepth < self.mAutoExpansionDepth))
                else:
                    # save expansion state
                    self.mNodeExpansion[nodeName] = self.isExpanded(index)

                for row in range(rows):
                    idx = model.index(row, 0, index)
                    self.updateNodeExpansion(restore, index=idx, prefix=nodeName)

        return self.mNodeExpansion

    def setModel(self, model: QAbstractItemModel):
        """
        Sets the TreeModel
        :param model: TreeModel
        """
        super().setModel(model)

        self.mModel = model
        if isinstance(self.mModel, QAbstractItemModel):
            self.mModel.modelReset.connect(self.onModelReset)
            self.mModel.dataChanged.connect(self.onDataChanged)
            self.mModel.rowsInserted.connect(self.onRowsInserted)

        # update column spans
        self.onModelReset()

    def onModelReset(self):
        if self.mAutoFirstColumnSpan:
            self.setColumnSpan(QModelIndex(), None, None)

    def nodeDepth(self, index: QModelIndex) -> int:
        if not index.isValid():
            return 0
        return 1 + self.nodeDepth(index.parent())

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        if self.mAutoFirstColumnSpan:
            self.setColumnSpan(parent, first, last)
        else:
            s = ""
        if True:
            level = self.nodeDepth(parent)
            if level < self.mAutoExpansionDepth:
                self.setExpanded(parent, True)

    def onDataChanged(self, tl: QModelIndex, br: QModelIndex, roles):
        if self.mAutoFirstColumnSpan:
            self.setColumnSpan(tl.parent(), tl.row(), br.row())

    def setColumnSpan(self, parent: QModelIndex, first: int, last: int):
        """
        Sets the column span for node in rows "first" to "last" recursively
        :param parent:
        :param first: (optional) 1st row to set column span for. Defaults to 0
        :param last: (optional) last row to set column span for. Defaults to rowCount()-1 of parent
        """

        model: QAbstractItemModel = self.model()
        if not isinstance(model, QAbstractItemModel):
            return
        assert isinstance(parent, QModelIndex)

        if parent.column() > 0:
            return

        rows = model.rowCount(parent)
        cols = model.columnCount(parent)

        if rows == 0:
            return
        if not isinstance(first, int):
            first = 0
        if not isinstance(last, int):
            last = rows - 1

        assert last < rows
        assert first <= last

        for r in range(first, last + 1):
            idx0: QModelIndex = model.index(r, 0, parent)
            node = idx0.data(Qt.UserRole)
            if isinstance(node, PyObjectTreeNode):
                # workaround for EnMAP-Box issue 672 and issue 737
                # https://bitbucket.org/hu-geomatics/enmap-box/issues/672
                # https://bitbucket.org/hu-geomatics/enmap-box/issues/737
                continue

            spanned: bool = True

            for c in range(1, cols):
                idx_right = model.index(r, c, parent)
                if idx_right.isValid():
                    txt = idx_right.data(Qt.DisplayRole)
                    if txt not in [None, '']:
                        spanned = False
                        break

            self.setFirstColumnSpanned(r, parent, spanned)

        return

    def selectedNode(self) -> TreeNode:
        """
        Returns the first of all selected TreeNodes
        :return: TreeNode
        """
        for i in self.selectedIndexes():
            node = self.model().data(i, Qt.UserRole)
            if isinstance(node, TreeNode):
                return node

        return None

    def selectedNodes(self) -> list:
        """
        Returns all selected TreeNodes
        :return: [list-of-TreeNodes]
        """
        nodes = []
        for i in self.selectedIndexes():
            node = self.model().data(i, Qt.UserRole)
            if isinstance(node, TreeNode) and node not in nodes:
                nodes.append(node)
        return nodes


class SettingsNode(TreeNode):

    def __init__(self, settings: QgsSettings, settings_key: str, **kwds):
        super(SettingsNode, self).__init__(**kwds)
        self.mSettings: QgsSettings = settings
        self.mSettingsKey = f'{settings.group()}/{settings_key}'
        self.mType = type(self.value())


class SettingsModel(TreeModel):
    sigSettingsValueChanged = pyqtSignal(str)

    def __init__(self,
                 settings: QgsSettings,
                 key_filter: re.Pattern = '.*',
                 options: Dict = None,
                 ranges: Dict = None,
                 parent: QObject = None):

        super().__init__(parent=parent)

        self.mRANGES: Dict[str, Tuple] = dict()
        self.mOPTIONS: Dict[str, List[Option]] = dict()
        self.mSettings: QgsSettings = None
        self.initSettings(settings, key_filter=key_filter)
        if options:
            self.updateOptions(options)

        if ranges:
            self.updateRanges(ranges)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        node = index.data(Qt.UserRole)

        if isinstance(node, SettingsNode):
            flags = flags | Qt.ItemIsEditable
            if isinstance(node.value(), bool):
                flags = flags | Qt.ItemIsUserCheckable
        return flags

    def keys(self) -> List[str]:
        keys = [n.mSettingsKey for n in self.findChildren(SettingsNode)]
        return keys

    def updateRanges(self, ranges: Dict[str, Tuple]):
        for k, v in ranges.items():
            assert len(v) >= 2

        self.mRANGES.update(ranges)

    def updateOptions(self, options: Dict[str, List[Option]]):
        assert isinstance(options, dict)
        opt = dict()
        for k, olist in options.items():
            olist2 = []
            for o in olist:
                if isinstance(o, enum.Enum):
                    icon = None
                    try:
                        icon = o.icon(o.value)
                    except Exception:
                        pass
                    o = Option(value=o.value, name=o.name, toolTip=str(o), icon=icon)
                if not isinstance(o, Option):
                    o = Option(o)
                olist2.append(o)

            opt[k] = olist2

        self.mOPTIONS.update(opt)

    def initSettings(self, settings: QgsSettings,
                     key_filter: Union[Pattern, str] = None):

        self.mSettings = settings

        if not isinstance(key_filter, list):
            key_filter = [key_filter]

        for i in range(len(key_filter)):
            if isinstance(key_filter[i], str):
                key_filter[i] = re.compile(key_filter[i])
            assert isinstance(key_filter[i], Pattern)

        self.mRootNode.removeAllChildNodes()
        self._readGroup(settings, '', self.mRootNode, key_filter)

    def _readGroup(self, settings: QgsSettings, group: str, parent_node: TreeNode, key_filter):
        settings.beginGroup(group)
        added_nodes = []
        for k in settings.childKeys():
            longkey = f'{settings.group()}/{k}'
            for filter in key_filter:
                if filter.match(longkey):
                    parts = k.split('/')
                    value = settings.value(k)
                    node = SettingsNode(settings, k, value=value, name=parts[-1])
                    added_nodes.append(node)
        for g in settings.childGroups():
            node = TreeNode(name=g)
            self._readGroup(settings, g, node, key_filter)
            if len(node) > 0:
                added_nodes.append(node)
        settings.endGroup()
        parent_node.appendChildNodes(added_nodes)

    def setting_key_node(self, key: str) -> SettingsNode:

        for n in self.mRootNode.findChildNodes(SettingsNode, recursive=True):
            assert isinstance(n, SettingsNode)
            if n.mSettingsKey == key:
                return n
        return None

    def sync(self):
        pass

    def data(self, index: QModelIndex, role=Qt.DisplayRole):

        if not index.isValid():
            return None

        node = index.internalPointer()

        if isinstance(node, SettingsNode) and index.column() == 1:
            value = node.value()
            k = node.mSettingsKey
            option = None
            for o in self.mOPTIONS.get(k, []):
                o: Option
                if o.value() == value:
                    option = o
                    break

            # handle colors
            if isinstance(value, QColor):
                if role == Qt.DecorationRole:
                    return value
                if role == Qt.DisplayRole:
                    return value.name()

            if role == Qt.DecorationRole:
                if isinstance(option, Option):
                    return option.icon()

            if role == Qt.ToolTipRole:
                if isinstance(option, Option):
                    return option.toolTip()
                else:
                    return f'{value}'

            if role == Qt.EditRole:
                return value

            if role == Qt.UserRole + 1:
                return self.mOPTIONS.get(node.mSettingsKey, None)

            if role == Qt.UserRole + 2:
                return self.mRANGES.get(node.mSettingsKey, None)

        return super().data(index, role=role)

    def setData(self, index: QModelIndex, value, role=None) -> bool:

        if not index.isValid():
            return False

        node = index.data(Qt.UserRole)

        if not isinstance(node, SettingsNode):
            return False

        old_value = node.value()
        if old_value != value:
            node.setValue(value)  # this triggers the dataChanged signal
            self.sigSettingsValueChanged.emit(node.mSettingsKey)
            return True

        return False


class SettingsTreeViewDelegate(QStyledItemDelegate):
    """

    """

    def __init__(self, parent=None):
        super(SettingsTreeViewDelegate, self).__init__(parent=parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # cName = self.mTableView.model().headerData(index.column(), Qt.Horizontal)
        c = index.column()

        value = index.data(Qt.UserRole)

        super().paint(painter, option, index)

    def setItemDelegates(self, tableView: QTableView):
        for c in range(tableView.model().columnCount()):
            tableView.setItemDelegateForColumn(c, self)

    def createEditor(self, parent, option, index):
        # cname = self.bridgeColumnName(index)
        # bridge = self.bridge()
        # pmodel = self.sortFilterProxyModel()

        w = None
        if index.isValid() and index.column() == 1:
            value = index.data(Qt.EditRole)
            options = index.data(Qt.UserRole + 1)
            range = index.data(Qt.UserRole + 2)

            if isinstance(value, QColor):
                w = QgsColorButton(parent=parent)
            elif isinstance(options, list):
                w = QComboBox(parent=parent)
                model = OptionListModel(options)
                w.__model = model
                w.setModel(model)

            elif isinstance(range, tuple):
                v_min, v_max = range[0], range[1]
                if isinstance(v_min, int):
                    w = QgsSpinBox(parent=parent)
                    w.setRange(range[0], range[1])
                elif isinstance(v_min, float):
                    w = QgsDoubleSpinBox(parent=parent)
                    w.setRange(range[0], range[1])
            else:
                w = super().createEditor(parent, option, index)
        return w

    def setEditorData(self, editor, index: QModelIndex):

        if index.isValid():
            value = index.data(Qt.EditRole)
            if isinstance(editor, QgsColorButton):
                assert isinstance(value, QColor)
                editor.setColor(value)
            elif isinstance(editor, QComboBox):
                setCurrentComboBoxValue(editor, value)
            elif isinstance(editor, (QgsSpinBox, QgsDoubleSpinBox)):
                editor.setValue(value)
            else:
                super().setEditorData(editor, index)

    def setModelData(self, w, model, index):

        if index.isValid():
            value_old = index.data(Qt.EditRole)
            value_new = None
            if isinstance(w, QgsColorButton):
                model.setData(index, w.color())
            elif isinstance(w, (QgsSpinBox, QgsDoubleSpinBox)):
                model.setData(index, w.value())
            elif isinstance(w, QComboBox):
                value = currentComboBoxValue(w)
                model.setData(index, value)
            else:
                super().setModelData(w, model, index)


class SettingsTreeView(TreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setAutoExpansionDepth(2)
        self.mDelegate = SettingsTreeViewDelegate(self)
        self.setItemDelegate(self.mDelegate)
