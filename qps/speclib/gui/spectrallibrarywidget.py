import enum
import sys
import typing
import warnings

from PyQt5.QtCore import pyqtSignal, Qt, QModelIndex
from PyQt5.QtGui import QIcon, QDragEnterEvent, QContextMenuEvent, QDropEvent, QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QAction, QMenu, QToolBar, QToolButton, QWidgetAction, QPushButton, \
    QHBoxLayout, QFrame, QDialog, QLabel, QMessageBox
from qgis.core import QgsVectorLayer

from qgis.core import QgsFeature
from qgis.gui import QgsMapCanvas, QgsDualView, QgsAttributeTableView, QgsAttributeTableFilterModel, QgsDockWidget, \
    QgsActionMenu, QgsStatusBar
from ..core import is_spectral_library, profile_field_list
from ...layerproperties import AttributeTableWidget, showLayerPropertiesDialog, CopyAttributesDialog
from ...plotstyling.plotstyling import PlotStyle, PlotStyleWidget
from ..core.spectrallibrary import SpectralLibrary, SpectralLibraryUtils
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportDialog, SpectralLibraryExportDialog
from ..core.spectralprofile import SpectralProfile
from .spectrallibraryplotwidget import SpectralProfilePlotWidget, SpectralLibraryPlotWidget, \
    SpectralLibraryPlotItem, SpectralLibraryPlotStats, SpectralProfilePlotControlModel
from ..processing import SpectralProcessingWidget
from ...unitmodel import BAND_NUMBER
from ...utils import SpatialExtent, SpatialPoint, nextColor


