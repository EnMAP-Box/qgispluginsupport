from qgis.PyQt.QtCore import Qt, QModelIndex, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QTableView, QDialog

from qgis.core import QgsField, QgsFields, QgsEditorWidgetSetup, QgsVectorLayer
from qgis.core import QgsFieldModel
from .. import EDITOR_WIDGET_REGISTRY_KEY, speclibUiPath
from ..core import is_profile_field, can_store_spectral_profiles, profile_fields
from ..core.spectrallibrary import SpectralLibraryUtils
from ...utils import loadUi


class SpectralProfileFieldListModel(QgsFieldModel):
    """A list-model that shows all SpectralProfile fields of a vector layer"""

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)
        self.mLayer: QgsVectorLayer = None

    def updateFields(self):
        """
        Call this to update the list of spectral profile fields, e.g. after removal of fields or changing the
        editor widget setup.
        """

        pfields = QgsFields()

        if isinstance(self.mLayer, QgsVectorLayer):
            for field in profile_fields(self.mLayer):
                pfields.append(field)
        super().setFields(pfields)

    def layer(self) -> QgsVectorLayer:
        """
        Returns the layer, i.e. the spectral library
        :return: QgsVectorLayer
        """
        return self.mLayer

    def setLayer(self, layer: QgsVectorLayer):
        """
        Sets the vectorlayer, i.e. the spectral library
        :param layer:
        :return:
        """
        self.mLayer = layer
        self.mLayer.updatedFields.connect(self.updateFields)
        self.updateFields()

    def field(self, index: QModelIndex) -> QgsField:
        return self.fields().at(index.row())

    def data(self, index: QModelIndex, role):
        field = self.field(index)

        if role == Qt.DisplayRole:
            return field.name()

        if role == Qt.ToolTipRole:
            return QgsFieldModel.fieldToolTip(field)


class SpectralProfileFieldActivatorModel(QgsFieldModel):
    # CN_ID = 0
    CN_Field = 0
    CN_Type = 1
    CN_Comment = 2
    CN_EditorWidget = 3

    editorWidgetChanged = pyqtSignal(int)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mLayer: QgsVectorLayer = None

        self.mColNames = {
            # self.CN_ID: self.tr('Id'),
            self.CN_Field: self.tr('Name'),
            self.CN_Type: self.tr('Type'),
            self.CN_Comment: self.tr('Comment'),
            self.CN_EditorWidget: self.tr('Widget')
        }

        self.mColTooltip = {
            self.CN_Field: self.tr('Field name.'),
            self.CN_Comment: self.tr('Field comment'),
            self.CN_Type: self.tr('Field data type.'),
            self.CN_EditorWidget: self.tr('The widget to edit field values.')
        }

        self.mDefaultEditorWidgets = dict()

    def setLayer(self, layer: QgsVectorLayer):

        super().setLayer(layer)

        self.mDefaultEditorWidgets.clear()

        for i, field in enumerate(layer.fields()):
            self.mDefaultEditorWidgets[field.name()] = layer.editorWidgetSetup(i)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):

        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.mColNames[section]
            if role == Qt.ToolTipRole:
                return self.mColTooltip[section]

        return super().headerData(section, orientation, role)

    def field(self, index: QModelIndex) -> QgsField:
        return self.fields().at(index.row())

    def fields(self) -> QgsFields:

        layer = self.layer()
        if not (isinstance(layer, QgsVectorLayer) and layer.isValid()):
            return QgsFields()
        else:
            return self.layer().fields()

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:

        # flags = super().flags(index)
        flags = Qt.NoItemFlags
        if can_store_spectral_profiles(self.field(index)):
            flags = flags | Qt.ItemIsEnabled
            if index.column() == 0:
                flags = flags | Qt.ItemIsUserCheckable
        else:
            s = ""

        return flags

    def rowCount(self, parent=None, *args, **kwargs):
        return self.fields().count()

    def columnCount(self, parent=None):
        return len(self.mColNames)

    def setData(self, index: QModelIndex, value, role):

        changed = False
        if index.column() == 0 and role == Qt.CheckStateRole:
            field = self.field(index)
            i = index.row()
            layer = self.layer()

            if value == Qt.Checked:
                changed = SpectralLibraryUtils.makeToProfileField(layer, field)

            elif value == Qt.Unchecked:
                last: QgsEditorWidgetSetup = self.mDefaultEditorWidgets[field.name()]
                if last.type() == EDITOR_WIDGET_REGISTRY_KEY:
                    last = QgsEditorWidgetSetup()
                layer.setEditorWidgetSetup(i, last)
                changed = True
                s = ""

            if changed:
                # update entire row
                i0 = self.index(index.row(), 0)
                i1 = self.index(index.row(), self.columnCount() - 1)
                self.dataChanged.emit(i0, i1, [Qt.DisplayRole, Qt.CheckStateRole, Qt.ToolTipRole, Qt.DecorationRole])
                self.editorWidgetChanged.emit(index)

        return changed

    def data(self, index: QModelIndex, role):

        col = index.column()

        field: QgsField = self.field(index)
        layer: QgsVectorLayer = self.layer()

        if role == Qt.DisplayRole:
            if col == self.CN_Field:
                return field.name()
            if col == self.CN_Type:
                return field.typeName()
            if col == self.CN_EditorWidget:
                return field.editorWidgetSetup().type()
            if col == self.CN_Comment:
                return field.comment()

        if role == Qt.ToolTipRole:

            tt = QgsFieldModel.fieldToolTipExtended(field, layer)

            if not can_store_spectral_profiles(field):
                tt += '<br><i>Field type can not store spectral profiles.<i>'
            return tt

        if role == Qt.DecorationRole:
            if col == self.CN_Type:
                if is_profile_field(field):
                    return QIcon(r':/qps/ui/icons/profile.svg')
                else:
                    return QgsFields.iconForFieldType(field.type(), subType=field.subType(),
                                                      typeString=field.typeName())
            else:
                return None

        if role == Qt.CheckStateRole and col == 0:
            if self.flags(index) & Qt.ItemIsUserCheckable != 0:
                if is_profile_field(field):
                    return Qt.Checked
                else:
                    return Qt.Unchecked

        return None


class SpectralProfileFieldActivatorDialog(QDialog):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        loadUi(speclibUiPath(self), self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.mModel = SpectralProfileFieldActivatorModel()
        self.tableView().setModel(self.mModel)

    def setLayer(self, layer: QgsVectorLayer):
        self.mModel.setLayer(layer)

        tv: QTableView = self.tableView()
        for col in range(3):
            tv.resizeColumnToContents(col)

    def tableView(self) -> QTableView:
        return self.mTableView
