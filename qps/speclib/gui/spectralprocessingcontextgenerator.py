from typing import List

from qgis.core import QgsMapLayer
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

        self._p_context = QgsProcessingContext()
        self._p_context.setProject(self._project)

        self._speclib.attributeAdded.connect(self.updateExampleLayers)
        self._speclib.attributeDeleted.connect(self.updateExampleLayers)

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

        EXISTING = dict()
        UPDATES = dict()

        for layer in self._example_layers:
            EXISTING[layer.name()] = layer
        for layer in createRasterLayers(self._speclib):
            UPDATES[layer.name()] = layer

        all_layers = list(EXISTING.values()) + list(UPDATES.values())

        to_remove = [k for k in EXISTING.keys() if k not in UPDATES]
        to_add = [k for k in UPDATES.keys() if k not in EXISTING]

        layers_to_add = []
        for name in to_add:
            lyr = UPDATES.get(name)
            if isinstance(lyr, QgsRasterLayer):
                layers_to_add.append(lyr)
        if len(layers_to_add) > 0:
            self._project.addMapLayers(layers_to_add)

        for name in to_remove:
            lyr = EXISTING.get(name)
            if isinstance(lyr, QgsMapLayer):
                self._project.takeMapLayer(lyr)

        self._example_layers.clear()
        for lyr in self._project.mapLayers().values():
            if lyr in all_layers:
                self._example_layers.append(lyr)

    def exampleLayers(self) -> List[QgsRasterLayer]:
        return self._example_layers[:]
