# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 :
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import json
import os
import unittest

from qgis.PyQt.QtCore import QByteArray, QDataStream, QIODevice, QSize, Qt
from qgis.PyQt.QtGui import QColor, QPen
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsAction, QgsActionManager, QgsAttributeTableConfig, QgsEditorWidgetSetup, QgsFeature, QgsField, \
    QgsVectorLayer
from qgis.gui import QgsDualView, QgsGui, QgsMapCanvas, QgsSearchWidgetWrapper
from qps.plotstyling.plotstyling import createSetPlotStyleAction, list2pen, MarkerSymbol, MarkerSymbolComboBox, \
    pen2list, PlotStyle, PlotStyleButton, PlotStyleEditorConfigWidget, PlotStyleEditorWidgetFactory, \
    plotStyleEditorWidgetFactory, PlotStyleEditorWidgetWrapper, PlotStyleWidget, PlotWidgetStyle, XMLTAG_PLOTSTYLENODE
from qps.pyqtgraph.pyqtgraph.graphicsItems.ScatterPlotItem import Symbols as pgSymbols
from qps.qgisenums import QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QSTRING
from qps.testing import start_app, TestCase

start_app()


class PlotStyleTests(TestCase):

    def create_vectordataset(self) -> QgsVectorLayer:
        vl = QgsVectorLayer("Point?crs=EPSG:4326", 'test', "memory")
        vl.startEditing()
        vl.addAttribute(QgsField(name='fStyle', type=QMETATYPE_QSTRING, typeName='varchar', len=500))
        vl.addAttribute(QgsField(name='fString', type=QMETATYPE_QSTRING, typeName='varchar', len=50))
        vl.addAttribute(QgsField(name='fInt', type=QMETATYPE_INT, typeName='int'))
        vl.addAttribute(QgsField(name='fDouble', type=QMETATYPE_DOUBLE))
        vl.addFeature(QgsFeature(vl.fields()))
        vl.commitChanges()
        return vl

    def test_PlotStyleButton(self):

        bt1 = PlotStyleButton()
        bt1.setCheckable(True)

        bt2 = PlotStyleButton()
        bt2.setCheckable(False)

        bt3 = PlotStyleButton()
        bt3.setColorWidgetVisibility(False)

        w = QWidget()
        g = QGridLayout()
        g.addWidget(QLabel('Checkable PlotStyleButton'), 0, 0)
        g.addWidget(bt1, 0, 1)
        g.addWidget(QLabel('None-Checkable PlotStyleButton'), 1, 0)
        g.addWidget(bt2, 1, 1)

        g.addWidget(QLabel('No color widgets'), 2, 0)
        g.addWidget(bt3, 2, 1)
        w.setLayout(g)
        # w.setMaximumSize(200, 50)
        self.showGui(w)

    def test_json(self):

        pen = QPen()
        encoded = pen2list(pen)
        self.assertIsInstance(encoded, list)
        penStr = json.dumps(encoded)
        pen2 = list2pen(json.loads(penStr))
        self.assertIsInstance(pen2, QPen)
        self.assertEqual(pen, pen2)

        plotStyle = PlotStyle()
        plotStyle.markerPen.setColor(QColor('green'))

        jsonStr = plotStyle.json()
        self.assertIsInstance(jsonStr, str)
        plotStyle2 = PlotStyle.fromJSON(jsonStr)

        self.assertIsInstance(plotStyle2, PlotStyle)
        self.assertTrue(plotStyle == plotStyle2)

        self.assertTrue(PlotStyle.fromJSON(None) is None)
        self.assertTrue(PlotStyle.fromJSON('') is None)

    def test_XML_IO(self):
        testDir = self.createTestOutputDirectory() / 'plotStyle'
        os.makedirs(testDir, exist_ok=True)
        path = testDir / 'plotstyle.xml'
        doc = QDomDocument()

        style = PlotStyle()
        style.setMarkerColor('red')
        style.setLineColor('green')

        stylesIn = [style]
        node = doc.createElement('PlotStyles')
        doc.appendChild(node)
        for style in stylesIn:
            style.writeXml(node, doc)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(doc.toString())

        with open(path, 'r', encoding='utf-8') as f:
            xml = f.read()

        dom = QDomDocument()
        dom.setContent(xml)
        stylesOut = []
        stylesNode = doc.firstChildElement('PlotStyles').toElement()
        self.assertFalse(stylesNode.isNull())
        childs = stylesNode.childNodes()
        for i in range(childs.count()):
            node = childs.at(i).toElement()
            self.assertEqual(node.tagName(), XMLTAG_PLOTSTYLENODE)
            style = PlotStyle.readXml(node)
            self.assertIsInstance(style, PlotStyle)
            stylesOut.append(style)

        for A, B in zip(stylesIn, stylesOut):
            self.assertEqual(A, B, msg='XML Export/Import changed style property')

    def test_copy_paste(self):

        s1 = PlotStyle()
        s1.setLineColor(QColor('red'))
        s1.toClipboard()
        s2 = PlotStyle.fromClipboard()

        self.assertEqual(s1, s2)

    def test_PlotStyle(self):

        s1 = PlotStyle()
        s2 = PlotStyle()

        self.assertEqual(s1, s2)

        s3 = PlotStyle()
        s3.setLineColor('red')

        self.assertNotEqual(s1, s3)

        s4 = s3.clone()

        self.assertEqual(s4, s3)
        s1.json()

    def test_PlotWidgetStyle(self):

        style1 = PlotWidgetStyle()
        style2 = PlotWidgetStyle(name='myStyle', bg='black', fg='green')
        testDir = self.createTestOutputDirectory()
        pathJson = testDir / 'styles.json'
        stylesA = [style1, style2]
        PlotWidgetStyle.writeJson(pathJson, stylesA)
        stylesB = PlotWidgetStyle.fromJson(pathJson)

        for styleA, styleB in zip(stylesA, stylesB):
            self.assertEqual(styleA, styleB)

        #  self.assertIsInstance(PlotWidgetStyle.plotWidgetStyle('default'), PlotWidgetStyle)
        self.assertIsInstance(PlotWidgetStyle.plotWidgetStyle('dark'), PlotWidgetStyle)
        self.assertIsInstance(PlotWidgetStyle.plotWidgetStyle('bright'), PlotWidgetStyle)
        self.assertEqual(PlotWidgetStyle.plotWidgetStyle('foobar'), None)

    def test_PlotStyleWidget(self):
        psw = PlotStyleWidget()
        F = psw.VisibilityFlags

        grid = QGridLayout()
        for col, f in enumerate([F.Type, F.Color, F.Size]):
            cb = QCheckBox(f.name)
            cb.setCheckState(Qt.Checked)
            cb.clicked.connect(lambda b, flag=f: psw.setVisibilityFlag(flag, b))
            grid.addWidget(cb, 0, col + 1)
        for row, f in enumerate([F.Symbol, F.SymbolPen, F.Line, F.Visibility, F.Preview]):
            cb = QCheckBox(f.name)
            cb.setCheckState(Qt.Checked)
            cb.clicked.connect(lambda b, flag=f: psw.setVisibilityFlag(flag, b))
            grid.addWidget(cb, row + 1, 0)

        l1 = QHBoxLayout()
        l1.addLayout(grid)
        lv = QVBoxLayout()
        lv.addWidget(psw)
        lv.addStretch()
        l1.addLayout(lv)
        w = QWidget()
        w.setLayout(l1)

        self.showGui(w)

    def test_serialize_plotstyle(self):

        # Create a QPen
        pen = QPen(QColor("blue"))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)

        # Serialize the QPen to a QByteArray
        byte_array = QByteArray()
        stream = QDataStream(byte_array, QIODevice.WriteOnly)
        stream << pen  # Use the Qt operator<< to serialize

        # Convert to a string (e.g., for storage or transmission)
        pen_string = byte_array.toHex().data().decode("utf-8")
        print("Serialized Pen:", pen_string)

        s = ""

    def test_PlotStyleQgsAction(self):

        layer = QgsVectorLayer(
            "Point?field=fldtxt:string&field=fldint:integer&field=flddate:datetime&field=fldstyle:string",
            "test_layer", "memory")

        mgr = layer.actions()
        self.assertIsInstance(mgr, QgsActionManager)
        action = createSetPlotStyleAction(layer.fields().at(layer.fields().lookupField('fldstyle')))
        self.assertIsInstance(action, QgsAction)
        mgr.addAction(action)
        # fill some testdata
        layer.startEditing()
        for i, symbol in enumerate(MarkerSymbol):
            self.assertIsInstance(symbol, MarkerSymbol)
            f = QgsFeature(layer.fields())
            f.setAttribute('fldint', i)
            f.setAttribute('fldtxt', symbol.name)
            style = PlotStyle()
            style.markerSymbol = symbol.value
            f.setAttribute('fldstyle', style.json())
            layer.addFeature(f)
        layer.commitChanges()

        canvas = QgsMapCanvas()
        myWidget = QWidget()
        myWidget.setWindowTitle('Layer Action Example')
        myWidget.setLayout(QVBoxLayout())
        dualView = QgsDualView()
        dualView.setView(QgsDualView.AttributeTable)

        checkBox = QCheckBox()
        checkBox.setText('Show Form View')

        def onClicked(b: bool):
            if b:
                dualView.setView(QgsDualView.AttributeEditor)
            else:
                dualView.setView(QgsDualView.AttributeTable)

        checkBox.clicked.connect(onClicked)
        myWidget.layout().addWidget(dualView)
        myWidget.layout().addWidget(checkBox)
        myWidget.resize(QSize(300, 250))

        # we like to see the "Action
        columns = layer.attributeTableConfig().columns()
        columns = [columns[-1]] + columns[:-1]
        conf = QgsAttributeTableConfig()
        conf.setColumns(columns)
        conf.setActionWidgetVisible(True)
        conf.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)
        layer.setAttributeTableConfig(conf)
        canvas.setLayers([layer])
        dualView.init(layer, canvas)
        dualView.setAttributeTableConfig(layer.attributeTableConfig())

        self.showGui(myWidget)

    def test_PlotStyleEditorWidgetFactory(self):

        # init some other requirements
        print('initialize EnMAP-Box editor widget factories')
        # register Editor widgets, if not done before
        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        plotStyleEditorWidgetFactory(True)
        from qps.plotstyling.plotstyling import EDITOR_WIDGET_REGISTRY_KEY
        self.assertTrue(EDITOR_WIDGET_REGISTRY_KEY in reg.factories().keys())

        factory = reg.factories()[EDITOR_WIDGET_REGISTRY_KEY]
        self.assertIsInstance(factory, PlotStyleEditorWidgetFactory)

        vl = self.create_vectordataset()

        am = vl.actions()
        self.assertIsInstance(am, QgsActionManager)

        uid = am.addAction(QgsAction.Generic, 'sdsd', 'sdsd')

        c = QgsMapCanvas()
        w = QWidget()
        w.setLayout(QVBoxLayout())
        dv = QgsDualView()
        dv.init(vl, c)
        dv.setView(QgsDualView.AttributeTable)

        cb = QCheckBox()
        cb.setText('Show Editor')

        def onClicked(b: bool):
            if b:
                dv.setView(QgsDualView.AttributeEditor)
            else:
                dv.setView(QgsDualView.AttributeTable)

        cb.clicked.connect(onClicked)
        w.layout().addWidget(dv)
        w.layout().addWidget(cb)

        w.resize(QSize(300, 250))

        self.assertTrue(factory.fieldScore(vl, 0) > 0)  # specialized support style + str len > 350
        self.assertTrue(factory.fieldScore(vl, 1) == 5)
        self.assertTrue(factory.fieldScore(vl, 2) == 0)
        self.assertTrue(factory.fieldScore(vl, 3) == 0)

        self.assertIsInstance(factory.configWidget(vl, 0, dv), PlotStyleEditorConfigWidget)
        self.assertIsInstance(factory.createSearchWidget(vl, 0, dv), QgsSearchWidgetWrapper)

        eww = factory.create(vl, 0, None, dv)
        self.assertIsInstance(eww, PlotStyleEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), PlotStyleWidget)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))

        fields = vl.fields()
        vl.setEditorWidgetSetup(fields.lookupField('fStyle'), QgsEditorWidgetSetup('PlotSettings', {}))

        vl.startEditing()
        value = eww.value()
        f = vl.getFeature(1)
        f.setAttribute('fStyle', value)
        self.assertTrue(vl.updateFeature(f))

        self.showGui(w)

    def test_marker_symbols(self):

        for k in pgSymbols.keys():
            s = MarkerSymbol.decode(k)
            self.assertIsInstance(s, MarkerSymbol)

        symbols = []
        symbol_text = []
        for s in MarkerSymbol:
            self.assertIsInstance(s, MarkerSymbol)
            encoded = MarkerSymbol.encode(s)
            decoded = MarkerSymbol.decode(encoded)
            symbols.append(s)
            symbol_text.append(encoded)
            self.assertEqual(s, decoded, msg='Failed to decode {} to {}'.format(encoded, s))

        n = len(MarkerSymbol)
        cb = MarkerSymbolComboBox()
        self.assertIsInstance(cb, QComboBox)
        self.assertEqual(cb.count(), n)

        for i in range(cb.count()):
            cb.setCurrentIndex(i)
            s = cb.markerSymbol()
            self.assertEqual(cb.markerSymbol(), symbols[i])
            self.assertEqual(cb.currentText(), symbol_text[i])
            self.assertEqual(cb.markerSymbolString(), s.value)

        cb = MarkerSymbolComboBox()

        for s in MarkerSymbol:
            cb.setMarkerSymbol(s)
            self.assertEqual(cb.markerSymbol(), s)

        self.showGui(cb)


if __name__ == '__main__':
    unittest.main(buffer=False)
