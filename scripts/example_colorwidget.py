from qgis._gui import QgsExpressionLineEdit
from qgis.gui import QgsColorTextWidget

from qps.testing import start_app
app = start_app()

w = QgsColorTextWidget()
w = QgsExpressionLineEdit()
w.setExpectedOutputFormat('color')
w.show()

app.exec_()