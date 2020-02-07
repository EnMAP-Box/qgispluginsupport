# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 30.11.2017
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
import unittest, tempfile, shutil
from qgis.core import *
from qgis.gui import *
from qps.testing import TestObjects, TestCase


from qpstestdata import enmap, hymap
from qpstestdata import speclib as speclibpath


import qps
import qps.speclib

from qps.speclib.csvdata import *
from qps.speclib.envi import *
from qps.speclib.asd import *
from qps.speclib.plotting import *


os.environ['CI'] = 'True'

TEST_DIR = os.path.join(os.path.dirname(__file__), 'SPECLIB_TEST_DIR')

class TestPlotting(TestCase):


    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        os.makedirs(TEST_DIR, exist_ok=True)
        super(TestPlotting, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestPlotting, cls).tearDownClass()
        if os.path.isdir(TEST_DIR):
            import shutil
            shutil.rmtree(TEST_DIR)


    def test_PyQtGraphPlot(self):
        import qps.externals.pyqtgraph as pg
        pg.systemInfo()

        plotWidget = pg.plot(title="Three plot curves")

        item1 = pg.PlotItem(x=[1,2,3],   y=[2, 3, 4], color='white')
        plotWidget.plotItem.addItem(item1)
        self.assertIsInstance(plotWidget, pg.PlotWidget)

        self.showGui(plotWidget)

    def test_SpectralLibraryPlotWidgetSimple(self):

        speclib = TestObjects.createSpectralLibrary(10)
        w = SpectralLibraryPlotWidget()
        w.setSpeclib(speclib)

        self.showGui(w)

    def test_SpectralLibraryWidgetThousands(self):

        import qpstestdata

        pathSL = os.path.join(os.path.dirname(qpstestdata.__file__), 'roberts2017_urban.sli')
        if True and os.path.exists(pathSL):
            t0 = datetime.datetime.now()
            speclib = SpectralLibrary.readFrom(pathSL)

            dt = datetime.datetime.now() - t0
            print('Reading required : {}'.format(dt))
        else:
            speclib = TestObjects.createSpectralLibrary(5000)

        t0 = datetime.datetime.now()
        w = SpectralLibraryWidget()

        w.addSpeclib(speclib)
        dt = datetime.datetime.now() - t0
        print('Adding speclib required : {}'.format(dt))

        self.showGui(w)

    def test_SpectralLibraryPlotColorScheme(self):

        self.assertIsInstance(SpectralLibraryPlotColorScheme.default(), SpectralLibraryPlotColorScheme)
        self.assertIsInstance(SpectralLibraryPlotColorScheme.dark(), SpectralLibraryPlotColorScheme)
        self.assertIsInstance(SpectralLibraryPlotColorScheme.bright(), SpectralLibraryPlotColorScheme)
        self.assertIsInstance(SpectralLibraryPlotColorScheme.fromUserSettings(), SpectralLibraryPlotColorScheme)

        b = SpectralLibraryPlotColorScheme.bright()
        b.saveToUserSettings()
        self.assertEqual(b, SpectralLibraryPlotColorScheme.fromUserSettings())
        d = SpectralLibraryPlotColorScheme.default()
        d.saveToUserSettings()
        self.assertEqual(d, SpectralLibraryPlotColorScheme.fromUserSettings())

    def test_SpectralLibraryPlotColorSchemeWidget(self):

        w = SpectralLibraryPlotColorSchemeWidget()
        self.assertIsInstance(w, SpectralLibraryPlotColorSchemeWidget)
        self.showGui(w)

    def test_SpeclibWidgetCurrentProfilOverlayerXUnit(self):

        sw = SpectralLibraryWidget()
        self.assertIsInstance(sw, SpectralLibraryWidget)
        pw = sw.plotWidget()
        self.assertIsInstance(pw, SpectralLibraryPlotWidget)
        self.assertEqual(pw.xUnit(), BAND_INDEX)
        slib = TestObjects.createSpectralLibrary(10)


        xunits = []
        for p in slib:
            self.assertIsInstance(p, SpectralProfile)
            u = p.xUnit()
            if u not in xunits:
                xunits.append(u)

        sw = SpectralLibraryWidget(speclib=slib)
        self.assertEqual(sw.speclib(), slib)
        sw.applyAllPlotUpdates()

        sw = SpectralLibraryWidget()
        sp = slib[0]
        sw.setCurrentProfiles([sp])
        sw.applyAllPlotUpdates()


    def test_SpectraLibraryPlotDataItem(self):

        sl = TestObjects.createSpectralLibrary(10)
        profile = sl[0]
        sp = SpectralProfilePlotDataItem(profile)

        plotStyle = defaultCurvePlotStyle()
        plotStyle.apply(sp)

        ps2 = PlotStyle.fromPlotDataItem(sp)

        self.assertEqual(plotStyle, ps2)


    def test_SpectralLibraryPlotWidget(self):

        speclib = SpectralLibrary.readFrom(speclibpath)



        pw = SpectralLibraryPlotWidget()
        self.assertIsInstance(pw, SpectralLibraryPlotWidget)
        self.assertTrue(pw.xUnit(), BAND_INDEX)

        p = speclib[0]
        sl = SpectralLibrary()
        sl.startEditing()
        pw.setSpeclib(sl)

        sl.addProfiles([p])
        self.assertTrue(pw.xUnit(), p.xUnit())


        w = QWidget()
        w.setLayout(QVBoxLayout())
        pw = SpectralLibraryPlotWidget()

        btn = QPushButton('Add speclib')
        btn.clicked.connect(lambda : pw.setSpeclib(speclib))
        w.layout().addWidget(pw)
        w.layout().addWidget(btn)


        self.assertIsInstance(pw.plotItem, pg.PlotItem)
        self.assertIsInstance(pw.plotItem.getViewBox(), SpectralViewBox)
        self.assertIsInstance(pw.plotItem.getAxis('bottom'), SpectralXAxis)



        plotItem = pw.getPlotItem()
        self.assertIsInstance(plotItem, pg.PlotItem)
        self.assertTrue(len(plotItem.dataItems) == 0)
        pw.setSpeclib(speclib)
        pw.updateSpectralProfilePlotItems()
        n = len([sp for sp in plotItem.dataItems if isinstance(sp, SpectralProfilePlotDataItem)])
        self.assertTrue(n == len(speclib))

        pw.setXUnit('nm')
        self.showGui(w)




if __name__ == '__main__':

    unittest.main()

