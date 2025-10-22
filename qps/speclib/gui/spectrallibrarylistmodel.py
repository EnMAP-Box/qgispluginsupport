from typing import List

from qgis.core import QgsVectorLayer, QgsMapLayerModel
from ..core import is_spectral_library
from ...layerfielddialog import FilteredMapLayerProxyModel


class SpectralLibraryListModel(FilteredMapLayerProxyModel):
    """
    A list model that displays only QgsVectorLayers that contain at least one spectral profile field.
    Automatically updates when layers are added or removed from the project.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.setShowAll(False)
        filter = lambda layer: is_spectral_library(layer)
        self.setFilterFunc(filter)

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        """
        Returns a list of QgsVectorLayers that contain at least one spectral profile field.
        """
        return [l for l in self.layers() if isinstance(l, QgsVectorLayer) and is_spectral_library(l)]
