from .pyqtgraph.pyqtgraph.SignalProxy import SignalProxy


class SignalProxyUndecorated(SignalProxy):
    """
    A SignalProxy that can be connected with any Qt signal
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def signalReceived(self, *args):
        super().signalReceived(*args)
