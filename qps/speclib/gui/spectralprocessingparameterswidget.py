from qgis.core import (
    QgsProcessingParameterDefinition
)
from qgis.core import QgsProcessingParameterRasterLayer, QgsProcessingParameterRasterDestination, QgsVectorLayer

from .spectralprocessingrasterdestination import SpectralProcessingRasterDestination
from .spectralprocessingrasterlayerwidgetwrapper import SpectralProcessingRasterLayerWidgetWrapper
from ...reimplementation.processingparameterswidget import ProcessingParametersWidget


class SpectralProcessingParametersWidget(ProcessingParametersWidget):

    def __init__(self, *args, speclib: QgsVectorLayer, **kwds):
        if not isinstance(speclib, QgsVectorLayer):
            raise TypeError('SpectralProcessingParametersWidget requires a QgsVectorLayer object "speclib"')
        super().__init__(*args, **kwds)

        self._speclib = speclib

    def createParameterWidgetWrapper(self, definition: QgsProcessingParameterDefinition, mode):

        if isinstance(definition, QgsProcessingParameterRasterLayer):
            # input rasters are taken from speclib field inputs.
            # to provide, them, we need to define a special widget
            return SpectralProcessingRasterLayerWidgetWrapper(definition, mode)
        elif isinstance(definition, QgsProcessingParameterRasterDestination):
            wrapper = SpectralProcessingRasterDestination(definition, mode)
            wrapper.setFields(self._speclib.fields())
            return wrapper
        else:
            return super().createParameterWidgetWrapper(definition, mode)
