from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import QgsPointXY


class MyQObject(QObject):
    def __init__(self, *args):
        super(MyQObject, self).__init__(*args)


class MyPoint(QgsPointXY):
    def __init__(self, *args):
        super(MyPoint, self).__init__(*args)


class SignalingClass(QObject):
    sig = pyqtSignal([MyQObject], [MyPoint])

    def __init__(self):
        super().__init__()


def genericSlot(*args):
    print(f'slot argument type: {type(args[0])}')


# from qgis.testing import start_app
# start_app() # uncomment to raise KeyError: 'there is no matching overloaded signal'

SC = SignalingClass()

print(SC.sig[MyQObject].signal)
SC.sig[MyQObject].connect(genericSlot)
SC.sig[MyQObject].emit(MyQObject())

print(SC.sig[MyPoint].signal)
SC.sig[MyPoint].connect(genericSlot)  # fails with start_app()
SC.sig[MyPoint].emit(MyPoint(100, 200))  # fails with #start_app()

# stop_app()
