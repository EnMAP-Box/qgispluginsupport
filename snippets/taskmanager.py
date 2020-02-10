import time, typing, multiprocessing
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from qgis.core import *
from qgis.testing import start_app
app = start_app()

mgr = QgsApplication.taskManager()
assert isinstance(mgr, QgsTaskManager)


class MyTask(QgsTask):

    def __init__(self, description='MyTask'):

        super(MyTask, self).__init__(description, QgsTask.CanCancel)
        self.mWasCanceled = False
        self.mSeconds = 10

    def run(self):

        for i in range(self.mSeconds):
            if self.isCanceled():
                self.mWasCanceled = True
                return False
            time.sleep(1)


            self.progressChanged.emit(100 * i / self.mSeconds)

        return True

    def finished(self, result:bool):

        if result:

            if self.mWasCanceled:
                print('{} CANCELED'.format(self.description()))
            else:
                print('{} FINISHED'.format(self.description()))
        else:
            print('{} NO RESULT'.format(self.description()))



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
        self.mRunningTasks = dict()

        mgr: QgsTaskManager = QgsApplication.taskManager()
        mgr.progressChanged.connect(self.onProgressChanged)
        mgr.statusChanged.connect(self.onStatusChanged)

    def onProgressChanged(self, taskId, progress):
        mgr: QgsTaskManager = QgsApplication.taskManager()
        #print('{}:{}%'.format(taskId, progress))
        #self.pbar.setValue(int(progress))
        self.pbar.setValue(int(100. * mgr.countActiveTasks() / mgr.count()))

    def onStatusChanged(self, taskID, status):



        if status == QgsTask.Queued:
            print('{} Qeued'.format(taskID))
        elif status == QgsTask.OnHold:
            print('{} On Hold'.format(taskID))
        elif status == QgsTask.Running:
            print('{} Running'.format(taskID))
        elif status == QgsTask.Complete:
            print('{} Complete'.format(taskID))

        elif status == QgsTask.Terminated:
            print('{} Terminated'.format(taskID))
            if taskID in self.mRunningTasks:
                self.mRunningTasks.pop(taskID)
        s = ""

    def addTasks(self, tasks:typing.List[QgsTask]):
        self.mTasks.extend(tasks)

    def onCancel(self):
        mgr: QgsTaskManager = QgsApplication.taskManager()
        for lid in list(self.mRunningTasks.keys()):
            task = mgr.task(lid)
            if isinstance(task, QgsTask):
                task.cancel()

        self.reject()


    def onStart(self):

        mgr:QgsTaskManager = QgsApplication.taskManager()
        for t in self.mTasks[:]:
            self.mTasks.remove(t)

            lid = mgr.addTask(t)
            self.mRunningTasks[lid] = t





d1 = MyTaskDialog()
tasks = []
for i in range(1000):
    tasks.append(MyTask('Task A {}'.format(i)))
d1.setWindowTitle('Dialog 1')
d1.addTasks(tasks)
d1.exec_()

d2 = MyTaskDialog()
tasks = []
for i in range(7):
    tasks.append(MyTask('Task B {}'.format(i)))
d2.setWindowTitle('Second Dialog')
d2.addTasks(tasks)
d2.exec_()

print('Script finished')