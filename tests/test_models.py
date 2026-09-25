# noinspection PyPep8Naming
import fnmatch
import os
import unittest
from typing import List, Union

import numpy as np
from qgis.PyQt.QtCore import QModelIndex, QSettings, QSortFilterProxyModel, Qt, QMetaType
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtTest import QAbstractItemModelTester
from qgis.PyQt.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QTreeView, QVBoxLayout, QWidget)
from qgis.core import QgsField, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFieldModel, QgsMapLayerModel
from qgis.gui import QgsMapCanvas

from qps.layerfielddialog import FilteredFieldProxyModel, FilteredMapLayerProxyModel
from qps.models import (
    Option, OptionListModel, PyObjectTreeNode,
    SettingsModel, SettingsNode, SettingsTreeView,
    TreeModel, TreeNode, TreeView)
from qps.plotstyling.plotstyling import MarkerSymbol
from qps.testing import start_app, TestCase, TestObjects

start_app()


def findNode(view, path: Union[str, List[str]], parent: QModelIndex = QModelIndex()) -> QModelIndex:
    """
    Returns the QModelIndex for the deepest node in a node-path., e.g. n3 from 'n1/n2/n3'
    :param view: QAbstractItemView
    :param path: node-path, e.g. 'node/subNode'
                 node names need to match on a QModelIndex.data(Qt.DisplayRole)
                 node names can be wildcard expressions
    :param parent: QModelIndex, parent of the give node-path.
    :return: QModelIndex or None
    """
    model = view.model()
    if isinstance(path, str):
        path = path.split('/')
    expression = path[0]

    child_names = []

    CHILD_NAMES = {}
    row = 0
    # last_row = None
    while True:
        if row == model.rowCount(parent):
            if model.canFetchMore(parent):
                # sm = model.sourceModel()
                # sp = model.mapToSource(parent)
                # A = [sm.index(r, 0, sp).data() for r in range(sm.rowCount(sp))]
                model.fetchMore(parent)
                # B = [sm.index(r, 0, sp).data() for r in range(sm.rowCount(sp))]
                # if len(B) == len(A) + 1 and A != B[0:-1]:
                #    s = ""
                continue
            else:
                break
        if not (row not in CHILD_NAMES):
            raise AssertionError
        CHILD_NAMES[row] = [model.index(r2, 0, parent).data() for r2 in range(row)]
        child: QModelIndex = model.index(row, 0, parent)
        child_name = child.data(Qt.ItemDataRole.DisplayRole)

        child_names.append(child_name)
        if fnmatch.fnmatch(child_name, expression):
            if len(path) == 1:
                return child
            else:
                node = findNode(view, path[1:], parent=child)
                if isinstance(node, QModelIndex):
                    return node
        # last_row = row
        row += 1

    return None


def expandNodes(view,
                path: Union[str, List[str]],
                parent: QModelIndex = QModelIndex(),
                expanded: bool = True,
                last_only: bool = False):
    """
    :param view: QAbstractItemView
    :param path: node path, e.g. 'rootNodeName/subNodeName/subsubNodeName'.
                 can contain Wildcards, e.g. 'sub*' to catch Nodes called 'subA' and 'subB'
    :param parent: QModelIndex
    :param expanded: True (default) to expand the nodes
    :param last_only: False. Set True to expand only the last node in the path.
    :return:
    """
    if isinstance(path, str):
        path = path.split('/')

    node = findNode(view, path, parent=parent)
    if isinstance(node, QModelIndex):
        if last_only:
            view.setExpanded(node, expanded)
        else:
            while node.isValid():
                view.setExpanded(node, expanded)
                node = node.parent()


