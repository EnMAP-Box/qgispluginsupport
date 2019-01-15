# noinspection PyPep8Naming
import unittest, json, pickle
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qps.testing import initQgisApplication

from qps.models import *

QAPP = initQgisApplication()
SHOW_GUI = False

class ModelTests(unittest.TestCase):

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
        n2 = TreeNode(node)
        QApplication.processEvents()
        self.assertTrue(len(argList) > 0)

    def test_treeModel(self):

        TM = TreeModel()
        self.assertIsInstance(TM, TreeModel)

        self.assertIsInstance(TM.rootNode(), TreeNode)

        node = TM.rootNode()

    def test_modelview(self):

        treeModel = TreeModel()
        cbModel = OptionListModel()
        for k in sorted(os.environ.keys()):
            v = os.environ[k]
            cbModel.addOption(Option(v, k, tooltip=v))

        cb = QComboBox()
        cb.setModel(cbModel)
        cb.show()

        tv = QTreeView(None)
        tv.show()
        tv.setModel(treeModel)

        rn = treeModel.rootNode()
        n1 = TreeNode(None, 'Node1')
        rn.appendChildNodes([n1])
        rn.appendChildNodes([TreeNode(rn, 'Node2')])
        n3 = TreeNode(None, 'Node3')
        n4 = TreeNode(None, 'Node4')
        n1.appendChildNodes([n3])
        n1.appendChildNodes(n4)

        print('DONE')


if __name__ == '__main__':

    unittest.main()
