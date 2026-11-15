import warnings

from ..reimplementation.algorithmwidget import AlgorithmWidget

warnings.warn(
    "Ths module is deprecated and will be removed in a future version. "
    "Please use 'qps.reimplementation.algorithmwidget' instead.",
    DeprecationWarning,
    stacklevel=2
)
AlgorithmWidget = AlgorithmWidget
