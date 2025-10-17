import logging
import sys
import warnings
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set, Tuple

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QCloseEvent
from qgis.PyQt.QtGui import QDragEnterEvent, QDropEvent
from qgis.PyQt.QtWidgets import QDialog, QMenu, QWidget
from qgis.PyQt.QtWidgets import QToolButton
from qgis.PyQt.QtXml import QDomElement
from qgis.core import (QgsFeature, QgsProcessingOutputFile, QgsProject, QgsReadWriteContext,
                       QgsVectorLayer)
from qgis.core import QgsProcessingContext, QgsProcessingFeedback
from qgis.gui import QgsActionMenu, QgsAttributeTableView, QgsDockWidget, QgsMapCanvas
from .spectrallibraryplotitems import SpectralProfilePlotItem, SpectralProfilePlotWidget
from .spectrallibraryplotwidget import SpectralLibraryPlotWidget
from .spectralprocessingdialog import SpectralProcessingDialog
from .spectralprofilefieldmodel import SpectralProfileFieldActivatorDialog
from .spectralprofileplotmodel import SpectralProfilePlotModel
from ..core import is_spectral_library, profile_field_names
from ..core.spectrallibrary import SpectralLibraryUtils
from ..processing.exportspectralprofiles import ExportSpectralProfiles
from ..processing.importspectralprofiles import ImportSpectralProfiles
from ...layerproperties import CopyAttributesDialog, showLayerPropertiesDialog
from ...plotstyling.plotstyling import PlotStyle
from ...processing.algorithmdialog import AlgorithmDialog
from ...utils import loadUi

logger = logging.getLogger(__name__)


