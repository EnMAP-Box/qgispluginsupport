import warnings

warnings.warn(
    "Ths module is deprecated and will be removed in a future version. "
    "Please use 'qps.reimplementation.algorithmwidget' instead.",
    DeprecationWarning,
    stacklevel=2
)
from ..reimplementation.algorithmwidget import AlgorithmWidget

AlgorithmWidget = AlgorithmWidget
