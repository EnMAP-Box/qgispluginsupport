from qgis.PyQt.QtCore import QObject, pyqtSignal, QSignalBlocker


class MyClass(QObject):
    wasTriggered = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def callBlocked(self):
        self.blockSignals(True)
        self.wasTriggered.emit('blocked')
        self.blockSignals(False)

    def callUnblocked(self):
        self.wasTriggered.emit('unblocked')


M = MyClass()


def onTriggered(message):
    print(f'Triggered: {message}')


M.wasTriggered.connect(onTriggered)

M.callUnblocked()
M.callBlocked()
M.callUnblocked()

print('before')
with QSignalBlocker(M) as blocker:
    M.callUnblocked()
print('after')
M.callUnblocked()
