import pathlib
from pathlib import Path
from typing import List, Union, Optional

from qgis.core import (QgsCoordinateReferenceSystem,
                       QgsMapLayer,
                       QgsFeature,
                       QgsProcessingFeedback, QgsVectorFileWriter, QgsVectorLayer)
from qgis.core import QgsProject
from ..core.spectralprofile import SpectralProfileFileReader, SpectralProfileFileWriter
from ...fieldvalueconverter import GenericFieldValueConverter


class GeoPackageSpectralLibraryWriter(SpectralProfileFileWriter):

    def __init__(self, *args, crs: QgsCoordinateReferenceSystem, **kwds):
        super().__init__(*args, **kwds)
        self.mCrs: QgsCoordinateReferenceSystem = crs

    @classmethod
    def id(cls) -> str:
        return 'GeoPackage'

    @classmethod
    def filterString(cls) -> str:
        return 'Geopackage (*.gpkg)'

    def writeFeatures(self, path: Union[str, Path],
                      features: List[QgsFeature],
                      feedback: Optional[QgsProcessingFeedback] = None,
                      **kwargs) -> List[Path]:

        path = str(path)

        if feedback is None:
            feedback = QgsProcessingFeedback()

        if len(features) == 0:
            feedback.pushInfo('No features to write')
            return []

        f0 = features[0]

        srcFields = f0.fields()
        wkbType = f0.geometry().wkbType()

        layerName = Path(path).stem
        ogrDataSourceOptions = []
        ogrLayerOptions = [
            f'IDENTIFIER={layerName}',
            f'DESCRIPTION={layerName}']

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
        options.feedback = feedback
        options.datasourceOptions = ogrDataSourceOptions
        options.layerOptions = ogrLayerOptions
        options.fileEncoding = 'UTF-8'
        options.skipAttributeCreation = False
        options.driverName = 'GPKG'

        transformationContext = QgsProject.instance().transformContext()

        dstFields = GenericFieldValueConverter.compatibleTargetFields(srcFields, options.driverName)
        converter = GenericFieldValueConverter(srcFields, dstFields)
        options.fieldValueConverter = converter

        writer: QgsVectorFileWriter = QgsVectorFileWriter.create(path,
                                                                 dstFields,
                                                                 # fields,
                                                                 wkbType,
                                                                 self.mCrs,
                                                                 transformationContext,
                                                                 options)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            feedback.reportError(f'Error when creating {path}: {writer.errorMessage()}')
            return []

        if not writer.addFeatures(features):
            if writer.hasError() != QgsVectorFileWriter.NoError:
                feedback.reportError(f'Error when creating feature: {writer.errorMessage()}')
                return []
        del writer

        lyr = QgsVectorLayer(path)
        if lyr.isValid():
            for dstField in dstFields:
                i = lyr.fields().lookupField(dstField.name())
                if i >= 0:
                    lyr.setEditorWidgetSetup(i, dstField.editorWidgetSetup())
            msg, success = lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            if not success:
                feedback.reportError(msg)

        return [Path(path)]


class GeoPackageSpectralLibraryReader(SpectralProfileFileReader):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def id(cls) -> str:
        return 'GeoPackage'

    @classmethod
    def canReadFile(cls, path: Union[str, pathlib.Path]) -> bool:
        return pathlib.Path(path).suffix == '.gpkg'

    def asFeatures(self) -> List[QgsFeature]:
        lyr = QgsVectorLayer(self.path().as_posix())
        lyr.loadDefaultStyle()
        return list(lyr.getFeatures())
