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
# noinspection PyPep8Naming
import os
import unittest

import xmlrunner
from qgis.PyQt.QtCore import QVariant, QSize
from qgis.PyQt.QtGui import QPen, QColor
from qgis.PyQt.QtWidgets import QWidget, QGridLayout, QLabel, QVBoxLayout, QCheckBox, QComboBox
from qgis.PyQt.QtXml import QDomDocument

from qgis.core import QgsFeature, QgsField, QgsVectorLayer, QgsAttributeTableConfig, \
    QgsEditorWidgetSetup, QgsActionManager, QgsAction
from qgis.gui import QgsMapCanvas, QgsDualView, QgsGui, QgsSearchWidgetWrapper
from qps.plotstyling.plotstyling import PlotStyleButton, pen2tuple, PlotStyle, XMLTAG_PLOTSTYLENODE, \
    createSetPlotStyleAction, MarkerSymbol, tuple2pen, registerPlotStyleEditorWidget, PlotStyleEditorWidgetFactory, \
    PlotStyleEditorWidgetWrapper, PlotStyleWidget, MarkerSymbolComboBox, PlotStyleEditorConfigWidget

from qps.testing import TestCase


class PlotStyleTests(TestCase):

    def create_vectordataset(self) -> QgsVectorLayer:
        vl = QgsVectorLayer("Point?crs=EPSG:4326", 'test', "memory")
        vl.startEditing()

        vl.addAttribute(QgsField(name='fStyle', type=QVariant.String, typeName='varchar', len=500))
        vl.addAttribute(QgsField(name='fString', type=QVariant.String, typeName='varchar', len=50))
        vl.addAttribute(QgsField(name='fInt', type=QVariant.Int, typeName='int'))
        vl.addAttribute(QgsField(name='fDouble', type=QVariant.Double))
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
        encoded = pen2tuple(pen)
        self.assertIsInstance(encoded, tuple)
        pen2 = tuple2pen(encoded)
        self.assertIsInstance(pen2, QPen)
        self.assertEqual(pen, pen2)

        plotStyle = PlotStyle()
        plotStyle.markerPen.setColor(QColor('green'))

        jsonStr = plotStyle.json()
        self.assertIsInstance(jsonStr, str)
        plotStyle2 = PlotStyle.fromJSON(jsonStr)

        self.assertIsInstance(plotStyle2, PlotStyle)
        self.assertTrue(plotStyle == plotStyle2)

        self.assertTrue(PlotStyle.fromJSON(None) == None)
        self.assertTrue(PlotStyle.fromJSON('') == None)

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
        for style in stylesIn:
            style.writeXml(node, doc)
        doc.appendChild(node)

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

    def test_PlotStyle(self):

        s1 = PlotStyle()
        s2 = PlotStyle()

        self.assertEqual(s1, s2)

        s3 = PlotStyle()
        s3.setLineColor('red')

        self.assertNotEqual(s1, s3)

    def test_PlotStyleWidget(self):
        from qps.plotstyling.plotstyling import PlotStyleWidget
        w = PlotStyleWidget()
        self.showGui(w)

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

        registerPlotStyleEditorWidget()
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
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
