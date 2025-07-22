from typing import Callable, Dict, Union, Optional

from PyQt5.QtWidgets import QSizePolicy

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QGridLayout, QLabel, QDialogButtonBox, QHBoxLayout, QCheckBox
from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsMapLayer, QgsField, QgsFieldProxyModel, QgsMapLayerProxyModel, QgsFieldModel, \
    QgsMapLayerModel, QgsVectorLayer, QgsFields
from qgis.core import QgsProject


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
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mFilterFunc: Callable = lambda layer: isinstance(layer, QgsMapLayer)
        self.mShowAll = True
        self.mSrcModel = self.sourceLayerModel()

    def setShowAll(self, show: bool):
        self.mShowAll = show
        self.invalidateFilter()

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


class SelectLayerFieldDialog(QDialog):

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
                new_lyr = self.layer()
                last_field = self.mLastFields.get(new_lyr.id(), None)
                self.setField(last_field)
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
        b = isinstance(lyr, QgsMapLayer)

        if self.mFieldComboBox.isVisible():
            b &= isinstance(lyr, QgsVectorLayer) and self.field() in lyr.fields().names()

        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(b)

        return b
