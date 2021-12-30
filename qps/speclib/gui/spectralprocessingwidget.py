import os
import pathlib
import re
import sys
import typing

from PyQt5.QtCore import pyqtSignal, QObject, QModelIndex, QMimeData, Qt, QPointF, QSortFilterProxyModel, QTimer, \
    QVariant
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QFileDialog, QInputDialog, QMessageBox, QGridLayout, QToolButton, QAction, QMenu, \
    QTreeView, QGroupBox, QLabel, QHBoxLayout, QComboBox, QLineEdit, QCheckBox, QTabWidget, QTextEdit
from qgis._core import QgsProcessing, QgsProcessingFeedback, QgsProcessingContext, QgsVectorLayer, \
    QgsProcessingRegistry, \
    QgsApplication, Qgis, QgsProcessingModelAlgorithm, QgsProcessingAlgorithm, QgsFeature, \
    QgsProcessingParameterRasterLayer, QgsProcessingOutputRasterLayer, QgsProject, QgsProcessingParameterDefinition, \
    QgsProcessingModelChildAlgorithm, QgsProcessingException, QgsRasterDataProvider, QgsMapLayer, QgsRasterLayer, \
    QgsMapLayerModel, QgsProcessingParameterRasterDestination, QgsFields, QgsProcessingOutputLayerDefinition, \
    QgsRasterFileWriter, QgsRasterBlockFeedback, QgsRasterPipe, QgsProcessingUtils, QgsCoordinateTransformContext, \
    QgsField
from qgis._gui import QgsProcessingContextGenerator, QgsProcessingParameterWidgetContext, \
    QgsProcessingToolboxProxyModel, QgsProcessingRecentAlgorithmLog, QgsProcessingToolboxTreeView, \
    QgsProcessingParametersWidget, QgsAbstractProcessingParameterWidgetWrapper, QgsGui, QgsProcessingGui, \
    QgsFieldComboBox, QgsMapLayerComboBox, QgsProcessingHiddenWidgetWrapper, QgsFilterLineEdit

from processing import createContext
from processing.gui.AlgorithmDialogBase import AlgorithmDialogBase
from processing.modeler.ModelerAlgorithmProvider import ModelerAlgorithmProvider
from processing.modeler.ProjectProvider import ProjectProvider
from qps.speclib import speclibUiPath
from qps.speclib.core import create_profile_field, is_profile_field
from qps.speclib.core.spectrallibraryrasterdataprovider import SpectralLibraryRasterDataProvider, \
    SpectralLibraryRasterLayerModel, VectorLayerFieldRasterDataProvider, createExampleLayers
from qps.speclib.core.spectralprofile import SpectralProfileBlock, SpectralSetting, prepareProfileValueDict, \
    encodeProfileValueDict
from qps.speclib.gui.spectralprofilefieldcombobox import SpectralProfileFieldComboBox
from qps.speclib.processing import SpectralProcessingAlgorithmTreeView
from qps.utils import loadUi, printCaller, rasterLayerArray, iconForFieldType, numpyToQgisDataType


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
    if not isinstance(alg, QgsProcessingAlgorithm):
        return False
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


class SpectralProfileFieldAsRasterLayerComboBox(QgsFieldComboBox):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.mLayers: typing.List[QgsRasterLayer] = None
        self.mProvider: SpectralLibraryRasterDataProvider = None

    def setLayer(self, layer: QgsMapLayer):

        if isinstance(layer, QgsVectorLayer):
            self.mSpeclib = layer
        else:
            self.mSpeclib = None

        self._updateFields()

    def _updateFields(self):

        pass


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
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex):

        sourceIdx = self.toolboxModel().index(sourceRow, 0, sourceParent)
        if self.toolboxModel().isAlgorithm(sourceIdx):
            # algId = self.sourceModel().data(sourceIdx, QgsProcessingToolboxModel.RoleAlgorithmId)
            # procReg = QgsApplication.instance().processingRegistry()
            # alg = procReg.algorithmById(algId)
            alg = self.toolboxModel().algorithmForIndex(sourceIdx)
            return super().filterAcceptsRow(sourceRow, sourceParent) and is_raster_io(alg)
        else:
            return super().filterAcceptsRow(sourceRow, sourceParent)


