import enum
import sys
import typing
import warnings

from PyQt5.QtCore import pyqtSignal, Qt, QModelIndex
from PyQt5.QtGui import QIcon, QDragEnterEvent, QContextMenuEvent
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QAction, QMenu, QToolBar, QToolButton, QWidgetAction, QPushButton, \
    QHBoxLayout, QFrame, QDialog, QLabel
from qgis.core import QgsFeature
from qgis.gui import QgsMapCanvas, QgsDualView, QgsAttributeTableView, QgsAttributeTableFilterModel, QgsDockWidget, \
    QgsActionMenu, QgsStatusBar
from ...layerproperties import AttributeTableWidget, showLayerPropertiesDialog
from ...plotstyling.plotstyling import PlotStyle, PlotStyleWidget
from ..core.spectrallibrary import SpectralLibrary
from ..core.spectrallibraryio import AbstractSpectralLibraryIO
from ..core.spectralprofile import SpectralProfile
from .spectrallibraryplotwidget import SpectralProfilePlotWidget, SpectralLibraryPlotWidget, \
    SpectralLibraryPlotItem, SpectralLibraryPlotStats, SpectralProfilePlotControlModel
from ..processing import SpectralProcessingWidget
from ...unitmodel import BAND_NUMBER
from ...utils import SpatialExtent, SpatialPoint


