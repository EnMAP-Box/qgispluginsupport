from qgis.core import QgsProject, QgsField, QgsFeature
from qgis.core import edit
from qgis.gui import QgsFieldCalculator
from qgis.utils import iface
from qps.qgisenums import QMETATYPE_QSTRING
from qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qps.speclib.core.spectralprofile import encodeProfileValueDict

sl = SpectralLibraryUtils.createSpectralLibrary(['profile'])
expected = {
    'A': [2.5, 4.0, 3.5],
    'B': [1, 1, 1],
    'C': [2.5, 3, 3.5, 5.5]

}

data = [
    {'x': [1, 2, 3], 'y': [2, 2, 2], 'class': 'A'},  # A should average t 2.5, 4.0, 3.5
    {'x': [1, 2, 3], 'y': [3, 4, 5], 'class': 'A'},
    {'x': [1, 2, 3], 'y': [1, 1, 1], 'class': 'B'},  # B should average to 1 1 1
    # {'x': [4, 5, 6, 7], 'y': [2, 2, 2, 5], 'class': 'C'},  # C should average to 2.5, 3, 3.5, 5.5
    # {'x': [4, 5, 6, 7], 'y': [3, 4, 5, 6], 'class': 'C'},
    # {'x': [1, 2, 3, 4], 'y': [5, 4, 3, 4], 'class': 'D'},  # D should fail, because arrays have different values
    # {'x': [1, 2], 'y': [5, 4], 'class': 'D'},
    #
]
QgsProject.instance().addMapLayer(sl)
iface.showAttributeTable(sl)

with edit(sl):
    sl.addAttribute(QgsField('class', QMETATYPE_QSTRING))
    for item in data:
        f = QgsFeature(sl.fields())

        data = {'x': item['x'], 'y': item['y']}
        dump = encodeProfileValueDict(data, sl.fields()['profile'])
        f.setAttribute('profile', dump)
        f.setAttribute('class', item['class'])
        assert sl.addFeature(f)

calc = QgsFieldCalculator(sl)
calc.exec_()

for f in sl.getFeatures():
    f: QgsFeature
    print(f.attributeMap())
s = ""
