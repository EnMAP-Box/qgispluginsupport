import site
import pathlib
import importlib

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget, QGridLayout

if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

TESTS = REPO / 'tests' / 'speclib'
site.addsitedir(TESTS)
from qgis._core import QgsMapLayerModel, QgsApplication, QgsRasterDataProvider, Qgis, QgsProcessingParameterRasterLayer, \
    QgsProcessingParameterMultipleLayers, QgsProcessingContext, QgsVectorLayer, QgsProcessingRegistry, QgsFeature

from qgis._gui import QgsMapToolIdentify, QgsProcessingContextGenerator, QgsProcessingParameterWidgetContext, \
    QgsProcessingGui
from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas
from qgis.core import QgsProject, QgsRasterLayer, QgsContrastEnhancement
from qps import initAll
from qps.speclib.core.spectralprofile import groupBySpectralProperties
from qps.speclib.gui.spectralprocessingwidget import SpectralProcessingRasterLayerWidgetWrapper, \
    SpectralProcessingWidget
from qps.speclib.core import spectrallibraryrasterdataprovider, profile_fields

importlib.reload(spectrallibraryrasterdataprovider)
from qps.speclib.core.spectrallibraryrasterdataprovider import registerDataProvider, VectorLayerFieldRasterDataProvider
from qps.testing import TestObjects, start_app, StartOptions
from qps.utils import qgisAppQgisInterface
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget

uri = 'Point?crs=epsg:4326&field=name:string(20)'
layer = QgsVectorLayer(uri, 'Layer', 'memory')
layer.startEditing()
f = QgsFeature(layer.fields())
f.setAttribute('name', 'A')
layer.addFeature(f)

if True:
    print('Feature not committed')
else:
    layer.commitChanges(False)
    print('Feature committed')

def onAttributeValueChanged(fid, i, newValue):
    print(f'AttributeValueChanged: ({fid},{i})={newValue}')

def onEditCommandEnded(*args):
    print('changedAttributeValues() after editCommandEnded:')
    print(layer.editBuffer().changedAttributeValues())

layer.attributeValueChanged.connect(onAttributeValueChanged)
layer.editCommandEnded.connect(onEditCommandEnded)

layer.beginEditCommand('Change attribute values')
i = layer.fields().lookupField('name')
for f in layer.getFeatures():
    layer.changeAttributeValue(f.id(), i, 'B')
layer.endEditCommand()

