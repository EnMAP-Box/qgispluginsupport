from qgis.gui import QgsFileWidget, QgsFilterLineEdit
from qps.testing import start_app

app = start_app()

w = QgsFileWidget()
w.lineEdit().setPlaceholderText('Select L2 root folder')
w.show()
app.exec_()

