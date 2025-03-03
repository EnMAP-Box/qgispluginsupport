# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/cursorlocationvalue.py

    Retrieval and visualization of cursor location values from QgsMapCanvases
    ---------------------
    Beginning            : 2019-01-15 (and earlier)
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""

import collections
import os
from typing import List

from qgis.PyQt.QtCore import QModelIndex, QPoint, QAbstractListModel, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QClipboard, QColor
from qgis.PyQt.QtWidgets import QMenu, QApplication, QDockWidget

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsRasterDataProvider
from qgis.core import QgsCoordinateReferenceSystem, QgsWkbTypes, QgsField, QgsFeature, \
    QgsMapLayer, QgsVectorLayer, QgsRasterLayer, QgsPointXY, QgsRectangle, QgsTolerance, \
    QgsFeatureRequest, QgsRasterBlock, QgsPalettedRasterRenderer, QgsRaster
from qgis.gui import QgsMapCanvas
from . import DIR_UI_FILES
from .classification.classificationscheme import ClassInfo, ClassificationScheme
from .models import TreeNode, TreeModel, TreeView
from .utils import SpatialPoint, geo2px, as_py_value, loadUi


class SourceValueSet(object):
    def __init__(self, source, point: SpatialPoint):
        assert isinstance(point, SpatialPoint)
        self.source = source
        self.point = point

    def baseName(self):
        return os.path.basename(self.source)

    def crs(self):
        return QgsCoordinateReferenceSystem(self.wktCrs)


class RasterValueSet(SourceValueSet):
    class BandInfo(object):
        def __init__(self, bandIndex, bandValue, bandName,
                     is_nodata: bool = False, classInfo=None):
            assert bandIndex >= 0
            if bandValue is not None:
                assert type(bandValue) in [float, int]
            if bandName is not None:
                assert isinstance(bandName, str)

            self.is_nodata: bool = bool(is_nodata)
            self.bandIndex = bandIndex
            self.bandValue = bandValue
            self.bandName: str = bandName
            self.classInfo = classInfo

    def __init__(self, source, point, pxPosition: QPoint):
        assert isinstance(pxPosition, QPoint)
        super(RasterValueSet, self).__init__(source, point)
        self.pxPosition = pxPosition
        self.noDataValue = None
        self.bandValues = []


class VectorValueSet(SourceValueSet):
    class FeatureInfo(object):
        def __init__(self, fid):
            assert isinstance(fid, int)
            self.fid = fid
            self.attributes = collections.OrderedDict()

    def __init__(self, source, point: SpatialPoint):
        super(VectorValueSet, self).__init__(source, point)
        self.features = []

    def addFeatureInfo(self, featureInfo):
        assert isinstance(featureInfo, VectorValueSet.FeatureInfo)
        self.features.append(featureInfo)


class PixelPositionTreeNode(TreeNode):

    def __init__(self, px: QPoint, coord: SpatialPoint, *args,
                 name: str = 'Pixel',
                 zeroBased: bool = True, **kwds):

        super().__init__(*args, **kwds)
        self.setName(name)
        self.mPx: QPoint = px
        self.mGeo: SpatialPoint = coord
        self.mZeroBased = zeroBased

        if self.mZeroBased:
            self.setValues([(px.x(), px.y())])
            self.setToolTip('Pixel Coordinate (upper-left = (0,0) )')
        else:
            self.setValues([(px.x() + 1, px.y() + 1)])
            self.setToolTip('Pixel Coordinate (upper-left = (1,1) )')

    def populateContextMenu(self, menu: QMenu):

        a = menu.addAction('Copy pixel coordinate (0-based)')
        a.setToolTip('Copies the zero-based pixel coordinate (first/upper-left pixel = 0,0)')
        a.triggered.connect(lambda *args, txt=f'{self.mPx.x()}, {self.mPx.y()}':
                            self.onCopyToClipBoad(txt))

        a = menu.addAction('Copy pixel coordinate (1-based)')
        a.setToolTip('Copies the one-based pixel coordinate (first/upper-left pixel = 1,1)')
        a.triggered.connect(lambda *args, txt=f'{self.mPx.x() + 1}, {self.mPx.y() + 1}':
                            self.onCopyToClipBoad(txt))

        a = menu.addAction('Copy spatial coordinate')
        a.setToolTip('Copies the spatial coordinate as <x>,<y> pair')
        a.triggered.connect(lambda *args, txt=self.mGeo.toString():
                            self.onCopyToClipBoad(txt))

        a = menu.addAction('Copy spatial coordinate (WKT)')
        a.setToolTip('Copies the spatial coordinate as Well-Known-Type')
        a.triggered.connect(lambda *args, txt=self.mGeo.asWkt():
                            self.onCopyToClipBoad(txt))

    def onCopyToClipBoad(self, text: str):
        cb: QClipboard = QApplication.clipboard()
        cb.setText(text)


