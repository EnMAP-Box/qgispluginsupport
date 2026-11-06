from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QWidget, QComboBox, QLabel
from qgis.core import (
    QgsMapLayer,
    QgsMapLayerModel,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsRasterLayer,
)
from qgis.gui import QgsAbstractProcessingParameterWidgetWrapper, QgsProcessingGui

from ..core.spectrallibraryrasterdataprovider import VectorLayerFieldRasterDataProvider


class SpectralProcessingRasterLayerWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter: QgsProcessingParameterDefinition = None,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.WidgetType.Standard,
                 parent: QObject = None
                 ):

        if not (isinstance(parameter, QgsProcessingParameterRasterLayer)):
            raise AssertionError(f'expected QgsProcessingParameterRasterLayer, got {parameter}')

        self.mMapLayerWidget: Optional[QWidget] = None
        self.mMapLayerModel: Optional[QgsMapLayerModel] = None

        self.mLabel: Optional[QLabel] = None

        super(SpectralProcessingRasterLayerWidgetWrapper, self).__init__(parameter, dialogType, parent)
        self.mProfileField: Optional[str] = None

    def createWidget(self):

        model = QgsMapLayerModel(self.widgetContext().project())
        model.setProject(self.widgetContext().project())
        self.mMapLayerModel = model

        param = self.parameterDefinition()
        is_optional = param.flags() & QgsProcessingParameterDefinition.Flag.FlagOptional
        if is_optional:
            model.setAllowEmptyLayer(True)

        mapLayerWidget = None
        if isinstance(param, QgsProcessingParameterRasterLayer):
            cb = QComboBox()
            model.setParent(cb)
            cb.setModel(model)
            cb.currentIndexChanged.connect(lambda idx, m=model: self.onIndexChanged(idx, m))
            mapLayerWidget = cb
        else:
            raise NotImplementedError()

        self.mMapLayerWidget = mapLayerWidget
        return mapLayerWidget

    def onIndexChanged(self, idx, model):
        layer = model.data(model.index(idx, 0), QgsMapLayerModel.CustomRole.LayerRole)
        self.setValue(layer)

    def createWrappedWidget(self, context) -> QWidget:

        if not isinstance(self.mMapLayerWidget, QWidget):
            self.mMapLayerWidget = self.createWidget()
        return self.mMapLayerWidget

    def createWrappedLabel(self) -> Optional[QLabel]:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def setWidgetValue(self, value, context):
        if isinstance(self.mMapLayerWidget, QComboBox):
            if isinstance(value, str):
                # find the best match in order of

                LAYER_INFOS: Dict[int, Tuple[str, str]] = dict()

                max_similarity = 0
                for i in range(self.mMapLayerWidget.count()):
                    layer = self.mMapLayerWidget.itemData(i, QgsMapLayerModel.ItemDataRole.LayerRole)

                    if not isinstance(layer, QgsMapLayer):
                        continue

                    similarity = SequenceMatcher(None, layer.name(), value).ratio()
                    max_similarity = max(max_similarity, similarity)
                    LAYER_INFOS[i] = (layer.id() == value, layer.name() == value, value in layer.name(), similarity)
                # match on 1. exact layer id,  2. exact layer name, 3. value in layer name
                for j in range(0, 3):
                    for i, t in LAYER_INFOS.items():
                        if t[j]:
                            self.mMapLayerWidget.setCurrentIndex(i)
                            return

                # match on 4. max similarity
                for i, t in LAYER_INFOS.items():
                    if t[3] == max_similarity:
                        self.mMapLayerWidget.setCurrentIndex(i)
                        return

    def widgetValue(self):
        if isinstance(self.mMapLayerWidget, QWidget):
            if isinstance(self.mMapLayerWidget, QComboBox):
                return self.mMapLayerWidget.currentData(QgsMapLayerModel.CustomRole.LayerRole)
            else:
                raise NotImplementedError()

        return None

    def createLabel(self) -> QLabel:
        # l = QLabel(f'<html><img width="20"px" height="20"
        # src=":/qps/ui/icons/profile.svg">{self.parameterDefinition().description()}</html>')
        param = self.parameterDefinition()

        if isinstance(param, QgsProcessingParameterRasterLayer):
            label = QLabel(f'<html><img src=":/qps/ui/icons/field_to_raster.svg">   '
                           f'{self.parameterDefinition().description()}</html>')
            tt = 'A field whose values will be converted into a temporary raster image:'
            tt += '<br>int, float -> 2D raster image'
            tt += '<br>spectral profiles with n values -> 3D raster images with n bands'
            tt += '<br>string -> 2D raster classification image, using the unique values field values as class name'
            label.setToolTip(tt)
        elif isinstance(param, QgsProcessingParameterMultipleLayers):
            label = QLabel(f'<html><img src=":/qps/ui/icons/field_to_raster.svg">   '
                           f'{self.parameterDefinition().description()}')
            label.setToolTip('A set of fields whose values will be converted into temporary raster images')
        else:
            raise NotImplementedError()
        self.mLabel = label
        return label

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def wrappedWidget(self) -> QWidget:
        if not isinstance(self.mMapLayerWidget, QComboBox):
            self.mMapLayerWidget = self.createWidget()
        return self.mMapLayerWidget

    def setValue(self, value):

        old = self.mProfileField
        if isinstance(value, QgsRasterLayer) and isinstance(value.dataProvider(), VectorLayerFieldRasterDataProvider):
            dp: VectorLayerFieldRasterDataProvider = value.dataProvider()
            self.mProfileField = dp.activeField()

        if old != self.mProfileField:
            self.widgetValueHasChanged.emit(self)

    def value(self):

        return self.mProfileField

        if self.mDialogType == QgsProcessingGui.WidgetType.Modeler:
            return self.widget.windowTitle() + '+Modeler'
        elif self.mDialogType == QgsProcessingGui.WidgetType.Batch:
            return self.widget.windowTitle() + '+Batch'
        else:
            return self.widget.windowTitle() + '+Std'
