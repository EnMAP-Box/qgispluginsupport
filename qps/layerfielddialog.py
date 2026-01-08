from typing import Callable, Dict, Union, Optional, List

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import pyqtSignal, QAbstractListModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QComboBox, QGridLayout, QLabel, QDialogButtonBox, QHBoxLayout, QCheckBox, QAction
from qgis.PyQt.QtWidgets import QDialog
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget, QToolButton
from qgis.core import QgsMapLayer, QgsField, QgsFieldProxyModel, QgsMapLayerProxyModel, QgsFieldModel, \
    QgsMapLayerModel, QgsVectorLayer, QgsFields
from qgis.core import QgsProject


class FilteredProjectFieldsModel(QAbstractListModel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mProject = None
        self.mLayerFields = []
        self.mLayerFilterFunc: Optional[Callable] = None
        self.mFieldFilterFunc: Optional[Callable] = None

        self.setProject(QgsProject.instance())

    def setFieldFilter(self, func: Optional[Callable]):
        self.mFieldFilterFunc = func
        self.updateModel()

    def setLayerFilter(self, func: Optional[Callable]):
        self.mLayerFilterFunc = func
        self.updateModel()

    def rowCount(self, parent=None):
        return len(self.mLayerFields)

    def columnCount(self, parent=None):
        return 1

    def data(self, index, role):

        if not index.isValid():
            return None

        lid, field = self.mLayerFields[index.row()]

        lyr = self.mProject.mapLayer(lid)
        if isinstance(lyr, QgsMapLayer):
            if role == Qt.ItemDataRole.DisplayRole:
                if isinstance(field, QgsField):
                    return f'{lyr.name()}:{field.name()}'
                else:
                    return f'{lyr.name()}'
            if role == Qt.ItemDataRole.ToolTipRole:
                if isinstance(field, QgsField):
                    return f'Layer {lyr.source()}<br>Field {field.name()}'
                else:
                    return f'Layer {lyr.source()}'
            if role == Qt.ItemDataRole.UserRole:
                return lyr, field
        return None

    def updateModel(self):
        self.beginResetModel()
        self.mLayerFields.clear()
        if isinstance(self.mProject, QgsProject):

            for layer in self.mProject.mapLayers().values():
                if isinstance(layer, QgsMapLayer) and layer.isValid():
                    if self.mLayerFilterFunc is None or self.mLayerFilterFunc(layer):
                        if isinstance(layer, QgsVectorLayer):
                            fields = layer.fields()
                            for i in range(fields.count()):
                                field = fields.at(i)
                                if self.mFieldFilterFunc is None or self.mFieldFilterFunc(field):
                                    self.mLayerFields.append((layer.id(), field))
                        else:
                            self.mLayerFields.append((layer.id(), None))
        self.endResetModel()

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        if self.mProject != project:

            if isinstance(self.mProject, QgsProject):
                self.mProject.layersAdded.disconnect(self.updateModel)
                self.mProject.layersRemoved.disconnect(self.updateModel)

            self.mProject = project
            project.layersAdded.connect(self.updateModel)
            project.layersRemoved.connect(self.updateModel)
            self.updateModel()


class FilteredFieldProxyModel(QgsFieldProxyModel):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mSrcModel = self.sourceFieldModel()
        self.mFilterFunc: Callable = lambda field: isinstance(field, QgsField)
        self.mShowAll = True

    def showAll(self) -> bool:
        return self.mShowAll

    def setShowAll(self, show: bool):
        self.mShowAll = show
        self.invalidateFilter()

    def setFilterFunc(self, func: Callable):
        self.mFilterFunc = func
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow, sourceParent):
        if self.mShowAll:
            return True
        else:
            # show only fields that pass the filter function
            m = self.sourceModel()
            idx = m.data(m.index(sourceRow, 0, sourceParent), QgsFieldModel.CustomRole.FieldIndex)
            field = m.fields().at(idx)
            return self.mFilterFunc(field)

    def flags(self, index):
        f = super().flags(index)

        # disable out-filtered fields
        fname = self.data(index, QgsFieldModel.CustomRole.FieldName)

        fields = self.sourceFieldModel().fields()
        field: QgsField = fields[fname]
        if not self.mFilterFunc(field):
            f &= ~Qt.ItemIsSelectable
            f &= ~Qt.ItemIsEnabled
        return f


