import sys, os, re, pathlib, pickle, typing, enum, copy
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qps.utils import loadUI, loadUIFormClass, nextColor
from osgeo import gdal
import numpy as np
pathFlagRasterRendererUI = os.path.join(os.path.dirname(__file__), 'flagrasterrenderer.ui')

TYPE = 'FlagRasterRenderer'

QGIS2NUMPY_DATA_TYPES = {Qgis.Byte: np.byte,
                         Qgis.UInt16: np.uint16,
                         Qgis.Int16: np.int16,
                         Qgis.UInt32: np.uint32,
                         Qgis.Int32: np.int32,
                         Qgis.Float32: np.float32,
                         Qgis.Float64: np.float64,
                         Qgis.CFloat32: np.complex,
                         Qgis.CFloat64: np.complex64,
                         Qgis.ARGB32: np.uint32,
                         Qgis.ARGB32_Premultiplied: np.uint32}

class FlagState(object):

    def __init__(self, offset:int, number:int, name:str, color:QColor=QColor('blue')):

        self.mBitShift:int
        self.mBitShift = offset
        self.mNumber: int
        self.mNumber = number
        self.mName:str
        self.mName = name
        self.mColor:QColor
        self.mColor = color

        self.mVisible:bool
        self.mVisible = True

    def name(self)->str:
        return self.mName

    def isVisible(self)->bool:
        return self.mVisible

    def color(self)->QColor:
        return self.mColor

    def firstBit(self)->int:
        return self.mBitShift

    def lastBit(self)->int:
        """
        Returns the last bit affected by this FlagState
        :return:
        :rtype:
        """
        if self.mNumber == 0:
            return self.firstBit()
        else:
            return self.firstBit() + self.mNumber.bit_length() - 1

    def __eq__(self, other):
        if not isinstance(other, FlagState):
            return False
        else:
            return (self.mBitShift, self.mNumber, self.mName, self.mColor.getRgb()) == \
                   (other.mBitShift, other.mNumber, other.mName, other.mColor.getRgb())

    def __gt__(self, other):
        assert isinstance(other, FlagState)
        if self.mBitShift == other.mBitShift:
            return self.mNumber > other.mNumber
        else:
            return self.mBitShift > other.mBitShift



class FlagSet(object):
    """
    A class to define possible states of a flag / flag-set
    """

    def __init__(self, name:str, startBit:int, bitCount:int):
        assert isinstance(name, str)
        assert isinstance(startBit, int) and startBit >= 0
        assert isinstance(bitCount, int) and bitCount >= 1 and bitCount <= 128 # this should be enough
        self.mName = name
        self.mStartBit = startBit
        self.mBitCount = bitCount
        self.mFlagStates = list()


        color0 = QColor('black')
        for i in range(startBit+1):
            color0 = nextColor(color0, 'cat')
        color = QColor(color0)

        offset = 2**(startBit)

        for i in range(2**(bitCount-1)):
            name = '{}'.format(i)
            color = nextColor(color, 'con')
            flagState = FlagState(offset, i, name, color)
            self.mFlagStates.append(flagState)


    def setFlagState(self, flagState:FlagState):
        assert isinstance(flagState, FlagState)
        assert flagState.mBitShift == self.mStartBit


class FlagModel(QAbstractItemModel):

    def __init__(self, *args, **kwds):
        super(FlagModel, self).__init__(*args, **kwds)
        self.mFlagStates = []

        self.cnBit = 'Bit No.'
        self.cnNum = 'Bit Comb'
        self.cnName = 'Name'

    def setLayer(self, layer:QgsRasterLayer):

        if isinstance(layer, QgsRasterLayer):
            self.mLyr = layer

        else:
            self.mLyr = None


    def setFlagState(self, flagState:FlagState):
        """Sets a single flag state"""
        assert isinstance(flagState, FlagState)



    def flagStates(self):
        return self.mFlagStates[:]


