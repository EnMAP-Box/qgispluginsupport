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
import unittest, json, pickle
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qps.testing import initQgisApplication

from qps.plotstyling.plotstyling import *

QAPP = initQgisApplication()
SHOW_GUI = False

class PlotStyleTests(unittest.TestCase):

    def setUp(self):
        pass

    def create_vectordataset(self)->QgsVectorLayer:
        vl = QgsVectorLayer("Point?crs=EPSG:4326", 'test', "memory")
        vl.startEditing()

        vl.addAttribute(QgsField(name='fStyle', type=QVariant.String,typeName='varchar',len=500))
        vl.addAttribute(QgsField(name='fString', type=QVariant.String, typeName='varchar', len=50))
        vl.addAttribute(QgsField(name='fInt', type=QVariant.Int, typeName='int'))
        vl.addAttribute(QgsField(name='fDouble', type=QVariant.Double))
        vl.addFeature(QgsFeature(vl.fields()))
        vl.commitChanges()
        return vl

    def test_PlotStyleButton(self):

        bt = PlotStyleButton()

        def onChanged(*args):
            print(args)

        bt.sigPlotStyleChanged.connect(onChanged)



        if SHOW_GUI:
            bt.show()
            QAPP.exec_()

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

    def test_PlotStyleQgsAction(self):

        layer = QgsVectorLayer("Point?field=fldtxt:string&field=fldint:integer&field=flddate:datetime&field=fldstyle:string",
                                    "test_layer", "memory")

        mgr = layer.actions()
        self.assertIsInstance(mgr, QgsActionManager)
        action = createSetPlotStyleAction(layer.fields().at(layer.fields().lookupField('fldstyle')))
        self.assertIsInstance(action, QgsAction)
        mgr.addAction(action)
        # fill some testdata
        layer.startEditing()
        for i, o in enumerate(MARKERSYMBOLS):
            assert isinstance(o, Option)
            f = QgsFeature(layer.fields())
            f.setAttribute('fldint', i)
            f.setAttribute('fldtxt', o.name())
            style = PlotStyle()
            style.markerSymbol = o.value()
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

        if SHOW_GUI:
            myWidget.show()
            QAPP.exec_()

    def test_PlotStyleEditorWidgetFactory(self):

        # init some other requirements
        print('initialize EnMAP-Box editor widget factories')
        # register Editor widgets, if not done before
        reg = QgsGui.editorWidgetRegistry()
        if len(reg.factories()) == 0:
            reg.initEditors()

        registerPlotStyleEditorWidget()
        self.assertTrue('PlotSettings' in reg.factories().keys())

        factory = reg.factories()['PlotSettings']
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
        def onClicked(b:bool):
            if b:
                dv.setView(QgsDualView.AttributeEditor)
            else:
                dv.setView(QgsDualView.AttributeTable)
        cb.clicked.connect(onClicked)
        w.layout().addWidget(dv)
        w.layout().addWidget(cb)

        w.resize(QSize(300,250))

        self.assertTrue(factory.fieldScore(vl, 0) > 0) #specialized support style + str len > 350
        self.assertTrue(factory.fieldScore(vl, 1) == 5)
        self.assertTrue(factory.fieldScore(vl, 2) == 0)
        self.assertTrue(factory.fieldScore(vl, 3) == 0)


        self.assertIsInstance(factory.configWidget(vl, 0, dv), PlotStyleEditorConfigWidget)
        self.assertIsInstance(factory.createSearchWidget(vl, 0, dv), QgsSearchWidgetWrapper)


        eww = factory.create(vl, 0, None, dv )
        self.assertIsInstance(eww, PlotStyleEditorWidgetWrapper)
        self.assertIsInstance(eww.widget(), PlotStyleWidget)

        eww.valueChanged.connect(lambda v: print('value changed: {}'.format(v)))

        fields = vl.fields()
        vl.setEditorWidgetSetup(fields.lookupField('fStyle'), QgsEditorWidgetSetup('PlotSettings',{}))

        vl.startEditing()
        value = eww.value()
        f = vl.getFeature(1)
        f.setAttribute('fStyle', value)
        self.assertTrue(vl.updateFeature(f))

        if SHOW_GUI:
            w.show()
            QAPP.exec_()


       # qApp.exec_()




if __name__ == '__main__':
    SHOW_GUI = False
    unittest.main()
