import qgis  # NOQA
import os

from qgis.core import QgsRasterLayer
from qgis.gui import QgsRasterBandComboBox
from qgis.testing import start_app, unittest
from qgis.PyQt.QtCore import QFileInfo
from qgis.PyQt.QtTest import QSignalSpy
from qgis.PyQt.Qt import Qt
from qgis.PyQt.QtWidgets import QWidget, QComboBox, QHBoxLayout, QVBoxLayout, QGridLayout, QSlider, QLabel
from utilities import unitTestDataPath


#start_app()
from qps.testing import initQgisApplication
app = initQgisApplication()

import qgis.testing

class QgsRasterBandComboBoxV2Demonstrator(QWidget):
    """
    Demo of an enhanced QgsRasterBandComboBox which
    allows to select a raster band using a QSlider.

    Optimally the widget still inherits from QComboBox.

    """
    def __init__(self, sliderPosition:Qt.AlignmentFlag=Qt.AlignLeft, *args, **kwds):

        super(QWidget, self).__init__(*args, **kwds)


        assert sliderPosition in [Qt.AlignLeft, Qt.AlignRight, Qt.AlignTop, Qt.AlignBottom]
        self.mComboBox = QgsRasterBandComboBox()
        self.mSlider = QSlider(Qt.Horizontal)

        # should provide the same combobox-specific methods and properties as before

        for m in ['layer', 'bandChanged', 'currentBand', 'count', 'isShowingNotSetOption',
                  'setBand', 'setShowNotSetOption']:
            setattr(self, m, getattr(self.mComboBox, m))



        # no raster layer, no slider to
        self.mSlider.setEnabled(False)

        # slider is invisible by default
        self.mSlider.setVisible(False)

        if sliderPosition in [Qt.AlignTop, Qt.AlignBottom]:
            layout = QVBoxLayout()
        else:
            layout = QHBoxLayout()
        if sliderPosition in [Qt.AlignLeft, Qt.AlignRight]:
            layout.setStretchFactor(self.mSlider, 1)
            layout.setStretchFactor(self.mComboBox,2)
        else:
            layout.setStretchFactor(self.mSlider, 1)
            layout.setStretchFactor(self.mComboBox, 1)

        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)

        if sliderPosition == Qt.AlignBottom:
            self.mSlider.setTickPosition(QSlider.TicksAbove)
        else:
            self.mSlider.setTickPosition(QSlider.TicksBelow)

        if sliderPosition in [Qt.AlignLeft, Qt.AlignTop]:
            layout.addWidget(self.mSlider)
            layout.addWidget(self.mComboBox)
        else:
            layout.addWidget(self.mComboBox)
            layout.addWidget(self.mSlider)

        self.mComboBox.bandChanged.connect(self.mSlider.setValue)
        self.mSlider.valueChanged.connect(self.mComboBox.setBand)

    def setLayer(self, layer:QgsRasterLayer):

        if layer.isValid() and layer.bandCount() > 0:
            nb = layer.bandCount()
            self.mSlider.setEnabled(True)
            self.mSlider.setMaximum(nb)
            self.mSlider.setMinimum(1)

            if nb > 100:
                self.mSlider.setTickInterval(10)
            elif nb <= 10:
                self.mSlider.setTickInterval(1)

        else:
            self.mSlider.setEnabled(False)
            self.mSlider.setMaximum(0)

        self.mComboBox.setLayer(layer)


    def setSliderVisibility(self, b:bool):
        self.mSlider.setVisible(b)

    def sliderVisibility(self)->bool:
        return self.mSlider.isVisible()



