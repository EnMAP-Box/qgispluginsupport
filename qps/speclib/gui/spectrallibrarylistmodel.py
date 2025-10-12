from typing import List

from qgis.core import QgsVectorLayer, QgsMapLayerModel
from qps.layerfielddialog import FilteredMapLayerProxyModel
from qps.speclib.core import is_spectral_library


class SpectralLibraryListModel(FilteredMapLayerProxyModel):
    """
    A list model that displays only QgsVectorLayers that contain at least one spectral profile field.
    Automatically updates when layers are added or removed from the project.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        filter = lambda layer: is_spectral_library(layer)
        self.setFilterFunc(filter)
        
    def __getitem__(self, slice):
        return self.spectralLibraries()[slice]

    def __len__(self) -> int:
        return self.rowCount()

    def spectralLibraries(self) -> List[QgsVectorLayer]:
        """
        Returns a list of QgsVectorLayers that contain at least one spectral profile field.
        """
        layers = []
        for i in range(self.rowCount()):
            idx = self.index(i, 0)
            lyr = self.data(idx, role=QgsMapLayerModel.CustomRole.Layer)
            if isinstance(lyr, QgsVectorLayer) and is_spectral_library(lyr):
                layers.append(lyr)
        return layers
