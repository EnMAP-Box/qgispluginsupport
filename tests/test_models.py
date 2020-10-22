# noinspection PyPep8Naming
import unittest
import xmlrunner
import os
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtWidgets import QMenu, QComboBox, QTreeView, QApplication
from qps.models import TreeModel, TreeView, TreeNode, OptionListModel, Option
from qps.testing import TestCase

class ModelTests(TestCase):

    def test_treeNode(self):

        node = TreeNode(None)
        self.assertIsInstance(node, TreeNode)

        argList = list()
        kwdList = list()

        def onSignal(*args, **kwargs):
            nonlocal argList, kwdList
            argList.append(args)
            kwdList.append(kwargs)

        node.sigAddedChildren.connect(onSignal)
        n2 = TreeNode()
        self.assertIsInstance(n2, TreeNode)
        node.appendChildNodes(n2)
        self.assertEqual(n2.parentNode(), node)
        QApplication.processEvents()
        self.assertTrue(len(argList) > 0)

        t = 'test'
        n2.setToolTip(t)
        assert n2.toolTip() == t

        n2.setStatusTip(t)
        assert n2.statusTip() == t

    def test_treeModel(self):

        TM = TreeModel()

        self.assertIsInstance(TM, TreeModel)

        self.assertIsInstance(TM.rootNode(), TreeNode)
        parent = TM.rootNode()

        idxParent = TM.node2idx(parent)
        self.assertIsInstance(idxParent, QModelIndex)
        self.assertEqual(TM.idx2node(idxParent), TM.rootNode())

        n = 5
        nodes = []
        for i in range(n):
            n = TreeNode('Node {}'.format(i + 1))
            parent.appendChildNodes(n)
            self.assertTrue(n.parentNode() == parent)
            nodes.append(n)

            parent = n

        for node in nodes:
            idx = TM.node2idx(node)
            self.assertIsInstance(idx, QModelIndex)
            self.assertTrue(idx.internalPointer() == node)

        self.assertTrue(TM.rowCount(None), 1)

    def test_treeView(self):

        TV = TreeView()
        self.assertIsInstance(TV, TreeView)
        TM = TreeModel()
        TV.setModel(TM)

        self.assertEqual(TV.model(), TM)

        class TestNodeA(TreeNode):

            def __init__(self, *args, **kwds):
                super(TestNodeA, self).__init__(*args, **kwds)

        class TestNodeB(TreeNode):

            def __init__(self, *args, **kwds):
                super(TestNodeB, self).__init__(*args, **kwds)

            def contextMenu(self) -> QMenu:
                m = QMenu()
                m2 = m.addMenu('SubMenu')
                return m

        nodes = []
        n = 5
        parent = TM.rootNode()
        for i in range(n):
            n = TreeNode(pname='Node {}'.format(i + 1), value=i)
            parent.appendChildNodes(n)
            self.assertTrue(n.parentNode() == parent)
            nodes.append(n)

            idx = TM.node2idx(n)
            self.assertIsInstance(idx, QModelIndex)
            self.assertEqual(idx.isValid(), True)
            self.assertEqual(idx.internalPointer(), n)
            n2 = TM.idx2node(idx)
            self.assertEqual(n2, n)
            parent = n

        nA = TestNodeA(name='TestNodeA')
        nB = TestNodeB('TestNodeB')
        nLast = TreeNode()
        nInBetween = TreeNode()
        nFirst = TreeNode()

        nFirst.appendChildNodes(nA)
        nA.appendChildNodes(nInBetween)
        nInBetween.appendChildNodes(nB)
        nB.appendChildNodes(nLast)

        self.assertEqual(TM.findParentNode(nLast, TestNodeA), nA)
        self.assertEqual(TM.findParentNode(nLast, TestNodeB), nB)

        nLast.parentNode().removeChildNodes(nLast)
        self.assertEqual(TM.findParentNode(nLast, TestNodeB), None)
        self.showGui(TV)

    def test_nodeColumnSpan(self):

        TV = TreeView()
        self.assertIsInstance(TV, TreeView)
        TM = TreeModel()
        TV.setModel(TM)

        TM.rootNode()
        if True:
            n1 = TreeNode(name='Node1 looooong text')
            n11 = TreeNode(name='spanned')
            n12 = TreeNode(name='value', value=1)
            n13 = TreeNode(name='value', values=[1, 2])

            n1.appendChildNodes([n11, n12, n13])
            TM.rootNode().appendChildNodes(n1)

        n2 = TreeNode(name='ins. spanned1')
        n21 = TreeNode(name='ins. value', value=[1])
        n22 = TreeNode(name='ins. spanned2')
        n23 = TreeNode(name='ins. value', value=[1])
        b24 = TreeNode(name='ins. spanned3')
        n2.appendChildNodes([n21, n22, n23, b24])
        TM.rootNode().appendChildNodes([n2])

        if True:

            n2 = TreeNode(name='mod. spanned', value=1)
            TM.rootNode().appendChildNodes(n2)
            n2.setValue(None)
            n21 = TreeNode(name='mod. value')
            n21.setValue('block')
            n2.appendChildNodes(n21)

            n21 = TreeNode(name='mod. spanned', value='do not show')
            n2.appendChildNodes(n21)
            n21.setValues(None)

        # todo: test if columns are spanned / not
        self.showGui(TV)

    def test_modelview(self):

        treeModel = TreeModel()
        cbModel = OptionListModel()
        for k in sorted(os.environ.keys()):
            v = os.environ[k]
            cbModel.addOption(Option(v, k, toolTip=v))

        cb = QComboBox()
        cb.setModel(cbModel)

        tv = QTreeView(None)

        tv.setModel(treeModel)

        rn = treeModel.rootNode()
        n1 = TreeNode('Node1')
        rn.appendChildNodes([n1])
        rn.appendChildNodes([TreeNode(rn, 'Node2')])
        n3 = TreeNode('Node3')
        n4 = TreeNode('Node4')
        n1.appendChildNodes([n3])
        n1.appendChildNodes(n4)

        self.showGui(tv)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
