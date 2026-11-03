"""
Reimplementation of AlgorithmWidget that allows using an external QgsProcessingContext.

This module provides a reimplementation of the QGIS processing AlgorithmWidget that
accepts an external QgsProcessingContext through its constructor, instead of always
creating a new context with dataobjects.createContext(self.feedback).

The external context can be provided via the `context` parameter in the constructor.
When provided, this context will be used instead of creating a new one.
"""
from processing.gui.algorithm_widget import AlgorithmWidget as _AlgorithmWidget
from processing.tools import dataobjects
from qgis._gui import QgsProcessingParameterWidgetContext
from qgis.core import (
    QgsProcessingContext,
)
from qgis.core import QgsVectorLayer
from qgis.gui import (
    QgsGui,
)
from qgis.gui import QgsMessageBar

from .processingparamterswidget import ProcessingParametersWidget


class AlgorithmWidget(_AlgorithmWidget):
    def __init__(self, *args,
                 context: QgsProcessingContext | None = None,
                 widget_context: QgsProcessingParameterWidgetContext | None = None,
                 **kwargs):
        self._context = context
        self._widget_context = widget_context
        self._parameters_panel = None

        super().__init__(*args, **kwargs)

    def createWidgetContext(self) -> QgsProcessingParameterWidgetContext:
        if self._widget_context is None:
            self._widgetContext = QgsGui.processingGuiRegistry().createWidgetContext()
            if self._widget_context is None:
                self._widget_context = QgsProcessingParameterWidgetContext()
            if isinstance(self._context, QgsProcessingContext):
                self._widget_context.setProject(self._context.project())
        return self._widget_context

    def processingContext(self) -> QgsProcessingContext:
        if self._context is None:
            self.feedback = self.createFeedback()
            self._context = dataobjects.createContext(self.feedback)
        return self._context

    def createParametersPanel(self, inPlaceMode: bool, activeLayer: QgsVectorLayer | None = None,
                              messageBar: QgsMessageBar | None = None):

        widget = ProcessingParametersWidget(self.algorithm(), inPlaceMode, activeLayer, messageBar)
        widget.registerProcessingContextGenerator(self)
        widget.registerWidgetContextGenerator(self)
        widget.initWidgets()

        self._parameters_panel = widget
        return widget
