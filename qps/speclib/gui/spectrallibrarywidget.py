import logging
import warnings
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QCloseEvent
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
from qgis.PyQt.QtWidgets import QMenu, QWidget
from qgis.PyQt.QtWidgets import QToolButton
from qgis.PyQt.QtXml import QDomElement
from qgis.core import (QgsFeature, QgsProcessingOutputFile, QgsProject, QgsReadWriteContext,
                       QgsVectorLayer)
from qgis.core import QgsProcessingContext, QgsProcessingFeedback
from qgis.gui import QgsAttributeTableView, QgsMapCanvas
from qgis.gui import QgsMessageBar
from .spectrallibraryplotitems import SpectralProfilePlotItem, SpectralProfilePlotWidget
from .spectrallibraryplotmodelitems import ProfileVisualizationGroup
from .spectrallibraryplotwidget import SpectralLibraryPlotWidget
from .spectralprocessingdialog import SpectralProcessingDialog
from .spectralprofilefieldmodel import SpectralProfileFieldActivatorDialog
from .spectralprofileplotmodel import SpectralProfilePlotModel
from ..core import is_spectral_library, profile_field_names
from ..core.spectrallibrary import SpectralLibraryUtils
from ..processing.exportspectralprofiles import ExportSpectralProfiles
from ..processing.extractspectralprofiles import ExtractSpectralProfiles
from ..processing.importspectralprofiles import ImportSpectralProfiles
from ...layerproperties import showLayerPropertiesDialog, AttributeTableWidget
from ...plotstyling.plotstyling import PlotStyle
from ...processing.algorithmdialog import AlgorithmDialog
from ...utils import loadUi

logger = logging.getLogger(__name__)


