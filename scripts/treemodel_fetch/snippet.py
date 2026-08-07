from typing import Optional, Any, List

from qgis.PyQt.QtCore import (
    QObject, QModelIndex
)
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem
from qgis.PyQt.QtTest import QAbstractItemModelTester
from qgis.PyQt.QtWidgets import QTreeView
from qgis.testing import QgisTestCase, start_app

app = start_app()


class TreeNode(QStandardItem):
    """
    A TreeNode that extends QStandardItem for use with QStandardItemModel.
    Provides additional metadata and helper methods.
    """

    def __init__(self, name: str = "", value: Any = None, obj: Any = None):
        super().__init__(name)

    def canFetchMore(self) -> bool:
        """Returns whether this node can fetch more children."""
        return False

    def fetchItems(self) -> List[QStandardItem]:
        return []


class FetchingNode(TreeNode):
    """
    A node that can fetch more data
    """

    def __init__(self, name: str = "FetchingNode"):
        super().__init__(name=name)

        self._is_fetched = False
        self._refs = []
        self.setText(str(name))

    def canFetchMore(self) -> bool:
        """Can fetch up to a depth of 3
        """
        m = self._parent_level()
        if m >= 3:
            self._is_fetched = True

        return not self._is_fetched

    def _parent_level(self) -> int:
        parent = self.parent()
        n = 0
        while isinstance(parent, QStandardItem):
            n += 1
            parent = parent.parent()
        return n

    def fetchItems(self) -> List[QStandardItem]:
        """Fetches 2 child nodes on demand."""
        if self._is_fetched:
            return []
        n = 2
        new_items = []

        # return child nodes
        for i in range(n):
            node = FetchingNode(f'{self.text()}-{i}')
            new_items.append(node)

        # keep a reference to the fetched items
        self._refs.extend(new_items)
        self._is_fetched = True
        return new_items


class TreeModel(QStandardItemModel):
    """
    A TreeModel using QStandardItemModel as the base.
    Provides helper methods for tree operations.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["Name"])
        self._refs = []

    def hasChildren(self, parent=None, *args, **kwargs):
        return self.rowCount(parent) > 0 or self.canFetchMore(parent)

    def canFetchMore(self, parent: QModelIndex):

        item = self.itemFromIndex(parent)

        if isinstance(item, TreeNode):
            return item.canFetchMore()
        return False

    def fetchMore(self, parent: QModelIndex):
        if not parent.isValid():
            return

        item = self.itemFromIndex(parent)

        if isinstance(item, TreeNode):
            new_items = item.fetchItems()
            n = len(new_items)
            if n > 0:
                item.appendRows(new_items)
                self._refs.extend(new_items)


class TreeModelTests(QgisTestCase):

    def test_treeNode(self):
        m = TreeModel()

        if True:
            tester = QAbstractItemModelTester(
                m,
                QAbstractItemModelTester.FailureReportingMode.Warning
            )
            self.assertIsInstance(tester, QAbstractItemModelTester)
            tester.setUseFetchMore(False)

        n = TreeNode('TOP')
        p1 = FetchingNode('Fetch')

        n.appendRow([p1])

        m.insertRow(0, n)
        idx1 = m.indexFromItem(n)
        idx2 = m.indexFromItem(p1)
        self.assertTrue(idx1.isValid())
        self.assertTrue(idx2.isValid())

        self.assertEqual(m.itemFromIndex(idx2), p1)
        self.assertEqual(m.itemFromIndex(idx1), n)

        view = QTreeView()
        view.setModel(m)
        view.expandAll()
        if not self.is_ci_run():
            view.show()
            app.exec()
