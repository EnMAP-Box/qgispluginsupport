from qgis.PyQt.QtCore import QModelIndex, QObject, Qt
from qgis.core import QgsProcessingAlgorithm, QgsProcessingOutputRasterLayer, QgsProcessingRegistry
from qgis.core import QgsProcessingOutputMultipleLayers
from qgis.gui import QgsProcessingRecentAlgorithmLog, QgsProcessingToolboxProxyModel


def has_raster_output(alg: QgsProcessingAlgorithm) -> bool:
    if not isinstance(alg, QgsProcessingAlgorithm):
        return False

    for output in alg.outputDefinitions():
        if isinstance(output, (QgsProcessingOutputRasterLayer, QgsProcessingOutputMultipleLayers)):
            return True
    return False


class SpectralProcessingAlgorithmModel(QgsProcessingToolboxProxyModel):
    """
    A proxy model to show only QgsProcessingAlgorithms that use
    rasters as inputs and outputs, and therefore can be used
    to process spectral profiles.
    """

    def __init__(self,
                 parent: QObject | None = None,
                 registry: QgsProcessingRegistry | None = None,
                 recentLog: QgsProcessingRecentAlgorithmLog | None = None):
        super().__init__(parent, registry, recentLog)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QModelIndex):

        tbm = self.toolboxModel()
        sourceIdx = tbm.index(sourceRow, 0, sourceParent)
        if tbm.isAlgorithm(sourceIdx):
            alg = tbm.algorithmForIndex(sourceIdx)
            if alg.flags() & QgsProcessingAlgorithm.Flag.FlagHideFromToolbox:
                return False
            return (
                super().filterAcceptsRow(sourceRow, sourceParent) and has_raster_output(alg)
            )
        # isParameter was introduced with QGIS 3.44
        if hasattr(tbm, 'isParameter') and tbm.isParameter(sourceIdx):
            return False
        else:
            return super().filterAcceptsRow(sourceRow, sourceParent)
