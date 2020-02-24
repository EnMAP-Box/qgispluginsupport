import typing, pathlib
from qgis.core import QgsRasterLayer, QgsRasterRenderer
from qgis.core import *
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsRasterBandComboBox
from qgis.gui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtCore import *
from ..utils import loadUi
import numpy as np
from .core import QpsMapLayerConfigWidget
from osgeo import gdal, ogr

class GDALMetadataModel(QAbstractTableModel):
    class MDItem(object):
        def __init__(self, major_object: str, domain: str, key: str, value: str):
            self.major_object: str = major_object
            self.domain: str = domain
            self.key: str = key
            self.value: str = value

    def __init__(self, parent=None):
        super(GDALMetadataModel, self).__init__(parent)

        self.mLayer: QgsMapLayer = None

        self.cnItem = 'Item'
        self.cnDomain = 'Domain'
        self.cnKey = 'Key'
        self.cnValue = 'Value(s)'

        # level0 = gdal.Dataset | ogr.DataSource
        # level1 = gdal.Band | ogr.Layer
        self.MD = []

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.MD)

    def columnNames(self) -> typing.List[str]:
        return [self.cnItem, self.cnDomain, self.cnKey, self.cnValue]

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.columnNames())

    def headerData(self, col, orientation, role=None):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columnNames()[col]
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            return col
        return None

    def setLayer(self, layer: QgsMapLayer):
        assert isinstance(layer, (QgsRasterLayer, QgsVectorLayer))
        self.mLayer = layer
        self.syncToLayer()

    def syncToLayer(self):
        self.beginResetModel()
        self.MD = self._read_maplayer()
        self.endResetModel()

    def data(self, index: QModelIndex, role=None):
        if not index.isValid():
            return None

        item = self.MD[index.row()]
        assert isinstance(item, GDALMetadataModel.MDItem)

        cname = self.columnNames()[index.column()]

        if role == Qt.DisplayRole:
            if cname == self.cnItem:
                return item.major_object
            elif cname == self.cnDomain:
                return item.domain
            elif cname == self.cnKey:
                return item.key
            elif cname == self.cnValue:
                return item.value

        return None  # super(GDALMetadataModel, self).data(index, role)

    def _read_majorobject(self, obj):
        assert isinstance(obj, (gdal.MajorObject, ogr.MajorObject))
        domains = obj.GetMetadataDomainList()
        if isinstance(domains, list):
            for domain in domains:
                for key, value in obj.GetMetadata(domain).items():
                    yield domain, key, value

    def _read_maplayer(self) -> list:
        items = []
        if isinstance(self.mLayer, QgsRasterLayer) and self.mLayer.dataProvider().name() == 'gdal':
            ds = gdal.Open(self.mLayer.source())
            if isinstance(ds, gdal.Dataset):
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataModel.MDItem('Dataset', domain, key, value))
                for b in range(ds.RasterCount):
                    band = ds.GetRasterBand(b + 1)
                    assert isinstance(band, gdal.Band)
                    bandKey = 'Band{}'.format(b + 1)
                    for (domain, key, value) in self._read_majorobject(band):
                        items.append(GDALMetadataModel.MDItem(bandKey, domain, key, value))

        if isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.dataProvider().name() == 'ogr':
            ds = ogr.Open(self.mLayer.source())
            if isinstance(ds, ogr.DataSource):
                for (domain, key, value) in self._read_majorobject(ds):
                    items.append(GDALMetadataModel.MDItem('Datasource', domain, key, value))
                for b in range(ds.GetLayerCount()):
                    lyr = ds.GetLayer(b)
                    assert isinstance(lyr, ogr.Layer)
                    lyrKey = 'Layer{}'.format(b + 1)
                    for (domain, key, value) in self._read_majorobject(lyr):
                        items.append(GDALMetadataModel.MDItem(lyrKey, domain, key, value))

        return items


class GDALMetadataModelTreeView(QTreeView):
    """
    A QTreeView for the GDALMetadataModel
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Opens a context menue
        """
        index = self.indexAt(event.pos())
        if index.isValid():
            value = str(index.data(Qt.DisplayRole))
            m = QMenu()
            a = m.addAction('Copy Value')
            a.triggered.connect(lambda *args, value=value: QApplication.clipboard().setText(value))
            m.exec_(event.globalPos())


class GDALMetadataModelConfigWidget(QpsMapLayerConfigWidget):


    def __init__(self, layer:QgsMapLayer, canvas:QgsMapCanvas, parent:QWidget=None):
        super(GDALMetadataModelConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'gdalmetadatamodelwidget.ui'
        loadUi(pathUi, self)

        if isinstance(layer, QgsRasterLayer):
            self.setPanelTitle('GDAL Metadata')
            self.setToolTip('Layer metadata according to the GDAL Metadata model')
            self.setWindowIcon(QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))
        elif isinstance(layer, QgsVectorLayer):
            self.setPanelTitle('OGR Metadata')
            self.setToolTip('Layer metadata according to the OGR Metadata model')
            self.setWindowIcon(QIcon(':/qps/ui/icons/edit_ogr_metadata.svg'))

        self.tvMetadata: QTableView
        self.tbFilter: QLineEdit
        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)

        self.metadataModel = GDALMetadataModel()
        self.metadataProxyModel = QSortFilterProxyModel()
        self.metadataProxyModel.setSourceModel(self.metadataModel)
        self.metadataProxyModel.setFilterKeyColumn(-1)
        self.tableView.setModel(self.metadataProxyModel)

        self.tbFilter.textChanged.connect(self.updateFilter)
        self.optionMatchCase.changed.connect(self.updateFilter)
        self.optionRegex.changed.connect(self.updateFilter)

        is_gdal = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        is_ogr = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'

    def apply(self):
        #todo: apply changes to vector layer
        pass

    def syncToLayer(self):
        self.metadataModel.syncToLayer()

    def updateFilter(self, *args):

        text = self.tbFilter.text()
        if self.optionMatchCase.isChecked():
            matchCase = Qt.CaseSensitive
        else:
            matchCase = Qt.CaseInsensitive

        if self.optionRegex.isChecked():
            syntax = QRegExp.RegExp
        else:
            syntax = QRegExp.Wildcard
        rx = QRegExp(text, cs=matchCase, syntax=syntax)
        if rx.isValid():
            self.metadataProxyModel.setFilterRegExp(rx)
        else:
            self.metadataProxyModel.setFilterRegExp(None)

class GDALMetadataConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(GDALMetadataConfigWidgetFactory, self).__init__('GDAL/OGR Metadata', QIcon(':/qps/ui/icons/edit_gdal_metadata.svg'))

    def supportsLayer(self, layer):
        is_gdal = isinstance(layer, QgsRasterLayer) and layer.dataProvider().name() == 'gdal'
        is_ogr = isinstance(layer, QgsVectorLayer) and layer.dataProvider().name() == 'ogr'
        return is_gdal or is_ogr

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return False

    def createWidget(self, layer, canvas, dockWidget=True, parent=None)->GDALMetadataModelConfigWidget:
        w = GDALMetadataModelConfigWidget(layer, canvas, parent=parent)
        return w

    def title(self)->str:
        return 'GDAL Metadata'