class QgsRasterBandComboboxV2Tests(qgis.testing.TestCase):

    def createInMemoryQgsRasterLayer(self)->QgsRasterLayer:

        from osgeo import gdal
        from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

        # create an in-memory raster
        driver = gdal.GetDriverByName('GTiff')
        assert isinstance(driver, gdal.Driver)
        path = '/vsimem/inmemoryraster.tif'
        nb = 50
        dataSet = driver.Create(path, 100, 50, bands=nb, eType=gdal.GDT_Int16)
        assert isinstance(dataSet, gdal.Dataset)
        for b in range(nb):
            band = dataSet.GetRasterBand(b+1)
            assert isinstance(band, gdal.Band)
            band.SetDescription('In Memory Band {}'.format(b+1))


        c = QgsCoordinateReferenceSystem('EPSG:32632')
        dataSet.SetProjection(c.toWkt())
        dataSet.SetGeoTransform([0, 1.0, 0, 0, 0, -1.0])
        dataSet.FlushCache()
        dataSet = None

        ds2 = gdal.Open(path)
        assert isinstance(ds2, gdal.Dataset)

        layer = QgsRasterLayer(path)
        assert isinstance(layer, QgsRasterLayer)
        assert layer.isValid()
        return layer

    def test_showOptions(self):

        app = initQgisApplication()

        layer = self.createInMemoryQgsRasterLayer()

        w = QWidget()
        w.setWindowTitle('QgsRasterBandComboBoxV2Demonstrator')
        l = QGridLayout()
        w.setLayout(l)
        cb = QgsRasterBandComboBoxV2Demonstrator()
        cb.setLayer(layer)
        cb.setShowNotSetOption(True)
        l.addWidget(QLabel('Default'), 0, 0)
        l.addWidget(cb, 0, 1)


        for row, item in enumerate([(Qt.AlignLeft, 'Qt.AlignLeft'),
                                    (Qt.AlignRight, 'Qt.AlignRight'),
                                    (Qt.AlignTop, 'Qt.AlignTop'),
                                    (Qt.AlignBottom, 'Qt.AlignBottom')]):
            alignment, text = item
            label = QLabel(text)
            cb = QgsRasterBandComboBoxV2Demonstrator(sliderPosition=alignment)
            cb.setShowNotSetOption(True)
            cb.setLayer(layer)
            cb.setSliderVisibility(True)
            l.addWidget(label, row + 1, 0)
            l.addWidget(cb, row + 1, 1)
        w.show()
        app.exec_()


    def test_a(self):


        cb = QgsRasterBandComboBoxV2Demonstrator()

        lyr = self.createInMemoryQgsRasterLayer()

        self.assertTrue(cb.layer() is None)
        cb.setLayer(lyr)
        self.assertIsInstance(cb.layer(), QgsRasterLayer)
        self.assertTrue(cb.layer() == lyr)
        cb.setSliderVisibility(True)




    def testNoLayer(self):
        """
        Test widget with no layer
        """

        combo = QgsRasterBandComboBoxV2Demonstrator()
        self.assertFalse(combo.layer())
        self.assertEqual(combo.currentBand(), -1)

        combo.setShowNotSetOption(True)
        self.assertEqual(combo.currentBand(), -1)

        combo.setBand(11111)
        self.assertEqual(combo.currentBand(), -1)
        combo.setBand(-11111)
        self.assertEqual(combo.currentBand(), -1)

    def testOneBandRaster(self):
        path = os.path.join(unitTestDataPath('raster'),
                            'band1_float32_noct_epsg4326.tif')
        info = QFileInfo(path)
        base_name = info.baseName()
        layer = QgsRasterLayer(path, base_name)
        self.assertTrue(layer)

        combo = QgsRasterBandComboBoxV2Demonstrator()
        combo.setLayer(layer)
        self.assertEqual(combo.layer(), layer)
        self.assertEqual(combo.currentBand(), 1)
        self.assertEqual(combo.count(), 1)

        combo.setShowNotSetOption(True)
        self.assertEqual(combo.currentBand(), 1)
        self.assertEqual(combo.count(), 2)
        combo.setBand(-1)
        self.assertEqual(combo.currentBand(), -1)
        combo.setBand(1)
        self.assertEqual(combo.currentBand(), 1)

        combo.setShowNotSetOption(False)
        self.assertEqual(combo.currentBand(), 1)
        self.assertEqual(combo.count(), 1)

    def testMultiBandRaster(self):
        path = os.path.join(unitTestDataPath('raster'),
                            'band3_float32_noct_epsg4326.tif')
        info = QFileInfo(path)
        base_name = info.baseName()
        layer = QgsRasterLayer(path, base_name)
        self.assertTrue(layer)

        combo = QgsRasterBandComboBoxV2Demonstrator()
        combo.setLayer(layer)
        self.assertEqual(combo.layer(), layer)
        self.assertEqual(combo.currentBand(), 1)
        self.assertEqual(combo.count(), 3)
        combo.setBand(2)
        self.assertEqual(combo.currentBand(), 2)

        combo.setShowNotSetOption(True)
        self.assertEqual(combo.currentBand(), 2)
        self.assertEqual(combo.count(), 4)

        combo.setShowNotSetOption(False)
        self.assertEqual(combo.currentBand(), 2)
        self.assertEqual(combo.count(), 3)

    def testSignals(self):
        path = os.path.join(unitTestDataPath('raster'),
                            'band3_float32_noct_epsg4326.tif')
        info = QFileInfo(path)
        base_name = info.baseName()
        layer = QgsRasterLayer(path, base_name)
        self.assertTrue(layer)

        combo = QgsRasterBandComboBoxV2Demonstrator()
        combo.setLayer(layer)

        signal_spy = QSignalSpy(combo.bandChanged)
        combo.setBand(2)
        self.assertEqual(len(signal_spy), 1)
        self.assertEqual(signal_spy[0][0], 2)
        combo.setBand(3)
        self.assertEqual(len(signal_spy), 2)
        self.assertEqual(signal_spy[1][0], 3)

    def test_finalversion(self):
        """
        These tests fail for the Python-Demo, but it would be nice if the
        final version is still a QComboBox instance
        """
        from qps.testing import initQgisApplication
        app = initQgisApplication()
        cb = QgsRasterBandComboBoxV2Demonstrator()
        self.assertIsInstance(cb, QComboBox)

if __name__ == '__main__':

    unittest.main()