class SpectralLibraryWidget(QWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(object)
    sigMapCenterRequested = pyqtSignal(object)
    sigCurrentProfilesChanged = pyqtSignal(list)
    sigOpenAttributeTableRequest = pyqtSignal(str)
    sigOpenLayerPropertiesRequest = pyqtSignal(str)
    sigWindowIsClosing = pyqtSignal()

    def __init__(self, *args,
                 project: Optional[QgsProject] = None,
                 # plot_model: Optional[SpectralProfilePlotModel] = None,
                 profile_fields_check: Optional[str] = 'first_feature',
                 default_style: Optional[PlotStyle] = None,
                 default_candidate_style: Optional[PlotStyle] = None,
                 speclib: Optional[QgsVectorLayer] = None,
                 **kwds):

        super().__init__(*args, **kwds)

        ui_path = Path(__file__).parents[1] / "ui/spectrallibrarywidget.ui"
        loadUi(ui_path, self)

        if project is None:
            project = QgsProject.instance()
        assert isinstance(self.mSpeclibPlotWidget, SpectralLibraryPlotWidget)
        self.setProject(project)
        # self.mSpeclibPlotWidget.plotModel().setProject(project)
        model = self.plotModel()
        model.sigProfileCandidatesChanged.connect(self.updateActions)
        self.mSpeclibPlotWidget.sigTreeSelectionChanged.connect(self.updateActions)

        if default_style:
            self.mSpeclibPlotWidget.plotModel().setDefaultProfileStyle(default_style)

        if default_candidate_style:
            self.mSpeclibPlotWidget.plotModel().setDefaultProfileCandidateStyle(default_candidate_style)

        # self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mSpeclibPlotWidget.sigDragEnterEvent.connect(self.dragEnterEvent)
        self.mSpeclibPlotWidget.sigDropEvent.connect(self.dropEvent)
        # model = self.plotModel()

        if isinstance(speclib, QgsVectorLayer):

            if profile_fields_check:
                SpectralLibraryUtils.activateProfileFields(speclib, check=profile_fields_check)

            self.project().addMapLayer(speclib)
            self.mSpeclibPlotWidget.createProfileVisualization(layer_id=speclib)
        # else:
        #    self.mSpeclibPlotWidget.createProfileVisualization()

        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddCurrentProfiles.setShortcut(Qt.CTRL + Qt.Key_A)
        self.actionAddCurrentProfiles.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentProfilesToSpeclib)

        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)
        self.optionAddCurrentProfilesAutomatically.toggled.connect(
            self.plotModel().setAddProfileCandidatesAutomatically)

        self.actionRejectCurrentProfiles.setShortcut(Qt.CTRL + Qt.Key_Z)
        self.actionRejectCurrentProfiles.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.actionRejectCurrentProfiles.triggered.connect(self.rejectCurrentProfiles)

        m = QMenu()
        m.setToolTipsVisible(True)
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.actionRejectCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        m.addAction(self.actionSelectProfilesFromMap)

        self.actionGrpAddProfiles.triggered.connect(self.actionAddCurrentProfiles.trigger)
        self.actionGrpAddProfiles.setMenu(m)
        btn: QToolButton = self.toolBar.widgetForAction(self.actionGrpAddProfiles)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        m = QMenu()
        m.setToolTipsVisible(True)
        m.addAction(self.actionImportSpeclib)
        m.addAction(self.actionExtractProfiles)

        self.actionImportSpeclib.triggered.connect(self.onImportProfiles)
        self.actionExtractProfiles.triggered.connect(self.onExtractProfiles)

        self.actionGrpImportProfiles.triggered.connect(self.actionImportSpeclib.trigger)
        self.actionGrpImportProfiles.setMenu(m)
        btn: QToolButton = self.toolBar.widgetForAction(self.actionGrpImportProfiles)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.actionExportSpeclib.triggered.connect(self.onExportProfiles)
        self.actionShowProfileFields.triggered.connect(self.openProfileFieldDialog)

        m = QMenu()
        m.setToolTipsVisible(True)
        m.addAction(self.actionShowProperties)
        m.addAction(self.actionShowProfileFields)
        # m.setDefaultAction(self.actionShowProperties)
        self.actionGrpLayerProperties.triggered.connect(self.actionShowProperties.trigger)
        self.actionGrpLayerProperties.setMenu(m)
        btn: QToolButton = self.toolBar.widgetForAction(self.actionGrpLayerProperties)
        # btn.setDefaultAction(self.actionShowProperties)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        self.actionRefreshPlot.triggered.connect(self.updatePlot)

        self.actionShowProfileViewSettings.toggled.connect(self.mSpeclibPlotWidget.panelVisualization.setVisible)

        self.setAcceptDrops(True)

        self.mDelegateOpenRequests: bool = False

        self.actionShowProperties.triggered.connect(lambda *args: self.openLayerProperties())
        self.actionShowSpectralProcessingDialog.triggered.connect(lambda *args: self.openSpectralProcessingWidget())
        self.actionShowAttributeTable.triggered.connect(lambda *args: self.openAttributeTable())

        model = self.plotModel()

        model.sigOpenAttributeTableRequest.connect(self.openAttributeTable)
        model.sigOpenLayerPropertiesRequest.connect(self.openLayerProperties)
        model.sigOpenSpectralProcessingRequest.connect(self.onOpenSpectralProcessingWidget)

        self.updateActions()

    def onOpenSpectralProcessingWidget(self, lid, *args):
        self.openSpectralProcessingWidget(layer_id=lid)

    def setMainMessageBar(self, bar: QgsMessageBar):
        pass

    def setDelegateOpenRequests(self, b: bool):
        """
        Set on True to handle requests for opening an attribute table or the layer properties
        externally, using sigOpenAttributeTableRequest and sigOpenLayerPropertiesRequest
        :param b: bool
        :return:
        """
        self.mDelegateOpenRequests = b is True

    def closeEvent(self, event: QCloseEvent):
        super().closeEvent(event)
        if event.isAccepted():
            self.sigWindowIsClosing.emit()

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mSpeclibPlotWidget.setProject(project)

    def project(self) -> QgsProject:
        return self.plotModel().project()

    def tableView(self) -> QgsAttributeTableView:
        return self.mMainView.tableView()

    def _layerInstance(self, layer_id: Optional[str] = None) -> Optional[QgsVectorLayer]:
        if isinstance(layer_id, str):
            lyr = self.project().mapLayer(layer_id)
        elif isinstance(layer_id, QgsVectorLayer) and layer_id.isValid():
            lyr = layer_id
        else:
            lyr = self.currentSpeclib()
            if lyr is None:
                logging.debug('no currentSpeclib()')

        if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
            return lyr
        return None

    def openAttributeTable(self, layer_id: Optional[str] = None):
        """
        Opens an AttributeTableWidged for the given or current layer.
        :param layer_id:
        :return:
        """
        if lyr := self._layerInstance(layer_id=layer_id):
            if self.mDelegateOpenRequests:
                self.sigOpenAttributeTableRequest.emit(lyr.id())
            else:
                w = AttributeTableWidget(lyr, parent=self)
                w.show()

    def openLayerProperties(self, layer_id: Optional[str] = None):
        """"
        Opens a layer properties dialog
        """
        if lyr := self._layerInstance(layer_id=layer_id):
            if self.mDelegateOpenRequests:
                self.sigOpenLayerPropertiesRequest.emit(lyr.id())
            else:
                showLayerPropertiesDialog(lyr, None, parent=self)

    def openProfileFieldDialog(self, layer_id: Optional[str] = None):
        """
        Opens a profile field dialog.
        :param layer_id:
        :return:
        """
        if lyr := self._layerInstance(layer_id=layer_id):
            d = SpectralProfileFieldActivatorDialog()
            d.setLayer(lyr)
            d.exec_()

    def libraryPlotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mSpeclibPlotWidget

    def profilePlotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget()

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        return self.plotModel().spectralLibraries()

    def plotModel(self) -> SpectralProfilePlotModel:
        return self.mSpeclibPlotWidget.plotModel()

    def plotControl(self) -> SpectralProfilePlotModel:
        warnings.warn(DeprecationWarning('Use .plotModel()'))
        return self.plotModel()

    def plotItem(self) -> SpectralProfilePlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.profilePlotWidget().plotItem1

    def readXml(self, parent: QDomElement, context: QgsReadWriteContext) -> bool:
        """
        Reads the visualization settings and tries to restore them on the given spectral library instance.
        This method cannot restore the QgsVectorLayer instance that has been associated with this widget.
        Use SpectralLibraryWidget.fromXml(...) instead
        """
        if not parent.tagName() == 'SpectralLibraryWidget':
            parent = parent.firstChildElement('SpectralLibraryWidget').toElement()

        if parent.isNull():
            return False
        nSLW: QDomElement = parent
        nS: QDomElement = nSLW.firstChildElement('source')
        nSL: QDomElement = nSLW.firstChildElement('maplayer')
        nVIS: QDomElement = nSLW.firstChildElement('Visualizations')

        if not nVIS.isNull():
            self.plotModel().readXml(nVIS, context)
        return True
        s = ""

    def updateActions(self):
        """
        Updates action appearance according to internal states
        :return:
        :rtype:
        """
        self.actionAddCurrentProfiles.setEnabled(self.plotModel().hasProfileCandidates())

        b = self.plotModel().hasProfileCandidates()
        self.actionAddCurrentProfiles.setEnabled(b)
        self.actionRejectCurrentProfiles.setEnabled(b)
        # self.actionGrpAddProfiles.setEnabled(b)

        b = self.mSpeclibPlotWidget.panelVisualization.isVisible()
        self.actionShowProfileViewSettings.setChecked(b)
        speclib = self.currentSpeclib()
        b = isinstance(speclib, QgsVectorLayer)
        self.actionShowAttributeTable.setEnabled(b)
        self.actionShowSpectralProcessingDialog.setEnabled(b)
        self.actionExportSpeclib.setEnabled(b)
        self.actionGrpLayerProperties.setEnabled(b)
        # self.actionShowProfileFields.setEnabled(b)
        # self.actionShowProperties.setEnabled(b)

    def updatePlot(self):
        """
        Calls an update of the plot
        """
        self.plotModel().updatePlot()

    def currentSpeclib(self) -> Optional[QgsVectorLayer]:
        """
        Returns the spectral library instance that is currently used / selected in the tree model
        """
        return self.mSpeclibPlotWidget.currentSpeclib()

    def speclib(self) -> Optional[QgsVectorLayer]:
        warnings.warn(DeprecationWarning('Use .speclib()'), stacklevel=2)
        return self.currentSpeclib()

    def sourceLayers(self) -> List[QgsVectorLayer]:
        return self.plotModel().sourceLayers()

    def addSpeclib(self, speclib: QgsVectorLayer) -> Optional[ProfileVisualizationGroup]:
        """
        Create a new visualization for the provided spectral library
        :param speclib: QgsVectorLayer
        :param askforNewFields: bool, if True and speclib to add contains other fields, a dialog will be shown
                that asks to add them first
        """
        if not is_spectral_library(speclib):
            return None
        return self.spectralLibraryPlotWidget().createProfileVisualization(layer_id=speclib)

    def openSpectralProcessingWidget(self,
                                     layer_id: Optional[str] = None,
                                     algorithmId: Optional[str] = None,
                                     parameters: Optional[dict] = None):
        # alg_key = 'qps/processing/last_alg_id'
        # reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        # if not isinstance(self.mSpectralProcessingWidget, SpectralProcessingDialog):

        if lyr := self._layerInstance(layer_id=layer_id):
            if not lyr.isEditable():
                lyr.startEditing()

            profile_fields_before = profile_field_names(lyr)
            dialog = SpectralProcessingDialog(
                speclib=lyr,
                algorithmId=algorithmId,
                parameters=parameters)
            # dialog.setMainMessageBar(self.mainMessageBar())
            # dialog.sigOutputsCreated.connect(self.onSpectralProcessingOutputsCreated)
            dialog.exec_()

            dialog.close()

    def onSpectralProcessingOutputsCreated(self, outputs: Dict):

        created_files = []
        for name, (oDef, oValue) in outputs.items():
            if isinstance(oDef, QgsProcessingOutputFile):
                created_files.append(oValue)

        if len(created_files) > 0:
            self.sigFilesCreated.emit(created_files)

    def createProfileVisualization(self, layer, field=None):

        vis = self.mSpeclibPlotWidget.createProfileVisualization(layer_id=layer, field_name=field)
        # m = self.plotModel()
        # vis = ProfileVisualizationGroup()
        # vis.setProject(self.project())
        # vis.setLayerField(layer, field)
        # vis.setPlotStyle(m.defaultProfileStyle())
        # vis.setCandidatePlotStyle(m.defaultProfileCandidateStyle())
        # m.insertPropertyGroup(-1, vis)
        #
        # idx = m.indexFromItem(vis)
        #
        # self

    def addCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def addCurrentProfilesToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """
        self.plotModel().confirmProfileCandidates()

    def rejectCurrentProfiles(self):
        self.plotModel().clearProfileCandidates()

    def spectralLibraryPlotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mSpeclibPlotWidget

    def setCurrentProfiles(self,
                           currentProfiles: Dict[str, List[QgsFeature]],
                           make_permanent: bool = None,
                           currentProfileStyles: Dict[Tuple[int, str], PlotStyle] = None,
                           ):
        """
        Sets temporary profiles for the spectral library.
        If not made permanent, they will be removed when adding the next set of temporary profiles
        :param make_permanent: bool, if not note, overwrite the value returned by optionAddCurrentProfilesAutomatically
        :type make_permanent:
        :param currentProfiles:
        :return:
        """
        warnings.warn(
            DeprecationWarning('Will be removed. use .plotModel().addProfileCandidates(...) instead'), stacklevel=2)
        if isinstance(currentProfiles, Generator):
            currentProfiles = list(currentProfiles)
        if isinstance(currentProfiles, list):
            currentProfiles = {self.speclib().id(): currentProfiles}
        assert isinstance(currentProfiles, dict)

        plotModel: SpectralProfilePlotModel = self.plotModel()
        plotModel.addProfileCandidates(currentProfiles)

        self.updateActions()
        # self.speclib().triggerRepaint()

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mMapCanvas

    def dropEvent(self, event: QDropEvent):

        if not isinstance(self.speclib(), QgsVectorLayer):
            return

        slNew = SpectralLibraryUtils.readFromMimeData(event.mimeData())

        if is_spectral_library(slNew) and slNew not in self.spectralLibraries():
            self.addSpeclib(slNew)
            event.acceptProposedAction()

    def dragEnterEvent(self, event: QDragEnterEvent):

        if event.proposedAction() == Qt.CopyAction and SpectralLibraryUtils.canReadFromMimeData(event.mimeData()):
            event.acceptProposedAction()

    def onExtractProfiles(self):
        """
        Reads profiles for vector geometry positions from a raster images
        :return:
        """
        context = QgsProcessingContext()
        context.setProject(self.project())

        feedback = QgsProcessingFeedback()
        context.setFeedback(feedback)

        results = {}

        def onFinished(ok, res):
            assert ok
            results.update(res)

        alg = ExtractSpectralProfiles()
        alg.initAlgorithm({})
        d = AlgorithmDialog(alg, context=context)
        d.algorithmFinished.connect(onFinished)
        d.exec_()

        lyr = results.get(ExtractSpectralProfiles.P_OUTPUT, None)
        if isinstance(lyr, (QgsVectorLayer, str)):
            self.project().addMapLayer(lyr)
            self.libraryPlotWidget().createProfileVisualization(layer_id=lyr)
            # self.addSpeclib(results['output'], askforNewFields=True)

    def onImportProfiles(self):
        """
        Imports a SpectralLibrary
        """

        context = QgsProcessingContext()
        context.setProject(self.project())

        feedback = QgsProcessingFeedback()
        context.setFeedback(feedback)

        results = {}

        def onFinished(ok, res):
            assert ok
            results.update(res)

        alg = ImportSpectralProfiles()
        alg.initAlgorithm({})
        d = AlgorithmDialog(alg, context=context)
        d.algorithmFinished.connect(onFinished)
        d.exec_()

        lyr = results.get(ImportSpectralProfiles.P_OUTPUT, None)
        if isinstance(lyr, (QgsVectorLayer, str)):
            self.libraryPlotWidget().createProfileVisualization(layer_id=lyr)
            # self.addSpeclib(results['output'], askforNewFields=True)

        # sl = self.currentSpeclib()
        # if isinstance(sl, QgsVectorLayer):
        #     with edit(sl):
        #         n_p = sl.featureCount()
        #         has_vis = False
        #         for vis in self.spectralLibraryPlotWidget().profileVisualizations():
        #             if vis.layerId() == sl.id():
        #                 has_vis = True
        #                 break
        #         SpectralLibraryImportDialog.importProfiles(sl, parent=self)
        #
        #         # add a new visualization if no one exists
        #         if not has_vis and sl.featureCount() > 0:
        #             self.spectralLibraryPlotWidget().createProfileVisualization(layer_id=sl)
        #
        #     # update plot
        #     self.plotModel().updatePlot()

    # def onImportFromRasterSource(self):
    #    from ..io.rastersources import SpectralProfileImportPointsDialog
    #    d = SpectralProfileImportPointsDialog(parent=self)
    #    d.setWkbType(self.spectralLibrary().wkbType())
    #    d.finished.connect(lambda *args, d0=d: self.onIODialogFinished(d0))
    #    d.show()
    #    self.mIODialogs.append(d)

    def addProfiles(self, profiles, add_missing_fields: bool = False):
        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            stopEditing = sl.startEditing()

            sl.beginEditCommand('Add {} profiles'.format(len(profiles)))
            SpectralLibraryUtils.addProfiles(sl, profiles, addMissingFields=add_missing_fields)
            sl.endEditCommand()
            sl.commitChanges(stopEditing=stopEditing)

    def onExportProfiles(self, *args):

        speclib = self.currentSpeclib()
        if isinstance(speclib, QgsVectorLayer):

            context = QgsProcessingContext()
            context.setProject(self.project())

            feedback = QgsProcessingFeedback()
            context.setFeedback(feedback)

            results = dict()

            def onFinished(ok, res):
                assert ok
                results.update(res)

            alg = ExportSpectralProfiles()
            alg.initAlgorithm({})
            d = AlgorithmDialog(alg, context=context)
            d.algorithmFinished.connect(onFinished)
            d.exec_()

            files = results.get(ExportSpectralProfiles.P_OUTPUT, [])
            if len(files) > 0:
                self.sigFilesCreated.emit(files)

            # files = SpectralLibraryExportDialog.exportProfiles(speclib=speclib, parent=self)
            # if len(files) > 0:
            #    self.sigFilesCreated.emit(files)