class SpectralLibraryWidget(AttributeTableWidget):
    sigFilesCreated = pyqtSignal(list)
    sigLoadFromMapRequest = pyqtSignal()
    sigMapExtentRequested = pyqtSignal(SpatialExtent)
    sigMapCenterRequested = pyqtSignal(SpatialPoint)
    sigCurrentProfilesChanged = pyqtSignal(list)

    class ViewType(enum.Enum):
        AttributeTable = enum.auto()
        FormView = enum.auto()
        ProcessingView = enum.auto()

    def __init__(self, *args, speclib: SpectralLibrary = None, mapCanvas: QgsMapCanvas = None, **kwds):

        if not isinstance(speclib, SpectralLibrary):
            speclib = SpectralLibrary()

        super().__init__(speclib)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib.svg'))
        self.mQgsStatusBar = QgsStatusBar(self.statusBar())
        self.mQgsStatusBar.setParentStatusBar(self.statusBar())
        self.mStatusLabel: SpectralLibraryInfoLabel = SpectralLibraryInfoLabel()
        self.mStatusLabel.setTextFormat(Qt.RichText)
        self.mQgsStatusBar.addPermanentWidget(self.mStatusLabel, 1, QgsStatusBar.AnchorLeft)

        self.mIODialogs: typing.List[QWidget] = list()

        from ..io.envi import EnviSpectralLibraryIO
        from ..io.csvdata import CSVSpectralLibraryIO
        from ..io.asd import ASDSpectralLibraryIO
        from ..io.ecosis import EcoSISSpectralLibraryIO
        from ..io.specchio import SPECCHIOSpectralLibraryIO
        from ..io.artmo import ARTMOSpectralLibraryIO
        from ..io.vectorsources import VectorSourceSpectralLibraryIO
        from ..io.rastersources import RasterSourceSpectralLibraryIO
        self.mSpeclibIOInterfaces = [
            EnviSpectralLibraryIO(),
            CSVSpectralLibraryIO(),
            ARTMOSpectralLibraryIO(),
            ASDSpectralLibraryIO(),
            EcoSISSpectralLibraryIO(),
            SPECCHIOSpectralLibraryIO(),
            VectorSourceSpectralLibraryIO(),
            RasterSourceSpectralLibraryIO(),
        ]

        self.mSpeclibIOInterfaces = sorted(self.mSpeclibIOInterfaces, key=lambda c: c.__class__.__name__)

        self.tableView().willShowContextMenu.connect(self.onWillShowContextMenuAttributeTable)
        self.mMainView.showContextMenuExternally.connect(self.onShowContextMenuAttributeEditor)

        self.mSpeclibPlotWidget: SpectralLibraryPlotWidget = SpectralLibraryPlotWidget()
        assert isinstance(self.mSpeclibPlotWidget, SpectralLibraryPlotWidget)
        self.mSpeclibPlotWidget.setDualView(self.mMainView)
        self.mStatusLabel.setPlotWidget(self.mSpeclibPlotWidget)
        self.mSpeclibPlotWidget.plotWidget.mUpdateTimer.timeout.connect(self.mStatusLabel.update)

        self.pageProcessingWidget: SpectralProcessingWidget = SpectralProcessingWidget()
        #self.pageProcessingWidget.sigSpectralProcessingModelChanged.connect(
        #    lambda *args: self.mSpeclibPlotWidget.addSpectralModel(self.pageProcessingWidget.model()))

        l = QVBoxLayout()
        l.addWidget(self.mSpeclibPlotWidget)
        # l.addWidget(self.pageProcessingWidget)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        self.widgetRight.setLayout(l)
        self.widgetRight.setVisible(True)

        self.widgetCenter.addWidget(self.pageProcessingWidget)
        self.widgetCenter.currentChanged.connect(self.onCenterWidgetChanged)
        self.mMainView.formModeChanged.connect(self.onCenterWidgetChanged)

        # define Actions and Options

        self.actionSelectProfilesFromMap = QAction(r'Select Profiles from Map')
        self.actionSelectProfilesFromMap.setToolTip(r'Select new profile from map')
        self.actionSelectProfilesFromMap.setIcon(QIcon(':/qps/ui/icons/profile_identify.svg'))
        self.actionSelectProfilesFromMap.setVisible(False)
        self.actionSelectProfilesFromMap.triggered.connect(self.sigLoadFromMapRequest.emit)

        self.actionAddProfiles = QAction('Add Profile(s)')
        self.actionAddProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.actionAddCurrentProfiles = QAction('Add Profiles(s)')
        self.actionAddCurrentProfiles.setToolTip('Adds currently overlaid profiles to the spectral library')
        self.actionAddCurrentProfiles.setIcon(QIcon(':/qps/ui/icons/plus_green_icon.svg'))
        self.actionAddCurrentProfiles.triggered.connect(self.addCurrentSpectraToSpeclib)

        self.optionAddCurrentProfilesAutomatically = QAction('Add profiles automatically')
        self.optionAddCurrentProfilesAutomatically.setToolTip('Activate to add profiles automatically '
                                                              'into the spectral library')
        self.optionAddCurrentProfilesAutomatically.setIcon(QIcon(':/qps/ui/icons/profile_add_auto.svg'))
        self.optionAddCurrentProfilesAutomatically.setCheckable(True)
        self.optionAddCurrentProfilesAutomatically.setChecked(False)

        self.actionImportVectorRasterSource = QAction('Import profiles from raster + vector source')
        self.actionImportVectorRasterSource.setToolTip('Import spectral profiles from a raster image '
                                                       'based on vector geometries (Points).')
        self.actionImportVectorRasterSource.setIcon(QIcon(':/images/themes/default/mActionAddOgrLayer.svg'))

        self.actionImportVectorRasterSource.triggered.connect(self.onImportFromRasterSource)

        m = QMenu()
        m.addAction(self.actionAddCurrentProfiles)
        m.addAction(self.optionAddCurrentProfilesAutomatically)
        self.actionAddProfiles.setMenu(m)

        self.actionImportSpeclib = QAction('Import Spectral Profiles')
        self.actionImportSpeclib.setToolTip('Import spectral profiles from other data sources')
        self.actionImportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_add.svg'))
        m = QMenu()
        m.addAction(self.actionImportVectorRasterSource)
        m.addSeparator()
        self.createSpeclibImportMenu(m)
        self.actionImportSpeclib.setMenu(m)
        self.actionImportSpeclib.triggered.connect(self.onImportSpeclib)

        self.actionExportSpeclib = QAction('Export Spectral Profiles')
        self.actionExportSpeclib.setToolTip('Export spectral profiles to other data formats')
        self.actionExportSpeclib.setIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))

        m = QMenu()
        self.createSpeclibExportMenu(m)
        self.actionExportSpeclib.setMenu(m)
        self.actionExportSpeclib.triggered.connect(self.onExportSpectra)

        self.tbSpeclibAction = QToolBar('Spectral Profiles')
        self.tbSpeclibAction.setObjectName('SpectralLibraryToolbar')
        self.tbSpeclibAction.addAction(self.actionSelectProfilesFromMap)
        self.tbSpeclibAction.addAction(self.actionAddProfiles)
        self.tbSpeclibAction.addAction(self.actionImportSpeclib)
        self.tbSpeclibAction.addAction(self.actionExportSpeclib)

        self.tbSpeclibAction.addSeparator()
        self.cbXAxisUnit = self.mSpeclibPlotWidget.optionXUnit.createUnitComboBox()
        self.tbSpeclibAction.addWidget(self.cbXAxisUnit)
        self.tbSpeclibAction.addAction(self.mSpeclibPlotWidget.optionColorsFromFeatureRenderer)

        self.actionShowFormView = QAction('Show Form View')
        self.actionShowFormView.setCheckable(True)
        self.actionShowFormView.setIcon(QIcon(':/images/themes/default/mActionFormView.svg'))
        self.actionShowFormView.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.FormView))

        self.actionShowAttributeTable = QAction('Show Attribute Table')
        self.actionShowAttributeTable.setCheckable(True)
        self.actionShowAttributeTable.setIcon(QIcon(':/images/themes/default/mActionOpenTable.svg'))
        self.actionShowAttributeTable.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.AttributeTable))

        self.actionShowProcessingWidget = QAction('Show Spectral Processing Options')
        self.actionShowProcessingWidget.setCheckable(True)
        self.actionShowProcessingWidget.setIcon(QIcon(':/qps/ui/icons/profile_processing.svg'))
        self.actionShowProcessingWidget.triggered.connect(
            lambda: self.setCenterView(SpectralLibraryWidget.ViewType.ProcessingView))
        self.mMainViewButtonGroup.buttonClicked.connect(self.onCenterWidgetChanged)

        self.tbSpectralProcessing = QToolBar('Spectral Processing')

        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionApplyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionVerifyModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionSaveModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionLoadModel)
        self.tbSpectralProcessing.addAction(self.pageProcessingWidget.actionRemoveFunction)

        self.addToolBar(self.tbSpectralProcessing)

        r = self.tbSpeclibAction.addSeparator()
        self.tbSpeclibAction.addAction(self.actionShowFormView)
        self.tbSpeclibAction.addAction(self.actionShowAttributeTable)
        self.tbSpeclibAction.addAction(self.actionShowProcessingWidget)

        # update toolbar visibilities
        self.onCenterWidgetChanged()

        self.insertToolBar(self.mToolbar, self.tbSpeclibAction)

        self.actionShowProperties = QAction('Show Spectral Library Properties')
        self.actionShowProperties.setToolTip('Show Spectral Library Properties')
        self.actionShowProperties.setIcon(QIcon(':/images/themes/default/propertyicons/system.svg'))
        self.actionShowProperties.triggered.connect(self.showProperties)

        self.btnShowProperties = QToolButton()
        self.btnShowProperties.setAutoRaise(True)
        self.btnShowProperties.setDefaultAction(self.actionShowProperties)

        self.tbSpeclibAction.addAction(self.actionShowProperties)
        self.centerBottomLayout.insertWidget(self.centerBottomLayout.indexOf(self.mAttributeViewButton),
                                             self.btnShowProperties)

        # QIcon(':/images/themes/default/mActionMultiEdit.svg').pixmap(20,20).isNull()
        self.setAcceptDrops(True)

    def setCenterView(self, view: typing.Union[QgsDualView.ViewMode,
                                               typing.Optional['SpectralLibraryWidget.ViewType']]):
        if isinstance(view, QgsDualView.ViewMode):
            if view == QgsDualView.AttributeTable:
                view = SpectralLibraryWidget.ViewType.AttributeTable
            elif view == QgsDualView.AttributeEditor:
                view = SpectralLibraryWidget.ViewType.FormView

        assert isinstance(view, SpectralLibraryWidget.ViewType)

        if view == SpectralLibraryWidget.ViewType.AttributeTable:
            self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
            self.mMainView.setView(QgsDualView.AttributeTable)

        elif view == SpectralLibraryWidget.ViewType.FormView:
            self.widgetCenter.setCurrentWidget(self.pageAttributeTable)
            self.mMainView.setView(QgsDualView.AttributeEditor)

        elif view == SpectralLibraryWidget.ViewType.ProcessingView:
            self.widgetCenter.setCurrentWidget(self.pageProcessingWidget)

        # legacy code
        self.mMainViewButtonGroup.button(QgsDualView.AttributeTable) \
            .setChecked(self.actionShowAttributeTable.isChecked())
        self.mMainViewButtonGroup.button(QgsDualView.AttributeEditor) \
            .setChecked(self.actionShowFormView.isChecked())

    def onCenterWidgetChanged(self, *args):
        w = self.widgetCenter.currentWidget()

        self.mToolbar.setVisible(w == self.pageAttributeTable)
        self.tbSpectralProcessing.setVisible(w == self.pageProcessingWidget)
        self.actionShowProcessingWidget.setChecked(w == self.pageProcessingWidget)

        if w == self.pageAttributeTable:
            viewMode: QgsDualView.ViewMode = self.mMainView.view()
            self.actionShowAttributeTable.setChecked(viewMode == QgsDualView.AttributeTable)
            self.actionShowFormView.setChecked(viewMode == QgsDualView.AttributeEditor)
        else:
            self.actionShowAttributeTable.setChecked(False)
            self.actionShowFormView.setChecked(False)

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

    def createSpeclibImportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to import SpectralProfiles
        """
        separated = []
        from ..io.rastersources import RasterSourceSpectralLibraryIO

        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO), iface
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addImportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addImportActions(self.speclib(), menu)

    def createSpeclibExportMenu(self, menu: QMenu):
        """
        :return: QMenu with QActions and submenus to export the SpectralLibrary
        """
        separated = []
        from ..io.rastersources import RasterSourceSpectralLibraryIO
        for iface in self.mSpeclibIOInterfaces:
            assert isinstance(iface, AbstractSpectralLibraryIO)
            if isinstance(iface, RasterSourceSpectralLibraryIO):
                separated.append(iface)
            else:
                iface.addExportActions(self.speclib(), menu)

        if len(separated) > 0:
            menu.addSeparator()
            for iface in separated:
                iface.addExportActions(self.speclib(), menu)

    def plotWidget(self) -> SpectralProfilePlotWidget:
        return self.mSpeclibPlotWidget.plotWidget

    def plotControl(self) -> SpectralProfilePlotControlModel:
        return self.mSpeclibPlotWidget.mPlotControlModel

    def plotItem(self) -> SpectralLibraryPlotItem:
        """
        :return: SpectralLibraryPlotItem
        """
        return self.plotWidget().getPlotItem()

    def updatePlot(self):
        self.plotWidget().updatePlot()

    def speclib(self) -> SpectralLibrary:
        return self.mLayer

    def spectralLibrary(self) -> SpectralLibrary:
        return self.speclib()

    def addSpeclib(self, speclib: SpectralLibrary):
        assert isinstance(speclib, SpectralLibrary)
        sl = self.speclib()
        wasEditable = sl.isEditable()
        try:
            sl.startEditing()
            info = 'Add {} profiles from {} ...'.format(len(speclib), speclib.name())
            sl.beginEditCommand(info)
            sl.addSpeclib(speclib)
            sl.endEditCommand()
            if not wasEditable:
                sl.commitChanges()
        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

    def addCurrentSpectraToSpeclib(self, *args):
        """
        Adds all current spectral profiles to the "persistent" SpectralLibrary
        """

        fids = list(self.plotControl().mTemporaryProfileIDs)
        self.plotControl().mTemporaryProfileIDs.clear()
        self.plotControl().updatePlot(fids)

    def setCurrentProfiles(self,
                           currentProfiles: typing.List[SpectralProfile]):
        """
        Sets temporary profiles for the spectral library.
        If not made permanent, they will be removes when adding the next set of temporary profiles
        :param currentProfiles:
        :param profileStyles:
        :return:
        """
        if isinstance(currentProfiles, typing.Generator):
            currentProfiles = list(currentProfiles)
        assert isinstance(currentProfiles, (list,))

        speclib: SpectralLibrary = self.speclib()
        plotWidget: SpectralProfilePlotWidget = self.plotWidget()

        #  stop plot updates
        plotWidget.mUpdateTimer.stop()
        restart_editing: bool = not speclib.startEditing()
        oldCurrentIDs = list(self.plotControl().mTemporaryProfileIDs)
        addAuto: bool = self.optionAddCurrentProfilesAutomatically.isChecked()

        if addAuto:
            self.addCurrentSpectraToSpeclib()
        else:
            # delete previous current profiles from speclib
            speclib.beginEditCommand('Remove temporary')
            speclib.deleteFeatures(oldCurrentIDs)
            speclib.endEditCommand()
            # now there shouldn't be any PDI or style ref related to an old ID
        self.plotControl().mTemporaryProfileIDs.clear()

        # if necessary, convert QgsFeatures to SpectralProfiles
        #for i in range(len(currentProfiles)):
        #    p = currentProfiles[i]
        #    assert isinstance(p, QgsFeature)
        #    if not isinstance(p, SpectralProfile):
        #        p = SpectralProfile.fromQgsFeature(p)
        #        currentProfiles[i] = p

        # add current profiles to speclib
        oldIDs = set(speclib.allFeatureIds())
        addedKeys = speclib.addProfiles(currentProfiles)

        if not addAuto:
            # give current spectra the current spectral style
            self.plotControl().mTemporaryProfileIDs.update(addedKeys)
        self.plotControl().updatePlot()

    def currentProfiles(self) -> typing.List[SpectralProfile]:
        return self.mSpeclibPlotWidget.plotWidget.currentProfiles()

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the internal, hidden QgsMapCanvas. Note: not to be used in other widgets!
        :return: QgsMapCanvas
        """
        return self.mMapCanvas

    def setAddCurrentProfilesAutomatically(self, b: bool):
        self.optionAddCurrentProfilesAutomatically.setChecked(b)

    def dropEvent(self, event):
        self.plotWidget().dropEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        self.plotWidget().dragEnterEvent(event)

    def onImportSpeclib(self):
        """
        Imports a SpectralLibrary
        :param path: str
        """

        slib = SpectralLibrary.readFromSourceDialog(self)

        if isinstance(slib, SpectralLibrary) and len(slib) > 0:
            self.addSpeclib(slib)

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
        b = self.speclib().isEditable()
        self.speclib().startEditing()
        self.speclib().beginEditCommand('Add {} profiles'.format(len(profiles)))
        self.speclib().addProfiles(profiles, addMissingFields=add_missing_fields)
        self.speclib().endEditCommand()
        self.speclib().commitChanges()
        if b:
            self.speclib().startEditing()

    def onExportSpectra(self, *args):
        files = self.speclib().write(None)
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
        if not isinstance(pw, SpectralProfilePlotWidget) or not isinstance(pw.speclib(), SpectralLibrary):
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