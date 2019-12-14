import sys, os, re, pathlib, pickle, typing, enum, copy, bisect
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

def contrastColor(c:QColor)->QColor:
    """
    Returns a QColor with good contrast to the input color c
    :param c: QColor
    :return: QColor
    """
    assert isinstance(c, QColor)
    if c.lightness() < 0.5:
        return QColor('white')
    else:
        return QColor('black')

class FlagState(object):

    def __init__(self, offset:int, number:int, name:str=None, color:QColor=None):

        self.mBitShift:int
        self.mBitShift = offset
        self.mNumber: int
        assert isinstance(number, int) and number >= 0
        self.mNumber = number

        self.mName:str
        if name is None:
            name = 'state {}'.format(number+1)
        self.mName = name

        if color is None:
            color = QColor('blue')
            for i in range(number):
                color = nextColor(color, mode='cat')

        self.mColor:QColor
        self.mColor = color

        self.mVisible:bool
        self.mVisible = True

    def __len__(self):
        return 0

    def bitCombination(self, nbits=1)->str:
        f = '{:'+str(nbits)+'b}'
        return f.format(self.mNumber)

    def bitNumber(self)->str:
        return self.mNumber

    def name(self)->str:
        return self.mName

    def setValues(self, name:str=None, color=None, isVisible:bool=None):

        if isinstance(name, str):
            self.setName(name)
        if color is not None:
            self.setColor(color)
        if isinstance(isVisible, bool):
            self.setVisible(isVisible)

    def setName(self, name:str):
        assert isinstance(name, str)
        self.mName = name

    def isVisible(self)->bool:
        return self.mVisible

    def setVisible(self, b:bool):
        assert isinstance(b, bool)
        self.mVisible = b

    def color(self)->QColor:
        return self.mColor

    def setColor(self, color):
        self.mColor = QColor(color)

    def __eq__(self, other):
        if not isinstance(other, FlagState):
            return False
        else:
            return (self.mBitShift, self.mNumber, self.mName, self.mColor.getRgb()) == \
                   (other.mBitShift, other.mNumber, other.mName, other.mColor.getRgb())

    def __lt__(self, other):
        assert isinstance(other, FlagState)
        if self.mBitShift == other.mBitShift:
            return self.mNumber < other.mNumber
        else:
            return self.mBitShift < other.mBitShift



class FlagParameter(object):
    """
    A class to define possible states of a flag / flag-set
    """

    def __init__(self, name:str, firstBit:int, bitCount:int=1):
        assert isinstance(name, str)
        assert isinstance(firstBit, int) and firstBit >= 0
        assert isinstance(bitCount, int) and bitCount >= 1 and bitCount <= 128 # this should be enough

        # initialize the parameter states
        self.mName = name
        self.mStartBit = firstBit
        self.mBitSize = bitCount
        self.mFlagStates = list()

        color0 = QColor('black')
        for i in range(firstBit + 1):
            color0 = nextColor(color0, 'cat')
        color = QColor(color0)

        for i in range(2 ** bitCount):
            color = nextColor(color, 'con')
            state = FlagState(self.mStartBit, i, name, color=color)
            self.mFlagStates.append(state)

    def __contains__(self, item):
        return item in self.mFlagStates

    def __getitem__(self, slice):
        return self.mFlagStates[slice]

    def __iter__(self)->typing.Iterator[FlagState]:
        return iter(self.mFlagStates)

    def bitCount(self)->int:
        return self.mBitSize

    def setFirstBit(self, firstBit:int):
        assert isinstance(firstBit, int) and firstBit >= 0
        self.mStartBit = firstBit
        for state in self.states():
            state.mBitShift = self.mStartBit

    def __len__(self):
        return len(self.mFlagStates)

    def __lt__(self, other):
        assert isinstance(other, FlagParameter)
        return self.mStartBit < other.mStartBit

    def setBitSize(self, bitSize:int):
        assert isinstance(bitSize, int) and bitSize >= 1
        nStates0 = 2 ** self.mBitSize
        nStates2 = 2 ** bitSize
        n = len(self.mFlagStates)
        diff = 2**bitSize - n
        if diff > 0:
            # add missing states
            for i in range(diff):
                state = FlagState(self.mStartBit, n+1)
                self.mFlagStates.append(state)
            # remove
        elif diff < 0:
            remove = self.mFlagStates[n-diff:]
            del self.mFlagStates[n-diff]

    def states(self)->typing.List[FlagState]:
        return self.mFlagStates

    def visibleStates(self)->typing.List[FlagState]:
        return [state for state in self.mFlagStates if state.isVisible()]

    def name(self)->str:
        return self.mName

    def setName(self, name:str):
        assert isinstance(name, str)
        self.mName = name

    def firstBit(self)->int:
        return self.mStartBit

    def lastBit(self)->int:
        """
        Returns the last bit affected by this FlagState
        :return:
        :rtype:
        """
        return self.mStartBit + self.mBitSize - 1




