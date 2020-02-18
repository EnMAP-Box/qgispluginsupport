
from qgis.PyQt.QtWidgets import QApplication
import qps.testing
import qgis.testing
#app = qgis.testing.start_app()
app = qps.testing.start_app()
print('SHOW1', flush=True)
w = qps.testing.showResources()
w.show()
print('SHOW2', flush=True)
app.exec_()