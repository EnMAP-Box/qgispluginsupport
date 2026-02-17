from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsFieldCalculator
from qgis.testing import start_app

start_app()

pA = QgsProject.instance()
pB = QgsProject()

lyrA = QgsVectorLayer('Point?crs=epsg:4326&field=foo:string(20)', 'A', 'memory')
lyrB1 = QgsVectorLayer('Point?crs=epsg:4326&field=bar:string(20)', 'B1', 'memory')
lyrB2 = QgsVectorLayer('Point?crs=epsg:4326&field=bar:string(20)', 'B2', 'memory')
pA.addMapLayer(lyrA)
pB.addMapLayers([lyrB1, lyrB2])

assert pA != pB
assert lyrA.project() == pA
assert lyrB1.project() == pB
assert lyrB2.project() == pB

calc = QgsFieldCalculator(lyrB1)
calc.exec_()
