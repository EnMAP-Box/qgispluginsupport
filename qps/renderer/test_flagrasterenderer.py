# -*- coding: utf-8 -*-
import unittest
import sys, os, re, pathlib, pickle, typing, enum
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *


from qps.testing import initQgisApplication, DIR_TESTDATA

from qps.utils import file_search
QAPP = initQgisApplication()

from .flagrasterrenderer import *

SHOW_GUI = True and os.environ.get('CI') is None

pathFlagImage = r'J:\diss_bj\level2\s-america\X0048_Y0025\20140826_LEVEL2_LND07_QAI.tif'
if not os.path.isfile(pathFlagImage):
    pathFlagImage = list(file_search(pathlib.Path(__file__).parents[2],  'force_QAI.tif', recursive=True))[0]

class MyTestCase(unittest.TestCase):

    def flagImageLayer(self)->QgsRasterLayer:
        lyr = QgsRasterLayer(pathFlagImage)
        lyr.setName('Falg Image')
        return lyr

    def createFlagParameters(self)->typing.List[FlagParameter]:
        parValid = FlagParameter('Valid data', 0)
        self.assertIsInstance(parValid, FlagParameter)
        self.assertEqual(len(parValid), 2)
        parValid[0].setValues('valid', 'green', False)
        parValid[1].setValues('no data', 'red', True)

        self.assertEqual(parValid[1].name(), 'no data')
        self.assertEqual(parValid[1].isVisible(), True)
        self.assertEqual(parValid[1].color(), QColor('red'))

        parCloudState = FlagParameter('Cloud state', 1, bitCount=2)
        self.assertIsInstance(parCloudState, FlagParameter)
        self.assertEqual(len(parCloudState), 4)
        parCloudState[0].setValues('clear', QColor('white'), False)
        parCloudState[1].setValues('less confident cloud', QColor('orange'), True)
        parCloudState[2].setValues('confident, opaque cloud', QColor('red'), True)
        parCloudState[3].setValues('cirrus', QColor('blue'), True)

        return [parValid, parCloudState]

    def test_FlagStates(self):

        # example FORCE cloud state:
        # bit positions 1,2
        # values:   00 = 0 = clear
        #           01 = 1 = less confident cloud
        #           10 = 2 = confident, opaque cloud
        #           11 = 3 = cirrus
        # define


        flagPar = FlagParameter('test', 2, 3)
        self.assertIsInstance(flagPar, FlagParameter)
        self.assertEqual(len(flagPar), 8)
        flagPar.setBitSize(2)
        self.assertEqual(len(flagPar), 4)
        flagPar.setBitSize(3)
        self.assertEqual(len(flagPar), 8)


        flagModel = FlagModel()
        tv = QTreeView()
        tv.setModel(flagModel)
        tv.show()

        flagParameters = self.createFlagParameters()
        for i, par in enumerate(flagParameters):
            flagModel.addFlagParameter(par)
            self.assertEqual(len(flagModel), i+1)
            self.assertIsInstance(flagModel[i], FlagParameter)
            self.assertIsInstance(flagModel[i][0], FlagState)
            self.assertEqual(flagModel[i], par)

        idx = flagModel.createIndex(0, 0)
        flagModel.setData(idx, '1-3', role=[Qt.EditRole])
        flagModel.setData(idx, '3', role=[Qt.EditRole])



        if SHOW_GUI:
            QAPP.exec_()


    def test_FlagRasterRendererWidget(self):

        lyr = self.flagImageLayer()

        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayer(lyr)
        canvas.mapSettings().setDestinationCrs(lyr.crs())
        ext = lyr.extent()
        ext.scale(1.1)
        canvas.setExtent(ext)
        canvas.setLayers([lyr])
        canvas.show()
        canvas.waitWhileRendering()
        canvas.setCanvasColor(QColor('grey'))


        w = FlagRasterRendererWidget(lyr, lyr.extent())

        btnReAdd = QPushButton('Re-Add')
        btnReAdd.clicked.connect(lambda : w.setRasterLayer(lyr))

        def onWidgetChanged(w, lyr):

            renderer = w.renderer()
            renderer.setInput(lyr.dataProvider())
            lyr.setRenderer(renderer)
            lyr.triggerRepaint()

        w.widgetChanged.connect(lambda lyr=lyr, w=w: onWidgetChanged(w, lyr))

        for p in self.createFlagParameters():
            w.mFlagModel.addFlagParameter(p)


        top = QWidget()
        top.setLayout(QHBoxLayout())
        top.layout().addWidget(canvas)
        v = QVBoxLayout()
        v.addWidget(btnReAdd)
        v.addWidget(w)
        top.layout().addLayout(v)
        top.show()

        if SHOW_GUI:
            QAPP.exec_()



    def test_FlagRasterRenderer(self):

        lyr = self.flagImageLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)
        dp = lyr.dataProvider()
        self.assertIsInstance(dp, QgsRasterDataProvider)

        renderer = FlagRasterRenderer()
        renderer.setInput(lyr.dataProvider())
        renderer.setBand(1)

        flagPars = self.createFlagParameters()

        renderer.setFlagParameters(flagPars)
        lyr.setRenderer(renderer)

        self.assertListEqual(flagPars, renderer.flagParameters())
        colorBlock = renderer.block(0, lyr.extent(), 200, 200)


        r2 = renderer.clone()
        self.assertIsInstance(r2, FlagRasterRenderer)

        r2.legendSymbologyItems()

        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayer(lyr)
        canvas.mapSettings().setDestinationCrs(lyr.crs())
        canvas.setExtent(lyr.extent())
        canvas.setLayers([lyr])
        canvas.show()
        canvas.waitWhileRendering()

        if SHOW_GUI:
            QAPP.exec_()

    def test_FlagLayerConfigWidget(self):

        factory = FlagRasterRendererConfigWidgetFactory()
        lyr = self.flagImageLayer()
        parameters = self.createFlagParameters()

        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayer(lyr)
        canvas.mapSettings().setDestinationCrs(lyr.crs())
        ext = lyr.extent()
        ext.scale(1.1)
        canvas.setExtent(ext)
        canvas.setLayers([lyr])
        canvas.show()
        canvas.waitWhileRendering()
        canvas.setCanvasColor(QColor('grey'))

        w = factory.createWidget(lyr, canvas)

        top = QWidget()
        top.setLayout(QHBoxLayout())
        top.layout().addWidget(canvas)
        top.layout().addWidget(w)
        top.show()

        #w = factory.createWidget(lyr, canvas)
        #w.show()

        if SHOW_GUI:
            QAPP.exec_()



if __name__ == '__main__':
    unittest.main()