class ModelTests(TestCase):

    def createTestNodes(self, parentNode: TreeNode,
                        rows: int = 2,
                        depth: int = 3,
                        cols: int = 4) -> TreeNode:
        self.assertIsInstance(parentNode, TreeNode)

        pDepth = parentNode.depth()
        if depth == pDepth:
            return parentNode

        to_add = []
        for row in range(rows):
            node = TreeNode(name=f'Node {pDepth}/{row + 1}')
            if pDepth == depth - 1:
                node.setValues([f'{row}/{cols}' for c in range(cols)])
            to_add.append(node)
        parentNode.appendChildNodes(to_add)
        for node in to_add:
            self.createTestNodes(node, rows=rows, depth=depth, cols=cols)
        return parentNode

    def test_pyObjectNodes2(self):

        tv = TreeView()
        tv.setSortingEnabled(True)

        tm = TreeModel()
        pm = QSortFilterProxyModel()
        tv.setModel(pm)
        pm.setSourceModel(tm)

        # tester = QAbstractItemModelTester(tm, QAbstractItemModelTester.FailureReportingMode.Fatal)

        # obj = {'X': np.random.rand(58, 177)}
        obj = {'X': np.random.rand(50)}
        # obj = {'X': np.random.rand(20, 10)}
        # obj = {'A':{'X': np.random.rand(50, 10)}}
        n1 = TreeNode('node')
        pynode = PyObjectTreeNode(name='Content', obj=obj)
        tm.rootNode().appendChildNodes(n1)
        n1.appendChildNodes(pynode)
        expandNodes(tv, 'node/Content/X/array')
        self.showGui(tv)

    def test_pyObjectNodes(self):

        m = TreeModel()
        tester = QAbstractItemModelTester(m, QAbstractItemModelTester.FailureReportingMode.Fatal)
        self.assertIsInstance(tester, QAbstractItemModelTester)
        tester.setUseFetchMore(False)

        if True:
            tv = TreeView()
            tv.setUniformRowHeights(True)
            tv.setAutoExpansionDepth(5)
            tv.setIndentation(12)
        else:
            tv = QTreeView()

        longString = ''
        for b in 'abcdefghijklmsdsfdfdsfv':
            for a in range(500):
                longString += b
            longString += '\n'

        root = m.rootNode()

        DATA = {'AAA': np.asarray([[1, 2], [3, 4], [5, 6]]),
                'BBB':
                    {'B1': root,
                     'B2': {'DDD': root},
                     'NP': np.arange(256),
                     'Array2': np.random.randint(0, 255, (25, 40, 10)),
                     'Long String': longString,
                     'M': m},
                'CA': QgsMapCanvas(),
                }

        objNode0 = PyObjectTreeNode('DATA', obj=DATA)
        objNode1 = PyObjectTreeNode('Array', obj=np.asarray([[1, 2], [3, 4], [5, 6]]))
        objNode2 = PyObjectTreeNode('String', obj=[['foo', 'bar'], ['foo1', 'bar1']])

        n = TreeNode('TOP')
        root.appendChildNodes(n)
        n2 = TreeNode('TOP2')
        n.appendChildNodes(n2)

        for node in [objNode0,
                     objNode1,
                     objNode2]:
            n2.appendChildNodes(node)
        # n.appendChildNodes(n2)
        # n.appendChildNodes(objNode0)
        # n.appendChildNodes(objNode1)
        # n.appendChildNodes(objNode2)
        # n.appendChildNodes([objNode])

        # root2 = TreeNode('ROOT2')
        # root2.appendChildNodes(n)

        tv.setModel(m)
        # tv.expandAll()
        # n.appendChildNodes(n2)
        self.showGui(tv)

    def test_treeNode(self):

        node = TreeNode(None)
        self.assertIsInstance(node, TreeNode)

        argList = list()
        kwdList = list()

        def onSignal(*args, **kwargs):
            argList.append(args)
            kwdList.append(kwargs)

        node.endAddChildNodes.connect(onSignal)
        n2 = TreeNode()
        self.assertIsInstance(n2, TreeNode)
        node.appendChildNodes(n2)
        self.assertEqual(n2.parentNode(), node)

        self.assertTrue(len(argList) > 0)

        t = 'test'
        n2.setToolTip(t)
        self.assertEqual(n2.toolTip(), t)

        n2.setStatusTip(t)
        self.assertEqual(n2.statusTip(), t)

    def test_treeModelNew(self):

        TM = TreeModel()
        TM.rootNode().appendChildNodes([TreeNode('Node1')])
        TM.rootNode().appendChildNodes([TreeNode('Node2')])
        _ = QAbstractItemModelTester(TM, QAbstractItemModelTester.FailureReportingMode.Fatal)

    def test_treeModel(self):

        TM = TreeModel()

        self.assertIsInstance(TM, TreeModel)
        _ = QAbstractItemModelTester(TM, QAbstractItemModelTester.FailureReportingMode.Fatal)
        self.assertIsInstance(TM.rootNode(), TreeNode)
        parent = TM.rootNode()

        idxParent = TM.node2idx(parent)
        self.assertIsInstance(idxParent, QModelIndex)
        n = 2
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

        view = QTreeView()
        view.setModel(TM)
        self.showGui(view)

    def test_treeViewSpan(self):

        TV = TreeView()
        TM = TreeModel()
        _ = QAbstractItemModelTester(TM, QAbstractItemModelTester.FailureReportingMode.Fatal)

        def onRowsInserted(p, first, last):
            print(f'ROWS INSERTED {p.data(Qt.ItemDataRole.UserRole).name()} {first} to {last}')

        TM.rowsInserted.connect(onRowsInserted)
        TV.setModel(TM)
        TV2 = QTreeView()
        TV2.setModel(TM)

        btnReset = QPushButton('Reset')
        btnClean = QPushButton('Clean')

        def onClean():
            TM.rootNode().removeAllChildNodes()

        def onReset(*args):
            TM.rootNode().removeAllChildNodes()

            new_nodes = []
            nA = TreeNode(name='AAAAAAAAAAAA')
            nAA = TreeNode(name='aa', value='avalues')
            nA.appendChildNodes(nAA)
            nB = TreeNode(name='BBBBBBBBBBBB')
            nBB = TreeNode(name='bb', value='bvalues')
            nB.appendChildNodes(nBB)
            new_nodes += [nA, nB]
            TM.rootNode().appendChildNodes(new_nodes)

        btnReset.clicked.connect(onReset)
        btnClean.clicked.connect(onClean)
        vbLayout = QVBoxLayout()
        lh = QHBoxLayout()
        lh.addWidget(btnReset)
        lh.addWidget(btnClean)
        vbLayout.addLayout(lh)

        lh = QHBoxLayout()
        lh.addWidget(TV)
        lh.addWidget(TV2)
        vbLayout.addLayout(lh)

        w = QWidget()
        w.setLayout(vbLayout)
        #  self.showGui(w)

    def test_treeView(self):

        TV = TreeView()
        self.assertIsInstance(TV, TreeView)
        TV.setAutoExpansionDepth(2)
        TM = TreeModel()

        TV.setModel(TM)
        tester = QAbstractItemModelTester(TM, QAbstractItemModelTester.FailureReportingMode.Fatal)
        self.assertIsInstance(tester, QAbstractItemModelTester)
        self.assertEqual(TV.model(), TM)

        class TestNodeA(TreeNode):

            def __init__(self, *args, **kwds):
                super(TestNodeA, self).__init__(*args, **kwds)

        class TestNodeB(TreeNode):

            def __init__(self, *args, **kwds):
                super(TestNodeB, self).__init__(*args, **kwds)

            def contextMenu(self) -> QMenu:
                m = QMenu()
                _ = m.addMenu('SubMenu')
                return m

        nodes = []
        n = 5
        parent = TM.rootNode()
        for i in range(n):
            n = TreeNode(name='Node {}'.format(i + 1), value=i + 1)
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
        #  self.showGui(TV)

    def test_nodeColumnSpan(self):

        TV = TreeView()
        self.assertIsInstance(TV, TreeView)
        TM = TreeModel()
        TV.setModel(TM)
        tester = QAbstractItemModelTester(TM, QAbstractItemModelTester.FailureReportingMode.Fatal)
        self.assertIsInstance(tester, QAbstractItemModelTester)
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
        #  self.showGui(TV)

    def test_proxyModel(self):

        tvR = QTreeView()
        tvRPM = QTreeView()
        tvN = TreeView()
        tvNPM = TreeView()
        css = """QTreeView::item:selected {\n    background-color: yellow;\n	color:black;\n}"""
        tvN.setStyleSheet(css)
        tvNPM.setStyleSheet(css)
        tm = TreeModel()
        self.createTestNodes(tm.rootNode())

        pm = QSortFilterProxyModel()
        pm.setSourceModel(tm)

        tvR.setModel(tm)
        tvRPM.setModel(pm)
        tvN.setModel(tm)
        tvNPM.setModel(pm)

        gridLayout = QGridLayout()
        gridLayout.addWidget(QLabel('Model'), 0, 1)
        gridLayout.addWidget(QLabel('Proxy Model'), 0, 2)
        gridLayout.addWidget(QLabel('QTreeView'), 1, 0)
        gridLayout.addWidget(QLabel('QPS Treeview'), 2, 0)
        gridLayout.addWidget(tvR, 1, 1)
        gridLayout.addWidget(tvRPM, 1, 2)
        gridLayout.addWidget(tvN, 2, 1)
        gridLayout.addWidget(tvNPM, 2, 2)

        w = QWidget()
        w.setWindowTitle('TreeModel test')
        w.setLayout(gridLayout)
        #  self.showGui(w)

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

        #  self.showGui(tv)

    def test_SettingsModel(self):

        settings = QSettings('my_app', application='my_model')
        # clear
        settings.clear()
        settings.sync()

        settings.setValue('MyColor', QColor('red'))
        settings.beginGroup('Group1')
        settings.setValue('My Group1 Text', 'text')
        settings.endGroup()
        settings.beginGroup('Group2')
        settings.setValue('MyBool', False)
        settings.setValue('Color2', QColor('orange'))
        settings.setValue('My Group2 Text', 'text')
        settings.setValue('Group2Options', 'A')
        settings.setValue('MyRangedInt', 10)
        settings.setValue('MyRangedFloat', 23)
        settings.setValue('MySymbol', 'x')

        settings.endGroup()

        OPTIONS = dict()
        RANGES = dict()
        OPTIONS['Group2/Group2Options'] = [Option('A'), Option('B'), Option('C')]
        OPTIONS['Group2/MySymbol'] = MarkerSymbol
        RANGES['Group2/MyRangedInt'] = (0, 20)
        RANGES['Group2/MyRangedFloat'] = (0.0, 20.0)

        model = SettingsModel(settings,
                              key_filter='Group2/.*',
                              options=OPTIONS,
                              ranges=RANGES)

        if False:
            idx = model.setting_key_node('Group2/Group2Options')
            self.assertIsInstance(idx, QModelIndex)
            node = idx.data(Qt.ItemDataRole.UserRole)
            self.assertIsInstance(node, SettingsNode)
            options = idx.data(Qt.ItemDataRole.UserRole + 1)
            ranges = idx.data(Qt.ItemDataRole.UserRole + 2)
            self.assertListEqual(OPTIONS['Group2/Group2Options'], options)
            self.assertEqual(RANGES['Group2/RangedValue'], ranges)

        view = SettingsTreeView()
        view.setModel(model)

        #  self.showGui(view)