class SpectralLibraryWidget(AttributeTableWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)
    sigCurrentProfilesChanged = pyqtSignal(list)

    class ViewType(enum.Flag):
        Empty = enum.auto()
        ProfileView = enum.auto()
        ProfileViewSettings = enum.auto()
        AttributeTable = enum.auto()
        FormView = enum.auto()
        ProcessingView = enum.auto()
        Standard = ProfileView | AttributeTable

    def __init__(self, *args, speclib: SpectralLibrary = None, mapCanvas: QgsMapCanvas = None, **kwds):

        if not isinstance(speclib, QgsVectorLayer):
            speclib = SpectralLibrary()

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

        self._SHOW_MODEL: bool = False

        self.mToolbar: QToolBar
        self.mIODialogs: typing.List[QWidget] = list()

        self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        self.mSpeclibPlotWidget: SpectralLibraryPlotWidget = SpectralLibraryPlotWidget()
        self.mSpeclibPlotWidget.plotControlModel()._SHOW_MODEL = self._SHOW_MODEL

        assert isinstance(self.mSpeclibPlotWidget, SpectralLibraryPlotWidget)
        self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mSpeclibPlotWidget.sigDragEnterEvent.connect(self.dragEnterEvent)
        self.mSpeclibPlotWidget.sigDropEvent.connect(self.dropEvent)

        # self.mStatusLabel.setPlotWidget(self.mSpeclibPlotWidget)
        # self.mSpeclibPlotWidget.plotWidget.mUpdateTimer.timeout.connect(self.mStatusLabel.update)

        self.pageProcessingWidget: SpectralProcessingWidget = SpectralProcessingWidget()

        l = QVBoxLayout()
        l.addWidget(self.mSpeclibPlotWidget)
        # l.addWidget(self.pageProcessingWidget)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        self.widgetLeft.setLayout(l)
        self.widgetLeft.setVisible(True)
        self.widgetRight.setVisible(False)

        self.widgetCenter.addWidget(self.pageProcessingWidget)
        self.widgetCenter.currentChanged.connect(self.updateToolbarVisibility)
        # self.widgetCenter.visibilityChanged.connect(self.updateToolbarVisibility)
        self.mMainView.formModeChanged.connect(self.updateToolbarVisibility)

        # define Actions and Options

        self.actionSelectProfilesFromMap = QAction(r'Select Profiles from Map', parent=self)
        self.actionSelectProfilesFromMap.setToolTip(r'Select new profile from map')
        self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddCurrentProfiles = QAction('Add Profiles(s)', parent=self)
        self.actionAddCurrentProfiles.setShortcut(Qt.CTRL + Qt.SHIFT + Qt.Key_A)
        # self.actionAddCurrentProfiles.setShortcut(Qt.Key_Z)
        self.actionAddCurrentProfiles.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.actionAddCurrentProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentProfilesToSpeclib)

        self.optionAddCurrentProfilesAutomatically = QAction('Add profiles automatically', parent=self)
        self.optionAddCurrentProfilesAutomatically.setToolTip('Activate to add profiles automatically '
                                                              'into the spectral library')
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

        self.actionImportSpeclib = QAction('Import Spectral Profiles', parent=self)
        self.actionImportSpeclib.setToolTip('Import spectral profiles from other data sources')
        self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        self.actionImportSpeclib.triggered.connect(self.onImportProfiles)

        self.actionExportSpeclib = QAction('Export Spectral Profiles', parent=self)
        self.actionExportSpeclib.setToolTip('Export spectral profiles to other data formats')
        self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))
        self.actionExportSpeclib.triggered.connect(self.onExportProfiles)

        self.actionShowProperties = QAction('Show Spectral Library Properties', parent=self)
        self.actionShowProperties.setToolTip('Show Spectral Library Properties')
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.tbSpeclibAction = QToolBar('Spectral Library')
        self.tbSpeclibAction.setObjectName('SpectralLibraryToolbar')
        self.tbSpeclibAction.setFloatable(False)
        self.tbSpeclibAction.setMovable(False)
        # self.tbSpeclibAction.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        self.tbSpeclibAction.addAction(self.actionAddProfiles)
        self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        self.tbSpeclibAction.addAction(self.actionExportSpeclib)
        self.tbSpeclibAction.addAction(self.actionShowProperties)

        # self.tbSpeclibAction.addSeparator()
        # self.cbXAxisUnit = self.mSpeclibPlotWidget.optionXUnit.createUnitComboBox()
        # self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        # self.tbSpeclibAction.addAction(self.mSpeclibPlotWidget.optionColorsFromFeatureRenderer)

        self.actionShowProfileView = QAction('Show Profile Plot', parent=self)
        self.actionShowProfileView.setCheckable(True)
        self.actionShowProfileView.setChecked(True)
        self.actionShowProfileView.setIcon(QIcon(self.mSpeclibPlotWidget.windowIcon()))
        self.actionShowProfileView.triggered.connect(self.setCenterView)

        self.actionShowProfileViewSettings = self.mSpeclibPlotWidget.optionShowVisualizationSettings
        self.actionShowProfileView.toggled.connect(self.actionShowProfileViewSettings.setEnabled)

        # show Attribute Table / Form View buttons in menu bar only
        self.mAttributeViewButton.setVisible(False)
        self.mTableViewButton.setVisible(False)

        self.actionShowFormView = QAction('Show Form View', parent=self)
        self.actionShowFormView.setCheckable(True)
        self.actionShowFormView.setIcon(QIcon(':/images/themes/default/mActionFormView.svg'))
        self.actionShowFormView.triggered.connect(self.setCenterView)

        self.actionShowAttributeTable = QAction('Show Attribute Table', parent=self)
        self.actionShowAttributeTable.setCheckable(True)
        self.actionShowAttributeTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        self.actionShowAttributeTable.triggered.connect(self.setCenterView)

        self.actionShowProcessingWidget = QAction('Show Spectral Processing Options', parent=self)
        self.actionShowProcessingWidget.setCheckable(True)
        self.actionShowProcessingWidget.setIcon(QIcon(':/qps/ui/icons/profile_processing.svg'))
        self.actionShowProcessingWidget.triggered.connect(self.setCenterView)
        self.actionShowProcessingWidget.setEnabled(self._SHOW_MODEL)

        self.mMainViewButtonGroup.buttonClicked.connect(self.updateToolbarVisibility)

        self.tbSpectralProcessing = QToolBar('Spectral Processing')
        self.tbSpectralProcessing.setMovable(False)
        self.tbSpectralProcessing.setFloatable(False)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionApplyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionVerifyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionSaveModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionLoadModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionRemoveFunction)

        r = self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowProfileView)
        self.tbSpeclibAction.addAction(self.actionShowProfileViewSettings)
        self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowFormView)
        self.tbSpeclibAction.addAction(self.actionShowAttributeTable)

        if self._SHOW_MODEL:
            self.tbSpeclibAction.addAction(self.actionShowProcessingWidget)

        self.insertToolBar(self.mToolbar, self.tbSpeclibAction)
        self.insertToolBar(self.mToolbar, self.tbSpectralProcessing)

        # update toolbar visibilities
        self.updateToolbarVisibility()
        self.updateActions()

        # property button now shown in speclib action toolbar only
        # self.btnShowProperties = QToolButton()
        # self.btnShowProperties.setAutoRaise(True)
        # self.btnShowProperties.setDefaultAction(self.actionShowProperties)
        # self.centerBottomLayout.insertWidget(self.centerBottomLayout.indexOf(self.mAttributeViewButton),
        #                                   self.btnShowProperties)

        # show attribute table by default
        self.actionShowAttributeTable.trigger()

        # QIcon(':/images/themes/default/mActionMultiEdit.svg').pixmap(20,20).isNull()
        self.setAcceptDrops(True)

        self.setViewVisibility(SpectralLibraryWidget.ViewType.Standard)

        # if self.speclib().featureCount() > 0:
        #    for field in profile_field_list(self.speclib()):
        #        self.spectralLibraryPlotWidget().createProfileVis(field=field)

        # try to give the plot widget most space
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([200, 10, 0])

    def setViewVisibility(self, viewType: ViewType):
        """
        Sets the visibility of views
        :param views: list of ViewsTypes to set visible
        :type views:
        :return:
        :rtype:
        """
        assert isinstance(viewType, SpectralLibraryWidget.ViewType)

        self.actionShowProfileView.setChecked(SpectralLibraryWidget.ViewType.ProfileView in viewType)
        self.actionShowProfileViewSettings.setChecked(SpectralLibraryWidget.ViewType.ProfileViewSettings in viewType)

        exclusive_actions = [self.actionShowAttributeTable,
                             self.actionShowFormView,
                             self.actionShowProcessingWidget]

        sender = None
        if SpectralLibraryWidget.ViewType.AttributeTable in viewType:
            sender = self.actionShowAttributeTable
        elif SpectralLibraryWidget.ViewType.FormView in viewType:
            sender = self.actionShowFormView
        elif SpectralLibraryWidget.ViewType.ProcessingView in viewType:
            sender = self.actionShowProcessingWidget

        for a in exclusive_actions:
            a.setChecked(a == sender)

        self.setCenterView()

    def setCenterView(self):

        sender = self.sender()

        # either show attribute table, form view or processing widget
        exclusive_actions = [self.actionShowAttributeTable,
                             self.actionShowFormView,
                             self.actionShowProcessingWidget]

        if sender in exclusive_actions:
            for a in exclusive_actions:
                if a != sender:
                    a.setChecked(False)

        is_profileview = self.actionShowProfileView.isChecked()
        is_formview = self.actionShowFormView.isChecked()
        is_tableview = self.actionShowAttributeTable.isChecked()
        is_processingview = self.actionShowProcessingWidget.isChecked()

        self.widgetLeft.setVisible(is_profileview)

        if not any([is_formview, is_tableview, is_processingview]):
            self.widgetCenter.setVisible(False)
        else:
            if is_tableview:
                self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
                self.mMainView.setView(QgsDualView.AttributeTable)
            elif is_formview:
                self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
                self.mMainView.setView(QgsDualView.AttributeEditor)
            elif is_processingview:
                self.widgetCenter.setCurrentWidget(self.pageProcessingWidget)
            self.widgetCenter.setVisible(True)

        self.updateToolbarVisibility()

    def updateToolbarVisibility(self, *args):

        self.mToolbar.setVisible(self.pageAttributeTable.isVisibleTo(self))
        self.tbSpectralProcessing.setVisible(self.pageProcessingWidget.isVisibleTo(self))

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
        l = QVBoxLayout()
        l.addWidget(psw)
        l.addLayout(hb)

        frame = QFrame()
        frame.setLayout(l)
        wa.setDefaultWidget(frame)
        menuProfileStyle.addAction(wa)

    def showProperties(self, *args):

        showLayerPropertiesDialog(self.speclib(), None, parent=self, useQGISDialog=True)

        s = ""

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget

    def plotControl(self) -> SpectralProfilePlotControlModel:
        return self.mSpeclibPlotWidget.mPlotControlModel

    def plotItem(self) -> SpectralLibraryPlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.plotWidget().getPlotItem()

    def updateActions(self):
        """
        Updates action appearance according to internal states
        :return:
        :rtype:
        """
        self.actionAddCurrentProfiles.setEnabled(len(self.temporaryProfileIDs()) > 0)
        s = ""

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
                result = QMessageBox.question(self, 'Create additional field(s)?',
                                              f'Data has {len(missing)} other field(s).\n'
                                              f'Do you like to copy them?')

                if result == QMessageBox.Yes:
                    if not CopyAttributesDialog.copyLayerFields(speclib_dst, speclib, parent=self):
                        return

        try:
            speclib_dst.startEditing()
            info = 'Add {} profiles from {} ...'.format(len(speclib), speclib.name())
            speclib_dst.beginEditCommand(info)
            SpectralLibraryUtils.addSpeclib(speclib_dst, speclib, addMissingFields=False)
            speclib_dst.endEditCommand()

            if not wasEditable:
                speclib_dst.commitChanges()
                s = ""

        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

    def addCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def addCurrentProfilesToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """

        fids = list(self.plotControl().mTemporaryProfileIDs)
        self.plotControl().mTemporaryProfileIDs.clear()
        self.plotControl().mTemporaryProfileColors.clear()
        self.plotControl().updatePlot(fids)
        self.updateActions()

    def temporaryProfileIDs(self) -> typing.Set[int]:
        return self.plotControl().mTemporaryProfileIDs

    def deleteCurrentProfilesFromSpeclib(self, *args):
        # delete previous current profiles
        speclib = self.speclib()
        if is_spectral_library(speclib):
            oldCurrentIDs = list(self.plotControl().mTemporaryProfileIDs)
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
                           currentProfiles: typing.List[SpectralProfile],
                           make_permanent: bool = None,
                           currentProfileColors: typing.List[typing.Tuple[int, QColor]] = None):
        """
        Sets temporary profiles for the spectral library.
        If not made permanent, they will be removes when adding the next set of temporary profiles
        :param colors:
        :param make_permanent: bool, if not note, overwrite the value returned by optionAddCurrentProfilesAutomatically
        :type make_permanent:
        :param currentProfiles:
        :return:
        """
        # print(f'set {currentProfiles}')
        if isinstance(currentProfiles, typing.Generator):
            currentProfiles = list(currentProfiles)
        assert isinstance(currentProfiles, (list,))

        speclib: QgsVectorLayer = self.speclib()
        plotWidget: SpectralProfilePlotWidget = self.plotWidget()

        #  stop plot updates
        # plotWidget.mUpdateTimer.stop()
        restart_editing: bool = not speclib.startEditing()

        addAuto: bool = make_permanent if isinstance(make_permanent, bool) \
            else self.optionAddCurrentProfilesAutomatically.isChecked()

        if addAuto:
            self.addCurrentProfilesToSpeclib()
        else:
            self.deleteCurrentProfilesFromSpeclib()

            # now there shouldn't be any PDI or style ref related to an old ID
        self.plotControl().mTemporaryProfileIDs.clear()
        self.plotControl().mTemporaryProfileColors.clear()

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
        addedKeys = SpectralLibraryUtils.addProfiles(speclib, currentProfiles)
        speclib.endEditCommand()

        if not addAuto:
            # give current spectra the current spectral style
            self.plotControl().mTemporaryProfileIDs.update(addedKeys)

            affected_profile_fields: typing.Dict[str, QColor] = dict()

            if isinstance(currentProfileColors, list):
                if len(currentProfileColors) == len(addedKeys):
                    for fid, profile_colors in zip(addedKeys, currentProfileColors):
                        for t in profile_colors:
                            attribute, color = t
                            if isinstance(attribute, int):
                                attribute = speclib.fields().at(attribute).name()
                            if attribute not in affected_profile_fields.keys():
                                affected_profile_fields[attribute] = color
                            self.plotControl().mTemporaryProfileColors[(fid, attribute)] = color

            visualized_attributes = [v.field().name() for v in self.plotControl().visualizations()]
            missing_visualization = [a for a in affected_profile_fields.keys() if a not in visualized_attributes]

            for attribute in missing_visualization:
                if False:
                    # create new vis color similar to temporal profile overly
                    color: QColor = affected_profile_fields[attribute]
                    # make the default color a bit darker
                    color = nextColor(color, 'darker')
                else:
                    color = None

                self.spectralLibraryPlotWidget().createProfileVis(field=attribute, color=color)

        self.plotControl().updatePlot()
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
        sl: QgsVectorLayer = self.speclib()

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
            self.spectralLibraryPlotWidget().createProfileVis()

    def onImportFromRasterSource(self):
        from ..io.rastersources import SpectralProfileImportPointsDialog
        d = SpectralProfileImportPointsDialog(parent=self)
        d.finished.connect(lambda *args, d=d: self.onIODialogFinished(d))
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


class SpectralLibraryInfoLabel(QLabel):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mPW: SpectralProfilePlotWidget = None

        self.mLastStats: SpectralLibraryPlotStats = None
        self.setStyleSheet('QToolTip{width:300px}')

    def setPlotWidget(self, pw: SpectralLibraryPlotWidget):
        assert isinstance(pw, SpectralLibraryPlotWidget)
        self.mPW = pw

    def plotWidget(self) -> SpectralLibraryPlotWidget:
        return self.mPW

    def update(self):
        if not isinstance(self.plotWidget(), SpectralProfilePlotWidget):
            self.setText('')
            self.setToolTip('')
            return

        stats = self.plotWidget().profileStats()
        if self.mLastStats == stats:
            return

        msg = f'<html><head/><body>'
        ttp = f'<html><head/><body><p>'

        # total + filtering
        if stats.filter_mode == QgsAttributeTableFilterModel.ShowFilteredList:
            msg += f'{stats.profiles_filtered}f'
            ttp += f'{stats.profiles_filtered} profiles filtered out of {stats.profiles_total}<br/>'
        else:
            # show all
            msg += f'{stats.profiles_total}'
            ttp += f'{stats.profiles_total} profiles in total<br/>'

        # show selected
        msg += f'/{stats.profiles_selected}'
        ttp += f'{stats.profiles_selected} selected in plot<br/>'

        if stats.profiles_empty > 0:
            msg += f'/<span style="color:red">{stats.profiles_empty}N</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_empty} profile fields empty (NULL)<br/>'

        if stats.profiles_error > 0:
            msg += f'/<span style="color:red">{stats.profiles_error}E</span>'
            ttp += f'<span style="color:red">At least {stats.profiles_error} profiles ' \
                   f'can not be converted to X axis unit "{self.plotWidget().xUnit()}" (ERROR)</span><br/>'

        if stats.profiles_plotted >= stats.profiles_plotted_max and stats.profiles_total > stats.profiles_plotted_max:
            msg += f'/<span style="color:red">{stats.profiles_plotted}</span>'
            ttp += f'<span style="color:red">{stats.profiles_plotted} profiles plotted. Increase plot ' \
                   f'limit ({stats.profiles_plotted_max}) to show more at same time.</span><br/>'
        else:
            msg += f'/{stats.profiles_plotted}'
            ttp += f'{stats.profiles_plotted} profiles plotted<br/>'

        msg += '</body></html>'
        ttp += '</p></body></html>'

        self.setText(msg)
        self.setToolTip(ttp)
        self.setMinimumWidth(self.sizeHint().width())

        self.mLastStats = stats

    def contextMenuEvent(self, event: QContextMenuEvent):
        m = QMenu()

        stats = self.plotWidget().profileStats()

        a = m.addAction('Select axis-unit incompatible profiles')
        a.setToolTip(f'Selects all profiles that cannot be displayed in {self.plotWidget().xUnit()}')
        a.triggered.connect(self.onSelectAxisUnitIncompatibleProfiles)

        a = m.addAction('Reset to band number')
        a.setToolTip('Resets the x-axis to show the band number.')
        a.triggered.connect(lambda *args: self.plotWidget().setXUnit(BAND_NUMBER))

        m.exec_(event.globalPos())

    def onSelectAxisUnitIncompatibleProfiles(self):
        incompatible = []
        pw: SpectralProfilePlotWidget = self.plotWidget()
        if not isinstance(pw, SpectralProfilePlotWidget) or \
                not is_spectral_library(pw.speclib()):
            return

        targetUnit = pw.xUnit()
        for p in pw.speclib():
            if isinstance(p, SpectralProfile):
                f = pw.unitConversionFunction(p.xUnit(), targetUnit)
                if f == pw.mUnitConverter.func_return_none:
                    incompatible.append(p.id())

        pw.speclib().selectByIds(incompatible)


class SpectralLibraryPanel(QgsDockWidget):
    sigLoadFromMapRequest = None

    def __init__(self, *args, speclib: SpectralLibrary = None, **kwds):
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

    def speclib(self) -> SpectralLibrary:
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