class SpectralLibraryWidget(QgsDockWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(object)
    sigMapCenterRequested = pyqtSignal(object)
    sigCurrentProfilesChanged = pyqtSignal(list)
    sigOpenAttributeTableRequest = pyqtSignal(str)
    sigWindowIsClosing = pyqtSignal()

    def __init__(self, *args,
                 project: Optional[QgsProject] = None,
                 # plot_model: Optional[SpectralProfilePlotModel] = None,
                 profile_fields_check: Optional[str] = 'first_feature',
                 default_style: Optional[PlotStyle] = None,
                 speclib: Optional[QgsVectorLayer] = None,
                 **kwds):

        super(SpectralLibraryWidget, self).__init__(*args, **kwds)

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

        # if isinstance(plot_model, SpectralProfilePlotModel):
        #     for vis in plot_model.visualizations():
        #         speclib = vis.layer()
        #         assert isinstance(speclib, QgsVectorLayer) and speclib.isValid()
        #         break
        # else:
        #     plot_model = SpectralProfilePlotModel()
        #     if isinstance(project, QgsProject):
        #         plot_model.setProject(project)
        #
        #     if not isinstance(speclib, QgsVectorLayer):
        #         speclib = SpectralLibraryUtils.createSpectralLibrary()
        #         plot_model.project().addMapLayer(speclib)
        #
        #     if profile_fields_check:
        #         SpectralLibraryUtils.activateProfileFields(speclib, check=profile_fields_check)

        # super().__init__(speclib)
        # self.setAttribute(Qt.WA_DeleteOnClose, on=True)
        # self.setWindowIcon(QIcon(':/qps/ui/icons/speclib.svg'))
        # self.mQgsStatusBar = QgsStatusBar()
        # self.mQgsStatusBar
        # self.mQgsStatusBar.setParentStatusBar(self.statusBar())
        # self.mStatusLabel: SpectralLibraryInfoLabel = SpectralLibraryInfoLabel()
        # self.mStatusLabel.setTextFormat(Qt.RichText)
        # self.mQgsStatusBar.addPermanentWidget(self.mStatusLabel, 1, QgsStatusBar.AnchorLeft)
        # self.mQgsStatusBar.setVisible(False)
        # self.mSpectralProcessingWidget: SpectralProcessingDialog = None

        # to be removed
        # self.mLayer = speclib

        # self.mToolbar: QToolBar
        # self.mIODialogs: List[QWidget] = list()

        # self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        # self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        # self.mSpeclibPlotWidget: SpectralLibraryPlotWidget = SpectralLibraryPlotWidget(plot_model=plot_model)
        # self.mSpeclibPlotWidget: SpectralLibraryPlotWidget

        s = ""
        if default_style:
            self.mSpeclibPlotWidget.plotModel().setDefaultProfileStyle(default_style)

        # self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mSpeclibPlotWidget.sigDragEnterEvent.connect(self.dragEnterEvent)
        self.mSpeclibPlotWidget.sigDropEvent.connect(self.dropEvent)
        model = self.plotModel()

        if isinstance(speclib, QgsVectorLayer):

            if profile_fields_check:
                SpectralLibraryUtils.activateProfileFields(speclib, check=profile_fields_check)

            self.project().addMapLayer(speclib)
            self.mSpeclibPlotWidget.createProfileVisualization(layer_id=speclib)
        else:
            self.mSpeclibPlotWidget.createProfileVisualization()

        # vl = QVBoxLayout()
        # vl.addWidget(self.mSpeclibPlotWidget)
        # vl.setContentsMargins(0, 0, 0, 0)
        # vl.setSpacing(2)
        # self.widgetLeft.setLayout(vl)
        # self.widgetLeft.setVisible(True)
        # self.widgetRight.setVisible(False)
        #
        # self.widgetCenter.currentChanged.connect(self.updateToolbarVisibility)
        # self.mMainView.formModeChanged.connect(self.updateToolbarVisibility)

        # define Actions and Options

        # self.actionSelectProfilesFromMap = QAction(self.tr(r'Select Profiles from Map'), parent=self)
        # self.actionSelectProfilesFromMap.setToolTip(self.tr(r'Select new profile from map'))
        # self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        # self.actionAddCurrentProfiles = QAction(self.tr('Add Profiles(s)'), parent=self)
        self.actionAddCurrentProfiles.setShortcut(Qt.CTRL + Qt.SHIFT + Qt.Key_A)
        # self.actionAddCurrentProfiles.setShortcut(Qt.Key_Z)
        self.actionAddCurrentProfiles.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # self.actionAddCurrentProfiles.setToolTip(self.tr('Adds currently overlaid profiles to the spectral library'))
        # self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentProfilesToSpeclib)

        # self.optionAddCurrentProfilesAutomatically = QAction(self.tr('Add profiles automatically'), parent=self)
        # self.optionAddCurrentProfilesAutomatically.setToolTip(self.tr(
        #    'Activate to add profiles automatically into the spectral library'))
        # self.optionAddCurrentProfilesAutomatically.setIcon(QIcon(':/qps/ui/icons/profile_add_auto.svg'))
        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)
        self.optionAddCurrentProfilesAutomatically.toggled.connect(
            self.plotModel().setAddProfileCandidatesAutomatically)

        m = QMenu()
        m.setToolTipsVisible(True)
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        m.addAction(self.actionSelectProfilesFromMap)
        # m.setDefaultAction(self.actionAddCurrentProfiles)

        # self.actionAddProfiles = QAction(self.actionAddCurrentProfiles.text(), self)
        # self.actionAddProfiles.setToolTip(self.actionAddCurrentProfiles.text())
        # self.actionAddProfiles.setIcon(self.actionAddCurrentProfiles.icon())
        # self.actionAddProfiles.triggered.connect(self.actionAddCurrentProfiles.trigger)
        # self.actionAddCurrentProfiles.setMenu(m)

        self.actionGrpAddProfiles.triggered.connect(self.actionAddCurrentProfiles.trigger)
        self.actionGrpAddProfiles.setMenu(m)
        btn: QToolButton = self.toolBar.widgetForAction(self.actionGrpAddProfiles)
        # btn.setDefaultAction(self.actionShowProperties)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        # self.actionImportSpeclib = QAction(self.tr('Import Spectral Profiles'), parent=self)
        # self.actionImportSpeclib.setToolTip(self.tr('Import spectral profiles from other data sources'))
        # self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        self.actionImportSpeclib.triggered.connect(self.onImportProfiles)

        # self.actionExportSpeclib = QAction(self.tr('Export Spectral Profiles'), parent=self)
        # self.actionExportSpeclib.setToolTip(self.tr('Export spectral profiles to other data formats'))
        # self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))
        self.actionExportSpeclib.triggered.connect(self.onExportProfiles)

        # self.actionShowProperties = QAction(self.tr('Speclib Layer Properties'), parent=self)
        # self.actionShowProperties.setToolTip(self.tr('Show the vector layer properties of the spectral library'))
        # self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        # self.actionShowProfileFields = QAction(self.tr('Show Spectral Profile Fields'), parent=self)
        # self.actionShowProfileFields.setToolTip(self.tr('Define which fields can contain spectral profiles'))
        # self.actionShowProfileFields.setIcon(QIcon(':/qps/ui/icons/profile_fields.svg'))
        self.actionShowProfileFields.triggered.connect(self.showProfileFields)

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
        # self.actionLayerSettings = QAction(self.actionShowProperties.text(), self)
        # self.actionLayerSettings.setToolTip(self.actionShowProperties.text())
        # self.actionLayerSettings.setIcon(self.actionShowProperties.icon())
        # self.actionLayerSettings.triggered.connect(self.actionShowProperties.trigger)
        # self.actionLayerSettings.setMenu(m)

        # self.tbSpeclibAction = QToolBar(self.tr('Spectral Library'))
        # self.tbSpeclibAction.setObjectName('SpectralLibraryToolbar')
        # self.tbSpeclibAction.setFloatable(False)
        # self.tbSpeclibAction.setMovable(False)
        # # self.tbSpeclibAction.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        # self.tbSpeclibAction.addAction(self.actionAddProfiles)
        # self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        # self.tbSpeclibAction.addAction(self.actionExportSpeclib)
        # self.tbSpeclibAction.addAction(self.actionLayerSettings)

        # self.tbSpeclibAction.addSeparator()
        # self.cbXAxisUnit = self.mSpeclibPlotWidget.optionXUnit.createUnitComboBox()
        # self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        # self.tbSpeclibAction.addAction(self.mSpeclibPlotWidget.optionColorsFromFeatureRenderer)

        # self.actionShowSpectralProcessingDialog = QAction(self.tr('Spectral Processing'))
        # self.actionShowSpectralProcessingDialog.setParent(self)
        # self.actionShowSpectralProcessingDialog.setCheckable(False)
        # self.actionShowSpectralProcessingDialog.setIcon(QIcon(':/qps/ui/icons/profile_processing.svg'))
        self.actionShowSpectralProcessingDialog.triggered.connect(self.showSpectralProcessingWidget)
        # self.mToolbar.insertAction(self.mActionOpenFieldCalculator, self.actionShowSpectralProcessingDialog)
        # self.actionShowSpectralProcessingDialog.setEnabled(self.speclib().isEditable())

        # self.actionShowProfileView = QAction(self.tr('Show Profile Plot'), parent=self)
        # self.actionShowProfileView.setCheckable(True)
        # self.actionShowProfileView.setChecked(True)
        # self.actionShowProfileView.setIcon(QIcon(self.mSpeclibPlotWidget.windowIcon()))
        # self.actionShowProfileView.toggled.connect(self.onChangeViewVisibility)

        # self.optionShowVisualizationSettings.toggled.connect(self.panelVisualization.setVisible)
        # self.actionShowProfileViewSettings = self.mSpeclibPlotWidget.optionShowVisualizationSettings

        self.actionShowProfileViewSettings.toggled.connect(self.mSpeclibPlotWidget.panelVisualization.setVisible)

        # show Attribute Table / Form View buttons in menu bar only
        # self.mAttributeViewButton.setVisible(False)
        # self.mTableViewButton.setVisible(False)

        # self.actionShowFormView = QAction(self.tr('Show Form View'), parent=self)
        # self.actionShowFormView.setCheckable(True)
        # self.actionShowFormView.setIcon(QIcon(':/images/themes/default/mActionFormView.svg'))
        # self.actionShowFormView.toggled.connect(self.onChangeViewVisibility)

        # self.actionShowAttributeTable = QAction(self.tr('Show Attribute Table'), parent=self)
        # self.actionShowAttributeTable.setCheckable(True)
        # self.actionShowAttributeTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        # self.actionShowAttributeTable.toggled.connect(self.onChangeViewVisibility)

        # self.mMainViewButtonGroup.buttonClicked.connect(self.updateToolbarVisibility)

        # r = self.tbSpeclibAction.addSeparator()
        # self.tbSpeclibAction.addAction(self.actionShowProfileView)
        # self.tbSpeclibAction.addAction(self.actionShowProfileViewSettings)
        # self.tbSpeclibAction.addSeparator()
        # self.tbSpeclibAction.addAction(self.actionShowFormView)
        # self.tbSpeclibAction.addAction(self.actionShowAttributeTable)
        #
        # self.mActionSaveEdits.triggered.connect(self._onSaveEdits)

        # self.insertToolBar(self.mToolbar, self.tbSpeclibAction)
        # self.updateToolbarVisibility()
        # self.updateActions()

        # QIcon(':/images/themes/default/mActionMultiEdit.svg').pixmap(20,20).isNull()
        self.setAcceptDrops(True)

        # show attribute table by default
        # self.setViewVisibility(SpectralLibraryWidget.ViewType.Standard)

        # # try to give the plot widget most space
        # self.splitter.setStretchFactor(0, 4)
        # self.splitter.setStretchFactor(1, 1)
        # self.splitter.setStretchFactor(2, 0)
        # self.splitter.setSizes([200, 10, 0])

        def onShowAttributeTable(layer_id: str):
            lyr = self.currentSpeclib()
            # call to open an external attribute table
            if isinstance(lyr, QgsVectorLayer):
                self.sigOpenAttributeTableRequest.emit(lyr.id())

        self.plotModel().sigOpenAttributeTableRequest.connect(onShowAttributeTable)

        self.updateActions()

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

    def onShowContextMenuAttributeEditor(self, menu: QgsActionMenu, fid):
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def showProperties(self, *args):
        lyr = self.currentSpeclib()
        if isinstance(lyr, QgsVectorLayer):
            showLayerPropertiesDialog(lyr, None, parent=self)
        else:
            logging.debug('no currentSpeclib() to open with showLayerPropertiesDialog')

    def showProfileFields(self, **args):

        lyr = self.currentSpeclib()
        if isinstance(lyr, QgsVectorLayer):
            d = SpectralProfileFieldActivatorDialog()
            d.setLayer(lyr)
            d.exec_()
        else:
            logging.debug('no currentSpeclib() to open with SpectralProfileFieldActivatorDialog')

    def libraryPlotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mSpeclibPlotWidget

    def profilePlotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget()

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        return self.plotModel().spectralLibraries()

    def plotModel(self) -> SpectralProfilePlotModel:
        return self.mSpeclibPlotWidget.mPlotModel

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
        This method can not restore the QgsVectorLayer instance that has been associated with this widget.
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
        self.actionAddCurrentProfiles.setEnabled(len(self.plotModel().mPROFILE_CANDIDATES) > 0)

        b = self.plotModel().hasProfileCandidates()
        self.actionAddCurrentProfiles.setEnabled(b)
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

    # def spectralLibrary(self) -> QgsVectorLayer:
    #    return self.speclib()

    def addSpeclib(self, speclib: QgsVectorLayer, askforNewFields: bool = False):
        """
        :param speclib: QgsVectorLayer
        :param askforNewFields: bool, if True and speclib to add contains other fields, a dialog will be shown
                that asks to add them first
        """
        assert is_spectral_library(speclib)
        speclib_dst = self.speclib()
        wasEditable = speclib_dst.isEditable()

        if askforNewFields:
            dst_fields = speclib_dst.fields().names()
            missing = [f for f in speclib.fields() if f.name() not in dst_fields]
            if len(missing) > 0:
                CopyAttributesDialog.copyLayerFields(speclib_dst, speclib, parent=self)

        try:
            speclib_dst.startEditing()
            info = 'Add {} profiles from {} ...'.format(len(speclib), speclib.name())
            speclib_dst.beginEditCommand(info)
            SpectralLibraryUtils.addSpeclib(speclib_dst, speclib, addMissingFields=False)
            speclib_dst.endEditCommand()

            if not wasEditable:
                speclib_dst.commitChanges()
                s = ""
            # self.plotControl().updatePlot()

        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

    def showSpectralProcessingWidget(self,
                                     algorithmId: Optional[str] = None,
                                     parameters: Optional[dict] = None):
        # alg_key = 'qps/processing/last_alg_id'
        # reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
        # if not isinstance(self.mSpectralProcessingWidget, SpectralProcessingDialog):

        sl = self.currentSpeclib()
        if isinstance(sl, QgsVectorLayer):
            if not sl.isEditable():
                sl.startEditing()

            profile_fields_before = profile_field_names(sl)
            dialog = SpectralProcessingDialog(
                speclib=sl,
                algorithmId=algorithmId,
                parameters=parameters)
            # dialog.setMainMessageBar(self.mainMessageBar())
            # dialog.sigOutputsCreated.connect(self.onSpectralProcessingOutputsCreated)
            dialog.exec_()

            dialog.close()

            profile_fields_after = profile_field_names(sl)

    def onSpectralProcessingOutputsCreated(self, outputs: Dict):

        created_files = []
        for name, (oDef, oValue) in outputs.items():
            if isinstance(oDef, QgsProcessingOutputFile):
                created_files.append(oValue)

        if len(created_files) > 0:
            self.sigFilesCreated.emit(created_files)

    def addCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def addCurrentProfilesToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """
        self.plotModel().confirmProfileCandidates()

    def temporaryProfileIDs(self) -> Set[int]:
        return self.plotModel().profileCandidates().count()
        # return self.plotControl().mTemporaryProfileIDs

    def deleteCurrentProfilesFromSpeclib(self, *args):
        # delete previous current profiles
        speclib = self.speclib()
        if is_spectral_library(speclib):
            oldCurrentIDs = list(self.plotModel().profileCandidates().candidateFeatureIds())
            restart_editing: bool = not speclib.startEditing()
            speclib.beginEditCommand('Remove temporary')
            speclib.deleteFeatures(oldCurrentIDs)
            speclib.endEditCommand()

            if restart_editing:
                speclib.startEditing()

        self.updateActions()

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

        if isinstance(slNew, QgsVectorLayer) and slNew.featureCount() > 0:
            self.addSpeclib(slNew, askforNewFields=True)
            event.acceptProposedAction()

    def dragEnterEvent(self, event: QDragEnterEvent):

        if event.proposedAction() == Qt.CopyAction and SpectralLibraryUtils.canReadFromMimeData(event.mimeData()):
            event.acceptProposedAction()

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

    def onIODialogFinished(self, w: QWidget):
        from ..io.rastersources import SpectralProfileImportPointsDialog
        if isinstance(w, SpectralProfileImportPointsDialog):
            if w.result() == QDialog.Accepted:
                profiles = w.profiles()
                info = w.rasterSource().name()
                self.addProfiles(profiles, add_missing_fields=w.allAttributes())
            else:
                s = ""

        if w in self.mIODialogs:
            self.mIODialogs.remove(w)
        w.close()

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