class SpectralProcessingRasterDestination(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.Standard,
                 parent: QObject = None):
        self.mLabel: QLabel = None
        self.mFieldComboBox: SpectralProfileFieldComboBox = None
        self.mFieldName: str = None
        self.mFields: QgsFields = QgsFields()
        super(SpectralProcessingRasterDestination, self).__init__(parameter, dialogType, parent)

    def setFields(self, fields: QgsFields):
        self.mFields = fields
        # self.mFieldComboBox.setFields(fields)

    def createLabel(self) -> QLabel:
        # l = QLabel(f'<html><img width="20"px" height="20" src=":/qps/ui/icons/profile.svg">{self.parameterDefinition().description()}</html>')
        l = QLabel(f'{self.parameterDefinition().description()} (to field)')
        l.setToolTip('Select a target field or create a new one')
        self.mLabel = l
        return l

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def createWrappedWidget(self, context: QgsProcessingContext) -> QWidget:

        if not isinstance(self.mFieldComboBox, SpectralProfileFieldComboBox):
            self.mFieldComboBox = self.createWidget()
        return self.mFieldComboBox

    def createWidget(self):
        cb = QComboBox()
        cb.setEditable(True)
        for f in self.mFields:
            cb.addItem(iconForFieldType(f), f.name(), f)
        is_optional = self.parameterDefinition().flags() & QgsProcessingParameterDefinition.FlagOptional
        if is_optional:
            pass
        cb.currentTextChanged.connect(self.setValue)
        self.mFieldComboBox = cb
        return cb

    def setValue(self, value):

        old = self.mFieldName
        if isinstance(value, str):
            self.mFieldName = value

        if old != self.mFieldName:
            self.widgetValueHasChanged.emit(self)

    def setWidgetValue(self, value, context: QgsProcessingContext):
        if isinstance(self.mFieldComboBox, QComboBox):
            if value:
                s = ""


    @classmethod
    def pathToFieldName(cls, path:str) -> str:
        name, ext = os.path.splitext(pathlib.Path(path).name)
        suffix = f'{QgsProcessing.TEMPORARY_OUTPUT}_'
        name = name.replace(suffix, '')
        return name


    def widgetValue(self):
        if isinstance(self.mFieldComboBox, QComboBox):
            path = self.mFieldComboBox.currentText()
            if not path.endswith('.tif'):
                path += '.tif'
            return f'{QgsProcessing.TEMPORARY_OUTPUT}_{path}'
        return None


