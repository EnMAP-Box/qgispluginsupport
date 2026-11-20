import warnings

from .spectralprocessingalgorithmwidget import SpectralProcessingAlgorithmWidget


class SpectralProcessingWidget(SpectralProcessingAlgorithmWidget):

    def __init__(self, *args, **kwds):
        warnings.warn(
            "SpectralProcessingWidget is deprecated. Use SpectralProcessingAlgorithmWidget instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwds)
