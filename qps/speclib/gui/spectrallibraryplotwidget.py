import re
import warnings
from typing import List, Optional, Union

from qgis.PyQt.QtCore import pyqtSignal, QAbstractItemModel, QItemSelectionModel, QMimeData, QModelIndex, \
    QRect, QSize, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QColor, QContextMenuEvent, QDragEnterEvent, QDropEvent, QFontMetrics, QIcon, \
    QPainter, QPalette, QPixmap
from qgis.PyQt.QtWidgets import QAbstractItemView, QAction, QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, \
    QMenu, QMessageBox, QStyle, QStyledItemDelegate, QStyleOptionButton, QStyleOptionViewItem, QTreeView, \
    QWidget
from qgis.PyQt.QtWidgets import QLineEdit
from qgis.core import QgsApplication, QgsField, QgsMapLayerProxyModel, QgsProject, QgsRasterLayer, \
    QgsSettings, QgsVectorLayer
from qgis.gui import QgsFilterLineEdit
from .spectrallibraryplotitems import SpectralProfilePlotWidget
from .spectrallibraryplotmodelitems import PlotStyleItem, ProfileVisualizationGroup, PropertyItem, \
    PropertyItemBase, PropertyItemGroup, PropertyLabel, RasterRendererGroup
from .spectrallibraryplotunitmodels import SpectralProfilePlotXAxisUnitWidgetAction
from .spectralprofileplotmodel import copy_items, SpectralProfilePlotModel, SpectralProfilePlotModelProxyModel
from .. import speclibUiPath
from ..core import profile_field_list
from ...models import SettingsModel
from ...plotstyling.plotstyling import PlotStyle, PlotWidgetStyle
from ...qgisenums import QMETATYPE_INT, QMETATYPE_QSTRING
from ...utils import loadUi, SelectMapLayerDialog


