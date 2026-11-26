"""
Reimplementation of QgsProcessingParametersWidget.

This module provides a Python reimplementation of the QGIS processing
QgsProcessingParametersWidget class based on the C++ implementation
"""
from typing import List, Tuple, Dict, Any

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QFrame
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox
from qgis.core import (
    Qgis, QgsProcessingModelAlgorithm,
    QgsProcessingFeatureBasedAlgorithm,
    QgsProcessingDestinationParameter,
)
from qgis.core import QgsProcessingContext
from qgis.core import QgsProcessingParameterDefinition
from qgis.core import QgsVariantUtils, QgsProject
from qgis.gui import (
    QgsGui,
    QgsPanelWidget,
    QgsScrollArea,
    QgsCollapsibleGroupBox,
)
from qgis.gui import (
    QgsMessageBar,
    QgsAbstractProcessingParameterWidgetWrapper,
    QgsProcessingHiddenWidgetWrapper,
)
from qgis.gui import QgsProcessingParametersGenerator, QgsProcessingContextGenerator, \
    QgsProcessingParameterWidgetContext


class _DefaultWidgetContextGenerator(object):

    def __init__(self, processing_context_generator: QgsProcessingContextGenerator, *args, **kwds):
        self._processing_context_generator = processing_context_generator
        self._widget_context = None

    def createWidgetContext(self) -> QgsProcessingParameterWidgetContext:
        # Sync project from processing context before returning
        # This ensures the widget context uses the same project as the processing context
        if self._widget_context is None:
            wc = QgsProcessingParameterWidgetContext()
            wc.registerProcessingContextGenerator(self._processing_context_generator)
            self._widget_context = wc

        return self._widget_context


class _DefaultProcessingContextGenerator(QgsProcessingContextGenerator):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._context = QgsProcessingContext()
        self._project = QgsProject.instance()
        self._context.setProject(self._project)

    def processingContext(self) -> QgsProcessingContext:
        return self._context


class _DefaultProcessingParametersGenerator(QgsProcessingParametersGenerator):
    def __init__(self, widget):
        super().__init__()

        self._widget = widget

    def createProcessingParameters(self, flags=None) -> dict:
        return self._widget.createProcessingParameters(flags)


