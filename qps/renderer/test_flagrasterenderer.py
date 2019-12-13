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

from .flagrasterenderer import *

SHOW_GUI = True and os.environ.get('CI') is None


pathFlagImage = list(file_search(pathlib.Path(__file__).parents[2],  'force_QAI.tif', recursive=True))[0]

class MyTestCase(unittest.TestCase):


    flagDescription = { (1,1,)

    }

    def flagImageLayer(self)->QgsRasterLayer:
        lyr = QgsRasterLayer(pathFlagImage)
        lyr.setName('Falg Image')
        return lyr

    def test_FlagStates(self):

        # example FORCE cloud state:
        # bit positions 1,2
        # values:   00 = 0 = clear
        #           01 = 1 = less confident cloud
        #           10 = 2 = confident, opaque cloud
        #           11 = 3 = cirrus
        # define

        flagStates = [(0, 'clear', None),
                      (1, 'less confident', QColor('yellow')),
                      (2, 'confident', QColor('red')),
                      (3, 'cirrus', QColor('blue'))
                      ]

        flagPar = FlagSet(name='Cloud state', startBit=1, bitCombinations=flagStates)
        self.assertIsInstance(flagPar, FlagSet)


    def test_FlagRasterRendererUi(self):


        w = FlagRasterRendererWidget()
        lyr = self.flagImageLayer()
        w.setLayer(lyr)
        w.show()

        if SHOW_GUI:
            QAPP.exec_()

    def test_FlagRasterRenderer(self):

        lyr = self.flagImageLayer()
        self.assertIsInstance(lyr, QgsRasterLayer)
        dp = lyr.dataProvider()
        self.assertIsInstance(dp, QgsRasterDataProvider)

        renderer = FlagRasterRenderer(input=lyr.dataProvider())
        renderer.setInput(lyr.dataProvider())
        lyr.setRenderer(renderer)
        flagsStates = []
        flagsStates.append(FlagState(0, 0, 'valid', QColor('red')))

        renderer.setFlagStates(flagsStates)

        colorBlock = renderer.block(0, lyr.extent(), 200, 200)

        self.assertListEqual(flagsStates, renderer.flagStates())

        r2 = renderer.clone()
        self.assertIsInstance(r2, FlagRasterRenderer)

        canvas = QgsMapCanvas()
        QgsProject.instance().addMapLayer(lyr)
        canvas.mapSettings().setDestinationCrs(lyr.crs())
        canvas.setExtent(lyr.extent())
        canvas.setLayers([lyr])
        canvas.show()
        canvas.waitWhileRendering()

        if SHOW_GUI:
            QAPP.exec_()



if __name__ == '__main__':
    unittest.main()