class SpectralProfilePlotView(QTreeView):

    def __init__(self, *args, **kwds):
        super(SpectralProfilePlotView, self).__init__(*args, **kwds)
        # self.horizontalHeader().setStretchLastSection(True)
        # self.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def controlTable(self) -> SpectralProfilePlotModel:
        return self.model()

    def selectedPropertyGroups(self) -> List[PropertyItemGroup]:
        return [idx.data(Qt.UserRole)
                for idx in self.selectionModel().selectedIndexes()
                if isinstance(idx.data(Qt.UserRole), PropertyItemGroup)]

    def selectPropertyGroups(self, visualizations):
        if isinstance(visualizations, ProfileVisualizationGroup):
            visualizations = [visualizations]

        model = self.model()
        rows = []
        for r in range(model.rowCount()):
            idx = model.index(r, 0)
            vis = model.data(idx, Qt.UserRole)
            if isinstance(vis, ProfileVisualizationGroup) and vis in visualizations:
                self.selectionModel().select(idx, QItemSelectionModel.Rows)

    def setModel(self, model: Optional[QAbstractItemModel]) -> None:
        super().setModel(model)
        if isinstance(model, QAbstractItemModel):
            model.rowsInserted.connect(self.onRowsInserted)

            for r in range(0, model.rowCount()):
                idx = model.index(r, 0)
                self.checkColumnSpanRecursively(idx)
                # item = idx.data(Qt.UserRole)
                # if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
                #    self.setFirstColumnSpanned(r, idx.parent(), True)

    def checkColumnSpanRecursively(self, index: QModelIndex):
        item = index.data(Qt.UserRole)

        if isinstance(item, PropertyItemBase):
            if item.firstColumnSpanned():
                self.setFirstColumnSpanned(index.row(), index.parent(), True)

            m: QAbstractItemModel = self.model()
            for r in range(m.rowCount(index)):
                index2 = m.index(r, 0, parent=index)
                self.checkColumnSpanRecursively(index2)

    def onRowsInserted(self, parent: QModelIndex, first: int, last: int):

        for r in range(first, last + 1):
            idx = self.model().index(r, 0, parent=parent)
            self.checkColumnSpanRecursively(idx)
            # item = idx.data(Qt.UserRole)
            # if isinstance(item, PropertyItemBase) and item.firstColumnSpanned():
            #    self.setFirstColumnSpanned(r, idx.parent(), True)
        s = ""

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """
        Default implementation. Emits populateContextMenu to create context menu
        :param event:
        :return:
        """

        menu: QMenu = QMenu()
        selected_indices = self.selectionModel().selectedRows()
        if len(selected_indices) == 1:
            item = selected_indices[0].data(Qt.UserRole)
            if isinstance(item, PropertyLabel):
                item = item.propertyItem()
            if isinstance(item, PropertyItemBase):
                item.populateContextMenu(menu)

        elif len(selected_indices) > 0:
            selected_items = []
            for idx in selected_indices:
                item = idx.data(Qt.UserRole)
                if isinstance(item, PropertyItemGroup) and item not in selected_items:
                    selected_items.append(item)

            removable = [item for item in selected_items if item.isRemovable()]
            copyAble = [item for item in selected_items if item.isDragEnabled()]

            profileVis = [item for item in selected_items if isinstance(item, ProfileVisualizationGroup)]

            a = menu.addAction('Remove')
            a.setIcon(QIcon(r':/images/themes/default/mActionDeleteSelected.svg'))
            a.triggered.connect(lambda *args, v=removable: self.removeItems(v))
            a.setEnabled(len(removable) > 0)

            a = menu.addAction('Copy')
            a.setIcon(QIcon(r':/images/themes/default/mActionEditCopy.svg'))
            a.triggered.connect(lambda *args, v=copyAble: self.copyItems(v))
            a.setEnabled(len(copyAble) > 0)

            a = menu.addAction('Paste')
            a.setIcon(QIcon(r':/images/themes/default/mActionEditPaste.svg'))
            a.setEnabled(QApplication.clipboard().mimeData().hasFormat(ProfileVisualizationGroup.MIME_TYPE))
            a.triggered.connect(lambda *args: self.pasteItems())
            a.setEnabled(
                QApplication.clipboard().mimeData().hasFormat(ProfileVisualizationGroup.MIME_TYPE)
            )

            if len(profileVis) > 0:
                a = menu.addAction('Use vector symbol colors')
                a.setToolTip('Use map vector symbol colors as profile color.')
                a.setIcon(QIcon(r':/qps/ui/icons/speclib_usevectorrenderer.svg'))
                a.triggered.connect(lambda *args, v=profileVis: self.userColorsFromSymbolRenderer(v))

        if not menu.isEmpty():
            # actions = menu.actions()
            menu.exec_(self.viewport().mapToGlobal(event.pos()))
            # s = actions

    def removeItems(self, vis: List[PropertyItemGroup]):

        model = self.model()

        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        if isinstance(model, SpectralProfilePlotModel):
            model.removePropertyItemGroups(vis)

    def copyItems(self, visualizations: List[ProfileVisualizationGroup]):

        indices = []
        for vis in visualizations:
            idx = self.vis2index(vis)
            if idx.isValid():
                indices.append(idx)
        if len(indices) > 0:
            mimeData = self.model().mimeData(indices)
            QApplication.clipboard().setMimeData(mimeData)

    def pasteItems(self):

        md: QMimeData = QApplication.clipboard().mimeData()

        idx = self.currentIndex()
        self.model().dropMimeData(md, Qt.CopyAction, idx.row(), idx.column(), idx.parent())

    def vis2index(self, vis: ProfileVisualizationGroup) -> QModelIndex:
        for r in range(self.model().rowCount()):
            idx = self.model().index(r, 0)
            if self.model().data(idx, Qt.UserRole) == vis:
                return idx
        return QModelIndex()

    def userColorsFromSymbolRenderer(self, vis: List[ProfileVisualizationGroup]):
        for v in vis:
            if isinstance(v, ProfileVisualizationGroup):
                v.mPColor.setToSymbolColor()