class FilteredMapLayerProxyModel(QgsMapLayerProxyModel):
    """
    A proxy model to filter layers based on a filter function.

    Use .setFilterFunc(func: Callable) to set a filter function.
    The function must accept a QgsMapLayer as an argument and return True or False.

    Use .setShowAll(b: bool) to either hide all layers that
    do not pass the filter (b = False) or show them as disable (b = True))

    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mFilterFunc: Callable = lambda layer: isinstance(layer, QgsMapLayer)
        self.mShowAll = True
        self.mSrcModel = self.sourceLayerModel()
        self.mProject = QgsProject.instance()

    def setShowAll(self, show: bool):
        self.mShowAll = show
        self.invalidateFilter()

    def setProject(self, project: QgsProject):
        super().setProject(project)
        self.mProject = project

    def project(self) -> QgsProject:
        return self.mProject

    def layers(self) -> List[QgsMapLayer]:
        results = []
        for i in range(self.rowCount()):
            idx = self.index(i, 0)
            results.append(self.data(idx, role=QgsMapLayerModel.CustomRole.Layer))
        return results

    def __getitem__(self, slice):
        return self.layers()[slice]

    def __len__(self) -> int:
        return self.rowCount()

    def flags(self, index):
        # disable selection of out-filtered layers
        f = super().flags(index)
        lyr = self.data(index, QgsMapLayerModel.CustomRole.Layer)

        if not self.mFilterFunc(lyr):
            f &= ~Qt.ItemIsSelectable
            f &= ~Qt.ItemIsEnabled
        return f

    def setFilterFunc(self, func: Callable):
        self.mFilterFunc = func
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow, sourceParent):

        if self.mShowAll:
            return True
        else:
            # show only layers that pass the filter function
            m = self.sourceModel()
            lyr = m.data(m.index(sourceRow, 0, sourceParent), QgsMapLayerModel.CustomRole.Layer)
            return self.mFilterFunc(lyr)


class LayerFieldDialog(QDialog):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.setWindowTitle("Select Layer Field")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.mLayerModel = FilteredMapLayerProxyModel()
        self.mFieldModel = FilteredFieldProxyModel()

        self.mLastFields: Dict[str, str] = dict()

        self.mLayerComboBox = QComboBox()
        self.mLayerComboBox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.mLayerComboBox.setModel(self.mLayerModel)
        self.mLayerComboBox.currentIndexChanged.connect(self.onLayerChanged)

        self.mShowFieldFilter: bool = True
        self.mLabelField = QLabel('Field')
        self.mFieldComboBox = QComboBox()
        self.mFieldComboBox.setModel(self.mFieldModel)
        self.mFieldComboBox.currentIndexChanged.connect(self.validate)

        self.mCbShowAll = QCheckBox(r'Show all')
        self.mCbShowAll.setToolTip(r'Show also layers and fields that did not pass the filter')
        self.mCbShowAll.setChecked(True)
        self.mCbShowAll.toggled.connect(self.setShowAll)

        self.mButtonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        btOk = self.mButtonBox.button(QDialogButtonBox.Ok)
        btOk.clicked.connect(self.accept)

        btCancel = self.mButtonBox.button(QDialogButtonBox.Cancel)
        btCancel.clicked.connect(self.reject)

        layout = QGridLayout()
        layout.addWidget(QLabel('Layer'), 0, 0)
        layout.addWidget(self.mLayerComboBox, 0, 1)

        layout.addWidget(self.mLabelField, 1, 0)
        layout.addWidget(self.mFieldComboBox, 1, 1)

        layout.addWidget(self.mCbShowAll, 2, 0, 1, 2)

        hbox = QHBoxLayout()
        hbox.addWidget(self.mButtonBox)
        layout.addLayout(hbox, 3, 0, 1, 2)
        self.setLayout(layout)

    def setShowFieldFilter(self, show: bool):
        self.mShowFieldFilter = show
        self.mFieldComboBox.setVisible(show)
        self.mLabelField.setVisible(show)

    def showFieldFilter(self) -> bool:
        return self.mShowFieldFilter

    def setLayer(self, layer: Union[QgsMapLayer, str]) -> bool:
        # save current field selection
        lyr = self.layer()
        if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
            self.mLastFields[lyr.id()] = self.field()

        # set new layer
        for i in range(self.mLayerComboBox.model().rowCount()):
            lyr = self.mLayerModel.data(self.mLayerModel.index(i, 0), QgsMapLayerModel.CustomRole.Layer)
            if layer in [lyr, lyr.id(), lyr.name()]:
                self.mLayerComboBox.setCurrentIndex(i)
                self.onLayerChanged(i)
                self.validate()
                return True

        self.validate()
        return False

    def onLayerChanged(self, index: int):

        lyr = self.mLayerComboBox.currentData(QgsMapLayerModel.CustomRole.Layer)

        lastField = None
        if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
            fields = lyr.fields()
            lastField = self.mLastFields.get(lyr.id(), None)

        else:
            fields = QgsFields()

        srcModel = self.mFieldModel.sourceFieldModel()
        srcModel.setFields(fields)

        if isinstance(lastField, str):
            self.setField(lastField)

        self.validate()

    def setShowAll(self, show: bool):
        self.mLayerModel.setShowAll(show)
        self.mFieldModel.setShowAll(show)

    def layer(self) -> Optional[QgsMapLayer]:
        return self.mLayerComboBox.currentData(QgsMapLayerModel.CustomRole.Layer)

    def field(self) -> Optional[str]:
        if self.showFieldFilter():
            return self.mFieldComboBox.currentData(QgsFieldModel.CustomRole.FieldName)
        else:
            return None

    def setField(self, field: Union[QgsField, str]) -> bool:

        if isinstance(field, QgsField):
            field = field.name()

        for i in range(self.mFieldComboBox.model().rowCount()):
            fname = self.mFieldComboBox.model().data(self.mFieldModel.index(i, 0), QgsFieldModel.CustomRole.FieldName)
            if fname == field:
                self.mFieldComboBox.setCurrentIndex(i)
                return True

        return False

    def setProject(self, project):
        assert isinstance(project, QgsProject)
        self.mLayerModel.setProject(project)

    def setLayerFilter(self, func: Optional[Callable]):
        self.mLayerModel.setFilterFunc(func)

    def setFieldFilter(self, func: Optional[Callable]):

        if callable(func):
            self.mFieldModel.setFilterFunc(func)
            self.setShowFieldFilter(True)

        else:
            self.setShowFieldFilter(False)

    def validate(self) -> bool:

        lyr = self.layer()

        b = isinstance(lyr, QgsMapLayer) and lyr.isValid()
        has_fields = isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        if self.mShowFieldFilter:
            b &= has_fields and self.field() in lyr.fields().names()
        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(b)

        self.mFieldComboBox.setEnabled(has_fields)
        self.mLabelField.setEnabled(has_fields)

        return b


class LayerFieldWidget(QWidget):
    """
    A widget to show the selected layer and field, with a button to open the LayerFieldDialog
    """
    layerFieldChanged = pyqtSignal(QgsMapLayer, str)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.setMinimumSize(5, 5)
        self.setMaximumHeight(75)

        self.mLayerFilterFunc = lambda layer: isinstance(layer, QgsVectorLayer) and layer.isValid()
        self.mFieldFilterFunc = lambda field: isinstance(field, QgsField)

        self.mLayer = None
        self.mField = None
        self.mProject: QgsProject = QgsProject.instance()
        layout = QHBoxLayout()

        p = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        p.setHorizontalStretch(2)
        self.mComboBox = QComboBox(parent=self)
        self.mComboBox.setSizePolicy(p)

        self.mComboBoxModel = FilteredProjectFieldsModel()
        self.mComboBoxModel.setFieldFilter(self.mFieldFilterFunc)
        self.mComboBoxModel.setLayerFilter(self.mLayerFilterFunc)
        self.mComboBoxModel.setProject(self.mProject)
        self.mComboBox.setModel(self.mComboBoxModel)
        self.mComboBox.currentIndexChanged.connect(self.onComboBoxChanged)

        self.mBtnAction = QAction('...')
        self.mBtnAction.setIcon(QIcon(':/images/themes/default/mSourceFields.svg'))
        self.mBtnAction.setText('...')
        self.mBtn = QToolButton(parent=self)
        self.mBtn.setDefaultAction(self.mBtnAction)

        # layout.addWidget(self.mLabel)
        layout.addWidget(self.mComboBox)
        layout.addWidget(self.mBtn)
        layout.setSpacing(2)

        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)
        self.sizePolicy().setHorizontalPolicy(QSizePolicy.Preferred)
        self.mBtn.clicked.connect(self.onClicked)

    def setLayerFilter(self, func: Optional[Callable]):
        self.mLayerFilterFunc = func
        self.mComboBoxModel.setLayerFilter(func)

    def setFieldFilter(self, func: Optional[Callable]):
        self.mFieldFilterFunc = func
        self.mComboBoxModel.setFieldFilter(func)

    def onComboBoxChanged(self, index):

        data = self.mComboBox.currentData(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple):
            lyr, field = data

            self.setLayerField(lyr, field)

    def onClicked(self, *args):

        d = LayerFieldDialog()
        d.setProject(self.mProject)
        d.setLayerFilter(self.mLayerFilterFunc)
        d.setFieldFilter(self.mFieldFilterFunc)

        d.setLayer(self.mLayer)
        d.setField(self.mField)

        if d.exec_() == d.Accepted:
            self.setLayerField(d.layer(), d.field())

    def setLayerField(self, layer: QgsMapLayer, field: Union[None, str, QgsField] = None):
        assert isinstance(layer, QgsMapLayer)
        if isinstance(field, QgsField):
            field = field.name()
        changed = self.mLayer != layer or self.mField != field

        if changed:
            self.mLayer = layer
            self.mField = field

            for i in range(self.mComboBox.count()):
                cLyr, cField = self.mComboBox.itemData(i, Qt.ItemDataRole.UserRole)
                if isinstance(cField, QgsField):
                    cField = cField.name()
                if cLyr == layer and cField == field:
                    self.mComboBox.setCurrentIndex(i)
                    break
            self.layerFieldChanged.emit(layer, field)

    def layerField(self) -> (Optional[QgsMapLayer], Optional[str]):
        return self.mLayer, self.mField

    def project(self):
        return self.mProject

    def setProject(self, project):
        assert isinstance(project, QgsProject)
        self.mProject = project
        self.mComboBoxModel.setProject(project)