class FlagModel(QAbstractItemModel):

    def __init__(self, *args, **kwds):
        super(FlagModel, self).__init__(*args, **kwds)
        self.mFlagParameters = []

        self.cnBit = 'Bit No.'
        self.cnName = 'Name'
        self.cnBitComb = 'Bits'
        self.cnBitNum = 'Num'
        self.cnColor = 'Color'

        self.mRootIndex = QModelIndex()

    def columnNames(self):
        return [self.cnBit, self.cnName, self.cnBitComb, self.cnBitNum, self.cnColor]

    def __contains__(self, item):
        return item in self.mFlagParameters

    def __getitem__(self, slice):
        return self.mFlagParameters[slice]


    def __len__(self):
        return len(self.mFlagParameters)

    def __iter__(self)->typing.Iterator[FlagParameter]:
        return iter(self.mFlagParameters)

    def __repr__(self):
        return self.toString()

    def toString(self):
        lines = []
        for i, par in enumerate(self):
            assert isinstance(par, FlagParameter)
            lines.append('{}:{}'.format(par.mStartBit, par.name()))
            for j, state in enumerate(par):
                assert isinstance(state, FlagState)
                line = '  {}:{}'.format(state.bitCombination(), state.mNumber, state.name())
                lines.append(line)
        return '\n'.join(lines)

    def rowCount(self, parent: QModelIndex = ...) -> int:
        if not parent.isValid():
            return len(self.mFlagParameters)

        item = parent.internalPointer()
        assert isinstance(item, (FlagParameter, FlagState))
        return len(item)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.columnNames())


    def addFlagParameter(self, flagParameter:FlagParameter):
        row = bisect.bisect(self.mFlagParameters, flagParameter)
        self.beginInsertRows(self.mRootIndex, row, row)
        self.mFlagParameters.insert(row, flagParameter)
        self.endInsertRows()

    def removeFlagParameter(self, flagParameter:FlagParameter):
        if flagParameter in self.mFlagParameters:
            row = self.mFlagParameters.index(flagParameter)
            self.beginRemoveRows(self.mRootIndex, row, row)
            self.mFlagParameters.remove(flagParameter)
            self.endRemoveRows()




    def flagStates(self)->typing.List[FlagState]:
        return [state for parameter in self for state in parameter]

    def visibleFlagStates(self)->typing.List[FlagState]:
        return [state for parameter in self for state in parameter if state.isVisible()]

    def headerData(self, section, orientation, role):
        assert isinstance(section, int)

        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames()[section]

        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return section

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        cName = self.columnNames()[index.column()]

        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(index.internalPointer(), (FlagParameter, FlagState)) and index.column() == 0:
            flags = flags | Qt.ItemIsUserCheckable

        if cName in [self.cnName, self.cnColor]:
            flags = flags | Qt.ItemIsEditable
        return flags

    def parent(self, child: QModelIndex) -> QModelIndex:

        if not child.isValid():
            return QModelIndex()

        item = child.internalPointer()
        if isinstance(item, FlagParameter):
            return self.mRootIndex

        if isinstance(item, FlagState):
            for row, parameter in enumerate(self):
                if item in parameter:
                    return self.createIndex(row, 0, parameter)

        return QModelIndex()

    def nextFreeBit(self)->int:
        if len(self) == 0:
            return 0
        else:
            lastParameter = self[-1]
            return lastParameter.lastBit()+1

    def index(self, row: int, column: int, parent: QModelIndex=QModelIndex()) -> QModelIndex:

        if parent == self.mRootIndex:
            # root index -> return FlagParameter
            return self.createIndex(row, column, self[row])

        if parent.parent() == self.mRootIndex:
            # sub 1 -> return FlagState
            flagParameter = self[parent.row()]
            return self.createIndex(row, column, flagParameter[row])
        return QModelIndex()


    def data(self, index: QModelIndex, role: int) -> typing.Any:

        assert isinstance(index, QModelIndex)
        if not index.isValid():
            return None

        item = index.internalPointer()
        cName = self.columnNames()[index.column()]
        if isinstance(item, FlagParameter):

            if role in [Qt.DisplayRole, Qt.EditRole]:
                if cName == self.cnBit:
                    if item.bitCount() == 1:
                        return '{}'.format(item.firstBit())
                    else:
                        return '{}-{}'.format(item.firstBit(), item.lastBit())
                if cName == self.cnName:
                    return item.name()

            if role == Qt.ToolTipRole:
                if cName == self.cnName:
                    return item.name()

            if role == Qt.CheckStateRole and index.column() == 0:
                nStates = len(item)
                nChecked = len(item.visibleStates())
                if nChecked == 0:
                    return Qt.Unchecked
                elif nChecked < nStates:
                    return Qt.PartiallyChecked
                else:
                    return Qt.Checked

            if role == Qt.UserRole:
                return item

        if isinstance(item, FlagState):

            if role in [Qt.DisplayRole, Qt.EditRole]:
                if cName == self.cnBitNum:
                    return item.bitNumber()
                if cName == self.cnName:
                    return item.name()
                if cName == self.cnBitComb:
                    param = index.parent().internalPointer()
                    assert isinstance(param, FlagParameter)
                    return item.bitCombination(param.bitCount())

                if cName == self.cnColor:
                    return item.color().name()

            if role == Qt.BackgroundColorRole:
                if cName == self.cnColor:
                    return item.color()

            if role == Qt.TextColorRole:
                if cName == self.cnColor:
                    return contrastColor(item.color())

            if role == Qt.TextAlignmentRole:
                if cName in [self.cnBitNum, self.cnBitComb]:
                    return Qt.AlignRight

            if role == Qt.CheckStateRole and index.column() == 0:
                return Qt.Checked if item.isVisible() else Qt.Unchecked

            if role == Qt.UserRole:
                return item

        return None

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:

        if not index.isValid():
            return False

        result = False

        item = index.internalPointer()
        cName = self.columnNames()[index.column()]

        if isinstance(item, FlagState):
            if role == Qt.CheckStateRole and index.column() == 0:

                isChecked = value == Qt.Checked
                if item.mVisible != isChecked:
                    item.mVisible = isChecked
                    # inform parent FlagParameter
                    flagIndex = index.parent()
                    self.dataChanged.emit(flagIndex, flagIndex, [role])
                    result = True

            if role == Qt.EditRole:
                if cName == self.cnName:
                    item.setName(str(value))
                    result = True

                if cName == self.cnColor:
                    item.setColor(QColor(value))
                    result = True

        if isinstance(item, FlagParameter):
            if role == Qt.CheckStateRole and index.column() == 0:
                if value in [Qt.Checked, Qt.Unchecked]:
                    # apply new checkstate downwards to all FlagStates
                    for row in range(len(item)):
                        stateIndex = self.index(row, 0, index)
                        if self.data(stateIndex, Qt.CheckStateRole) != value:
                            self.setData(stateIndex, value, Qt.CheckStateRole)
                            result = True

            if role == Qt.EditRole:
                if cName == self.cnName:
                    item.setName(str(value))
                    result = True




        if result == True:
            self.dataChanged.emit(index, index, [role])

        return result