class CursorLocationInfoModel(TreeModel):
    ALWAYS_EXPAND = 'always'
    NEVER_EXPAND = 'never'
    REMAINDER = 'reminder'

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setColumnNames(['Band/Field', 'Value'])
        self.mCountFromZero: bool = True
        self.mCursorLocation: SpatialPoint = None

    def setCursorLocation(self, location: SpatialPoint):
        assert isinstance(location, SpatialPoint)
        self.mCursorLocation = location

    def setCountFromZero(self, b: bool):
        """
        Specifies if the 1st pixel (upper left corner) is countes as 0,0 (True, default) or 1,1 (False)
        :param b: bool
        """
        assert isinstance(b, bool)
        self.mCountFromZero = b

    def flags(self, index: QModelIndex):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def addSourceValues(self, sourceValueSet: SourceValueSet):
        if not isinstance(sourceValueSet, SourceValueSet):
            return
        bn = os.path.basename(sourceValueSet.source)

        newSourceNodes: List[TreeNode] = []

        if isinstance(sourceValueSet, RasterValueSet):

            root = TreeNode(bn)
            root.setIcon(QIcon(':/images/themes/default/mIconRasterLayer.svg'))

            # add sub-nodes
            pxNode = PixelPositionTreeNode(sourceValueSet.pxPosition,
                                           self.mCursorLocation,
                                           name='Pixel',
                                           zeroBased=self.mCountFromZero)

            subNodes = [pxNode]

            for bv in sourceValueSet.bandValues:
                if isinstance(bv, RasterValueSet.BandInfo):
                    # n = TreeNode(name='Band {}'.format(bv.bandIndex + 1))
                    n = TreeNode(name=bv.bandName)
                    n.setToolTip('Band {} {}'.format(bv.bandIndex + 1, bv.bandName).strip())
                    n.setValues([bv.bandValue, bv.bandName])
                    subNodes.append(n)

                    if isinstance(bv.classInfo, ClassInfo):
                        nc = TreeNode(name='Class')
                        nc.setValue(bv.classInfo.name())
                        nc.setIcon(bv.classInfo.icon())
                        n.appendChildNodes(nc)

                elif isinstance(bv, QColor):
                    n = TreeNode(name='Color')
                    n.setToolTip('Color selected from screen pixel')
                    n.setValue(bv.getRgb())
                    subNodes.append(n)
            root.appendChildNodes(subNodes)
            newSourceNodes.append(root)

        if isinstance(sourceValueSet, VectorValueSet):
            if len(sourceValueSet.features) == 0:
                return

            root = TreeNode(name=bn)
            refFeature = sourceValueSet.features[0]
            assert isinstance(refFeature, QgsFeature)
            typeName = QgsWkbTypes.displayString(refFeature.geometry().wkbType()).lower()
            if 'polygon' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconPolygonLayer.svg'))
            elif 'line' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconLineLayer.svg'))
            if 'point' in typeName:
                root.setIcon(QIcon(r':/images/themes/default/mIconPointLayer.svg'))

            subNodes = []
            for field in refFeature.fields():
                assert isinstance(field, QgsField)

                fieldNode = TreeNode(name=field.name())

                featureNodes = []
                for i, feature in enumerate(sourceValueSet.features):
                    assert isinstance(feature, QgsFeature)
                    nf = TreeNode(name='{}'.format(feature.id()))
                    nf.setValues([feature.attribute(field.name()), field.typeName()])
                    nf.setToolTip('Value of feature "{}" in field with name "{}"'.format(feature.id(), field.name()))
                    featureNodes.append(nf)
                fieldNode.appendChildNodes(featureNodes)
                subNodes.append(fieldNode)
            root.appendChildNodes(subNodes)
            newSourceNodes.append(root)

        self.rootNode().appendChildNodes(newSourceNodes)

    def clear(self):
        # self.beginResetModel()
        self.mRootNode.removeAllChildNodes()
        # self.endResetModel()


