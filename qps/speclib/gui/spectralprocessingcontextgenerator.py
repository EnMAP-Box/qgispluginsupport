from typing import List

from qgis.core import QgsVectorLayer, QgsProcessingContext, QgsProject, QgsRasterLayer
from qgis.gui import QgsProcessingContextGenerator, QgsProcessingParametersGenerator, \
    QgsProcessingParameterWidgetContext

from ..core.spectrallibraryrasterdataprovider import createRasterLayers


class SpectralProcessingContextGenerator(QgsProcessingContextGenerator, QgsProcessingParametersGenerator):

    def __init__(self, speclib: QgsVectorLayer):
        super(SpectralProcessingContextGenerator, self).__init__()

        self._speclib = speclib
        self._example_layers: List[QgsRasterLayer] = []

        self._project = QgsProject()

        self._speclib.attributeAdded.connect(self.updateExampleLayers)
        self._speclib.attributeDeleted.connect(self.updateExampleLayers)

        self._p_context = QgsProcessingContext()
        self._p_context.setProject(self._project)

        self.updateExampleLayers()

    def processingContext(self) -> QgsProcessingContext:
        return self._p_context

    def createWidgetContext(self) -> QgsProcessingParameterWidgetContext:

        c = QgsProcessingParameterWidgetContext()
        c.registerProcessingContextGenerator(self)
        c.setProject(self._project)

        return c

    def createProcessingParameters(self, flags=None):
        if flags is None:
            flags = QgsProcessingParametersGenerator.Flags()

        return {}

    def updateExampleLayers(self):

        for layer in self._example_layers:
            if lyr := self._project.mapLayer(layer.id()):
                self._project.takeMapLayer(lyr)
        self._example_layers.clear()
        self._example_layers.extend(createRasterLayers(self._speclib))
        self._project.addMapLayers(self._example_layers)

    def exampleLayers(self) -> List[QgsRasterLayer]:
        return self._example_layers[:]