class FlagRasterRendererWidget(QgsRasterRendererWidget, loadUIFormClass(pathFlagRasterRendererUI)):

    def __init__(self, layer:QgsRasterLayer, extent:QgsRectangle):
        super(FlagRasterRendererWidget, self).__init__(layer, extent)
        self.setupUi(self)
        self.mRasterBandComboBox.setShowNotSetOption(False)

        assert isinstance(self.mTreeView, QTreeView)

        self.mFlagModel:FlagModel
        self.mFlagModel = FlagModel()
        self.mFlagModel.dataChanged.connect(self.onModelDataChanged)
        self.mFlagModel.rowsInserted.connect(self.onModelDataChanged)
        self.mFlagModel.rowsRemoved.connect(self.onModelDataChanged)

        self.mProxyModel = QSortFilterProxyModel()
        self.mProxyModel.setSourceModel(self.mFlagModel)
        self.mTreeView.setModel(self.mProxyModel)
        self.mTreeView.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.mTreeView.doubleClicked.connect(self.onTreeViewDoubleClick)
        self.mTreeView.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.actionAddParameter.triggered.connect(self.onAddParameter)
        self.actionRemoveParameters.triggered.connect(self.onRemoveParameters)
        self.btnAddFlag.setDefaultAction(self.actionAddParameter)
        self.btnRemoveFlags.setDefaultAction(self.actionRemoveParameters)

        if isinstance(layer, QgsRasterLayer):
            self.setLayer(layer)

        self.updateWidgets()

    def onTreeViewDoubleClick(self, idx):
        idx = self.mProxyModel.mapToSource(idx)
        item = idx.internalPointer()
        cname = self.mFlagModel.columnNames()[idx.column()]
        if isinstance(item, FlagState) and cname == self.mFlagModel.cnColor:
            c = QColorDialog.getColor(item.color(), self.treeView(), \
                                      'Set color for "{}"'.format(item.name()))

            self.mFlagModel.setData(idx, c, role=Qt.EditRole)

    def onModelDataChanged(self, *args, **kwds):
        # todo: compare renderer differences
        self.widgetChanged.emit()

    def setRasterLayer(self, layer:QgsRasterLayer):
        super(FlagRasterRendererWidget, self).setRasterLayer(layer)
        self.mRasterBandComboBox.setLayer(layer)


    def onSelectionChanged(self, selected, deselected):
        self.updateWidgets()

    def selectedBand(self, index:int=0):
        return self.mRasterBandComboBox.currentBand()

    def onAddParameter(self):

        startBit = self.mFlagModel.nextFreeBit()
        name = 'Parameter {}'.format(len(self.mFlagModel) + 1)
        bitCount = self.sbBitCount.value()
        flagParameter = FlagParameter(name, startBit, bitCount)
        self.mFlagModel.addFlagParameter(flagParameter)
        self.updateWidgets()

    def updateWidgets(self):
        b = len(self.treeView().selectionModel().selectedRows()) > 0
        self.actionRemoveParameters.setEnabled(b)

        b = self.mFlagModel.nextFreeBit() < self.layerBitCount()
        self.actionAddParameter.setEnabled(b)
        self.sbBitCount.setEnabled(b)
        self.labelBits.setEnabled(b)


    def renderer(self)->QgsRasterRenderer:

        r = FlagRasterRenderer()
        r.setInput(self.rasterLayer().dataProvider())
        r.setBand(self.selectedBand())
        r.setFlagParameters(copy.deepcopy(self.mFlagModel[:]))

        return r



    def onRemoveParameters(self):

        selectedRows = self.mTreeView.selectionModel().selectedRows()
        toRemove = []
        for idx in selectedRows:
            idx = self.mProxyModel.mapToSource(idx)
            parameter = self.mFlagModel.data(idx, Qt.UserRole)
            if isinstance(parameter, FlagParameter) and parameter not in toRemove:
                toRemove.append(parameter)
        for parameter in reversed(toRemove):
            self.mFlagModel.removeFlagParameter(parameter)


    def treeView(self)->QTreeView:
        return self.mTreeView

    def layerBitCount(self)->int:
        lyr = self.rasterLayer()
        if isinstance(lyr, QgsRasterLayer):
            return gdal.GetDataTypeSize(lyr.dataProvider().dataType(self.selectedBand()))
        else:
            return 0

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

        self.mFlagParameters:typing.List[FlagParameter]
        self.mFlagParameters = []
        self.mNoDataColor = QColor(0, 255, 0, 0)
        self.mBand = 1

    def type(self)->str:
        return TYPE

    def setBand(self, band:int):
        self.mBand = band

    def setFlagParameters(self, flagParameters:typing.List[FlagParameter]):
        self.mFlagParameters.clear()
        self.mFlagParameters.extend(flagParameters)

    def flagParameters(self)->typing.List[FlagParameter]:
        return self.mFlagParameters[:]

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
        for parameter in self.flagParameters():
            for flagState in parameter:
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
        if len(self.mFlagParameters) == 0:
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

        parameterNumbers = np.zeros(band_data.shape, dtype=np.uint8)
        for i, flagParameter in enumerate(self.mFlagParameters):
            b0 = flagParameter.firstBit()

            # extract the parameter number
            for b in range(flagParameter.bitCount()):
                mask = 1 << (flagParameter.firstBit() + b)
                parameterNumbers += 2**b * np.uint8((band_data & mask) != 0)

            # compare each flag state
            for j, flagState in enumerate(flagParameter):
                if not flagState.isVisible():
                    continue
                color_array[np.where(parameterNumbers == flagState.bitNumber())[0]] = flagState.color().rgb()

            parameterNumbers.fill(0)
        output_block.setData(color_array.tobytes())
        return output_block

    def clone(self) -> QgsRasterRenderer:
        """ Overwritten from parent class. """
        r = FlagRasterRenderer()
        parameters = [copy.copy(par) for par in self.mFlagParameters]
        r.setFlagParameters(parameters)

        return r


