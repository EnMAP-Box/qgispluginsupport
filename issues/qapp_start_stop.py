from qgis.PyQt.QtWidgets import QApplication

app = QApplication([])
app.exit(0)

print('2nd start')
app = QApplication([])
app.exit(0)
print('Done')
