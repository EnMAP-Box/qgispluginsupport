import pathlib
import re
import sys
import typing

from PyQt5.QtCore import pyqtSignal, QObject, QModelIndex, QMimeData, Qt, QPointF
from PyQt5.QtWidgets import QWidget, QFileDialog, QInputDialog, QMessageBox, QGridLayout, QToolButton, QAction, QMenu, \
    QTreeView, QGroupBox, QLabel, QHBoxLayout
from qgis._core import QgsProcessingFeedback, QgsProcessingContext, QgsVectorLayer, QgsProcessingRegistry, \
    QgsApplication, Qgis, QgsProcessingModelAlgorithm, QgsProcessingAlgorithm, QgsFeature, \
    QgsProcessingParameterRasterLayer, QgsProcessingOutputRasterLayer, QgsProject, QgsProcessingParameterDefinition, \
    QgsProcessingModelChildAlgorithm, QgsProcessingException, QgsRasterDataProvider
from qgis._gui import QgsProcessingContextGenerator, QgsProcessingParameterWidgetContext, \
    QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog, QgsProcessingToolboxTreeView, \
    QgsProcessingParametersWidget, QgsAbstractProcessingParameterWidgetWrapper, QgsGui, QgsProcessingGui

from processing.modeler.ModelerAlgorithmProvider import ModelerAlgorithmProvider
from processing.modeler.ProjectProvider import ProjectProvider
from qps.speclib import speclibUiPath
from qps.speclib.core.spectralprofile import SpectralProfileBlock
from qps.speclib.gui.spectralprofilefieldcombobox import SpectralProfileFieldComboBox
from qps.speclib.processing import SpectralProcessingAlgorithmTreeView
from qps.utils import loadUi, printCaller


def alg2model(alg: QgsProcessingAlgorithm) -> QgsProcessingModelAlgorithm:
    """
    Converts a single QgsProcessingAlgorithm into a QgsProcessingModelAlgorithm
    :param alg: QgsProcessingAlgorithm
    :return: QgsProcessingModelAlgorithm
    """

    configuration = {}
    feedback = QgsProcessingFeedback()
    context = QgsProcessingContext()
    context.setFeedback(feedback)

    model = QgsProcessingModelAlgorithm()
    model.setName(alg.name())

    def createChildAlgorithm(algorithm_id: str, description='') -> QgsProcessingModelChildAlgorithm:
        alg = QgsProcessingModelChildAlgorithm(algorithm_id)
        alg.generateChildId(model)
        alg.setDescription(description)
        return alg

    # self.testProvider().addAlgorithm(alg)
    # self.assertIsInstance(self.testProvider().algorithm(alg.name()), SpectralProcessingAlgorithmExample)
    # create child algorithms, i.e. instances of QgsProcessingAlgorithms
    cid: str = model.addChildAlgorithm(createChildAlgorithm(alg.id(), alg.name()))
    calg = model.childAlgorithm(cid)

    # set model input / output
    pname_src_profiles = 'input_profiles'
    pname_dst_profiles = 'processed_profiles'
    model.addModelParameter(SpectralProcessingProfiles(pname_src_profiles, description='Source profiles'),
                            QgsProcessingModelParameter(pname_src_profiles))

    # connect child inputs and outputs

    calg.addParameterSources(
        alg.INPUT,
        [QgsProcessingModelChildParameterSource.fromModelParameter(pname_src_profiles)])


    # allow to write the processing alg outputs as new SpectralLibraries
    model.addOutput(SpectralProcessingProfilesOutput(pname_dst_profiles))
    childOutput = QgsProcessingModelOutput(pname_dst_profiles)
    childOutput.setChildOutputName(alg.OUTPUT)
    childOutput.setChildId(calg.childId())
    calg.setModelOutputs({pname_dst_profiles: childOutput})

    model.initAlgorithm(configuration)

    # set the positions for parameters and algorithms in the model canvas:
    x = 150
    y = 50
    dx = 100
    dy = 75
    components = model.parameterComponents()
    for n, p in components.items():
        p.setPosition(QPointF(x, y))
        x += dx
    model.setParameterComponents(components)

    y = 150
    x = 250
    for calg in [calg]:
        calg: QgsProcessingModelChildAlgorithm
        calg.setPosition(QPointF(x, y))
        y += dy

    return model

def is_raster_io(alg: QgsProcessingAlgorithm) -> bool:

    has_raster_input = False
    has_raster_output = False
    for input in alg.parameterDefinitions():
        if isinstance(input, QgsProcessingParameterRasterLayer):
            has_raster_input = True
            break

    for output in alg.outputDefinitions():
        if isinstance(output, QgsProcessingOutputRasterLayer):
            has_raster_output = True
            break

    return has_raster_input and has_raster_output