class CursorLocationInfoTreeView(TreeView):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class ComboBoxOption(object):
    def __init__(self, value, name=None, tooltip=None, icon=None):
        self.value = value
        self.name = str(value) if name is None else str(name)
        self.tooltip = tooltip
        self.icon = icon


LUT_GEOMETRY_ICONS = {}

RASTERBANDS = [
    ComboBoxOption('VISIBLE', 'Visible', 'Visible bands only.'),
    ComboBoxOption('ALL', 'All', 'All raster bands.'),

]

LAYERMODES = [
    ComboBoxOption('TOP_LAYER', 'Top layer', 'Show values of the top-most map layer only.'),
    ComboBoxOption('ALL_LAYERS', 'All layers', 'Show values of all map layers.')
]

LAYERTYPES = [
    ComboBoxOption('ALL', 'Raster and Vector', 'Show values of both, raster and vector layers.'),
    ComboBoxOption('VECTOR', 'Vector only', 'Show values of vector layers only.'),
    ComboBoxOption('RASTER', 'Raster only', 'Show values of raster layers only.')
]


class ComboBoxOptionModel(QAbstractListModel):

    def __init__(self, options, parent=None):
        super(ComboBoxOptionModel, self).__init__(parent)
        assert isinstance(options, list)

        for o in options:
            assert isinstance(o, ComboBoxOption)

        self.mOptions = options

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.mOptions)

    def columnCount(self, index=None, *args, **kwargs):
        return 1

    def index2option(self, index):

        if isinstance(index, QModelIndex) and index.isValid():
            return self.mOptions[index.row()]
        elif isinstance(index, int):
            return self.mOptions[index]
        return None

    def option2index(self, option):
        assert option in self.mOptions
        return self.mOptions.index(option)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        option = self.index2option(index)
        assert isinstance(option, ComboBoxOption)
        value = None
        if role == Qt.DisplayRole:
            value = option.name
        if role == Qt.ToolTipRole:
            value = option.tooltip
        if role == Qt.DecorationRole:
            value = option.icon
        if role == Qt.UserRole:
            value = option
        return value