class ProcessingParametersWidget(QgsPanelWidget):
    """
    Reimplementation of QgsProcessingParametersWidget.
    This class provides a pure Python implementation of the QGIS processing
    parameters widget, allowing users to select values for algorithm parameters.
    """

    def __init__(
        self,
        algorithm,
        in_place=False,
        active_layer=None,
        message_bar=None,
        parent=None
    ):
        super().__init__(parent)

        self.mAlgorithm = algorithm
        self.mInPlace = in_place
        self.mActiveLayer = active_layer
        self.mMessageBar = message_bar
        self.mWrappers = {}
        self.mWidgets = []
        self.mLabels = []

        self.mExtraParameters = {}

        self._processing_context_generator = _DefaultProcessingContextGenerator()
        self._processing_parameters_generator = _DefaultProcessingParametersGenerator(self)
        self._widget_context_generator = _DefaultWidgetContextGenerator(self._processing_context_generator)

        self.setupUi()

        self.grpAdvanced.hide()
        self.grpOutputs.hide()

        self.scrollAreaWidgetContents.setContentsMargins(4, 4, 4, 4)

    def setupUi(self):
        self.setObjectName("ProcessingParametersWidget")
        self.verticalLayout = QVBoxLayout(self)
        self.verticalLayout.setSpacing(2)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)

        self.scrollArea = QgsScrollArea(self)
        self.scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        self.scrollArea.setWidgetResizable(True)

        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setGeometry(0, 0, 386, 104)

        self.mScrollAreaLayout = QVBoxLayout(self.scrollAreaWidgetContents)
        self.mScrollAreaLayout.setContentsMargins(0, 0, 0, 0)

        self.grpAdvanced = QgsCollapsibleGroupBox(self.scrollAreaWidgetContents)
        self.grpAdvanced.setTitle("Advanced Parameters")
        self.grpAdvanced.setCollapsed(True)
        self.mAdvancedGroupLayout = QVBoxLayout(self.grpAdvanced)
        self.mAdvancedGroupLayout.setContentsMargins(0, 0, 0, 0)

        self.mScrollAreaLayout.addWidget(self.grpAdvanced)

        self.grpOutputs = QGroupBox(self.scrollAreaWidgetContents)
        self.grpOutputs.setTitle("Outputs")
        self.mOutputGroupLayout = QVBoxLayout(self.grpOutputs)
        self.mOutputGroupLayout.setContentsMargins(0, 0, 0, 0)

        self.mScrollAreaLayout.addWidget(self.grpOutputs)

        self.verticalSpacer = self.mScrollAreaLayout.addStretch()
        # self.verticalSpacer.setSizeHint(Qt.SizeHint(20, 40))

        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout.addWidget(self.scrollArea)

    def createParameterWidgetWrapper(self, definition: QgsProcessingParameterDefinition, mode: Qgis.ProcessingMode):
        return QgsGui.processingGuiRegistry().createParameterWidgetWrapper(definition, mode)

    def initWidgets(self):
        context = self.processingContext()
        if not isinstance(context, QgsProcessingContext):
            raise ValueError("Processing context is not set")

        defs = self.algorithm().parameterDefinitions()
        for param in defs:
            if param.flags() & Qgis.ProcessingParameterFlag.Advanced:
                self.grpAdvanced.show()
                break

        if not self.algorithm():
            return

        widgetContext = self.widgetContext()
        if isinstance(self.mMessageBar, QgsMessageBar):
            widgetContext.setMessageBar(self.mMessageBar)
        alg = self.algorithm()
        if isinstance(alg, QgsProcessingModelAlgorithm):
            widgetContext.setModel(alg)

        inPlaceInputParameterName = "INPUT"
        if isinstance(alg, QgsProcessingFeatureBasedAlgorithm):
            inPlaceInputParameterName = alg.inputParameterName()

        hasNonInputParams = False
        for definition in defs:
            if definition.name() != inPlaceInputParameterName and definition.name() != "OUTPUT":
                hasNonInputParams = True
                break

        if self.mInPlace and not hasNonInputParams:
            widget = QWidget(self)
            layout = QVBoxLayout(widget)
            label = QLabel(widget)
            label.setWordWrap(True)

            layerName = self.mActiveLayer.name() if self.mActiveLayer else ""
            infoText = QCoreApplication.translate(
                "QgsProcessingParametersWidget",
                "<i>No additional parameters are required. This algorithm will activate "
                "edit mode and modify the features on layer <b>%1</b> in place.</i>"
            ).arg(layerName)
            label.setText(infoText)

            layout.addWidget(label)
            layout.addStretch()
            self.addExtraWidget(widget)

        for definition in defs:
            if definition.flags() & Qgis.ProcessingParameterFlag.Hidden:
                continue

            if definition.isDestination():
                continue

            if self.mInPlace and (definition.name() == inPlaceInputParameterName or definition.name() == "OUTPUT"):
                wrapper = QgsProcessingHiddenWidgetWrapper(definition, Qgis.ProcessingMode.Standard, self)
                wrapper.setLinkedVectorLayer(self.mActiveLayer)
                self.mWrappers[definition.name()] = wrapper
                continue

            wrapper = self.createParameterWidgetWrapper(definition, Qgis.ProcessingMode.Standard)
            # wrapper = QgsGui.processingGuiRegistry().createParameterWidgetWrapper(definition,
            #                                                                      Qgis.ProcessingMode.Standard)
            if not wrapper:
                continue

            wrapper.setDialog(self.parentWidget())
            # Register processing context generator before setting widget context
            # This ensures the widget context has the correct project
            wrapper.registerProcessingContextGenerator(self._processing_context_generator)
            wrapper.registerProcessingParametersGenerator(self._processing_parameters_generator)
            wrapper.setWidgetContext(widgetContext)
            self.mWrappers[definition.name()] = wrapper

            widget = wrapper.createWrappedWidget(context)
            wrapper.widgetValueHasChanged.connect(self.parameterChanged)

            if isinstance(widget, QWidget):
                self.mWidgets.append(widget)
                label = wrapper.createWrappedLabel()
                if isinstance(label, QWidget):
                    self.addParameterLabel(definition, label)
                    self.mLabels.append(label)

                self.addParameterWidget(definition, widget, wrapper.stretch())

        destinationDefinitions = self.algorithm().destinationParameterDefinitions()
        for output in destinationDefinitions:
            if output.flags() & Qgis.ProcessingParameterFlag.Hidden:
                continue

            if self.mInPlace and (output.name() == inPlaceInputParameterName or output.name() == "OUTPUT"):
                continue

            # wrapper = QgsGui.processingGuiRegistry()
            # .createParameterWidgetWrapper(output, Qgis.ProcessingMode.Standard)
            wrapper = self.createParameterWidgetWrapper(output, Qgis.ProcessingMode.Standard)
            if not wrapper:
                continue

            # Register processing context generator before setting widget context
            wrapper.registerProcessingContextGenerator(self._processing_context_generator)
            wrapper.registerProcessingParametersGenerator(self._processing_parameters_generator)
            wrapper.setWidgetContext(widgetContext)
            self.mWrappers[output.name()] = wrapper

            label = wrapper.createWrappedLabel()
            if isinstance(label, QWidget):
                self.addOutputLabel(label)
                self.mLabels.append(label)

            widget = wrapper.createWrappedWidget(context)
            if isinstance(widget, QWidget):
                self.mWidgets.append(widget)
                self.addOutputWidget(widget, wrapper.stretch())

        wrapperList = list(self.mWrappers.values())
        for k, wrapper in self.mWrappers.items():
            wrapper.postInitialize(wrapperList)

    def widgetContext(self) -> QgsProcessingParameterWidgetContext:
        return self._widget_context_generator.createWidgetContext()

    def processingContext(self) -> QgsProcessingContext | None:
        return self._processing_context_generator.processingContext()

    def algorithm(self):
        return self.mAlgorithm

    def createProcessingParameters(self, flags=None):
        if flags is None:
            flags = QgsProcessingParametersGenerator.Flags()
        return self.createAndValidateParameters(flags)[0]

    def validate(self) -> List:
        _, validationResults = self.createAndValidateParameters(QgsProcessingParametersGenerator.Flags())
        return validationResults

    def createAndValidateParameters(self, flags) -> Tuple[Dict[str, Any], List]:
        context = self.processingContext()
        validationResults = []
        includeDefault = not bool(flags & QgsProcessingParametersGenerator.Flag.SkipDefaultValueParameters)
        validate = not bool(flags & QgsProcessingParametersGenerator.Flag.SkipValidation)

        parameters = dict(self.mExtraParameters)
        defs = self.mAlgorithm.parameterDefinitions()

        for definition in defs:
            # dn = definition.name()
            if definition.flags() & Qgis.ProcessingParameterFlag.Hidden:
                continue

            if not definition.isDestination():
                wrapper = self.mWrappers.get(definition.name())
                if not wrapper:
                    continue

                widget = wrapper.wrappedWidget()

                if not isinstance(wrapper, QgsProcessingHiddenWidgetWrapper) and not widget:
                    continue

                value = wrapper.parameterValue()
                if definition.defaultValue() != value or includeDefault:
                    parameters[definition.name()] = value

                if validate and not definition.checkValueIsAcceptable(value, context):
                    try:
                        result = QgsProcessingParametersGenerator.ParameterValidationResult()
                        result.parameterName = definition.name()
                        result.result = QgsProcessingParametersGenerator.ValidationResult.InvalidValue
                    except AttributeError:
                        result = {
                            'parameterName': definition.name(),
                            'result': 'InvalidValue',
                            'message': 'Invalid value',
                        }
                        pass
                    validationResults.append(result)
            else:
                if self.mInPlace and definition.name() == "OUTPUT":
                    parameters[definition.name()] = "memory:"
                    continue

                wrapper = self.mWrappers.get(definition.name())
                if not wrapper:
                    continue

                value = wrapper.parameterValue()

                destinationProject = None
                if wrapper.customProperties().get("OPEN_AFTER_RUNNING", False):
                    destinationProject = context.project()
                    if destinationProject is None:
                        destinationProject = QgsProject.instance()

                if hasattr(value, 'userType') and value.userType() == "QgsProcessingOutputLayerDefinition":
                    outputDefinition = value.value()
                    outputDefinition.destinationProject = destinationProject
                    value = outputDefinition

                if not QgsVariantUtils.isNull(value) and (definition.defaultValue() != value or includeDefault):
                    parameters[definition.name()] = value
                    if validate and isinstance(definition, QgsProcessingDestinationParameter):
                        destinationParam: QgsProcessingDestinationParameter = definition
                        ok, error = destinationParam.isSupportedOutputValue(value, context)
                        if not ok:
                            try:
                                result = QgsProcessingParametersGenerator.ParameterValidationResult()
                                result.parameterName = definition.name()
                                result.result = QgsProcessingParametersGenerator.ValidationResult.InvalidOutputExtension
                                result.message = error
                            except AttributeError:
                                result = {
                                    'parameterName': definition.name(),
                                    'result': 'InvalidOutputExtension',
                                    'message': error
                                }
                            validationResults.append(result)

        return self.mAlgorithm.preprocessParameters(parameters), validationResults

    def setParameters(self, parameters: dict):
        context = self.processingContext()

        self.mExtraParameters.clear()
        defs = self.mAlgorithm.parameterDefinitions()
        for definition in defs:
            paramIt = parameters.get(definition.name())
            if definition.flags() & Qgis.ProcessingParameterFlag.Hidden:
                if paramIt is not None:
                    self.mExtraParameters[definition.name()] = paramIt
                continue

            if paramIt is None:
                continue

            value = paramIt

            wrapperIt = self.mWrappers.get(definition.name())
            if wrapperIt:
                wrapperIt.setParameterValue(value, context)

    def wrapper(self, name):
        return self.mWrappers.get(name)

    def wrappers(self):
        return list(self.mWrappers.values())

    def registerProcessingParametersGenerator(self, generator: QgsProcessingParametersGenerator):
        if not isinstance(generator, QgsProcessingParametersGenerator):
            raise ValueError("Generator must be an instance of QgsProcessingParametersGenerator")
        self._processing_parameters_generator = generator

    def registerProcessingContextGenerator(self, generator: QgsProcessingContextGenerator):
        if not isinstance(generator, QgsProcessingContextGenerator):
            raise ValueError("Generator must be an instance of QgsProcessingContextGenerator")
        self._processing_context_generator = generator

    def registerWidgetContextGenerator(self, generator):
        if Qgis.versionInt() >= 44000:
            from qgis.gui import QgsProcessingWidgetContextGenerator
            if not isinstance(generator, QgsProcessingWidgetContextGenerator):
                raise ValueError("Generator must be an instance of QgsProcessingWidgetContextGenerator")

        self._widget_context_generator = generator

    def parameterChanged(self):
        wrapper = self.sender()
        if not isinstance(wrapper, QgsAbstractProcessingParameterWidgetWrapper):
            return

        defaultValues = self.mAlgorithm.autogenerateParameterValues(
            self.createProcessingParameters(
                QgsProcessingParametersGenerator.Flags(QgsProcessingParametersGenerator.Flag.SkipValidation)),
            wrapper.parameterDefinition().name(),
            Qgis.ProcessingMode.Standard
        )

        if len(defaultValues) > 0:
            self.setParameters(defaultValues)

    def addParameterWidget(self, parameter, widget, stretch=0):
        if parameter.flags() & Qgis.ProcessingParameterFlag.Advanced:
            self.mAdvancedGroupLayout.addWidget(widget, stretch)
        else:
            self.mScrollAreaLayout.insertWidget(self.mScrollAreaLayout.count() - 3, widget, stretch)

    def addParameterLabel(self, parameter, label):
        if parameter.flags() & Qgis.ProcessingParameterFlag.Advanced:
            self.mAdvancedGroupLayout.addWidget(label)
        else:
            self.mScrollAreaLayout.insertWidget(self.mScrollAreaLayout.count() - 3, label)

    def addOutputLabel(self, label):
        self.grpOutputs.show()
        self.mOutputGroupLayout.addWidget(label)

    def addOutputWidget(self, widget, stretch=0):
        self.grpOutputs.show()
        self.mOutputGroupLayout.addWidget(widget, stretch)

    def addExtraWidget(self, widget):
        self.mScrollAreaLayout.addWidget(widget)
