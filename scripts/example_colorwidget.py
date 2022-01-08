from qgis.PyQt.QtWidgets import QHBoxLayout, QWidget
from qgis.gui import QgsExpressionLineEdit, QgsPropertyOverrideButton
from qgis.gui import QgsColorTextWidget

from qps.testing import start_app
app = start_app()

tw = QgsColorTextWidget()
btn = QgsPropertyOverrideButton()

# w = QgsExpressionLineEdit()
# w.setExpectedOutputFormat('color')
w = QWidget()
l = QHBoxLayout()

l.addWidget(tw)
l.addWidget(btn)
w.setLayout(l)
w.show()

app.exec_()