class FilteredMapLayerProxyModelTests(TestCase):

    def test_init(self):
        project = QgsProject()
        model = FilteredMapLayerProxyModel(project)
        self.assertIsInstance(model, FilteredMapLayerProxyModel)
        self.assertEqual(model.project(), project)

    def test_default_filter(self):
        project = QgsProject()
        model = FilteredMapLayerProxyModel(project)
        self.assertEqual(model.project(), project)

        vl = TestObjects.createVectorLayer(name='vector')
        rl = TestObjects.createRasterLayer(name='raster')
        project.addMapLayers([vl, rl])
        cb = QComboBox()
        cb.setModel(model)
        self.showGui(cb)
        self.assertEqual(model.rowCount(), 2)

    def test_filter_vector_layers_only(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        vl2 = TestObjects.createVectorLayer(name='vector2')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl1, vl2, rl])

        model = FilteredMapLayerProxyModel(project)

        def filter_vector(layer):
            return isinstance(layer, QgsVectorLayer)

        model.setFilterFunc(filter_vector)

        self.assertEqual(model.rowCount(), 2)

    def test_filter_raster_layers_only(self):
        project = QgsProject()

        vl = TestObjects.createVectorLayer(name='vector')
        rl1 = TestObjects.createRasterLayer(name='raster1')
        rl2 = TestObjects.createRasterLayer(name='raster2')

        project.addMapLayers([vl, rl1, rl2])

        model = FilteredMapLayerProxyModel(project)
        model.setShowAll(False)

        def filter_raster(layer):
            return isinstance(layer, QgsRasterLayer)

        model.setFilterFunc(filter_raster)

        self.assertEqual(model.rowCount(), 2)

    def test_setShowAll_false_hides_filtered(self):
        project = QgsProject()

        vl = TestObjects.createVectorLayer(name='vector')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl, rl])

        model = FilteredMapLayerProxyModel(project)

        def filter_vector(layer):
            return isinstance(layer, QgsVectorLayer)

        model.setFilterFunc(filter_vector)
        model.setShowAll(False)

        self.assertEqual(model.rowCount(), 1)

        idx = model.index(0, 0)
        layer = model.data(idx, QgsMapLayerModel.CustomRole.Layer)
        self.assertIsInstance(layer, QgsVectorLayer)

    def test_layers_method(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        vl2 = TestObjects.createVectorLayer(name='vector2')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl1, vl2, rl])

        model = FilteredMapLayerProxyModel(project)

        layers = model.layers()
        self.assertEqual(len(layers), 3)
        self.assertIn(vl1, layers)
        self.assertIn(vl2, layers)
        self.assertIn(rl, layers)

    def test_layer_filtering_with_layers_method(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        vl2 = TestObjects.createVectorLayer(name='vector2')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl1, vl2, rl])

        model = FilteredMapLayerProxyModel(project)

        def filter_vector(layer):
            return isinstance(layer, QgsVectorLayer)

        model.setFilterFunc(filter_vector)

        layers = model.layers()
        self.assertEqual(len(layers), 2)
        for layer in layers:
            self.assertIsInstance(layer, QgsVectorLayer)

    def test_getitem_dunder(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        vl2 = TestObjects.createVectorLayer(name='vector2')

        project.addMapLayers([vl1, vl2])

        model = FilteredMapLayerProxyModel(project)

        layer0 = model[0]
        layer1 = model[1]

        self.assertEqual(layer0, vl1)
        self.assertEqual(layer1, vl2)

    def test_layer_slicing(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        vl2 = TestObjects.createVectorLayer(name='vector2')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl1, vl2, rl])

        model = FilteredMapLayerProxyModel(project)
        for lyrP, lyrM in zip(project.mapLayers().values(), model[:]):
            self.assertEqual(lyrP, lyrM)

    def test_project_change(self):
        project1 = QgsProject()
        project2 = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='vector1')
        project1.addMapLayer(vl1)

        vl2 = TestObjects.createVectorLayer(name='vector2')
        project2.addMapLayer(vl2)

        model = FilteredMapLayerProxyModel(project1)
        self.assertEqual(model.rowCount(), 1)

        model.setProject(project2)
        self.assertEqual(model.rowCount(), 1)

        layer = model.layers()[0]
        self.assertEqual(layer, vl2)

    def test_filter_accepts_row(self):
        project = QgsProject()

        vl = TestObjects.createVectorLayer(name='vector')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl, rl])

        model = FilteredMapLayerProxyModel(project)

        def filter_vector(layer):
            return isinstance(layer, QgsVectorLayer)

        model.setFilterFunc(filter_vector)
        model.setShowAll(True)
        self.assertEqual(model.rowCount(), 2)
        model.setShowAll(False)
        self.assertEqual(model.rowCount(), 1)

        for i in range(model.rowCount()):
            layer = model.data(model.index(i, 0), QgsMapLayerModel.CustomRole.Layer)
            self.assertIsInstance(layer, QgsVectorLayer)

    def test_filter_with_complex_condition(self):
        project = QgsProject()

        vl1 = TestObjects.createVectorLayer(name='small')
        vl2 = TestObjects.createVectorLayer(name='large')
        rl = TestObjects.createRasterLayer(name='raster')

        project.addMapLayers([vl1, vl2, rl])

        model = FilteredMapLayerProxyModel(project)

        def filter_by_name(layer):
            return layer.name() in ['small', 'raster']

        model.setFilterFunc(filter_by_name)
        model.setShowAll(False)

        self.assertEqual(model.rowCount(), 2)
        names = [model.data(model.index(i, 0), Qt.ItemDataRole.DisplayRole) for i in range(model.rowCount())]
        self.assertIn('small', names)
        self.assertIn('raster', names)