class SpectralProfilePlotViewDelegate(QStyledItemDelegate):
    """
    A QStyleItemDelegate to create and manage input editors for the SpectralProfilePlotControlView
    """

    def __init__(self, treeView: SpectralProfilePlotView, parent=None):
        assert isinstance(treeView, SpectralProfilePlotView)
        super(SpectralProfilePlotViewDelegate, self).__init__(parent=parent)
        self.mTreeView: SpectralProfilePlotView = treeView

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        item: PropertyItem = index.data(Qt.UserRole)
        bc = QColor(self.plotControl().generalSettings().backgroundColor())
        total_h = self.mTreeView.rowHeight(index)
        total_w = self.mTreeView.columnWidth(index.column())
        style: QStyle = option.styleObject.style()
        # print(style)
        margin = 2  # px
        if isinstance(item, PropertyItemBase):
            if item.hasPixmap():
                super().paint(painter, option, index)
                rect = option.rect
                size = QSize(rect.width(), rect.height())
                pixmap = item.previewPixmap(size)
                if isinstance(pixmap, QPixmap):
                    painter.drawPixmap(rect, pixmap)

            elif isinstance(item, ProfileVisualizationGroup):
                # super().paint(painter, option, index)
                to_paint = []
                if index.flags() & Qt.ItemIsUserCheckable:
                    to_paint.append(item.checkState())

                h = option.rect.height()
                plot_style: PlotStyle = item.plotStyle(add_symbol_scope=True)

                # add pixmap
                pm = plot_style.createPixmap(size=QSize(2 * h, h), hline=True, bc=bc)
                to_paint.append(pm)
                if not item.isComplete():
                    to_paint.append(QIcon(r':/images/themes/default/mIconWarning.svg'))
                to_paint.append(item.data(Qt.DisplayRole))

                x0 = option.rect.x()  # + 1
                y0 = option.rect.y()
                # print(to_paint)

                for p in to_paint:
                    o: QStyleOptionViewItem = QStyleOptionViewItem(option)
                    self.initStyleOption(o, index)
                    o.styleObject = option.styleObject
                    o.palette = QPalette(option.palette)

                    if isinstance(p, Qt.CheckState):
                        # size = style.sizeFromContents(QStyle.CE_CheckBox, o, QSize(), None)
                        o = QStyleOptionButton()

                        o.rect = QRect(x0, y0, h, h)
                        # print(o.rect)
                        o.state = {Qt.Unchecked: QStyle.State_Off,
                                   Qt.Checked: QStyle.State_On,
                                   Qt.PartiallyChecked: QStyle.State_NoChange}[p]
                        o.state = o.state | QStyle.State_Enabled | QStyleOptionButton.Flat | QStyleOptionButton.AutoDefaultButton

                        check_option = QStyleOptionButton()
                        check_option.state = o.state  # Checkbox is enabled

                        # Set the geometry of the checkbox within the item
                        check_option.rect = option.rect
                        QApplication.style().drawControl(QStyle.CE_CheckBox, check_option, painter)

                    elif isinstance(p, QPixmap):
                        o.rect = QRect(x0, y0, h * 2, h)
                        painter.drawPixmap(o.rect, p)

                    elif isinstance(p, QIcon):
                        o.rect = QRect(x0, y0, h, h)
                        p.paint(painter, o.rect)
                    elif isinstance(p, str):
                        font_metrics = QFontMetrics(self.mTreeView.font())
                        w = font_metrics.horizontalAdvance(p)
                        o.rect = QRect(x0 + margin, y0, x0 + margin + w, h)
                        # palette =
                        # palette = style.standardPalette()

                        enabled = item.checkState() == Qt.Checked
                        if not enabled:
                            o.palette.setCurrentColorGroup(QPalette.Disabled)
                        style.drawItemText(painter, o.rect, Qt.AlignLeft | Qt.AlignVCenter, o.palette, enabled, p,
                                           textRole=QPalette.Foreground)

                    else:
                        raise NotImplementedError(f'Does not support painting of "{p}"')
                    x0 = o.rect.x() + margin + o.rect.width()

            elif isinstance(item, PlotStyleItem):
                # self.initStyleOption(option, index)
                grp = item.parent()
                if isinstance(grp, ProfileVisualizationGroup) and item.key() == 'style':
                    plot_style = grp.plotStyle(add_symbol_scope=True)
                else:
                    plot_style: PlotStyle = item.plotStyle()

                if total_h > 0 and total_w > 0:
                    px = plot_style.createPixmap(size=QSize(total_w, total_h), bc=bc)
                    painter.drawPixmap(option.rect, px)
                else:
                    super().paint(painter, option, index)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

    def setItemDelegates(self, treeView: QTreeView):
        for c in range(treeView.model().columnCount()):
            treeView.setItemDelegateForColumn(c, self)

    def onRowsInserted(self, parent, idx0, idx1):
        nameStyleColumn = self.bridge().cnPlotStyle

        for c in range(self.mTreeView.model().columnCount()):
            cname = self.mTreeView.model().headerData(c, Qt.Horizontal, Qt.DisplayRole)
            if cname == nameStyleColumn:
                for r in range(idx0, idx1 + 1):
                    idx = self.mTreeView.model().index(r, c, parent=parent)
                    self.mTreeView.openPersistentEditor(idx)

    def plotControl(self) -> SpectralProfilePlotModel:
        return self.mTreeView.model().sourceModel()

    def createEditor(self, parent, option, index):
        w = None
        editor = None
        if index.isValid():
            item = index.data(Qt.UserRole)
            if callable(getattr(item, 'createEditor', None)):
                editor = item.createEditor(parent)
        if isinstance(editor, QWidget):
            return editor
        else:
            return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index: QModelIndex):

        # index = self.sortFilterProxyModel().mapToSource(index)
        if not index.isValid():
            return

        item = index.data(Qt.UserRole)
        # if isinstance(item, PropertyItem):
        if callable(getattr(item, 'setEditorData', None)):
            item.setEditorData(editor, index)
        else:
            if isinstance(item, ProfileVisualizationGroup) and isinstance(editor, QLineEdit):
                editor.setText(item.text())
            else:
                super().setEditorData(editor, index)

        return

    def setModelData(self, w, model, index):

        item = index.data(Qt.UserRole)
        if callable(getattr(item, 'setModelData', None)):
            item.setModelData(w, model, index)
        else:
            if isinstance(item, ProfileVisualizationGroup) and isinstance(w, QLineEdit):
                if item.text() != w.text():
                    item.mAutoName = False
            super().setModelData(w, model, index)