class SpectralProcessingRasterLayerWidgetWrapper(QgsAbstractProcessingParameterWidgetWrapper):

    def __init__(self,
                 parameter: QgsProcessingParameterDefinition = None,
                 dialogType: QgsProcessingGui.WidgetType = QgsProcessingGui.Standard,
                 parent: QObject = None
                 ):

        self.mProfileComboBox: QWidget = None
        self.mProfileComboBoxModel = None
        self.mLayers: typing.List[QgsRasterLayer] = list()
        self.mLabel: QLabel = None

        super(SpectralProcessingRasterLayerWidgetWrapper, self).__init__(parameter, dialogType, parent)
        self.mProfileField: str = None

    def setRasterLayers(self, layers: typing.List[QgsRasterLayer]):
        self.mLayers.clear()
        self.mLayers.extend(layers)

    def createWidget(self):

        model = QgsMapLayerModel(self.mLayers)
        is_optional = self.parameterDefinition().flags() & QgsProcessingParameterDefinition.FlagOptional
        if is_optional:
            model.setAllowEmptyLayer(True)

        cb = QComboBox()
        cb.setModel(model)
        cb.currentIndexChanged.connect(lambda idx, m=model: self.onIndexChanged(idx, m))

        self.mProfileComboBoxModel = model
        self.mProfileComboBox = cb
        return cb

    def onIndexChanged(self, idx, model):
        layer = model.data(model.index(idx, 0), QgsMapLayerModel.LayerRole)
        self.setValue(layer)

    def createWrappedWidget(self, context: QgsProcessingContext) -> QWidget:

        if not isinstance(self.mProfileComboBox, SpectralProfileFieldComboBox):
            self.mProfileComboBox = self.createWidget()
        return self.mProfileComboBox

    def setWidgetValue(self, value, context: QgsProcessingContext):
        if isinstance(self.mProfileComboBox, QComboBox):
            if value:
                s = ""

    def widgetValue(self):
        if isinstance(self.mProfileComboBox, QComboBox):
            return self.mProfileComboBox.currentData(QgsMapLayerModel.LayerRole)

        return None

    def createLabel(self) -> QLabel:
        # l = QLabel(f'<html><img width="20"px" height="20" src=":/qps/ui/icons/profile.svg">{self.parameterDefinition().description()}</html>')
        l = QLabel(f'{self.parameterDefinition().description()} (from profile field)')

        l.setToolTip('Select the profile source column')
        self.mLabel = l
        return l

    def wrappedLabel(self) -> QLabel:
        if not isinstance(self.mLabel, QLabel):
            self.mLabel = self.createLabel()
        return self.mLabel

    def wrappedWidget(self) -> QWidget:
        if not isinstance(self.mProfileComboBox, QComboBox):
            self.mProfileComboBox = self.createWidget()
        return self.mProfileComboBox

    def setValue(self, value):

        old = self.mProfileField
        if isinstance(value, QgsRasterLayer) and isinstance(value.dataProvider(), VectorLayerFieldRasterDataProvider):
            dp: VectorLayerFieldRasterDataProvider = value.dataProvider()
            self.mProfileField = dp.activeField()

        if old != self.mProfileField:
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
        assert isinstance(speclib, QgsVectorLayer)
        super().__init__(alg, None)
        # self.alg: QgsProcessingAlgorithm = alg.create({})
        self.name: str = self.algorithm().displayName()

        self.mParameterWidgets: typing.Dict[str, QWidget] = dict()
        self.mOutputWidgets: typing.Dict[str, QWidget] = dict()

        # self.parameterValuesDefault: typing.Dict[str, typing.Any] = dict()
        self.mParameterValues: typing.Dict[str, typing.Any] = dict()
        self.mErrors: typing.List[str] = []
        self.mSpeclib: QgsVectorLayer = speclib
        self.mExampleLayers: typing.List[QgsRasterLayer] = []

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
        self.updateExampleLayers()
        self.initWidgets()
        self.tooltip: str = ''

        self.is_active: bool = True

        # self.verify(self.mTestBlocks)

    def addParameterWidget(self, parameter: QgsProcessingParameterDefinition, widget: QWidget,
                           stretch: int = ...) -> None:

        super().addParameterWidget(parameter, widget, stretch)
        self.mParameterWidgets[parameter.name()] = widget

    def parameterWidget(self, name: str) -> QWidget:
        return self.mParameterWidgets.get(name, None)

    def addOutputWidget(self, widget: QWidget, stretch: int = ...) -> None:
        super().addOutputWidget(widget, stretch)
        self.mOutputWidgets[widget.objectName()] = widget

    def outputWidget(self, name: str) -> QWidget:
        return self.mOutputWidgets.get(name, None)

    def initWidgets(self):
        super().initWidgets()
        # Create widgets and put them in layouts
        widget_context = QgsProcessingParameterWidgetContext()
        widget_context.setProject(QgsProject.instance())

        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue
            # if isinstance(param, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
            #    continue
            if param.isDestination():
                continue

            if isinstance(param, QgsProcessingParameterRasterLayer):
                # wrapper = SpectralProcessingProfilesWidgetWrapper(param, QgsProcessingGui.Standard)
                # wrapper.setSpeclib(self.mSpeclib)
                # wrapper.setSpeclibRasterDataProvider(self.mSpeclibProvider)
                wrapper = SpectralProcessingRasterLayerWidgetWrapper(param, QgsProcessingGui.Standard)
                wrapper.setRasterLayers(self.exampleLayers())
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

        for output in self.algorithm().destinationParameterDefinitions():
            if output.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue

            if isinstance(output, QgsProcessingParameterRasterDestination):
                # raster outputs will written to new or existing spectral profile columns
                wrapper = SpectralProcessingRasterDestination(param, QgsProcessingGui.Standard)
                wrapper.setFields(self.mSpeclib.fields())

            else:
                wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(output, QgsProcessingGui.Standard)

            wrapper.setWidgetContext(widget_context)
            wrapper.registerProcessingContextGenerator(self.context_generator)
            wrapper.registerProcessingParametersGenerator(self)
            self.wrappers[output.name()] = wrapper

            label = wrapper.createWrappedLabel()
            if label is not None:
                self.addOutputLabel(label)

            widget = wrapper.createWrappedWidget(self.processing_context)
            self.addOutputWidget(widget, wrapper.stretch())

        for wrapper in list(self.wrappers.values()):
            wrapper.postInitialize(list(self.wrappers.values()))

    def parameterWidgetValueChanged(self, wrapper: QgsAbstractProcessingParameterWidgetWrapper):

        print(f'new value: {self.name}:{wrapper}= {wrapper.parameterValue()} = {wrapper.widgetValue()}')
        # self.verify(self.mTestBlocks)
        self.mParameterValues[wrapper.parameterDefinition().name()] = wrapper.widgetValue()
        self.sigParameterValueChanged.emit(wrapper.parameterDefinition().name())

    def createProcessingParameters(self, include_default=True):
        parameters = {}
        for p, v in self.extra_parameters.items():
            parameters[p] = v

        for param in self.algorithm().parameterDefinitions():
            if param.flags() & QgsProcessingParameterDefinition.FlagHidden:
                continue
            if not param.isDestination():
                try:
                    wrapper = self.wrappers[param.name()]
                except KeyError:
                    continue

                widget = wrapper.wrappedWidget()

                if not isinstance(wrapper, QgsProcessingHiddenWidgetWrapper) and widget is None:
                    continue

                value = wrapper.parameterValue()
                if param.defaultValue() != value or include_default:
                    parameters[param.name()] = value

                if not param.checkValueIsAcceptable(value):
                    raise AlgorithmDialogBase.InvalidParameterValue(param, widget)
            else:
                # if self.in_place and param.name() == 'OUTPUT':
                #    parameters[param.name()] = 'memory:'
                #    continue

                try:
                    wrapper = self.wrappers[param.name()]
                except KeyError:
                    continue

                widget = wrapper.wrappedWidget()
                value = wrapper.parameterValue()

                dest_project = None
                if wrapper.customProperties().get('OPEN_AFTER_RUNNING'):
                    dest_project = QgsProject.instance()

                if value and isinstance(value, QgsProcessingOutputLayerDefinition):
                    value.destinationProject = dest_project
                if value and (param.defaultValue() != value or include_default):
                    parameters[param.name()] = value

                    context = createContext()
                    ok, error = param.isSupportedOutputValue(value, context)
                    if not ok:
                        raise AlgorithmDialogBase.InvalidOutputExtension(widget, error)

        return self.algorithm().preprocessParameters(parameters)

    def undefinedParameters(self) -> typing.List[QgsProcessingParameterDefinition]:
        """
        Return the parameters with missing values
        :return:
        :rtype:
        """
        missing = []
        for p in self.algorithm().parameterDefinitions():
            # if isinstance(p, (SpectralProcessingProfiles, SpectralProcessingProfilesSink)):
            #    # will be connected automatically
            #    continue
            if not bool(p.flags() & QgsProcessingParameterDefinition.FlagOptional) and p.defaultValue() is None:
                value = self.mParameterValues.get(p.name(), None)
                if value is None:
                    missing.append(p)
        return missing

    def isVerified(self) -> bool:
        return len(self.mErrors) == 0

    def updateExampleLayers(self):

        self.mExampleLayers.clear()
        self.mExampleLayers.extend(createExampleLayers(self.mSpeclib))

    def exampleLayers(self) -> typing.List[QgsRasterLayer]:
        return self.mExampleLayers[:]

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

        self.cbSelectedFeaturesOnly: QCheckBox
        self.cbSelectedFeaturesOnly.toggled.connect(self.updateSpeclibRasterDataProvider)

        self.mSpeclib: QgsVectorLayer = None
        self.mSpeclibRasterDataProvider: SpectralLibraryRasterDataProvider = SpectralLibraryRasterDataProvider()

        self.mProcessingFeedback: QgsProcessingFeedback = QgsProcessingFeedback()
        self.mProcessingWidgetContext: QgsProcessingParameterWidgetContext = QgsProcessingParameterWidgetContext()
        self.mProcessingWidgetContext.setMessageBar(self.mMessageBar)

        self.mProcessingContext: QgsProcessingContext = QgsProcessingContext()
        self.mProcessingContext.setFeedback(self.mProcessingFeedback)
        self.mProcessingAlg: QgsProcessingAlgorithm = None
        self.mProcessingAlgParametersStore: dict = dict()

        self.mProcessingModelWrapper: SpectralProcessingModelCreatorAlgorithmWrapper = None

        self.mTreeViewAlgorithmsModel = SpectralProcessingAlgorithmModel(self)
        self.mTreeViewProxyModel = QSortFilterProxyModel()
        self.mTreeViewProxyModel.setSourceModel(self.mTreeViewAlgorithmsModel)
        self.mTreeViewAlgorithms: SpectralProcessingAlgorithmTreeView
        self.mTreeViewAlgorithms.header().setVisible(False)
        self.mTreeViewAlgorithms.setDragDropMode(QTreeView.DragOnly)
        self.mTreeViewAlgorithms.setDropIndicatorShown(True)
        self.mTreeViewAlgorithms.doubleClicked.connect(self.onAlgorithmTreeViewDoubleClicked)
        self.mTreeViewAlgorithms.setToolboxProxyModel(self.mTreeViewAlgorithmsModel)

        self.tbAlgorithmFilter: QgsFilterLineEdit
        self.tbAlgorithmFilter.textChanged.connect(self.setAlgorithmFilter)

        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: QgsProcessingAlgorithm = None

        self.actionApplyModel.triggered.connect(self.applyModel)
        self.actionCancelProcessing.triggered.connect(self.cancelProcessing)
        self.actionCopyLog.triggered.connect(self.onCopyLog)
        self.actionClearLog.triggered.connect(self.tbLog.clear)
        self.actionSaveLog.triggered.connect(self.onSaveLog)

        self.btnCancel.clicked.connect(self.cancelProcessing)
        self.btnRun.clicked.connect(self.applyModel)
        self.btnCopyLog.setDefaultAction(self.actionCopyLog)
        self.btnClearLog.setDefaultAction(self.actionClearLog)
        self.btnSaveLog.setDefaultAction(self.actionSaveLog)

        for tb in self.findChildren(QToolButton):
            tb: QToolButton
            a: QAction = tb.defaultAction()
            if isinstance(a, QAction) and isinstance(a.menu(), QMenu):
                tb.setPopupMode(QToolButton.MenuButtonPopup)

    def cancelProcessing(self):
        pass

    def processingAlgorithm(self) -> QgsProcessingAlgorithm:
        return self.mProcessingAlg

    def processingContext(self) -> QgsProcessingContext:
        return self.mProcessingContext

    def onCopyLog(self):
        mimeData = QMimeData()
        mimeData.setText(self.tbLogs.toPlainText())
        mimeData.setHtml(self.tbLogs.toHtml())
        QgsApplication.clipboard().setMimeData(mimeData)

    def onSaveLog(self):

        pass

    def applyModel(self, *args):
        # verify model
        valid, msg = self.verifyModel()

        selected_only: bool = False
        wrapper = self.processingModelWrapper()
        if not isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            return None

        speclib: QgsVectorLayer = self.speclib()
        if not speclib.isEditable():
            self.log(f'{speclib} is not editable')
            return None

        alg = wrapper.algorithm()
        parameters = None
        try:
            parameters = wrapper.createProcessingParameters()
            self.tabWidget.setCurrentWidget(self.tabLog)

            # save parameters
            self.log(f'Save parameters for {alg.id()}')
            self.mProcessingAlgParametersStore[alg.id()] = parameters

            transformContext: QgsCoordinateTransformContext = QgsProject.instance().transformContext()
            # copy and replace input rasters with temporary data sets
            # that contain spectral profiles

            self.log(f'Calculate feature intersection')
            FID_Intersection = set()
            for k, v in parameters.items():
                if isinstance(v, QgsRasterLayer) and isinstance(v.dataProvider(), VectorLayerFieldRasterDataProvider):
                    dp: VectorLayerFieldRasterDataProvider = v.dataProvider()
                    fids = dp.activeFeatureIds()
                    if len(FID_Intersection) == 0:
                        FID_Intersection.update(fids)
                    else:
                        FID_Intersection.intersection_update(fids)
            if len(FID_Intersection) == 0:
                s = ""

            activeFeatures = list(self.speclib().getFeatures(sorted(FID_Intersection)))
            activeFeatureIDs = [f.id() for f in activeFeatures]

            parametersHard = parameters.copy()
            self.log(f'Make virtual rasters permanent')
            for k, v in parametersHard.items():
                if isinstance(v, QgsRasterLayer) and isinstance(v.dataProvider(), VectorLayerFieldRasterDataProvider):
                    dp: VectorLayerFieldRasterDataProvider = v.dataProvider().clone()
                    dp.setActiveFeatures(activeFeatures)

                    fb = QgsRasterBlockFeedback()
                    # file_name = f'{QgsProcessing.TEMPORARY_OUTPUT}_{k}.tif'
                    # file_name = pathlib.Path(QgsProcessingUtils.tempFolder()) / 'temp.tif'
                    file_name = QgsProcessingUtils.generateTempFilename(f'{k}.tif')
                    file_writer = QgsRasterFileWriter(file_name)
                    pipe = QgsRasterPipe()

                    if not pipe.set(dp):
                        msg = "Cannot set pipe provider"

                    error = file_writer.writeRaster(
                        pipe,
                        dp.xSize(),
                        dp.ySize(),
                        dp.extent(),
                        dp.crs(),
                        transformContext,
                        fb
                    )
                    assert error == QgsRasterFileWriter.WriterError.NoError
                    parametersHard[k] = file_name
                    # lyr = QgsRasterLayer(file_name.as_posix())
                    # tmp = rasterLayerArray(lyr)
                    # s = ""

            from processing.gui.AlgorithmExecutor import execute as executeAlg
            feedback = QgsProcessingFeedback()
            context = QgsProcessingContext()
            context.setProject(QgsProject.instance())
            context.setFeedback(feedback)

            # results, ok = alg.run(parameters, context, feedback)
            ok, results = executeAlg(alg, parametersHard, feedback=feedback, catch_exceptions=True)
            if ok:

                OUT_RASTERS = dict()
                for parameter in alg.outputDefinitions():
                    if isinstance(parameter, QgsProcessingOutputRasterLayer):
                        lyr = QgsRasterLayer(results[parameter.name()])
                        if not lyr.isValid():
                            info = f'Unable to open {lyr.source()}'
                            self.log(info)
                        else:
                            tmp = rasterLayerArray(lyr)
                            nb, nl, ns = tmp.shape

                            path1 = parameters[parameter.name()]
                            target_field_name = SpectralProcessingRasterDestination.pathToFieldName(path1)
                            target_field_index = speclib.fields().lookupField(target_field_name)
                            if target_field_index == -1:
                                # create a new field
                                if nb > 1:
                                    field: QgsField = create_profile_field(target_field_name)
                                else:
                                    field: QgsField = QgsField(name=target_field_name,
                                                               type=numpyToQgisDataType(tmp.dtype))
                                    if not speclib.dataProvider().supportedType(field):
                                        field = QgsField(name=target_field_name, type=Qgis.DataType.Float32)

                                assert speclib.addAttribute(field)
                                speclib.commitChanges(False)
                                target_field_index = speclib.fields().lookupField(target_field_name)
                            if target_field_index >= 0:
                                OUT_RASTERS[parameter.name()] = (lyr, tmp, speclib.fields().at(target_field_index))

                if len(OUT_RASTERS) > 0:

                    # reload active features to include new fields
                    activeFeatures = list(speclib.getFeatures(activeFeatureIDs))
                    # write raster values to features
                    for parameterName, (lyr, tmp, target_field) in OUT_RASTERS.items():
                        target_field: QgsField
                        target_field_index: int = speclib.fields().lookupField(target_field.name())

                        wrapper.mExampleLayers

                        is_profile = is_profile_field(target_field)
                        for i, feature in enumerate(activeFeatures):
                            feature: QgsFeature
                            value = None
                            if is_profile:
                                pixel_profile = tmp[:, 0, i]
                                # todo: consider spectral setting
                                pdict = prepareProfileValueDict(x=None, y=pixel_profile)
                                value = encodeProfileValueDict(pdict)
                            else:
                                value = float(tmp[0, 0, i])
                                if target_field.type() == QVariant.String:
                                    value = str(value)
                            assert feature.setAttribute(target_field_index, value)

                    for feature in activeFeatures:
                        assert speclib.updateFeature(feature)

            self.log(feedback.htmlLog())

        except AlgorithmDialogBase.InvalidParameterValue as ex1:
            # todo: focus on widget with missing input
            s = ""
            msg = f'Invalid Parameter Value: {ex1.parameter.name()}'
            self.log(msg)
            # self.tabWidget.setCurrentWidget(self.tabLog)
            self.highlightParameterWidget(ex1.parameter, ex1.widget)
        except AlgorithmDialogBase.InvalidOutputExtension as ex2:
            s = ""
            msg = f'Invalid Output Extension'
            self.log(msg)
            self.tabWidget.setCurrentWidget(self.tabLog)
        except Exception as ex3:
            msg = f'{ex3}'
            self.log(msg)
            self.tabWidget.setCurrentWidget(self.tabLog)


    def log(self, text):
        self.tbLog: QTextEdit
        self.tbLog.append(text)

    def highlightParameterWidget(self, parameter, widget):
        self.tabWidget.setCurrentWidget(self.tabCurrentParameters)
        wrapper: SpectralProcessingModelCreatorAlgorithmWrapper = self.processingModelWrapper()
        if isinstance(wrapper, SpectralProcessingModelCreatorAlgorithmWrapper):
            self.scrollArea.ensureWidgetVisible(widget)

            css = widget.styleSheet()
            widget.setStyleSheet('background-color: rgba(255, 0, 0, 150);')
            QTimer.singleShot(1000, lambda *args, w=widget, c=css: w.setStyleSheet(c))

        s = ""

    def onResetModel(self, *args):
        s = ""

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
                self.setAlgorithm(filename)

    def clearModel(self):
        self.mProcessingModelTableModel.clearModel()

    def setAlgorithm(self, alg: typing.Union[str, pathlib.Path, QgsProcessingAlgorithm]):
        if isinstance(alg, str):
            alg = pathlib.Path(alg)

        if isinstance(alg, pathlib.Path):
            assert alg.is_file(), f'Not a model file: {alg}'
            m = QgsProcessingModelAlgorithm()
            m.fromFile(alg.as_posix())
            alg = m

        assert isinstance(alg, QgsProcessingAlgorithm)

        self.tbModelName.setText(alg.displayName())
        self.tbModelName.setToolTip(f'<b>{alg.name()}</b><br>Algorithm ID: {alg.id()}')

        self.mProcessingAlg = alg

        wrapper = SpectralProcessingModelCreatorAlgorithmWrapper(alg,
                                                                 self.mSpeclib,
                                                                 context=self.mProcessingContext)

        last_parameters = self.mProcessingAlgParametersStore.get(alg.id(), dict())
        if len(last_parameters) > 0:
            self.log(f'Restore parameters for {alg.id()}')
            s = ""
        self.mProcessingModelWrapper = wrapper
        self.scrollArea.setWidget(wrapper)
        self.updateGui()

        # create widgets

    def setAlgorithmFilter(self, pattern: str):
        self.mTreeViewAlgorithms.setFilterString(pattern)

    def processingModelWrapper(self) -> SpectralProcessingModelCreatorAlgorithmWrapper:
        return self.mProcessingModelWrapper

    def selectedFeaturesOnly(self) -> bool:
        return self.cbSelectedFeaturesOnly.isEnabled() and self.cbSelectedFeaturesOnly.isChecked()

    def setSpeclib(self, speclib: QgsVectorLayer):
        assert isinstance(speclib, QgsVectorLayer)
        self.mSpeclib = speclib

        self.updateGui()
        self.updateSpeclibRasterDataProvider()

    def updateGui(self):

        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            n = sl.selectedFeatureCount()
            self.cbSelectedFeaturesOnly.setEnabled(n > 0)
            self.cbSelectedFeaturesOnly.setText(f'Only process {n} selected features')

        self.tabCurrentParameters.setEnabled(isinstance(self.processingAlgorithm(), QgsProcessingAlgorithm))

    def updateSpeclibRasterDataProvider(self):
        fids = None
        if self.selectedFeaturesOnly():
            fids = self.speclib().selectedFeatureIds()
        self.mSpeclibRasterDataProvider.initData(self.mSpeclib, fids=fids)

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def projectProvider(self) -> ProjectProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('project')

    def modelerAlgorithmProvider(self) -> ModelerAlgorithmProvider:
        procReg = QgsApplication.instance().processingRegistry()
        return procReg.providerById('model')

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
        if alg and is_raster_io(alg):
            self.setAlgorithm(alg)
            self.tabWidget: QTabWidget
            self.tabWidget.setCurrentWidget(self.tabCurrentParameters)

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