class FilteredFieldProxyModelTests(TestCase):

    def test_init(self):
        model = FilteredFieldProxyModel()
        self.assertIsInstance(model, FilteredFieldProxyModel)

    def test_default_filter(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        self.assertEqual(model.rowCount(), fields.count())

    def test_filter_fields_by_type(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def filter_string_fields(field):
            return field.type() in [QgsField.Type.String]

        model.setFilterFunc(filter_string_fields)

        string_field_count = sum(1 for f in fields if f.type() == QgsField.Type.String)
        self.assertEqual(model.rowCount(), string_field_count)

    def test_setShowAll_false_hides_filtered_fields(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def filter_integer_fields(field):
            return field.type() == QgsField.Type.Int

        model.setFilterFunc(filter_integer_fields)
        model.setShowAll(False)

        int_field_count = sum(1 for f in fields if f.type() == QgsField.Type.Int)
        self.assertEqual(model.rowCount(), int_field_count)

    def test_setShowAll_true_shows_filtered_fields_disabled(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def filter_integer_fields(field: QgsField):
            return field.type() == QMetaType.Type.Int

        model.setFilterFunc(filter_integer_fields)
        model.setShowAll(True)
        self.assertEqual(model.rowCount(), fields.count())
        for i in range(fields.count()):
            idx = model.index(i, 0)
            fname = model.data(idx, QgsFieldModel.CustomRole.FieldName)
            field = model.sourceFieldModel().fields()[fname]

            flags = model.flags(idx)

            if field.type() == QgsField.Type.Int:
                self.assertTrue(flags & Qt.ItemFlag.ItemIsEnabled)
                self.assertTrue(flags & Qt.ItemFlag.ItemIsSelectable)
            else:
                self.assertFalse(flags & Qt.ItemFlag.ItemIsEnabled)
                self.assertFalse(flags & Qt.ItemFlag.ItemIsSelectable)

    def test_filter_accepts_row(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def filter_numeric_fields(field):
            return field.type() in [QgsField.Type.Int, QgsField.Type.Double]

        model.setFilterFunc(filter_numeric_fields)

        self.assertTrue(model.filterAcceptsRow(0, QModelIndex()))

        model.setShowAll(False)

        for i in range(fields.count()):
            idx = src_model.data(src_model.index(i, 0), QgsFieldModel.CustomRole.FieldIndex)
            field = fields.at(idx)
            expected = filter_numeric_fields(field)
            self.assertEqual(model.filterAcceptsRow(i, QModelIndex()), expected)

    def test_field_name_data_role(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        for i in range(fields.count()):
            idx = model.index(i, 0)
            field_name = model.data(idx, QgsFieldModel.CustomRole.FieldName)
            field = fields[i]

            self.assertEqual(field_name, field.name())

    def test_filter_fields_by_name_pattern(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def filter_by_prefix(field):
            return field.name().startswith('id') or field.name().startswith('name')

        model.setFilterFunc(filter_by_prefix)
        model.setShowAll(False)

        matching_fields = [f for f in fields if f.name().startswith('id') or f.name().startswith('name')]
        self.assertEqual(model.rowCount(), len(matching_fields))

    def test_complex_field_filter(self):
        model = FilteredFieldProxyModel()

        vl = TestObjects.createVectorLayer(name='vector')
        fields = vl.fields()

        src_model = model.sourceFieldModel()
        src_model.setFields(fields)

        def complex_filter(field):
            return field.type() in [QgsField.Type.String, QgsField.Type.Int]

        model.setFilterFunc(complex_filter)
        model.setShowAll(False)

        expected_count = sum(1 for f in fields if f.type() in [QgsField.Type.String, QgsField.Type.Int])
        self.assertEqual(model.rowCount(), expected_count)


if __name__ == '__main__':
    unittest.main(buffer=False)