class SpectralLibraryPlotWidget(QWidget):
    sigDragEnterEvent = pyqtSignal(QDragEnterEvent)
    sigDropEvent = pyqtSignal(QDropEvent)
    sigPlotWidgetStyleChanged = pyqtSignal()
    sigTreeSelectionChanged = pyqtSignal()

    SHOW_MAX_PROFILES_HINT = True

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryplotwidget.ui'), self)

        assert isinstance(self.panelVisualization, QFrame)

        assert isinstance(self.mPlotWidget, SpectralProfilePlotWidget)
        assert isinstance(self.treeView, SpectralProfilePlotView)

        self.mPlotWidget: SpectralProfilePlotWidget
        assert isinstance(self.mPlotWidget, SpectralProfilePlotWidget)
        # self.plotWidget.sigPopulateContextMenuItems.connect(self.onPopulatePlotContextMenu)

        self.mPlotModel = SpectralProfilePlotModel()
        # self.mPlotModel.mBlockUpdates = True
        self.mPlotModel.setPlotWidget(self.mPlotWidget)
        self.mPlotModel.sigPlotWidgetStyleChanged.connect(self.sigPlotWidgetStyleChanged.emit)
        self.mPlotModel.sigMaxProfilesExceeded.connect(self.onMaxProfilesReached)
        self.mINITIALIZED_VISUALIZATIONS = set()

        # self.mPlotControlModel.sigProgressChanged.connect(self.onProgressChanged)
        self.setAcceptDrops(True)

        self.mProxyModel = SpectralProfilePlotModelProxyModel()
        self.mProxyModel.setSourceModel(self.mPlotModel)

        self.mFilterLineEdit: QgsFilterLineEdit
        self.mFilterLineEdit.textChanged.connect(self.setFilter)

        self.treeView.setModel(self.mProxyModel)
        self.treeView.selectionModel().selectionChanged.connect(self.onVisSelectionChanged)

        self.mViewDelegate = SpectralProfilePlotViewDelegate(self.treeView)
        self.mViewDelegate.setItemDelegates(self.treeView)

        # self.mDualView: Union[QgsDualView] = None
        self.mSettingsModel = SettingsModel(QgsSettings('qps'), key_filter='qps/spectrallibrary')

        self.optionShowVisualizationSettings: QAction
        self.optionShowVisualizationSettings.setCheckable(True)
        self.optionShowVisualizationSettings.setChecked(True)
        self.optionShowVisualizationSettings.setIcon(QgsApplication.getThemeIcon(r'/legend.svg'))
        self.optionShowVisualizationSettings.toggled.connect(self.panelVisualization.setVisible)

        self.actionAddProfileVis: QAction
        self.actionAddProfileVis.triggered.connect(self.createProfileVisualization)
        self.actionAddProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionAdd.svg'))

        self.actionAddRasterLayerRenderer: QAction
        self.actionAddRasterLayerRenderer.triggered.connect(self.createLayerBandVisualization)
        self.actionAddRasterLayerRenderer.setIcon(QgsApplication.getThemeIcon('/rendererCategorizedSymbol.svg'))

        self.actionRemoveProfileVis: QAction
        self.actionRemoveProfileVis.triggered.connect(self.removeSelectedPropertyGroups)
        self.actionRemoveProfileVis.setIcon(QgsApplication.getThemeIcon('/mActionRemove.svg'))

        self.optionSelectedFeaturesOnly: QAction
        self.optionSelectedFeaturesOnly.toggled.connect(self.mPlotModel.setShowSelectedFeaturesOnly)
        self.optionSelectedFeaturesOnly.setIcon(QgsApplication.getThemeIcon("/mActionShowSelectedLayers.svg"))
        self.mPlotModel.sigShowSelectedFeaturesOnlyChanged.connect(self.optionSelectedFeaturesOnly.setChecked)

        self.actionClearSelection.triggered.connect(self.plotModel().clearCurveSelection)
        self.btnClearSelection.setDefaultAction(self.actionClearSelection)
        # self.sbMaxProfiles: QSpinBox
        # self.sbMaxProfiles.valueChanged.connect(self.mPlotControlModel.setMaxProfiles)
        # self.labelMaxProfiles: QLabel
        # self.mPlotControlModel.setMaxProfilesWidget(self.sbMaxProfiles)

        self.optionCursorCrosshair: QAction
        self.optionCursorCrosshair.toggled.connect(self.mPlotWidget.setShowCrosshair)

        self.optionCursorPosition: QAction
        self.optionCursorPosition.toggled.connect(self.mPlotWidget.setShowCursorInfo)

        self.optionXUnit = SpectralProfilePlotXAxisUnitWidgetAction(self, self.mPlotModel.mXUnitModel)
        self.optionXUnit.setUnit(self.mPlotModel.xUnit())
        self.optionXUnit.setDefaultWidget(self.optionXUnit.createUnitComboBox())
        self.optionXUnit.sigUnitChanged.connect(self.mPlotModel.setXUnit)
        self.mPlotModel.sigXUnitChanged.connect(self.optionXUnit.setUnit)

        self.visButtonLayout: QHBoxLayout
        self.visLayoutTop: QHBoxLayout
        # self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1,
        #                                  self.optionMaxNumberOfProfiles.createWidget(self))

        # self.visLayoutTop = QHBoxLayout()
        cb: QComboBox = self.optionXUnit.createUnitComboBox()
        # cb.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed))
        self.visLayoutTop.addWidget(cb)
        self.visLayoutTop.setStretchFactor(cb, 3)
        # self.visButtonLayout.insertWidget(self.visButtonLayout.count() - 1,
        #                                  self.optionMaxNumberOfProfiles.createWidget(self))

        # grid: QGridLayout = widgetXAxis.layout()
        # grid.addWidget(QLabel('Unit:'), 0, 0, 1, 1)
        # grid.addWidget(self.optionXUnit.createUnitComboBox(), 0, 2, 1, 2)

        self.mPlotWidget.plotItem.sigPopulateContextMenuItems.connect(self.populateProfilePlotContextMenu)

        # connect actions with buttons
        self.btnAddProfileVis.setDefaultAction(self.actionAddProfileVis)
        self.btnAddRasterLayerRenderer.setDefaultAction(self.actionAddRasterLayerRenderer)
        self.btnRemoveProfileVis.setDefaultAction(self.actionRemoveProfileVis)
        self.btnSelectedFeaturesOnly.setDefaultAction(self.optionSelectedFeaturesOnly)

    def setProject(self, project: QgsProject):
        self.plotModel().setProject(project)

        # ensure that the dual-view layer is added to the recent QgsProject
        # lyr = self.mDualView.masterModel().layer()
        # if isinstance(lyr, QgsVectorLayer) and lyr.id() not in project.mapLayers():
        #     project.addMapLayer(lyr)

    def project(self) -> QgsProject:
        return self.plotModel().project()

    def plotWidgetStyle(self) -> PlotWidgetStyle:
        return self.mPlotModel.plotWidgetStyle()

    def populateProfilePlotContextMenu(self, menu_list: list):
        s = ""

        items = list(self.plotWidget().spectralProfilePlotDataItems(is_selected=True))
        n = len(items)

        m = QMenu('Copy ...')
        m.setToolTipsVisible(True)
        m.setEnabled(n > 0)
        if n > 0:
            x_unit = self.plotWidget().xAxis().unit()

            a = m.addAction('JSON')
            a.setToolTip(f'Copy {n} selected profile(s) as JSON')
            a.setIcon(QIcon(r':/images/themes/default/mIconFieldJson.svg'))

            a.triggered.connect(lambda *args, xu=x_unit, itm=items: copy_items(itm, 'json', xUnit=x_unit))

            a = m.addAction('CSV')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_copy.svg'))
            a.setToolTip(f'Copy {n} selected profile(s) in CSV format')
            a.triggered.connect(lambda *args, xu=x_unit, itm=items: copy_items(itm, 'csv', xUnit=x_unit))

            a = m.addAction('EXCEL')
            a.setIcon(QIcon(r':/qps/ui/icons/speclib_copy.svg'))
            a.setToolTip(f'Copy {n} selected profile(s) in CSV format with tab delimiter')
            a.triggered.connect(lambda *args, xu=x_unit, itm=items: copy_items(itm, 'excel', xUnit=x_unit))

        menu_list.append(m)
        # update current renderer

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mPlotWidget

    def plotModel(self) -> SpectralProfilePlotModel:
        return self.mPlotModel

    def updatePlot(self):
        self.mPlotModel.updatePlot()

    def readSettings(self):
        pass

    def writeSettings(self):
        pass

    def onVisSelectionChanged(self):

        # rows = self.treeView.selectionModel().selectedRows()
        groups = [g for g in self.treeView.selectedPropertyGroups() if g.isRemovable()]
        self.actionRemoveProfileVis.setEnabled(len(groups) > 0)
        self.sigTreeSelectionChanged.emit()

    def onMaxProfilesReached(self):

        if self.SHOW_MAX_PROFILES_HINT:
            self.SHOW_MAX_PROFILES_HINT = False
            n = self.mPlotModel.maxProfiles()

            self.panelVisualization.setVisible(True)

            item = self.plotModel().mGeneralSettings.mP_MaxProfiles
            idx = self.plotModel().indexFromItem(item)
            idx2 = self.treeView.model().mapFromSource(idx)
            self.treeView.setExpanded(idx2, True)
            self.treeView.scrollTo(idx2, QAbstractItemView.PositionAtCenter)

            result = QMessageBox.information(self,
                                             'Maximum number of profiles',
                                             f'Reached maximum number of profiles to display ({n}).\n'
                                             'Increase this value to display more profiles at same time.\n'
                                             'Showing a large numbers of profiles (and bands) can reduce '
                                             'visualization speed')

    def createLayerBandVisualization(self, *args):

        layer = None
        d = SelectMapLayerDialog()
        d.setWindowTitle('Select Raster Layer')
        d.setProject(self.plotModel().project())
        d.mapLayerComboBox().setFilters(QgsMapLayerProxyModel.RasterLayer)
        if d.exec_() == QDialog.Accepted:
            layer = d.layer()

        existing_layers = [v.layerId() for v in self.mPlotModel.layerRendererVisualizations()]
        if isinstance(layer, QgsRasterLayer) and layer.isValid() and layer.id() not in existing_layers:
            lvis = RasterRendererGroup(layer=layer)
            self.mPlotModel.insertPropertyGroup(0, lvis)
            lvis.updateBarVisiblity()

    def createProfileVisualization(self, *args,
                                   name: str = None,
                                   layer_id: Union[QgsVectorLayer, str, None] = None,
                                   field_name: Union[QgsField, int, str] = None,
                                   color: Union[str, QColor] = None,
                                   color_expression: str = None,
                                   style: PlotStyle = None,
                                   checked: bool = True) -> ProfileVisualizationGroup:
        """
        Creates a new profile visualization
        :param args:
        :param name:
        :param field_name:
        :param color:
        :param style:
        :param checked:
        :return:
        """
        item = ProfileVisualizationGroup()
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

        # set defaults

        if isinstance(layer_id, QgsVectorLayer):
            layer_id = layer_id.id()
        if isinstance(field_name, QgsField):
            field_name = field_name.name()

        # already shown speclib fields
        existing_fields = [(v.layerId(), v.fieldName())
                           for v in self.plotModel().visualizations()
                           if isinstance(v.fieldName(), str) and isinstance(v.layerId(), str)]

        # other existing speclib fields
        for lyr in self.project().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                for field in profile_field_list(lyr):
                    k = (lyr.id(), field.name())
                    if k not in existing_fields:
                        existing_fields.append(k)

        # try to find a good guess for the layer and field
        if layer_id is None and field_name is None:
            last_speclib = self.currentSpeclib()
            if isinstance(last_speclib, QgsVectorLayer):

                layer_id = last_speclib.id()

                for field in profile_field_list(last_speclib):
                    k = (layer_id, field.name())
                    if k not in existing_fields:
                        layer_id, field_name = k
                        break
        if layer_id is None and field_name is None and len(existing_fields) > 0:
            layer_id, field_name = existing_fields[-1]

        if layer_id and field_name is None:
            layer = self.project().mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer):
                profile_fields = profile_field_list(layer)
                if len(profile_fields) > 0:
                    field_name = profile_fields[0].name()

        # set profile source in speclib
        if isinstance(layer_id, str) and isinstance(field_name, str):
            item.setLayerField(layer_id, field_name)

        if item.layerId() and item.fieldName():
            # get a good guess for the name expression
            # 1. "<source_field_name>_name"
            # 2. "name"
            # 3. $id (fallback)

            layer = self.project().mapLayer(item.layerId())
            if isinstance(layer, QgsVectorLayer):
                name_field = None
                source_field_name = item.fieldName()
                rx1 = re.compile(source_field_name + '_?name', re.I)
                rx2 = re.compile('name', re.I)
                rx3 = re.compile('fid', re.I)
                for rx in [rx1, rx2, rx3]:
                    for field_name in layer.fields():
                        if field_name.type() in [QMETATYPE_QSTRING, QMETATYPE_INT] and rx.search(field_name.name()):
                            name_field = field_name
                            break
                    if name_field:
                        break
                if isinstance(name_field, QgsField):
                    item.setLabelExpression(f'"{name_field.name()}"')
                else:
                    item.setLabelExpression('$id')

        if not isinstance(style, PlotStyle):
            style = self.plotModel().defaultProfileStyle()
        item.setPlotStyle(style)

        if color:
            color = QColor(color)
            item.setColor(color)
        elif color_expression:
            item.setColorExpression(color_expression)

        self.mPlotModel.insertPropertyGroup(-1, item)
        return item
        # self.mPlotControlModel.updatePlot()

    def profileVisualizations(self) -> List[ProfileVisualizationGroup]:
        return self.mPlotModel.visualizations()

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.sigDragEnterEvent.emit(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.sigDropEvent.emit(event)

    def removeSelectedPropertyGroups(self, *args):
        rows = self.treeView.selectionModel().selectedRows()
        to_remove = [r.data(Qt.UserRole) for r in rows if isinstance(r.data(Qt.UserRole), PropertyItemGroup)]
        self.mPlotModel.removePropertyItemGroups(to_remove)

    # def setDualView(self, dualView):
    #    self.mDualView = dualView
    #    self.mPlotModel.setDualView(dualView)

    def currentVisualization(self) -> Optional[ProfileVisualizationGroup]:

        for idx in self.treeView.selectionModel().selectedRows():
            node = idx.data(Qt.UserRole)

            if isinstance(node, PropertyLabel):
                node = node.propertyItem()
            if isinstance(node, PropertyItem):
                node = node.parent()
            if isinstance(node, ProfileVisualizationGroup):
                return node

        return None

    def currentSpeclib(self) -> Optional[QgsVectorLayer]:
        """
        Returns the currently selected speclib layer, or None if not Visualization Group
        """
        vis = self.currentVisualization()
        if isinstance(vis, ProfileVisualizationGroup):
            return vis.layer()
        else:
            return None

    def speclib(self) -> Optional[QgsVectorLayer]:
        warnings.warn(DeprecationWarning('use currentSpeclib() instead'), stacklevel=2)
        return self.currentSpeclib()
        # return self.mDualView.masterModel().layer()

    # def addSpectralModel(self, model):
    #    self.mPlotControlModel.addModel(model)

    def setFilter(self, pattern: str):
        self.mProxyModel.setFilterWildcard(pattern)
