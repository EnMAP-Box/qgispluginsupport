import logging
from typing import List, Dict, Set

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import QgsFeature, QgsProject, QgsVectorLayer
from ..core.spectrallibrary import SpectralLibraryUtils

logger = logging.getLogger(__name__)

CUSTOM_PROPERTY_CANDIDATE_FIDs = 'qps/candidate_fids'


class SharedSignals(QObject):
    """
    Provides signals to be shared between all SpectraProfileModels.
    """
    candidatesChanged = pyqtSignal(list)

    def __init__(self):
        super().__init__()


class SpectralProfileCandidates(object):
    SHARED_SIGNALS = SharedSignals()

    @classmethod
    def confirmProfileCandidates(cls, layers: List[QgsVectorLayer], block_signal: bool = False) -> Set[str]:
        changed = set()
        for lyr in layers:
            if (isinstance(lyr,
                           QgsVectorLayer) and lyr.isValid() and CUSTOM_PROPERTY_CANDIDATE_FIDs in lyr.customPropertyKeys()):
                lyr.removeCustomProperty(CUSTOM_PROPERTY_CANDIDATE_FIDs)
                changed.add(lyr.id())

        if len(changed) > 0 and not block_signal:
            cls.SHARED_SIGNALS.candidatesChanged.emit(list(changed))
        return changed

    @classmethod
    def removeProfileCandidates(cls, layers: List[QgsVectorLayer], block_signal: bool = False) -> Set[str]:
        changed = set()
        for lyr in layers:
            if isinstance(lyr, QgsVectorLayer):
                fids = lyr.customProperty(CUSTOM_PROPERTY_CANDIDATE_FIDs, None)
                if isinstance(fids, list):
                    stop_editing = lyr.startEditing()
                    lyr.deleteFeatures(fids)
                    lyr.commitChanges(stopEditing=stop_editing)
                    lyr.removeCustomProperty(CUSTOM_PROPERTY_CANDIDATE_FIDs)
                    changed.add(lyr.id())

        if len(changed) > 0 and not block_signal:
            cls.SHARED_SIGNALS.candidatesChanged.emit(list(changed))
        return changed

    @classmethod
    def addProfileCandidates(cls,
                             project: QgsProject,
                             candidates: Dict[str, List[QgsFeature]],
                             add_automatically: bool = False,
                             block_signal: bool = False) -> Set[str]:
        """
        Adds QgsFeatures to vector layers.
        If add_automatically is False (Default), new features are considered to be candidates.
        Candidates are added to the vector layer but will be overwritten with the next call of addProfileCandidates,
        unless being confirmed calling SpectralProfilePlotModel.confirmProfileCandidates()

        Candidate features can be confirmed calling SpectralProfilePlotModel.confirmProfileCandidates(), or
        removed calling SpectralProfilePlotModel.removeProfileCandidates().

        :project QgsProject:
        :param candidates: Dictionary with profile candidates as {layer id:[List of QgsFeatures]}.
        :param add_automatically: If True, the features will be added to the vector layer and not marked as candidates.
        """
        assert isinstance(candidates, dict)

        candidates = {k: list(c) if not isinstance(c, list) else c for k, c in candidates.items()}

        # remove previous candidates from layers for which we do not have new candidates
        candidate_layers = [lyr for lyr in project.mapLayers().values()
                            if
                            isinstance(lyr,
                                       QgsVectorLayer) and CUSTOM_PROPERTY_CANDIDATE_FIDs in lyr.customPropertyKeys()]
        changed_layers = set()
        if len(candidate_layers) > 0:
            changed_layers.update(cls.removeProfileCandidates(candidate_layers, block_signal=True))

        for lid, features in candidates.items():
            lyr = project.mapLayer(lid)
            if not isinstance(lyr, QgsVectorLayer) and lyr.isValid():
                logger.warning(f'Can not get layer for layer id:{lid}')
                continue

            stop_editing = lyr.startEditing()
            new_fids = SpectralLibraryUtils.addProfiles(lyr, features, addMissingFields=True)

            def check_commited_features_added(layer_id, idmap_2):
                new_fids.clear()
                new_fids.extend([f.id() for f in idmap_2])

            lyr.committedFeaturesAdded.connect(check_commited_features_added)
            lyr.commitChanges(stopEditing=stop_editing)
            lyr.committedFeaturesAdded.disconnect(check_commited_features_added)
            if add_automatically:
                lyr.removeCustomProperty(CUSTOM_PROPERTY_CANDIDATE_FIDs)
            else:
                lyr.setCustomProperty(CUSTOM_PROPERTY_CANDIDATE_FIDs, new_fids)
            changed_layers.add(lyr.id())

        if len(changed_layers) > 0 and not block_signal:
            s = ""
            cls.SHARED_SIGNALS.candidatesChanged.emit(list(changed_layers))
        return changed_layers
