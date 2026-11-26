import warnings

from ..reimplementation.algorithmwidget import AlgorithmWidget

warnings.warn(
    "This module is deprecated and will be removed in a future version. "
    "Please use 'qps.reimplementation.algorithmwidget' instead.",
    DeprecationWarning,
    stacklevel=2
)
AlgorithmWidget = AlgorithmWidget
