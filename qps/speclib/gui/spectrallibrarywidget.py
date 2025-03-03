import enum
import sys

import warnings
from typing import List, Set, Dict, Tuple, Generator, Any, Callable, Optional
from qgis.PyQt.QtXml import QDomElement, QDomDocument
from qgis.PyQt.QtCore import pyqtSignal, Qt, QModelIndex
from qgis.PyQt.QtGui import QIcon, QDragEnterEvent, QDropEvent, QColor
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QAction, QMenu, QToolBar, QWidgetAction, QPushButton, \
    QHBoxLayout, QFrame, QDialog
from qgis.core import (QgsFeature, QgsProject, QgsVectorLayer, QgsReadWriteContext,
                       QgsMapLayer, QgsProcessingOutputFile)
from qgis.gui import QgsMapCanvas, QgsDualView, QgsAttributeTableView, QgsDockWidget, \
    QgsActionMenu
from .spectrallibraryplotitems import SpectralProfilePlotItem, SpectralProfilePlotWidget
from .spectrallibraryplotwidget import SpectralLibraryPlotWidget, \
    SpectralProfilePlotModel
from .spectralprocessingdialog import SpectralProcessingDialog
from .spectralprofilefieldmodel import SpectralProfileFieldActivatorDialog
from ..core import is_spectral_library, profile_fields
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectrallibraryio import SpectralLibraryImportDialog, SpectralLibraryExportDialog
from ...layerproperties import AttributeTableWidget, showLayerPropertiesDialog, CopyAttributesDialog
from ...plotstyling.plotstyling import PlotStyle, PlotStyleWidget
from ...utils import nextColor  # , nodeXmlString


