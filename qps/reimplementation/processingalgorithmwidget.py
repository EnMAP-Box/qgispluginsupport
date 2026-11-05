import warnings
from typing import List

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import Qgis, QgsProcessingContext
from qgis.core import QgsProject
from qgis.gui import (
    QgsProcessingAlgorithmWidgetBase,
    QgsProcessingParametersGenerator,
)
from qgis.gui import QgsProcessingParameterWidgetContext, QgsProcessingGuiRegistry, QgisInterface

from .processingparameterswidget import ProcessingParametersWidget


def _default_widget_context() -> QgsProcessingParameterWidgetContext:
    try:
        context = QgsProcessingGuiRegistry.createWidgetContext()
    except Exception:
        context = QgsProcessingParameterWidgetContext()
        context.setProject(QgsProject.instance())

        from qgis.utils import iface
        if isinstance(iface, QgisInterface):
            context.setMapCanvas(iface.mapCanvas())
            context.setActiveLayer(iface.activeLayer())
    return context


class ProcessingAlgorithmWidget(QgsProcessingAlgorithmWidgetBase):
    def __init__(self, algorithm,
                 in_place=False, parent_window=None, flags=None, initial_state=None,
                 processing_context: QgsProcessingContext | None = None,
                 widget_context: QgsProcessingParameterWidgetContext | None = None):
        if flags is None:
            flags = QgsProcessingAlgorithmWidgetBase.WidgetFlags()
        if initial_state is None:
            initial_state = Qgis.DockableWidgetInitialState.RestorePreviousState

        super().__init__(
            parent_window,
            QgsProcessingAlgorithmWidgetBase.WidgetMode.Single,
            flags,
            initial_state,
        )

        self._in_place = in_place
        self._feedback = None
        if not isinstance(processing_context, QgsProcessingContext):
            processing_context: QgsProcessingContext = QgsProcessingContext()
            processing_context.setProject(QgsProject.instance())
            self._feedback = self.createFeedback()
            processing_context.setFeedback(self._feedback)
        else:
            self._feedback = processing_context.feedback()
        self._processing_context = processing_context

        if not isinstance(widget_context, QgsProcessingParameterWidgetContext):
            widget_context: QgsProcessingParameterWidgetContext = _default_widget_context()
            widget_context.setProject(processing_context.project())

        if processing_context.project() != widget_context.project():
            warnings.warn("processing_context.project() and widget_context.project() do not match", stacklevel=2)

        widget_context.registerProcessingContextGenerator(self)
        self._widget_context = widget_context

        self._widgets_to_reset_palette: List[QWidget] = []

        self.setAlgorithm(algorithm)
        self.buttonBox().accepted.connect(self._resetWidgetPalettes)

    def createParametersPanel(self, inPlaceMode, activeLayer, messageBar):
        widget = ProcessingParametersWidget(self.algorithm(), inPlaceMode, activeLayer, messageBar)
        widget.registerProcessingContextGenerator(self)
        widget.registerWidgetContextGenerator(self)
        widget.initWidgets()
        return widget

    def parametersWidget(self):
        widget = self.mainWidget()
        if isinstance(widget, ProcessingParametersWidget):
            return widget
        return None

    def inPlace(self):
        return self._in_place

    def setParameters(self, values):
        widget = self.parametersWidget()
        if widget:
            widget.setParameters(values)

    def createProcessingParameters(self, flags=None) -> dict:
        widget = self.parametersWidget()
        if not widget:
            return {}

        if flags is None:
            flags = QgsProcessingParametersGenerator.Flags()

        parameters, validation_results = widget.createAndValidateParameters(flags)
        if self.handleValidationResults(validation_results):
            return parameters
        return {}

    def handleValidationResults(self, results: List) -> bool:
        all_valid = True
        widget = self.parametersWidget()

        for result in results:
            parameterName = r = None
            message = ''
            if isinstance(result, dict):
                parameterName = result.get('parameterName', None)
                message = result.get('message', None)
                r = result.get('result', None)
            else:
                if hasattr(result, 'parameterName'):
                    parameterName = result.parameterName
                if hasattr(result, 'message'):
                    message = result.message
                if hasattr(result, 'result'):
                    r = result.result

            if parameterName is None or r is None:
                continue

            wrapper = widget.wrapper(parameterName) if widget else None
            wrapped_widget = wrapper.wrappedWidget() if wrapper else None
            if wrapped_widget is None:
                continue
            parameter = self.algorithm().parameterDefinition(parameterName)

            if r in ['Valid']:
                continue
            if r in ['InvalidOutputExtension']:
                self.flagInvalidOutputExtension(message, wrapped_widget)
                all_valid = False
            if r in ['InvalidValue']:
                message = parameter.description() if parameter else ""
                self.flagInvalidParameterValue(message, wrapped_widget)
                all_valid = False

        return all_valid

    def flagInvalidParameterValue(self, message, widget):
        if not widget:
            return

        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 0))
        widget.setPalette(palette)
        self._widgets_to_reset_palette.append(widget)

        self.messageBar().clearWidgets()
        self.messageBar().pushMessage(
            "",
            self.tr("Wrong or missing parameter value: %1").replace("%1", message),
            Qgis.MessageLevel.Warning,
            5,
        )

    def flagInvalidOutputExtension(self, message, widget):
        if not widget:
            return

        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 0))
        widget.setPalette(palette)
        self._widgets_to_reset_palette.append(widget)

        self.messageBar().clearWidgets()
        self.messageBar().pushMessage("", message, Qgis.MessageLevel.Warning, 5)

    def _resetWidgetPalettes(self):
        for widget in self._widgets_to_reset_palette:
            widget.setPalette(QPalette())
        self._widgets_to_reset_palette.clear()

    def processingContext(self):
        return self._processing_context
        if self._feedback is None:
            fb = self.context.feedback()
            if fb is None:
                fb = self.createFeedback()
            self._feedback = fb

        self.context.setFeedback(self._feedback)
        self.applyContextOverrides(self.context)
        return self.context

    def createWidgetContext(self) -> QgsProcessingParameterWidgetContext:
        return self._widget_context