class SpectralProcessingAppliers(QObject):

    def __init__(self):
        super().__init__()


class SpectralProcessingAlgorithmTreeView(QgsProcessingToolboxTreeView):
    """
    The QTreeView used to show SpectraProcessingAlgorithms in the SpectralProcessingWidget
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setHeaderHidden(True)


class SpectralProcessingAlgorithmModel(QgsProcessingToolboxProxyModel):
    """
    This proxy model filters out all QgsProcessingAlgorithms that do not use
    SpectralProcessingProfiles
    """

    def __init__(self,
                 parent: QObject,
                 registry: QgsProcessingRegistry = None,
                 recentLog: QgsProcessingRecentAlgorithmLog = None):
        super().__init__(parent, registry, recentLog)
        self.setRecursiveFilteringEnabled(True)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex):

        sourceIdx = self.toolboxModel().index(sourceRow, 0, sourceParent)
        if self.toolboxModel().isAlgorithm(sourceIdx):
            #algId = self.sourceModel().data(sourceIdx, QgsProcessingToolboxModel.RoleAlgorithmId)
            #procReg = QgsApplication.instance().processingRegistry()
            #alg = procReg.algorithmById(algId)
            alg = self.toolboxModel().algorithmForIndex(sourceIdx)
            return is_raster_io(alg)
        else:
            return super().filterAcceptsRow(sourceRow, sourceParent)


class SpectralProcessingProfilesWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    # def __init__(self, parameter: QgsProcessingParameterDefinition, wtype: QgsProcessingGui.WidgetType, parent=None):
    def __init__(self, parameter: QgsProcessingParameterDefinition = None,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.Standard,
                 parent: QObject = None
                 ):

        self.mProfileComboBox: QWidget = None
        self.mLabel: QLabel = None

        super(SpectralProcessingProfilesWidgetWrapper, self).__init__(parameter, dialogType, parent)
        self.mProfileField: str = None
        #self.mDialogType = dialogType
        self.mSpeclib: QgsVectorLayer = None
        #self.widget = self.createWidget(**kwargs)
        #self.label = self.createLabel(**kwargs)

        # super(SpectralProcessingProfilesWidgetWrapper, self).__init__(parameter, wtype, parent)

    def setSpeclib(self, speclib: QgsVectorLayer):
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def createWidget(self):
        w = SpectralProfileFieldComboBox()
        w.setLayer(self.speclib())
        w.fieldChanged.connect(self.setValue)
        self.mProfileComboBox = w
        return w

    def createWrappedWidget(self, context: QgsProcessingContext) -> QWidget:

        if not isinstance(self.mProfileComboBox, SpectralProfileFieldComboBox):
            self.mProfileComboBox = self.createWidget()
        return self.mProfileComboBox

    def setWidgetValue(self, value, context: QgsProcessingContext):
        if isinstance(self.mProfileComboBox, SpectralProfileFieldComboBox):
            if value:
                s = ""

    def widgetValue(self):
        if isinstance(self.mProfileComboBox, SpectralProfileFieldComboBox):
            return self.mProfileComboBox.currentData()

        return None

    def createLabel(self) -> QLabel:
        l = QLabel(f'Profiles "{self.parameterDefinition().description()}"')
        l.setToolTip('Select the profile source column')
        self.mLabel = l
        return l

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def setValue(self, value):

        if self.mProfileField != value:
            self.mProfileField = value
            self.widgetValueHasChanged.emit(self)

    def value(self):

        return self.mProfileField

        if self.mDialogType == QgsProcessingGui.Modeler:
            return self.widget.windowTitle() + '+Modeler'
        elif self.mDialogType == QgsProcessingGui.Batch:
            return self.widget.windowTitle() + '+Batch'
        else:
            return self.widget.windowTitle() + '+Std'


class SpectralProcessingModelCreatorAlgorithmWrapper(QgsProcessingParametersWidget):
    """
    A wrapper to keep a references on QgsProcessingAlgorithm
    and related parameter values and widgets
    """
    sigParameterValueChanged = pyqtSignal(str)
    sigVerificationChanged = pyqtSignal(bool)

    def __init__(self, alg: QgsProcessingAlgorithm,
                 speclib: QgsVectorLayer,
                 context: QgsProcessingContext = None):
        super().__init__(alg, None)
        # self.alg: QgsProcessingAlgorithm = alg.create({})
        self.name: str = self.algorithm().displayName()
        # self.parameterValuesDefault: typing.Dict[str, typing.Any] = dict()
        self.parameterValues: typing.Dict[str, typing.Any] = dict()
        self.mErrors: typing.List[str] = []
        self.mSpeclib = speclib
        self.wrappers = {}
        self.extra_parameters = {}
        if context is None:
            context = QgsProcessingContext()
        self.processing_context: QgsProcessingContext = context

        class ContextGenerator(QgsProcessingContextGenerator):

            def __init__(self, context):
                super().__init__()
                self.processing_context = context

            def processingContext(self):
                return self.processing_context

        self.context_generator = ContextGenerator(self.processing_context)

        self.initWidgets()
        self.tooltip: str = ''

        self._mWidgets = []
        self.is_active: bool = True

        # self.verify(self.mTestBlocks)

    def initWidgets(self):
        super().initWidgets()
        # Create widgets and put them in layouts
        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(QgsProject.instance())

        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue
            #if isinstance(param, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
            #    continue
            if param.isDestination():
                continue

            if isinstance(param, QgsProcessingParameterRasterLayer):
                wrapper = SpectralProcessingProfilesWidgetWrapper(param, QgsProcessingGui.Standard)
                wrapper.setSpeclib(self.mSpeclib)
            else:
                wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(param, QgsProcessingGui.Standard)
            wrapper.setWidgetContext(widget_context)
            wrapper.registerProcessingContextGenerator(self.context_generator)
            wrapper.registerProcessingParametersGenerator(self)
            wrapper.widgetValueHasChanged.connect(self.parameterWidgetValueChanged)
            # store wrapper instance
            self.wrappers[param.name()] = wrapper

            label = wrapper.createWrappedLabel()
            self.addParameterLabel(param, label)
            processing_context = self.processing_context
            widget = wrapper.createWrappedWidget(processing_context)
            stretch = wrapper.stretch()
            self.addParameterWidget(param, widget, stretch)

        for wrapper in list(self.wrappers.values()):
            wrapper.postInitialize(list(self.wrappers.values()))

    def parameterWidgetValueChanged(self, wrapper: QgsAbstractProcessingParameterWidgetWrapper):

        print(f'new value: {self.name}:{wrapper}= {wrapper.parameterValue()} = {wrapper.widgetValue()}')
        # self.verify(self.mTestBlocks)
        self.parameterValues[wrapper.parameterDefinition().name()] = wrapper.widgetValue()
        self.sigParameterValueChanged.emit(wrapper.parameterDefinition().name())

    def verify(self, test_blocks: typing.List[SpectralProfileBlock]) -> bool:
        context = self.context_generator.processingContext()
        feedback = QgsProcessingFeedback()
        alg = self.algorithm()
        self.mErrors.clear()
        try:
            undefined = self.undefinedParameters()
            assert len(undefined) == 0, f'Undefined parameters: {",".join([p.name() for p in undefined])}'

            parameters = {}
            for p in alg.parameterDefinitions():
                if p.name() in self.wrappers.keys():
                    parameters[p.name()] = self.wrappers[p.name()].parameterValue()

            success = alg.prepareAlgorithm(parameters, context, feedback)
            assert success, feedback.textLog()
            results = alg.processAlgorithm(parameters, context, feedback)

            for p in alg.outputDefinitions():
                pass
                #if isinstance(p, SpectralProcessingProfilesOutput):
                #    assert p.name() in results.keys(), feedback.textLog()
            s = ""

        except QgsProcessingException as ex1:
            self.mErrors.append(feedback.textLog())
        except AssertionError as ex2:
            self.mErrors.append(str(ex2))

        success = len(self.mErrors) == 0

        # enable css highlighting?
        if False and isinstance(self.parent(), QGroupBox):
            if success:
                self.setStyleSheet('')
            else:
                self.setStyleSheet("""background-color: red;""")

        return success, ','.join(self.mErrors)

    def undefinedParameters(self) -> typing.List[QgsProcessingParameterDefinition]:
        """
        Return the parameters with missing values
        :return:
        :rtype:
        """
        missing = []
        for p in self.algorithm().parameterDefinitions():
            #if isinstance(p, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
            #    # will be connected automatically
            #    continue
            if not bool(p.flags() & QgsProcessingParameterDefinition.FlagOptional) and p.defaultValue() is None:
                value = self.parameterValues.get(p.name(), None)
                if value is None:
                    missing.append(p)
        return missing

    def isVerified(self) -> bool:
        return len(self.mErrors) == 0

    def allParametersDefined(self) -> bool:
        """
        Returns True if all required parameters are set
        :return:
        """
        return len(self.undefinedParameters()) == 0

    def __hash__(self):
        return hash((self.algorithm().name(), id(self)))


class SpectralProcessingWidget(QWidget, QgsProcessingContextGenerator):
    sigSpectralProcessingModelChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        QgsProcessingContextGenerator.__init__(self)
        loadUi(speclibUiPath('spectralprocessingwidget.ui'), self)

        self.mSpeclib: QgsVectorLayer = None

        self.mProcessingFeedback: QgsProcessingFeedback = QgsProcessingFeedback()
        self.mProcessingWidgetContext: QgsProcessingParameterWidgetContext = QgsProcessingParameterWidgetContext()
        self.mProcessingWidgetContext.setMessageBar(self.mMessageBar)

        self.mProcessingContext: QgsProcessingContext = QgsProcessingContext()
        self.mProcessingContext.setFeedback(self.mProcessingFeedback)
        self.mProcessingAlg: QgsProcessingAlgorithm = None
        self.mProcessingAlgArguments: dict = dict()

        self.mTreeViewAlgorithmsModel = SpectralProcessingAlgorithmModel(self)
        self.mTreeViewAlgorithms: SpectralProcessingAlgorithmTreeView
        self.mTreeViewAlgorithms.header().setVisible(False)
        self.mTreeViewAlgorithms.setDragDropMode(QTreeView.DragOnly)
        self.mTreeViewAlgorithms.setDropIndicatorShown(True)
        self.mTreeViewAlgorithms.doubleClicked.connect(self.onAlgorithmTreeViewDoubleClicked)
        self.mTreeViewAlgorithms.setToolboxProxyModel(self.mTreeViewAlgorithmsModel)

        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: QgsProcessingAlgorithm = None

        self.actionApplyModel.triggered.connect(self.onApplyModel)

        self.actionCopyLog.triggered.connect(self.onCopyLog)
        self.actionClearLog.triggered.connect(self.tbLogs.clear)
        self.actionSaveLog.triggered.connect(self.onSaveLog)

        self.btnCopyLog.setDefaultAction(self.actionCopyLog)
        self.btnClearLog.setDefaultAction(self.actionClearLog)
        self.btnSaveLog.setDefaultAction(self.actionSaveLog)

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)

    def processingContext(self) -> QgsProcessingContext:
        return self.mProcessingContext

    def onCopyLog(self):
        mimeData = QMimeData()
        mimeData.setText(self.tbLogs.toPlainText())
        mimeData.setHtml(self.tbLogs.toHtml())
        QgsApplication.clipboard().setMimeData(mimeData)

    def onModelVerified(self, success: bool, message: str):

        self.actionApplyModel.setEnabled(success)

        self.mMessageBar.clearWidgets()
        if len(message) > 0:
            self.mMessageBar.pushMessage('', message, level=Qgis.Info, duration=0)
        else:
            self.mMessageBar.pushMessage('Model ready', level=Qgis.Success, duration=0)

    def onSaveLog(self):

        pass

    def onApplyModel(self, *args):
        # verify model
        valid, msg = self.verifyModel()
        if valid:
            self.sigSpectralProcessingModelChanged.emit()

    def onResetModel(self, *args):
        s = ""

    def onModelDataChanged(self, idx1: QModelIndex, idx2: QModelIndex, roles: typing.List[Qt.ItemDataRole]):

        wrapper = idx1.data(Qt.UserRole)
        current = self.currentAlgorithm()
        if isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            if wrapper == current:
                # update algorithm info
                self.gbParameterWidgets.setTitle(current.name)

    def openModel(self, filename):
        if isinstance(filename, bool):
            filename = None

        if filename is None:
            from processing.modeler.ModelerUtils import ModelerUtils

            filename, selected_filter = QFileDialog.getOpenFileName(self,
                                                                    self.tr('Open Model'),
                                                                    ModelerUtils.modelsFolders()[0],
                                                                    self.tr('Processing models (*.model3 *.MODEL3)'))
            if filename:
                self.loadModel(filename)

    def clearModel(self):
        self.mProcessingModelTableModel.clearModel()

    def loadModel(self, model: typing.Union[str, pathlib.Path, QgsProcessingAlgorithm]):
        if isinstance(model, str):

            model = pathlib.Path(model)
        if isinstance(model, pathlib.Path):
            assert model.is_file(), f'Not a model file: {model}'
            m = QgsProcessingModelAlgorithm()
            m.fromFile(model.as_posix())
            model = m
        assert isinstance(model, QgsProcessingAlgorithm)

        self.tbModelName.setText(model.displayName())
        self.tbModelName.setToolTip(f'<b>{model.name()}</b><br>Algorithm ID: {model.id()}')

        self.mProcessingAlg = model

        wrapper = SpectralProcessingModelCreatorAlgorithmWrapper(model, self.speclib(), context=self.mProcessingContext)
        self.mProcessingModelWrappers = wrapper
        self.scrollArea.setWidget(wrapper)
        # create widgets

    def setSpeclib(self, speclib: QgsVectorLayer):
        assert isinstance(speclib, QgsVectorLayer)
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def projectProvider(self) -> ProjectProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('project')

    def modelerAlgorithmProvider(self) -> ModelerAlgorithmProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('model')

    def saveModel(self, filename):
        model = self.mProcessingModelTableModel.createModel()
        if not isinstance(model, QgsProcessingModelAlgorithm):
            return
        if isinstance(filename, bool):
            filename = None

        projectProvider = self.projectProvider()

        destinations = ['Project', 'File']
        if filename is not None:
            destination = 'File'
        else:
            destination, success = QInputDialog.getItem(self, 'Save model', 'Save model to...', destinations,
                                                        editable=False, )
            if not success:
                return

        if destination == 'File' and filename is None:
            from processing.modeler.ModelerUtils import ModelerUtils
            name = model.name()
            if name == '':
                name = 'SpectralProcessingModel'
            default_path = pathlib.Path(ModelerUtils.modelsFolders()[0]) / f'{name}.model3'
            filename, filter = QFileDialog.getSaveFileName(self,
                                                           self.tr('Save Model'),
                                                           default_path.as_posix(),
                                                           self.tr('Processing models (*.model3 *.MODEL3)'))
        if destination == 'File' and filename is not None:
            # save to file
            filename = pathlib.Path(filename).as_posix()
            if not filename.endswith('.model3'):
                filename += '.model3'
            model.setSourceFilePath(filename)
            if not model.toFile(filename):
                QMessageBox.warning(self, self.tr('I/O error'),
                                    self.tr('Unable to save edits. Reason:\n {0}').format(str(sys.exc_info()[1])))
            else:
                modelerProvider = self.modelerAlgorithmProvider()
                # destFilename = os.path.join(ModelerUtils.modelsFolders()[0], os.path.basename(filename))
                # shutil.copyfile(filename, destFilename)
                modelerProvider.loadAlgorithms()

        elif destination == 'Project':
            # save to project
            projectProvider.add_model(model)

    def verifyModel(self, *args) -> typing.Tuple[bool, str]:
        messages = []
        rx_error_alg = re.compile('Error encountered while running (?P<algname>.+)$')

        feedback = QgsProcessingFeedback()
        context = QgsProcessingContext()
        context.setFeedback(feedback)

        # success, msg = self.processingTableModel().verifyModel(self.mDummyBlocks, context, feedback)
        # self.actionApplyModel.setEnabled(success)
        # if success:
        #     self.mProcessingFeedback
        return True, ''

    def onCurrentAlgorithmChanged(self, current, previous):

        # clear grid
        grid: QGridLayout = self.gbParameterWidgets.layout()
        while grid.count() > 0:
            item = grid.takeAt(0)
            widget = item.widget()
            if isinstance(widget, QWidget):
                widget.setParent(None)

        wrapper = current.data(Qt.UserRole)
        if not isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            self.gbParameterWidgets.setTitle('<No Algorithm selected>')
            self.gbParameterWidgets.setVisible(False)
        else:
            self.gbParameterWidgets.setVisible(True)
            self.gbParameterWidgets.setTitle(wrapper.name)

            row = 0
            wrapper.setParent(self.gbParameterWidgets)
            grid.addWidget(wrapper, row, 0)

    def onAlgorithmTreeViewDoubleClicked(self, *args):

        alg = self.mTreeViewAlgorithms.selectedAlgorithm()
        if is_raster_io(alg):
            self.loadModel(alg)

    def model(self) -> QgsProcessingModelAlgorithm:
        return self.mProcessingAlg

    def onSelectionChanged(self, selected, deselected):

        self.actionRemoveFunction.setEnabled(selected.count() > 0)
        current: QModelIndex = self.mTableView.currentIndex()
        f = None
        if current.isValid():
            f = current.data(Qt.UserRole)

        if f != self.mCurrentFunction:
            self.mCurrentFunction = f

    def tableView(self) -> SpectralProcessingAlgorithmTreeView:
        return self.mTableView