class FlagRasterRendererWidget(QWidget, loadUIFormClass(pathFlagRasterRendererUI)):

    def __init__(self, *args, **kwds):
        super(FlagRasterRendererWidget, self).__init__(*args, **kwds)
        self.setupUi(self)
        self.mRasterBandComboBox.setShowNotSetOption(False)


    def setLayer(self, rasterLayer:QgsRasterLayer):
        if isinstance(rasterLayer, QgsRasterLayer):
            self.mRasterBandComboBox.setLayer(rasterLayer)
            dt = rasterLayer.dataProvider().dataType(self.mRasterBandComboBox.currentBand())
            dtName = gdal.GetDataTypeName(dt)
            dtSize = gdal.GetDataTypeSize(dt)
            self.labelBandInfo.setText('{} bits ({}) '.format(dtSize, dtName))
        else:
            self.clear()

    def clear(self):
        self.mRasterBandComboBox.setLayer(None)
        self.labelBandInfo.setText('')
        pass



class FlagRasterRenderer(QgsRasterRenderer):
    """ A raster renderer to show flag states of a single band. """

    def __init__(self, input=None, type=TYPE):
        super(FlagRasterRenderer, self).__init__(input=input, type=type)

        self.mFlagStates = []
        self.mNoDataColor = QColor(0, 255, 0, 0)
        self.mBand = 1

    def setBand(self, band:int):
        self.mBand = band

    def flagStates(self)->typing.List[FlagState]:
        return self.mFlagStates[:]

    def setFlagStates(self, states:typing.List[FlagState]):
        states = sorted(states)
        self.mFlagStates.clear()
        self.mFlagStates.extend(states)


    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        dump = pickle.dumps(self.__dict__)
        return dump

    def __setstate__(self, state):
        d = pickle.loads(state)
        self.__dict__.update(d)

    def usesBands(self)->typing.List[int]:
        return [self.mBand]

    def legendSymbologyItems(self, *args, **kwargs):
        """ Overwritten from parent class. Items for the legend. """
        items = []
        for flagState in self.flagStates():
            assert isinstance(flagState, FlagState)
            if flagState.isVisible():
                b0 = flagState.firstBit()
                b1 = flagState.lastBit()
                if b0 == b1:
                    item = ('Bit {}:{}:{}'.format(b0, flagState.number(), flagState.name()), flagState.color())
                else:
                    item = ('Bit {}-{}:{}:{}'.format(b0, b1, flagState.number(), flagState.name()), flagState.color())
                items.append(item)
        return items

    def block(self, band_nr: int, extent: QgsRectangle, width: int, height: int,
              feedback: QgsRasterBlockFeedback = None):
        """" Overwritten from parent class. Todo.

        :param band_nr: todo
        :param extent: todo
        :param width: todo
        :param height: todo
        :param feedback: todo
        """

        # see https://github.com/Septima/qgis-hillshaderenderer/blob/master/hillshaderenderer.py
        nb = self.input().bandCount()
        input_missmatch = None
        if len(self.mFlagStates) == 0:
            input_missmatch = 'No flag stats defined to render pixels for.'

        output_block = QgsRasterBlock(Qgis.ARGB32_Premultiplied, width, height)
        color_array = np.frombuffer(output_block.data(), dtype=QGIS2NUMPY_DATA_TYPES[output_block.dataType()])
        color_array[:] = self.mNoDataColor.rgba()

        if input_missmatch:
            print(input_missmatch, file=sys.stderr)
            output_block.setData(color_array.tobytes())
            return output_block

        npx = height * width


        band_block = self.input().block(self.mBand, extent, width, height)
        assert isinstance(band_block, QgsRasterBlock)
        band_data = np.frombuffer(band_block.data(), dtype=QGIS2NUMPY_DATA_TYPES[band_block.dataType()])
        assert len(band_data) == npx
        # THIS! seems to be a very fast way to convert block data into a numpy array
        #block_data[b, :] = band_data

        for iState, flagState in enumerate(self.mFlagStates):
            assert isinstance(flagState, FlagState)
            if not flagState.isVisible():
                continue
            # check if bits are set

            # bin(8129)
            # '{0:16b}'.format(8192)
            # '{0:16b}'.format(8192 >> 0)

            #band_data >> flagState.firstBit() & flagState.mNumber
            mask = flagState.mNumber << flagState.firstBit()
            is_match = (band_data & mask)
            is_match = flagState.matchWithRasterBlock(band_data)
            color_array[np.where(is_match)[0]] = flagState.color().rgb()
        output_block.setData(color_array.tobytes())
        return output_block

    def clone(self) -> QgsRasterRenderer:
        """ Overwritten from parent class. """
        r = FlagRasterRenderer()
        states = [copy.copy(state) for state in  self.mFlagStates]
        r.setFlagStates(states)
        return r

