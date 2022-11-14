from PyQt5.QtCore import QObject, pyqtSignal

from qgis.testing import start_app
from qgis.core import QgsPointXY
from qgis.gui import QgsMapCanvas

class MyObject(QObject):

    def __init__(self):
        super(MyObject, self).__init__()

class MyPoint(QgsPointXY):
    def __init__(self, *args):
        super(MyPoint, self).__init__(*args)


class SignalingClass(QObject):

    sigLocationChanged = pyqtSignal([MyPoint], [MyObject], [object])

    def __init__(self):
        super().__init__()

def genericSignalSlot(*args):
    info = 'Received:'

    for a in args:
        info += f'\n {type(a)}:{a}'
    print(info)

SC = SignalingClass()
SC.sigLocationChanged.connect(genericSignalSlot)

print(SC.sigLocationChanged.signal) # default signal
print(SC.sigLocationChanged[MyPoint].signal)
print(SC.sigLocationChanged[MyObject].signal)
print(SC.sigLocationChanged[object].signal)

print('Signal MyPoint via [MyPoint]')
SC.sigLocationChanged[MyPoint].emit(MyPoint(100, 200))
print('Signal MyPoint via [object]')
SC.sigLocationChanged[object].emit(MyPoint(100, 200))

print('Signal MyObject via [MyObject]')
SC.sigLocationChanged[MyObject].emit(MyObject())
print('Signal MyObject via [object]')
SC.sigLocationChanged[object].emit(MyObject())

s = ""