class SpectralLibraryWidget(AttributeTableWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(object)
    sigMapCenterRequested = pyqtSignal(object)
    sigCurrentProfilesChanged = pyqtSignal(list)

    class ViewType(enum.Flag):
        Empty = enum.auto()
        ProfileView = enum.auto()
        ProfileViewSettings = enum.auto()
        AttributeTable = enum.auto()
        FormView = enum.auto()
        Standard = ProfileView | AttributeTable

    def __init__(self, *args,
                 speclib: QgsVectorLayer = None,
                 mapCanvas: QgsMapCanvas = None,
                 profile_fields_check: str = 'first_feature',
                 postInitHooks: Dict[str, Callable] = None,
                 **kwds):

        if not isinstance(speclib, QgsVectorLayer):
            speclib = SpectralLibraryUtils.createSpectralLibrary()

        super().__init__(speclib)
        # self.setAttribute(Qt.WA_DeleteOnClose, on=True)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib.svg'))
        # self.mQgsStatusBar = QgsStatusBar()
        # self.mQgsStatusBar
        # self.mQgsStatusBar.setParentStatusBar(self.statusBar())
        # self.mStatusLabel: SpectralLibraryInfoLabel = SpectralLibraryInfoLabel()
        # self.mStatusLabel.setTextFormat(Qt.RichText)
        # self.mQgsStatusBar.addPermanentWidget(self.mStatusLabel, 1, QgsStatusBar.AnchorLeft)
        # self.mQgsStatusBar.setVisible(False)
        self.mProject = QgsProject.instance()
        # self.mSpectralProcessingWidget: SpectralProcessingDialog = None

        self.mToolbar: QToolBar
        self.mIODialogs: List[QWidget] = list()

        self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        self.mSpeclibPlotWidget: SpectralLibraryPlotWidget = SpectralLibraryPlotWidget()

        assert isinstance(self.mSpeclibPlotWidget, SpectralLibraryPlotWidget)
        self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mSpeclibPlotWidget.sigDragEnterEvent.connect(self.dragEnterEvent)
        self.mSpeclibPlotWidget.sigDropEvent.connect(self.dropEvent)

        vl = QVBoxLayout()
        vl.addWidget(self.mSpeclibPlotWidget)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)
        self.widgetLeft.setLayout(vl)
        self.widgetLeft.setVisible(True)
        self.widgetRight.setVisible(False)

        self.widgetCenter.currentChanged.connect(self.updateToolbarVisibility)
        self.mMainView.formModeChanged.connect(self.updateToolbarVisibility)

        # define Actions and Options

        self.actionSelectProfilesFromMap = QAction(self.tr(r'Select Profiles from Map'), parent=self)
        self.actionSelectProfilesFromMap.setToolTip(self.tr(r'Select new profile from map'))
        self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddCurrentProfiles = QAction(self.tr('Add Profiles(s)'), parent=self)
        self.actionAddCurrentProfiles.setShortcut(Qt.CTRL + Qt.SHIFT + Qt.Key_A)
        # self.actionAddCurrentProfiles.setShortcut(Qt.Key_Z)

        self.actionAddCurrentProfiles.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.actionAddCurrentProfiles.setToolTip(self.tr('Adds currently overlaid profiles to the spectral library'))
        self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentProfilesToSpeclib)

        self.optionAddCurrentProfilesAutomatically = QAction(self.tr('Add profiles automatically'), parent=self)
        self.optionAddCurrentProfilesAutomatically.setToolTip(self.tr(
            'Activate to add profiles automatically into the spectral library'))
        self.optionAddCurrentProfilesAutomatically.setIcon(QIcon(':/qps/ui/icons/profile_add_auto.svg'))
        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)

        m = QMenu()
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        m.setDefaultAction(self.actionAddCurrentProfiles)

        self.actionAddProfiles = QAction(self.actionAddCurrentProfiles.text(), self)
        self.actionAddProfiles.setToolTip(self.actionAddCurrentProfiles.text())
        self.actionAddProfiles.setIcon(self.actionAddCurrentProfiles.icon())
        self.actionAddProfiles.triggered.connect(self.actionAddCurrentProfiles.trigger)
        self.actionAddProfiles.setMenu(m)

        self.actionImportSpeclib = QAction(self.tr('Import Spectral Profiles'), parent=self)
        self.actionImportSpeclib.setToolTip(self.tr('Import spectral profiles from other data sources'))
        self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        self.actionImportSpeclib.triggered.connect(self.onImportProfiles)

        self.actionExportSpeclib = QAction(self.tr('Export Spectral Profiles'), parent=self)
        self.actionExportSpeclib.setToolTip(self.tr('Export spectral profiles to other data formats'))
        self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))
        self.actionExportSpeclib.triggered.connect(self.onExportProfiles)

        self.actionShowProperties = QAction(self.tr('Speclib Layer Properties'), parent=self)
        self.actionShowProperties.setToolTip(self.tr('Show the vector layer properties of the spectral library'))
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.actionShowProfileFields = QAction(self.tr('Show Spectral Profile Fields'), parent=self)
        self.actionShowProfileFields.setToolTip(self.tr('Define which fields can contain spectral profiles'))
        self.actionShowProfileFields.setIcon(QIcon(':/qps/ui/icons/profile_fields.svg'))
        self.actionShowProfileFields.triggered.connect(self.showProfileFields)

        m = QMenu()
        m.addAction(self.actionShowProperties)
        m.addAction(self.actionShowProfileFields)
        m.setDefaultAction(self.actionShowProperties)

        self.actionLayerSettings = QAction(self.actionShowProperties.text(), self)
        self.actionLayerSettings.setToolTip(self.actionShowProperties.text())
        self.actionLayerSettings.setIcon(self.actionShowProperties.icon())
        self.actionLayerSettings.triggered.connect(self.actionShowProperties.trigger)
        self.actionLayerSettings.setMenu(m)

        self.tbSpeclibAction = QToolBar(self.tr('Spectral Library'))
        self.tbSpeclibAction.setObjectName('SpectralLibraryToolbar')
        self.tbSpeclibAction.setFloatable(False)
        self.tbSpeclibAction.setMovable(False)
        # self.tbSpeclibAction.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        self.tbSpeclibAction.addAction(self.actionAddProfiles)
        self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        self.tbSpeclibAction.addAction(self.actionExportSpeclib)
        self.tbSpeclibAction.addAction(self.actionLayerSettings)

        # self.tbSpeclibAction.addSeparator()
        # self.cbXAxisUnit = self.mSpeclibPlotWidget.optionXUnit.createUnitComboBox()
        # self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        # self.tbSpeclibAction.addAction(self.mSpeclibPlotWidget.optionColorsFromFeatureRenderer)

        self.actionShowSpectralProcessingDialog = QAction(self.tr('Spectral Processing'))
        self.actionShowSpectralProcessingDialog.setParent(self)
        self.actionShowSpectralProcessingDialog.setCheckable(False)
        self.actionShowSpectralProcessingDialog.setIcon(QIcon(':/qps/ui/icons/profile_processing.svg'))
        self.actionShowSpectralProcessingDialog.triggered.connect(self.showSpectralProcessingWidget)
        self.mToolbar.insertAction(self.mActionOpenFieldCalculator, self.actionShowSpectralProcessingDialog)
        self.actionShowSpectralProcessingDialog.setEnabled(self.speclib().isEditable())

        self.actionShowProfileView = QAction(self.tr('Show Profile Plot'), parent=self)
        self.actionShowProfileView.setCheckable(True)
        self.actionShowProfileView.setChecked(True)
        self.actionShowProfileView.setIcon(QIcon(self.mSpeclibPlotWidget.windowIcon()))
        self.actionShowProfileView.toggled.connect(self.onChangeViewVisibility)

        self.actionShowProfileViewSettings = self.mSpeclibPlotWidget.optionShowVisualizationSettings
        self.actionShowProfileView.toggled.connect(self.actionShowProfileViewSettings.setEnabled)

        # show Attribute Table / Form View buttons in menu bar only
        self.mAttributeViewButton.setVisible(False)
        self.mTableViewButton.setVisible(False)

        self.actionShowFormView = QAction(self.tr('Show Form View'), parent=self)
        self.actionShowFormView.setCheckable(True)
        self.actionShowFormView.setIcon(QIcon(':/images/themes/default/mActionFormView.svg'))
        self.actionShowFormView.toggled.connect(self.onChangeViewVisibility)

        self.actionShowAttributeTable = QAction(self.tr('Show Attribute Table'), parent=self)
        self.actionShowAttributeTable.setCheckable(True)
        self.actionShowAttributeTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        self.actionShowAttributeTable.toggled.connect(self.onChangeViewVisibility)

        self.mMainViewButtonGroup.buttonClicked.connect(self.updateToolbarVisibility)

        r = self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowProfileView)
        self.tbSpeclibAction.addAction(self.actionShowProfileViewSettings)
        self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowFormView)
        self.tbSpeclibAction.addAction(self.actionShowAttributeTable)

        self.mActionSaveEdits.triggered.connect(self._onSaveEdits)

        self.insertToolBar(self.mToolbar, self.tbSpeclibAction)
        self.updateToolbarVisibility()
        self.updateActions()

        # QIcon(':/images/themes/default/mActionMultiEdit.svg').pixmap(20,20).isNull()
        self.setAcceptDrops(True)

        # show attribute table by default
        self.setViewVisibility(SpectralLibraryWidget.ViewType.Standard)

        # try to give the plot widget most space
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([200, 10, 0])

        self.mPostInitHooks: Dict[str, Any] = dict()

        if profile_fields_check:
            SpectralLibraryUtils.activateProfileFields(self.speclib(), check=profile_fields_check)
            self._onSaveEdits()
        self.runPostInitHooks()

        s = ""

    def runPostInitHooks(self):

        for name, func in self.mPostInitHooks.items():
            func(self)

    def _onSaveEdits(self, *args):

        # save styling information
        vl: QgsVectorLayer = self.speclib()
        styleCategories = QgsMapLayer.Symbology | QgsMapLayer.Forms
        success = vl.saveDefaultStyle(styleCategories)
        s = ""

    def setProject(self, project: QgsProject):
        assert isinstance(project, QgsProject)
        self.mProject = project
        self.mSpeclibPlotWidget.setProject(project)

    def editingToggled(self):
        super().editingToggled()
        if hasattr(self, 'actionShowSpectralProcessingDialog'):
            self.actionShowSpectralProcessingDialog.setEnabled(self.speclib().isEditable())

    def setViewVisibility(self, viewType: ViewType):
        """
        Sets the visibility of views
        :param views: list of ViewsTypes to set visible
        :type views:
        :return:
        :rtype:
        """
        assert isinstance(viewType, SpectralLibraryWidget.ViewType)

        show_profiles = SpectralLibraryWidget.ViewType.ProfileView in viewType
        show_profile_settings = SpectralLibraryWidget.ViewType.ProfileViewSettings in viewType
        self.actionShowProfileViewSettings.setChecked(show_profile_settings)

        show_dual_view = False
        dual_view_mode: QgsDualView.ViewMode = self.mMainView.view()
        if SpectralLibraryWidget.ViewType.AttributeTable in viewType:
            dual_view_mode = QgsDualView.ViewMode.AttributeTable
            show_dual_view = True
        elif SpectralLibraryWidget.ViewType.FormView in viewType:
            dual_view_mode = QgsDualView.ViewMode.AttributeEditor
            show_dual_view = True

        self.widgetLeft.setVisible(show_profiles)
        self.widgetCenter.setVisible(show_dual_view)
        self.mMainView.setView(dual_view_mode)

        # QTimer.singleShot(1000, self.updateActions)
        self.updateActions()

    def onChangeViewVisibility(self):

        sender: QAction = self.sender()
        assert isinstance(sender, QAction)

        dualview_actions = [self.actionShowAttributeTable,
                            self.actionShowFormView]

        if sender == self.actionShowProfileView:
            self.widgetLeft.setVisible(sender.isChecked())
        elif sender in dualview_actions:

            # either show attribute table or form view widget
            show_formview = sender == self.actionShowFormView and sender.isChecked()
            show_tableview = sender == self.actionShowAttributeTable and sender.isChecked()

            if not any([show_formview, show_tableview]):
                self.widgetCenter.setVisible(False)
            else:
                if show_tableview:
                    self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
                    self.mMainView.setView(QgsDualView.AttributeTable)
                elif show_formview:
                    self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
                    self.mMainView.setView(QgsDualView.AttributeEditor)

                self.widgetCenter.setVisible(True)

        self.updateToolbarVisibility()

    def updateToolbarVisibility(self, *args):

        self.mToolbar.setVisible(self.pageAttributeTable.isVisibleTo(self))
        self.updateActions()

    def tableView(self) -> QgsAttributeTableView:
        return self.mMainView.tableView()

    def onShowContextMenuAttributeEditor(self, menu: QgsActionMenu, fid):
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def onWillShowContextMenuAttributeTable(self, menu: QMenu, atIndex: QModelIndex):
        """
        Create the QMenu for the AttributeTable
        :param menu:
        :param atIndex:
        :return:
        """
        super().onWillShowContextMenuAttributeTable(menu, atIndex)
        menu.addSeparator()
        self.addProfileStyleMenu(menu)

    def addProfileStyleMenu(self, menu: QMenu):
        selectedFIDs = self.tableView().selectedFeaturesIds()
        return

        n = len(selectedFIDs)
        menuProfileStyle = menu.addMenu('Profile Style')
        wa = QWidgetAction(menuProfileStyle)

        btnResetProfileStyles = QPushButton('Reset')
        btnApplyProfileStyle = QPushButton('Apply')

        plotStyle = self.plotWidget().profileRenderer().profileStyle
        if n == 0:
            btnResetProfileStyles.setText('Reset All')
            btnResetProfileStyles.clicked.connect(self.plotWidget().resetProfileStyles)
            btnResetProfileStyles.setToolTip('Resets all profile styles')
        else:
            for fid in selectedFIDs:
                ps = self.plotWidget().profileRenderer().profilePlotStyle(fid, ignore_selection=True)
                if isinstance(ps, PlotStyle):
                    plotStyle = ps.clone()
                break

            btnResetProfileStyles.setText('Reset Selected')
            btnResetProfileStyles.clicked.connect(
                lambda *args, fids=selectedFIDs: self.plotWidget().setProfileStyles(None, fids))

        psw = PlotStyleWidget(plotStyle=plotStyle)
        psw.setPreviewVisible(False)
        psw.cbIsVisible.setVisible(False)
        btnApplyProfileStyle.clicked.connect(lambda *args, fids=selectedFIDs, w=psw:
                                             self.plotWidget().setProfileStyles(psw.plotStyle(), fids))

        hb = QHBoxLayout()
        hb.addWidget(btnResetProfileStyles)
        hb.addWidget(btnApplyProfileStyle)
        vl = QVBoxLayout()
        vl.addWidget(psw)
        vl.addLayout(hb)

        frame = QFrame()
        frame.setLayout(vl)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

    def showProperties(self, *args):
        showLayerPropertiesDialog(self.speclib(), None, parent=self)

    def showProfileFields(self, **args):
        d = SpectralProfileFieldActivatorDialog()
        d.setLayer(self.speclib())
        d.exec_()

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget

    def plotControl(self) -> SpectralProfilePlotModel:
        return self.mSpeclibPlotWidget.mPlotControlModel

    def plotItem(self) -> SpectralProfilePlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.plotWidget().getPlotItem()

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
            self.plotControl().readXml(nVIS, context)
        return True
        s = ""

    def writeXml(self, parent: QDomElement, context: QgsReadWriteContext) -> QDomElement:
        doc: QDomDocument = parent.ownerDocument()
        assert isinstance(doc, QDomDocument)

        sl: QgsVectorLayer = self.speclib()

        nSLW = doc.createElement('SpectralLibraryWidget')
        # layer node needs to be named 'maplayer'
        # see qgsvectorlayer.cpp -> bool QgsVectorLayer::writeXml(...)
        nS: QDomElement = doc.createElement('source')
        nSL: QDomElement = doc.createElement('maplayer')
        nVIS: QDomElement = doc.createElement('Visualizations')
        parent.appendChild(nSLW)
        for n in [nS, nSL, nVIS]:
            nSLW.appendChild(n)

        nS.setAttribute('provider', sl.providerType())
        nS.setAttribute('source', sl.source())
        nS.setAttribute('name', sl.name())
        nS.setAttribute('id', sl.id())

        assert self.speclib().writeXml(nSL, doc, context)
        self.plotControl().writeXml(nVIS, context)

        return nSLW

    @staticmethod
    def fromXml(node: QDomElement, context: QgsReadWriteContext, speclib: QgsVectorLayer = None,
                project: QgsProject = None) -> 'SpectralLibraryWidget':
        nSLW: QDomElement = node if node.tagName() == 'SpectralLibraryWidget' else (
            node.firstChildElement('SpectralLibraryWidget').toElement())

        if nSLW.isNull():
            return None

        if not isinstance(project, QgsProject):
            project = QgsProject.instance()

        if nSLW.isNull():
            return None

        if not isinstance(speclib, QgsVectorLayer):
            nS: QDomElement = nSLW.firstChildElement('source').toElement()
            nSL: QDomElement = nSLW.firstChildElement('maplayer').toElement()

            source = nS.attribute('source')
            provider = nS.attribute('provider')
            name = nS.attribute('name')
            sid = nS.attribute('id')

            # find layer in project
            speclib = project.mapLayer(sid)
            if not isinstance(speclib, QgsVectorLayer):
                for lyr in project.mapLayersByName(name):
                    speclib = lyr
                    break
            if not isinstance(speclib, QgsVectorLayer):
                c = QgsVectorLayer(source, name, provider)
                if isinstance(c, QgsVectorLayer) and c.isValid():
                    project.addMapLayer(c)
                    speclib = c

        if not isinstance(speclib, QgsVectorLayer):
            return None

        slw = SpectralLibraryWidget(speclib=speclib)
        pm = slw.plotControl()
        pm.readXml(node.firstChildElement('Visualizations'), context)

        return slw

    def updateActions(self):
        """
        Updates action appearance according to internal states
        :return:
        :rtype:
        """
        self.actionAddCurrentProfiles.setEnabled(self.plotControl().profileCandidates().count() > 0)
        dual_view_mode = self.mMainView.view()

        has_editor = self.widgetCenter.isVisibleTo(self) and dual_view_mode == QgsDualView.AttributeEditor
        has_table = self.widgetCenter.isVisibleTo(self) and dual_view_mode == QgsDualView.AttributeTable
        has_profiles = self.widgetLeft.isVisibleTo(self)

        self.actionShowFormView.setChecked(has_editor)
        self.actionShowAttributeTable.setChecked(has_table)
        self.actionShowProfileView.setChecked(has_profiles)

    def updatePlot(self):
        self.plotControl().updatePlot()

    def speclib(self) -> QgsVectorLayer:
        return self.mLayer

    def spectralLibrary(self) -> QgsVectorLayer:
        return self.speclib()

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
        dialog = SpectralProcessingDialog(
            speclib=self.speclib(),
            algorithmId=algorithmId,
            parameters=parameters)
        dialog.setMainMessageBar(self.mainMessageBar())
        dialog.sigOutputsCreated.connect(self.onSpectralProcessingOutputsCreated)
        dialog.exec_()

        dialog.close()

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
        plotModel: SpectralProfilePlotModel = self.plotControl()
        plotModel.profileCandidates().clearCandidates()

        # fids = list(self.plotControl().mTemporaryProfileIDs)
        # self.plotControl().mTemporaryProfileIDs.clear()
        # self.plotControl().mTemporaryProfileColors.clear()
        # self.plotControl().updatePlot(fids)
        # self.updateActions()

    def temporaryProfileIDs(self) -> Set[int]:
        return self.plotControl().profileCandidates().count()
        # return self.plotControl().mTemporaryProfileIDs

    def deleteCurrentProfilesFromSpeclib(self, *args):
        # delete previous current profiles
        speclib = self.speclib()
        if is_spectral_library(speclib):
            oldCurrentIDs = list(self.plotControl().profileCandidates().candidateFeatureIds())
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
                           currentProfiles: List[QgsFeature],
                           make_permanent: bool = None,
                           currentProfileStyles: Dict[Tuple[int, str], PlotStyle] = None,
                           ):
        """
        Sets temporary profiles for the spectral library.
        If not made permanent, they will be removes when adding the next set of temporary profiles
        :param make_permanent: bool, if not note, overwrite the value returned by optionAddCurrentProfilesAutomatically
        :type make_permanent:
        :param currentProfiles:
        :return:
        """
        if isinstance(currentProfiles, Generator):
            currentProfiles = list(currentProfiles)
        assert isinstance(currentProfiles, (list,))

        speclib: QgsVectorLayer = self.speclib()
        plotModel: SpectralProfilePlotModel = self.plotControl()

        with SpectralProfilePlotModel.UpdateBlocker(plotModel) as blocker:
            restart_editing: bool = not speclib.startEditing()

            addAuto: bool = make_permanent \
                if isinstance(make_permanent, bool) \
                else self.optionAddCurrentProfilesAutomatically.isChecked()

            if addAuto:
                self.addCurrentProfilesToSpeclib()
            else:
                self.deleteCurrentProfilesFromSpeclib()

                # now there shouldn't be any PDI or style ref related to an old ID
            plotModel.profileCandidates().clearCandidates()
            # self.plotControl().mTemporaryProfileIDs.clear()
            # self.plotControl().mTemporaryProfileColors.clear()

            # if necessary, convert QgsFeatures to SpectralProfiles
            # for i in range(len(currentProfiles)):
            #    p = currentProfiles[i]
            #    assert isinstance(p, QgsFeature)
            #    if not isinstance(p, SpectralProfile):
            #        p = SpectralProfile.fromQgsFeature(p)
            #        currentProfiles[i] = p

            # add current profiles to speclib
            oldIDs = set(speclib.allFeatureIds())

            speclib.beginEditCommand('Add current profiles')
            inputFIDs = [f.id() for f in currentProfiles]
            addedFIDs = SpectralLibraryUtils.addProfiles(speclib, currentProfiles)
            speclib.endEditCommand()

            affected_profile_fields = set()

            p_fields = profile_fields(self.speclib())
            for profile in currentProfiles:
                for fieldname in p_fields.names():
                    if profile.fieldNameIndex(fieldname) >= 0 and profile.attribute(fieldname) is not None:
                        affected_profile_fields.add(fieldname)

            if not addAuto:
                # give current spectra the current spectral style
                # self.plotControl().mTemporaryProfileIDs.update(addedFIDs)

                # affected_profile_fields: Dict[str, QColor] = dict()

                # find a profile style for each profile candidate

                if isinstance(currentProfileStyles, dict):
                    currentProfilesStyles = {(addedFIDs[inputFIDs.index(fid)], field): style
                                             for (fid, field), style in currentProfileStyles.items()}

                else:
                    if isinstance(currentProfileStyles, PlotStyle):
                        style = currentProfileStyles
                    else:
                        style = PlotStyle()
                        style.setLineColor('green')
                        style.setMarkerColor('green')
                    currentProfilesStyles = {}
                    for f in self.speclib().getFeatures(addedFIDs):
                        for n in profile_fields(f).names():
                            currentProfilesStyles[f.id(), n] = style

                plotModel.profileCandidates().setCandidates(currentProfilesStyles)

            visualized_attributes = [v.field().name() for v in self.plotControl().visualizations() if v.isComplete()]
            missing_visualization = [a for a in affected_profile_fields if a not in visualized_attributes]

            for attribute in missing_visualization:
                if False:
                    # create new vis color similar to temporal profile overly
                    color: QColor = affected_profile_fields[attribute]
                    # make the default color a bit darker
                    color = nextColor(color, 'darker')
                else:
                    color = None

                self.spectralLibraryPlotWidget().createProfileVisualization(field=attribute, color=color)

        plotModel.updatePlot()
        self.updateActions()
        self.speclib().triggerRepaint()

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
        n_p = self.speclib().featureCount()
        n_v = len(self.spectralLibraryPlotWidget().profileVisualizations())
        SpectralLibraryImportDialog.importProfiles(self.speclib(), parent=self)

        # add a new visualization if no one exists
        if n_p == 0 and n_v == 0 and self.speclib().featureCount() > 0:
            self.spectralLibraryPlotWidget().createProfileVisualization()

        # update plot
        self.plotControl().updatePlot()

    def onImportFromRasterSource(self):
        from ..io.rastersources import SpectralProfileImportPointsDialog
        d = SpectralProfileImportPointsDialog(parent=self)
        d.setWkbType(self.spectralLibrary().wkbType())
        d.finished.connect(lambda *args, d0=d: self.onIODialogFinished(d0))
        d.show()
        self.mIODialogs.append(d)

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

        files = SpectralLibraryExportDialog.exportProfiles(self.speclib(), parent=self)
        if len(files) > 0:
            self.sigFilesCreated.emit(files)

    def clearSpectralLibrary(self):
        """
        Removes all SpectralProfiles and additional fields
        """
        warnings.warn('Deprectated and desimplemented', DeprecationWarning)


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib: QgsVectorLayer = None, **kwds):
        super(SpectralLibraryPanel, self).__init__(*args, **kwds)
        self.setObjectName('spectralLibraryPanel')

        self.SLW = SpectralLibraryWidget(speclib=speclib)
        self.setWindowTitle(self.speclib().name())
        self.speclib().nameChanged.connect(lambda *args: self.setWindowTitle(self.speclib().name()))
        self.setWidget(self.SLW)

    def spectralLibraryWidget(self) -> SpectralLibraryWidget:
        """
        Returns the SpectralLibraryWidget
        :return: SpectralLibraryWidget
        """
        return self.SLW

    def speclib(self) -> QgsVectorLayer:
        """
        Returns the SpectralLibrary
        :return: SpectralLibrary
        """
        return self.SLW.speclib()

    def setCurrentSpectra(self, listOfSpectra):
        """
        Adds a list of SpectralProfiles as current spectra
        :param listOfSpectra: [list-of-SpectralProfiles]
        :return:
        """
        self.SLW.setCurrentProfiles(listOfSpectra)
