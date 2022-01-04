from qgis.core import QgsMapLayer, QgsVectorLayer
from qgis.gui import QgsFieldComboBox
from ..core import profile_fields


class SpectralProfileFieldComboBox(QgsFieldComboBox):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mSpeclib: QgsVectorLayer = None

    def setLayer(self, layer: QgsMapLayer):

        if isinstance(layer, QgsVectorLayer):
            self.mSpeclib = layer
        else:
            self.mSpeclib = None

        self._updateFields()

    def _updateFields(self):

        self.setFields(profile_fields(self.mSpeclib))