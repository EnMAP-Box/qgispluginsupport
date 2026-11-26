from typing import Dict, Any, List

from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtWidgets import QAbstractButton, QWidget
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsFeature, QgsVectorLayer, QgsVectorLayerTools, QgsDistanceArea, QgsProject, QgsAction, \
    QgsExpressionContextScope, QgsSettingsRegistryCore, QgsSettingsEntryBool, QgsVectorLayerUtils, QgsEditFormConfig
from qgis.gui import QgsAttributeEditorContext, QgsAttributeDialog, QgsHighlight, QgsAttributeForm


class QgsFeatureAction(QAction):
    """
    This is a python reimplementation of the qgis/app/QgsFeatureAction.cpp
    """
    sLastUsedValues: Dict[str, Dict[int, Any]] = dict()

    def __init__(self, name: str, f: QgsFeature, layer: QgsVectorLayer,
                 actionID: id = '',
                 defaultAttr: int = -1,
                 parent: QObject | None = None):

        super(QgsFeatureAction, self).__init__(name, parent)

        if not (isinstance(layer, QgsVectorLayer)):
            raise AssertionError
        self.mLayer = layer
        self.mFeature = f
        self.mActionId = actionID
        self.mIdx = defaultAttr
        self._refs = None
        self.mFeatureSaved = False
        self.mForceSuppressFormPopup = False
        self.mAttributeEditorContext = QgsAttributeEditorContext()
        self.mVectorLayerTools: QgsVectorLayerTools | None = None

    def setVectorLayerTools(self, tools: QgsVectorLayerTools):
        if not (isinstance(tools, QgsVectorLayerTools)):
            raise AssertionError
        self.mVectorLayerTools = tools

    def setAttributeEditorContext(self, context: QgsAttributeEditorContext):
        if not (isinstance(context, QgsAttributeEditorContext)):
            raise AssertionError
        self.mAttributeEditorContext = context

    def execute(self):
        self.mLayer.actions().doAction(self.mActionId, self.mFeature, self.mIdx)

    def parentWidget(self) -> QWidget | None:
        w = self.parent()
        if isinstance(w, QWidget):
            return w
        else:
            return None

    def newDialog(self, cloneFeatures: bool) -> QgsAttributeDialog:
        """
        Creates a new dialog
        :param cloneFeatures: bool
        :return: QgsAttributeDialog
        """
        refs = []
        if cloneFeatures:
            f = QgsFeature(self.mFeature)
        else:
            f = self.mFeature
        refs.append(f)

        myDa = QgsDistanceArea()
        myDa.setSourceCrs(self.mLayer.crs(), QgsProject.instance().transformContext())
        myDa.setEllipsoid(QgsProject.instance().ellipsoid())
        refs.append(myDa)

        context = QgsAttributeEditorContext(self.mAttributeEditorContext)
        context.setDistanceArea(myDa)
        context.setVectorLayerTools(self.mVectorLayerTools)
        # context.setMapCanvas()
        context.setFormMode(QgsAttributeEditorContext.FormMode.StandaloneDialog)
        refs.append(context)

        #
        featureOwner = False  # without the code fails
        dialog = QgsAttributeDialog(self.mLayer, f, featureOwner, self.parentWidget(), True, context)
        dialog.setObjectName('featureaction {} {}'.format(self.mLayer.id(), f.id()))

        actions = self.mLayer.actions().actions("Feature")
        if len(actions) == 0:
            dialog.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        a = QAction("Run Actions", dialog)
        a.setEnabled(False)
        dialog.addAction(a)

        for action in actions:
            if not (isinstance(action, QgsAction)):
                raise AssertionError
            if not action.runable():
                continue

            if not self.mLayer.isEditable() and action.isEnabledOnlyWhenEditable():
                continue

            feat = dialog.feature()
            a = QgsFeatureAction(action.name(), feat, self.mLayer, action.id(), -1, dialog)
            dialog.addAction(a)
            a.triggered.connect(a.execute)
            refs.append(a)
            pb = dialog.findChild(QAbstractButton, action.name())
            if isinstance(pb, QAbstractButton):
                pb.clicked.connect(a.execute)

        self._refs = refs
        return dialog

    def viewFeatureForm(self, h: QgsHighlight) -> bool:

        if not self.mLayer or not self.mFeature:
            return False

        _ = "featureactiondlg:{}:{}".format(self.mLayer.id(), self.mFeature.id())

        dialog = self.newDialog(True)
        dialog.setHighlight(h)
        # // delete the dialog when it is closed
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

        return True

    def editFeature(self, showModal: bool) -> bool:

        if not self.mLayer:
            return False

        if showModal:

            dialog = self.newDialog(False)

            if not self.mFeature.isValid():
                dialog.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)

            rv = dialog.exec()
            self.mFeature.setAttributes(dialog.feature().attributes())
            return rv

        else:

            _ = "featureactiondlg:{}:{}".format(self.mLayer.id(), self.mFeature.id())

            # QgsAttributeDialog *dialog = QgisApp::instance() -> findChild<QgsAttributeDialog *>( name );
            # if ( dialog )
            # {
            #  dialog->raise();
            #  return true;
            # }

            dialog = self.newDialog(False)

            if not self.mFeature.isValid():
                dialog.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)

            # // delete the dialog when it is closed
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.show()

        return True

    def addFeature(self,
                   defaultAttributeValues: dict = dict(),
                   showModal: bool = True,
                   scope: QgsExpressionContextScope = None) -> bool:

        if not (isinstance(self.mLayer, QgsVectorLayer) and self.mLayer.isEditable()):
            return False

        qgsSettingsRegistry = QgsSettingsRegistryCore()
        initialAttributeValues = dict()
        reuseLastValues = False
        entry = qgsSettingsRegistry.settingsEntry('qgis/digitizing/reuseLastValues')
        if isinstance(entry, QgsSettingsEntryBool):
            reuseLastValues = entry.value()

        lyr: QgsVectorLayer = self.mLayer
        for idx in range(lyr.fields().count()):

            if idx in defaultAttributeValues.keys():
                initialAttributeValues[idx] = defaultAttributeValues[idx]
            elif (
                (reuseLastValues or lyr.editFormConfig().reuseLastValue(idx))
                and self.mLayer.id() in self.sLastUsedValues.keys()  # noqa: W503
                and idx in self.sLastUsedValues[lyr.id()].keys()  # noqa: W503
            ):

                lastUsed = self.sLastUsedValues[lyr.id()][idx]
                """
                // Only set initial attribute value if it's different from the default clause or we may trigger
                // unique constraint checks for no reason, see https://github.com/qgis/QGIS/issues/42909
                """
                if lyr.dataProvider() and lyr.dataProvider().defaultValueClause(idx) != lastUsed:
                    initialAttributeValues[idx] = lastUsed

        fields = self.mLayer.fields()

        context = self.mLayer.createExpressionContext()
        if scope:
            context.appendScope(scope)

        newFeature = QgsVectorLayerUtils.createFeature(self.mLayer, self.mFeature.geometry(), initialAttributeValues,
                                                       context)

        self.mFeature = newFeature

        isDisabledAttributesValueDlg = False
        entry = qgsSettingsRegistry.settingsEntry('qgis/digitizing/disable_enter_attribute_values_dialog')
        if isinstance(entry, QgsSettingsEntryBool):
            isDisabledAttributesValueDlg = entry.value()

        if not self.mLayer.isSpatial():
            isDisabledAttributesValueDlg = False

        if fields.count() == 0:
            isDisabledAttributesValueDlg = True

        opt = self.mLayer.editFormConfig().suppress()
        if opt == QgsEditFormConfig.FeatureFormSuppress.SuppressOn:
            isDisabledAttributesValueDlg = True
        elif opt == QgsEditFormConfig.FeatureFormSuppress.SuppressOff:
            isDisabledAttributesValueDlg = False

        if self.mForceSuppressFormPopup:
            isDisabledAttributesValueDlg = True

        if isDisabledAttributesValueDlg:
            self.mLayer.beginEditCommand(self.text())
            self.mFeatureSaved = self.mLayer.addFeature(self.mFeature)
            if self.mFeatureSaved:
                self.mLayer.endEditCommand()
                self.mLayer.triggerRepaint()
            else:
                self.mLayer.destroyEditComand()
        else:

            dialog = self.newDialog(False)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)
            dialog.setEditCommandMessage(self.text())

            dialog.attributeForm().featureSaved.connect(
                lambda f, form=dialog.attributeForm(): self.onFeatureSaved(f, form))
            self._d = dialog
            if not showModal:
                self.setParent(dialog)
                dialog.show()

                self.mFeature = None
                return True

            dialog.exec()

        return self.mFeatureSaved

    def setForceSuppressFormPopup(self, force: bool):
        self.mForceSuppressFormPopup = force

    def onFeatureSaved(self, feature: QgsFeature, form=None):
        if form is None:
            form = self.sender()
        if not isinstance(form, QgsAttributeForm):
            return

        # // Assign provider generated values
        if self.mFeature:
            self.mFeature = feature

        self.mFeatureSaved = True

        qgsSettingsRegistry = QgsSettingsRegistryCore()

        reuseLastValues = False
        entry = qgsSettingsRegistry.settingsEntry('qgis/digitizing/reuseLastValues')
        if isinstance(entry, QgsSettingsEntryBool):
            reuseLastValues = entry.value()

        lyr = self.mLayer

        if reuseLastValues:
            fields = lyr.fields()
            origValues: Dict[int, Any] = self.sLastUsedValues.get(lyr.id(), dict())
            newValues: List = feature.attributes()
            for idx in range(fields.count()):
                origValues[idx] = newValues[idx]
            self.sLastUsedValues[lyr.id()] = origValues