class FlagRasterLayerConfigWidget(QgsMapLayerConfigWidget):

    def __init__(self, layer:QgsRasterLayer, canvas:QgsMapCanvas, parent:QWidget=None):

        super(FlagRasterLayerConfigWidget, self).__init__(layer, canvas, parent=parent)
        self.setupUi(self)
        self.mCanvas = canvas
        self.mLayer = layer
        self.mLayer.rendererChanged.connect(self.onRendererChanged)

        self.initRenderer()

        self.setPanelTitle('Flag Layer Settings')

    def onRendererChanged(self):
        self.initRenderer()

    def initRenderer(self):

        renderer = self.mLayer.renderer()

    def renderer(self)->QgsRasterRenderer:
        return self.mLayer.renderer()

    def apply(self):
        r = self.renderer()
        newRenderer = None

        if isinstance(newRenderer, QgsRasterRenderer):
            self.mLayer.setRenderer(newRenderer)

    def setDockMode(self, dockMode:bool):
        pass



class FlagRasterRendererConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):

        super(FlagRasterRendererConfigWidgetFactory, self).__init__()


        self.setSupportLayerPropertiesDialog(True)
        self.setSupportsStyleDock(True)
        self.setTitle('Flag Raster Renderer')

    def supportsLayer(self, layer):
        if isinstance(layer, QgsRasterLayer) and layer.isValid():
            dt = layer.dataProvider().dataType(1)
            return dt in [gdal.GDT_Byte, gdal.GDT_Int16, gdal.GDT_Int32, gdal.GDT_UInt16, gdal.GDT_UInt32, gdal.GDT_CInt16, gdal.GDT_CInt32]

        return False

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True


    def createWidget(self, layer, canvas, dockWidget=True, parent=None)->QgsMapLayerConfigWidget:

        w = FlagRasterLayerConfigWidget(layer, canvas, parent=parent)
        self._w = w
        return w

