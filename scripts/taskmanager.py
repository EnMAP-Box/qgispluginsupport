import time, typing, multiprocessing, os
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *
from qgis.testing import start_app


class MyTask(QgsTask):

    def __init__(self, description='MyTask', callback=None):
        super(MyTask, self).__init__(description, QgsTask.CanCancel)
        self.mWasCanceled = False
        self.mSeconds = 5
        self.mCount = 0
        self.mPID = None
        self.mError = None
        self.mCallback = callback

    def run(self):
        try:
            for i in range(self.mSeconds):
                if self.isCanceled():
                    self.mWasCanceled = True
                    return False

                time.sleep(1)
                self.mCount += 1

                self.progressChanged.emit(100 * i / self.mSeconds)
            self.mPID = os.getpid()
        except Exception as ex:
            self.mError = ex
            return False
        return True

    def finished(self, result:bool):
        print('{} FINISHED {}'.format(self.description(), result))
        self.mCallback(self)
        return

class MyTaskDialog(QDialog):

    def __init__(self, *args, **kwds):
        super(MyTaskDialog, self).__init__(*args, **kwds)
        self.setLayout(QHBoxLayout())
        self.btnStart = QPushButton('Start')
        self.btnStart.clicked.connect(self.onStart)
        self.btnCancel = QPushButton('Cancel')
        self.btnCancel.clicked.connect(self.onCancel)
        self.pbar = QProgressBar()
        self.pbar.setRange(0,100)
        self.layout().addWidget(self.btnStart)
        self.layout().addWidget(self.btnCancel)
        self.layout().addWidget(self.pbar)
        self.mTasks = list()

        mgr: QgsTaskManager = QgsApplication.taskManager()
        mgr.progressChanged.connect(self.onProgressChanged)
        mgr.statusChanged.connect(self.onStatusChanged)

    def onProgressChanged(self, taskId, progress):
        mgr: QgsTaskManager = QgsApplication.taskManager()
        #print('{}:{}%'.format(taskId, progress))
        #self.pbar.setValue(int(progress))


    def onFinished(self, task:MyTask):

        print('{} Canceled? {} {}'.format(task.description(), task.isCanceled(), task.mWasCanceled))
        print('{} PID {} CNT {}'.format(task.description(), task.mPID, task.mCount))




    def onStatusChanged(self, taskID, status):

        if status == QgsTask.Queued:
            print('{} Queued'.format(taskID))
        elif status == QgsTask.OnHold:
            print('{} On Hold'.format(taskID))
        elif status == QgsTask.Running:
            print('{} Running'.format(taskID))
        elif status == QgsTask.Complete:
            print('{} Complete'.format(taskID))
            self.pbar.setValue(self.pbar.value() + 1)
        elif status == QgsTask.Terminated:
            print('{} Terminated'.format(taskID))
            self.pbar.setValue(self.pbar.value() + 1)

        if self.pbar.value() >= self.pbar.maximum():
            self.close()

    def addTasks(self, tasks:typing.List[MyTask], start=True):
        self.mTasks.extend(tasks)
        if start:
            self.btnStart.click()

    def onCancel(self):
        mgr: QgsTaskManager = QgsApplication.taskManager()
        for t in mgr.tasks():
            assert isinstance(t, QgsTask)
            t.cancel()

        self.btnStart.setEnabled(True)
        self.btnCancel.setEnabled(False)
        #self.reject()


    def onStart(self):

        mgr:QgsTaskManager = QgsApplication.taskManager()
        tasks = self.mTasks[:]
        self.pbar.setRange(0, len(tasks))
        self.pbar.setValue(0)

        self.mTasks.clear()
        for t in tasks:
            assert isinstance(t, MyTask)
            t.mCallback = self.onFinished
            mgr.addTask(t)

        self.btnStart.setEnabled(False)
        self.btnCancel.setEnabled(True)



def run():

    print('PID MAIN: {}'.format(os.getpid()))
    d1 = MyTaskDialog()
    tasks = []
    for i in range(100):
        tasks.append(MyTask('Task A{}'.format(i+1)))
    d1.setWindowTitle('Dialog 1')
    d1.addTasks(tasks)
    d1.exec_()

    if False:
        d2 = MyTaskDialog()
        tasks = []
        for i in range(7):
            tasks.append(MyTask('Task B {}'.format(i)))
        d2.setWindowTitle('Second Dialog')
        d2.addTasks(tasks)
        d2.exec_()

    print('Script finished')

if __name__ == "__main__":
    app = start_app()
    run()