from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import *

from .maptools import QgsFeatureAction
class VectorTools(QgsVectorLayerTools):
    sigMessage = pyqtSignal(str, str, Qgis.MessageLevel)
    sigEditingStarted = pyqtSignal(QgsVectorLayer)
    sigEditingStopped = pyqtSignal(QgsVectorLayer)
    sigFreezeCanvases = pyqtSignal(bool)

    def __init__(self, *args, **kwds):
        super(VectorTools, self).__init__(*args, **kwds)
        pass

    def addFeature(self, layer: QgsVectorLayer, defaultValues, defaultGeometry:QgsGeometry, f:QgsFeature=None) -> bool:
        """
        This method should/will be called, whenever a new feature will be added to the layer.
        """
        if f is None:
            f = QgsFeature()
        a = QgsFeatureAction("Add feature", f, layer, None, None)
        return a.addFeature(defaultValues)

    def startEditing(self, layer:QgsVectorLayer ) -> bool:
        """
        This will be called, whenever a vector layer should be switched to edit mode.
        """
        if not isinstance(layer, QgsVectorLayer):
            return False

        if not layer.isEditable() and not layer.readOnly():

            if not (layer.dataProvider().capabilities() & QgsVectorDataProvider.EditingCapabilities ):
                title = "Start editing failed"
                msg = "Provider cannot be opened for editing"
                self.sigMessage.emit(title, msg, Qgis.Information)
                return False
            layer.startEditing()
            if layer.isEditable():
                self.sigEditingStarted.emit(layer)
        return layer.isEditable()

    def saveEdits(self, layer: QgsVectorLayer) -> bool:
        """
        Should be called, when the features should be committed but the editing session is not ended.
        """
        if layer.isModified():

            if not layer.commitChanges():
                self.commitError(layer)
            return False
            layer.startEditing()
        else:
            return True

    def stopEditing(self, layer: QgsVectorLayer, allowCancel:bool) -> bool:
        """
        Will be called, when an editing session is ended and the features should be committed.
        """


        if layer.isModified():
            buttons = QMessageBox.Save | QMessageBox.Discard
            if allowCancel:
                buttons = buttons | QMessageBox.Cancel

            button = QMessageBox.question(None,
                                          'Stop Editing',
                                          'Do you want to save the changes to layer {}'.format(layer.name())
                                          )
            result = True
            if button == QMessageBox.Cancel:
                result = False
            elif button == QMessageBox.Save:
                if not layer.commitChanges():
                    self.commitError(layer)
                    result = False
            elif button == QMessageBox.Discard:
                self.sigFreezeCanvases.emit(True)
                if not layer.rollBack():
                    title = 'Error'
                    text = 'Problems during rollback'
                    result = False
                    self.sigMessage.emit(title, text, Qgis.Critical)
                self.sigFreezeCanvases.emit(False)
                layer.triggerRepaint()

        else:
            result = True
            self.sigFreezeCanvases.emit(True)
            layer.rollBack()
            self.sigFreezeCanvases.emit(False)
            layer.triggerRepaint()

        self.sigEditingStopped.emit(layer)
        return result

    def commitError(self, layer: QgsVectorLayer):
        """
        collects the layer's commit errors and emits the sigMessage with a warning.
        """
        title = 'Commit Errors'

        info = "Could not commit changes to layer {}".format(layer.name())
        info += "\n\n{}".format('\n '.join(layer.commitErrors()))

        self.sigMessage.emit(title, info, Qgis.Warning)