class CursorLocationInfoDock(QDockWidget):
    sigLocationRequest = pyqtSignal()
    sigCursorLocationInfoAdded = pyqtSignal()

    def __init__(self, *args, **kwds):
        """Constructor."""
        super().__init__(*args, **kwds)

        path_ui = DIR_UI_FILES / 'cursorlocationinfodock.ui'
        loadUi(path_ui, self)

        self.mMaxPoints = 1
        self.mLocationHistory = []

        self.mCrs: QgsCoordinateReferenceSystem = QgsCoordinateReferenceSystem('EPSG:4326')
        self.mCanvases = []

        self.btnCrs.crsChanged.connect(self.setCrs)
        self.btnCrs.setCrs(QgsCoordinateReferenceSystem())

        self.mLocationInfoModel = CursorLocationInfoModel()
        self.mTreeView: CursorLocationInfoTreeView
        assert isinstance(self.mTreeView, CursorLocationInfoTreeView)
        self.mTreeView.setAutoExpansionDepth(3)
        self.mTreeView.setModel(self.mLocationInfoModel)

        self.mLayerModeModel = ComboBoxOptionModel(LAYERMODES, parent=self)
        self.mLayerTypeModel = ComboBoxOptionModel(LAYERTYPES, parent=self)
        self.mRasterBandsModel = ComboBoxOptionModel(RASTERBANDS, parent=self)

        self.cbLayerModes.setModel(self.mLayerModeModel)
        self.cbLayerTypes.setModel(self.mLayerTypeModel)
        self.cbRasterBands.setModel(self.mRasterBandsModel)
        self.actionRequestCursorLocation.triggered.connect(self.sigLocationRequest)
        self.actionReload.triggered.connect(self.reloadCursorLocation)

        self.btnActivateMapTool.setDefaultAction(self.actionRequestCursorLocation)
        self.btnReload.setDefaultAction(self.actionReload)

        self.actionAllRasterBands.triggered.connect(
            lambda: self.btnRasterBands.setDefaultAction(self.actionAllRasterBands))
        self.actionVisibleRasterBands.triggered.connect(
            lambda: self.btnRasterBands.setDefaultAction(self.actionVisibleRasterBands))

        self.updateCursorLocationInfo()

    def options(self):

        layerType = self.mLayerTypeModel.index2option(self.cbLayerTypes.currentIndex()).value
        layerMode = self.mLayerModeModel.index2option(self.cbLayerModes.currentIndex()).value
        rasterBands = self.mRasterBandsModel.index2option(self.cbRasterBands.currentIndex()).value

        return layerMode, layerType, rasterBands

    def loadCursorLocation(self, point: SpatialPoint, canvas: QgsMapCanvas):
        """
        :param point:
        :param canvas:
        :return:
        """
        assert isinstance(canvas, QgsMapCanvas)
        assert isinstance(point, SpatialPoint)

        self.setCursorLocation(point)
        self.setCanvas(canvas)
        self.reloadCursorLocation()

    def treeView(self) -> CursorLocationInfoTreeView:
        return self.mTreeView

    def reloadCursorLocation(self):
        """
        Call to load / re-load the data for the cursor location
        """

        ptInfo = self.cursorLocation()

        if not isinstance(ptInfo, SpatialPoint) or len(self.mCanvases) == 0:
            return

        mode, lyrtype, rasterbands = self.options()

        def layerFilter(canvas):
            assert isinstance(canvas, QgsMapCanvas)
            lyrs = canvas.layers()
            if lyrtype == 'VECTOR':
                lyrs = [lyr for lyr in lyrs if isinstance(lyr, QgsVectorLayer)]
            if lyrtype == 'RASTER':
                lyrs = [lyr for lyr in lyrs if isinstance(lyr, QgsRasterLayer)]

            return lyrs

        lyrs = []
        for c in self.mCanvases:
            lyrs.extend(layerFilter(c))

        self.treeView().updateNodeExpansion(False)
        self.mLocationInfoModel.clear()
        self.mLocationInfoModel.setCursorLocation(self.cursorLocation())

        for lyr in lyrs:
            assert isinstance(lyr, QgsMapLayer)
            if mode == 'TOP_LAYER' and self.mLocationInfoModel.rootNode().childCount() > 0:
                s = ""
                break

            assert isinstance(lyr, QgsMapLayer)

            pointLyr = ptInfo.toCrs(lyr.crs())
            if not (isinstance(pointLyr, SpatialPoint) and lyr.extent().contains(pointLyr)):
                continue

            if isinstance(lyr, QgsRasterLayer):
                renderer = lyr.renderer()
                px = geo2px(pointLyr, lyr)
                v = RasterValueSet(lyr.name(), pointLyr, px)

                # !Note: b is not zero-based -> 1st band means b == 1
                if rasterbands == 'VISIBLE':
                    if isinstance(renderer, QgsPalettedRasterRenderer):
                        bandNumbers = renderer.usesBands()
                        # sometime the renderer is set to band 0 (which does not exist)
                        # QGIS bug
                        if bandNumbers == [0] and lyr.bandCount() > 0:
                            bandNumbers = [1]
                    else:
                        bandNumbers = renderer.usesBands()

                elif rasterbands == 'ALL':
                    bandNumbers = list(range(1, lyr.bandCount() + 1))
                else:
                    bandNumbers = [1]

                pt2 = QgsPointXY(pointLyr.x() + lyr.rasterUnitsPerPixelX() * 3,
                                 pointLyr.y() - lyr.rasterUnitsPerPixelY() * 3)
                ext2Px = QgsRectangle(pointLyr.x(), pt2.y(), pt2.x(), pointLyr.y())

                if lyr.dataProvider().name() in ['wms']:
                    for b in bandNumbers:
                        block = lyr.renderer().block(b, ext2Px, 3, 3)
                        assert isinstance(block, QgsRasterBlock)
                        v.bandValues.append(QColor(block.color(0, 0)))
                else:
                    dp: QgsRasterDataProvider = lyr.dataProvider()
                    results = dp.identify(pointLyr, QgsRaster.IdentifyFormatValue).results()
                    classScheme = None
                    if isinstance(lyr.renderer(), QgsPalettedRasterRenderer):
                        classScheme = ClassificationScheme.fromRasterRenderer(lyr.renderer())
                    for b in bandNumbers:
                        if b in results.keys():
                            bandValue = results[b]
                            if bandValue:
                                bandValue = as_py_value(bandValue, lyr.dataProvider().dataType(b))

                            classInfo: ClassInfo = None
                            if isinstance(bandValue, (int, float)) and isinstance(classScheme, ClassificationScheme):
                                classInfo = classScheme.classInfo(label=int(bandValue))
                            info = RasterValueSet.BandInfo(b - 1, bandValue, lyr.bandName(b), classInfo=classInfo)
                            v.bandValues.append(info)

                self.mLocationInfoModel.addSourceValues(v)
                s = ""

            if isinstance(lyr, QgsVectorLayer):
                # searchRect = QgsRectangle(pt, pt)

                # searchRadius = QgsTolerance.toleranceInMapUnits(1, lyr, self.mCanvas.mapRenderer(),
                # QgsTolerance.Pixels)
                searchRadius = QgsTolerance.toleranceInMapUnits(1, lyr, self.mCanvases[0].mapSettings(),
                                                                QgsTolerance.Pixels)
                # searchRadius = QgsTolerance.defaultTolerance(lyr, self.mCanvas.mapSettings()) searchRadius =
                # QgsTolerance.toleranceInProjectUnits(1, self.mCanvas.mapRenderer(), QgsTolerance.Pixels)
                searchRect = QgsRectangle()
                searchRect.setXMinimum(pointLyr.x() - searchRadius)
                searchRect.setXMaximum(pointLyr.x() + searchRadius)
                searchRect.setYMinimum(pointLyr.y() - searchRadius)
                searchRect.setYMaximum(pointLyr.y() + searchRadius)

                flags = QgsFeatureRequest.ExactIntersect
                features = lyr.getFeatures(QgsFeatureRequest()
                                           .setFilterRect(searchRect)
                                           .setFlags(flags))
                feature = QgsFeature()
                s = VectorValueSet(lyr.source(), pointLyr)
                while features.nextFeature(feature):
                    s.features.append(QgsFeature(feature))

                self.mLocationInfoModel.addSourceValues(s)
                s = ""

                pass

        self.treeView().updateNodeExpansion(True)

    def setCursorLocation(self, spatialPoint: SpatialPoint):
        """
        Set the cursor location to be loaded.
        :param spatialPoint:
        """
        assert isinstance(spatialPoint, SpatialPoint)
        self.mLocationHistory.insert(0, spatialPoint)
        if len(self.mLocationHistory) > self.mMaxPoints:
            del self.mLocationHistory[self.mMaxPoints:]

        if self.mCrs is None:
            self.setCrs(spatialPoint.crs())
        self.updateCursorLocationInfo()

    def updateCursorLocationInfo(self):

        self.btnCrs.setToolTip(f'Set CRS<br>Selected CRS: {self.mCrs.description()}')

        # transform this point to targeted CRS
        pt = self.cursorLocation()
        if isinstance(pt, SpatialPoint):
            pt2 = pt.toCrs(self.mCrs)
            if isinstance(pt2, SpatialPoint):
                tt = f'{pt2.asWkt()} <br>CRS: {self.mCrs.description()}'
                self.tbX.setText('{}'.format(pt2.x()))
                self.tbY.setText('{}'.format(pt2.y()))
                self.tbX.setToolTip(tt)
                self.tbY.setToolTip(tt)
            else:
                self.tbX.setText('None')
                self.tbY.setText('None')
                tt = f'Unable to convert {pt.asWkt()} from ' \
                     f'<br>CRS 1: {pt.crs().description()} to' \
                     f'<br>CRS 2: {self.mCrs.description()}'
                self.tbX.setToolTip(tt)
                self.tbY.setToolTip(tt)

    def setCanvas(self, mapCanvas):
        self.setCanvases([mapCanvas])

    def setCanvases(self, mapCanvases):
        assert isinstance(mapCanvases, list)
        for c in mapCanvases:
            assert isinstance(c, QgsMapCanvas)

        if len(mapCanvases) == 0:
            self.setCrs(None)
        else:
            setNew = True
            for c in mapCanvases:
                if c in self.mCanvases:
                    setNew = False
            if setNew:
                self.setCrs(mapCanvases[0].mapSettings().destinationCrs())
        self.mCanvases = mapCanvases

    def setCrs(self, crs):
        """
        Set the coordinate reference system in which coordinates are shown
        :param crs:
        :return:
        """
        assert isinstance(crs, QgsCoordinateReferenceSystem)
        if crs != self.mCrs:
            self.mCrs = crs
            self.btnCrs.setCrs(crs)
        self.updateCursorLocationInfo()

    def cursorLocation(self) -> SpatialPoint:
        """
        Returns the last location that was set.
        """
        if len(self.mLocationHistory) > 0:
            return self.mLocationHistory[0]
        else:
            return None, None
