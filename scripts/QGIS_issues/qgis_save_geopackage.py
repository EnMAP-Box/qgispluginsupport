import pathlib
import os
import random
import pickle

from qgis.PyQt.QtCore import QVariant, QByteArray
from qgis.core import QgsProject, QgsFields, QgsField, QgsFeature, QgsWkbTypes, QgsCoordinateReferenceSystem
from qgis.core import QgsVectorFileWriter, QgsProcessingFeedback

feedback = QgsProcessingFeedback()

saveVectorOptions = QgsVectorFileWriter.SaveVectorOptions()
saveVectorOptions.feedback = feedback
saveVectorOptions.driverName = 'GPKG'
saveVectorOptions.symbologyExport = QgsVectorFileWriter.SymbolLayerSymbology
saveVectorOptions.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

path = pathlib.Path('~').expanduser() / 'test.gpkg'
# if path.is_file() and saveVectorOptions.actionOnExistingFile != QgsVectorFileWriter.CreateOrOverwriteLayer:
#    os.remove(path)
# assert not path.is_file()
print(f'file exists: {path}')
fields = QgsFields()
fields.append(QgsField('name', QVariant.String))
fields.append(QgsField('num', QVariant.Int))
fields.append(QgsField('binary', QVariant.ByteArray))

features = []
for i, n in enumerate(['A', 'B', 'C', 'D']):
    feature = QgsFeature(fields)
    feature.setAttribute('name', n)
    feature.setAttribute('num', random.randint(0, 100))
    pkl = QByteArray(pickle.dumps(dict(testdata=f'{i}:{n}')))
    feature.setAttribute('binary', pkl)
    features.append(feature)

transformContext = QgsProject.instance().transformContext()
writer = QgsVectorFileWriter.create(
    fileName=path.as_posix(),
    fields=fields,
    geometryType=QgsWkbTypes.NoGeometry,
    srs=QgsCoordinateReferenceSystem(),
    transformContext=transformContext,
    options=saveVectorOptions,
    # sinkFlags=None,
    # newLayer=newLayerName,
    newFilename=None
)
if writer.hasError() != QgsVectorFileWriter.NoError:
    raise Exception(f'Error when creating {path}: {writer.errorMessage()}')

for f in features:
    if not writer.addFeature(f):
        if writer.hasError() != QgsVectorFileWriter.NoError:
            raise Exception(f'Error when creating feature: {writer.errorMessage()}')
