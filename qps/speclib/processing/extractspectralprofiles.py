import os
from typing import Optional

import numpy as np
from osgeo import gdal

from qgis.PyQt.QtCore import QMetaType
from qgis._core import QgsVectorLayer, QgsFeatureRequest, QgsMapLayer
from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterVectorDestination,
    QgsProcessingException,
    QgsFeature,
    QgsField, QgsFields,
    QgsCoordinateTransform,
    QgsProject,
    QgsGeometry,
    QgsVectorFileWriter
)
from qps.fieldvalueconverter import GenericFieldValueConverter
from qps.qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from qps.speclib.core import create_profile_field
from qps.speclib.core.spectralprofile import (
    prepareProfileValueDict,
    encodeProfileValueDict
)


class ExtractSpectralProfiles(QgsProcessingAlgorithm):
    """
    Extracts spectral profiles from a raster layer at locations defined by vector features.
    """

    P_INPUT_RASTER = 'INPUT_RASTER'
    P_INPUT_VECTOR = 'INPUT_VECTOR'
    P_OUTPUT = 'OUTPUT'
    # PROFILE_FIELD_NAME = 'PROFILE_FIELD_NAME'
    COPY_ATTRIBUTES = 'COPY_FIELDS'

    F_SOURCE = 'source'
    F_PROFILE = 'profile'
    F_PX_X = 'px_x'
    F_PX_Y = 'px_y'

    def __init__(self):
        super().__init__()

        self._dstFields: Optional[QgsFields] = None

    def createInstance(self):
        return ExtractSpectralProfiles()

    def name(self):
        return 'extractspectralprofiles'

    def displayName(self):
        return 'Extract Spectral Profiles'

    def group(self):
        return 'Spectral Library'

    def groupId(self):
        return 'spectralibrary'

    def shortHelpString(self):
        return ('Extracts spectral profiles from a raster layer at each vector feature location.\n\n'
                'For point geometries, the pixel value at that location is extracted. '
                'For other geometries, the centroid is used.\n\n'
                'The output is a vector layer with spectral profile data stored in a profile field.')

    def initAlgorithm(self, configuration=None):

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.P_INPUT_RASTER,
                'Input raster layer (spectral data)',
                optional=False
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.P_INPUT_VECTOR,
                'Input vector layer (sample locations)',
                optional=False
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.P_OUTPUT,
                'Output vector layer with spectral profiles'
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        # Get input parameters
        raster_layer = self.parameterAsRasterLayer(parameters, self.P_INPUT_RASTER, context)
        vector_layer = self.parameterAsVectorLayer(parameters, self.P_INPUT_VECTOR, context)
        output_path = self.parameterAsOutputLayer(parameters, self.P_OUTPUT, context)

        if not raster_layer or not raster_layer.isValid():
            raise QgsProcessingException('Invalid input raster layer')

        if not vector_layer or not vector_layer.isValid():
            raise QgsProcessingException('Invalid input vector layer')

        feedback.pushInfo(f'Raster layer: {raster_layer.name()}')
        feedback.pushInfo(f'Vector layer: {vector_layer.name()}')
        feedback.pushInfo(f'Number of bands: {raster_layer.bandCount()}')
        feedback.pushInfo(f'Number of features: {vector_layer.featureCount()}')

        # Get spectral properties from raster
        spectral_props = QgsRasterLayerSpectralProperties.fromRasterLayer(raster_layer)

        xValues = spectral_props.wavelengths() if spectral_props else None
        xUnit = spectral_props.wavelengthUnits()[0] if spectral_props and spectral_props.wavelengthUnits() else None
        bbl = spectral_props.badBands(default=1) if spectral_props else None

        if all([v == 1 for v in bbl]):
            bbl = None

        if xValues and any(xValues):
            feedback.pushInfo(
                f'Wavelength range: {min([w for w in xValues if w])} - {max([w for w in xValues if w])} {xUnit}')

        # Open raster with GDAL
        ds = gdal.Open(raster_layer.source())
        if not ds:
            raise QgsProcessingException('Could not open raster with GDAL')

        no_data = []
        for b in range(ds.RasterCount):
            band: gdal.Band = ds.GetRasterBand(b + 1)
            no_data.append(band.GetNoDataValue())

        geotransform = ds.GetGeoTransform()

        feedback.setProgress(10)

        # Setup coordinate transformation if needed
        raster_crs = raster_layer.crs()
        vector_crs = vector_layer.crs()

        transform = None
        if raster_crs != vector_crs:
            transform = QgsCoordinateTransform(vector_crs, raster_crs, QgsProject.instance())
            feedback.pushInfo(f'Transforming coordinates from {vector_crs.authid()} to {raster_crs.authid()}')
            request_extent = transform.transformBoundingBox(raster_layer.extent(), Qgis.TransformDirection.Reverse)
        else:
            request_extent = raster_layer.extent()

        # Create output fields
        output_fields = QgsFields()
        output_fields.append(create_profile_field(self.F_PROFILE))
        output_fields.append(QgsField(self.F_SOURCE, QMetaType.QString))
        output_fields.append(QgsField(self.F_PX_X, QMetaType.Int))
        output_fields.append(QgsField(self.F_PX_Y, QMetaType.Int))

        if True:
            for f in vector_layer.fields():
                if f.name() not in output_fields.names():
                    f2 = QgsField(f)
                    f2.setEditorWidgetSetup(f.editorWidgetSetup())
                    output_fields.append(f2)

        driver = QgsVectorFileWriter.driverForExtension(os.path.splitext(output_path)[1])
        output_fields = GenericFieldValueConverter.compatibleTargetFields(output_fields, driver)

        self._dstFields = output_fields

        # Prepare output layer
        writer_options = QgsVectorFileWriter.SaveVectorOptions()
        writer_options.driverName = driver
        writer_options.fileEncoding = 'UTF-8'

        writer = QgsVectorFileWriter.create(
            output_path,
            output_fields,
            vector_layer.wkbType(),
            vector_layer.crs(),
            context.transformContext(),
            writer_options
        )

        if writer.hasError() != QgsVectorFileWriter.NoError:
            raise QgsProcessingException(f'Error creating output layer: {writer.errorMessage()}')

        feedback.setProgress(20)

        # Process features
        total_features = vector_layer.featureCount()
        features_processed = 0
        features_skipped = 0

        request = QgsFeatureRequest()
        request.setFilterRect(request_extent)

        for feature in vector_layer.getFeatures(request):

            if feedback.isCanceled():
                break

            if not feature.hasGeometry():
                features_skipped += 1
                continue

            geom = feature.geometry()

            # Transform geometry to raster CRS if needed
            if transform:
                geom_transformed = QgsGeometry(geom)
                geom_transformed.transform(transform)
            else:
                geom_transformed = geom

            # Get point coordinate (use centroid for non-point geometries)
            if geom_transformed.type() == 0:  # Point
                point = geom_transformed.asPoint()
            else:
                point = geom_transformed.centroid().asPoint()

            # Convert geographic coordinates to pixel coordinates
            px = int((point.x() - geotransform[0]) / geotransform[1])
            py = int((point.y() - geotransform[3]) / geotransform[5])

            # Check if pixel is within raster bounds
            if px < 0 or py < 0 or px >= ds.RasterXSize or py >= ds.RasterYSize:
                features_skipped += 1
                feedback.pushWarning(f'Feature {feature.id()} outside raster bounds - skipped')
                continue

            # Extract pixel values from all bands
            yValues = []
            data = ds.ReadAsArray(px, py, 1, 1)
            yValues = np.mean(data, axis=(1, 2)).tolist()
            # exclude no-data values
            yValues = [v if v != nd else None for nd, v in zip(no_data, yValues)]
            # Create profile dictionary
            profile_dict = prepareProfileValueDict(
                y=yValues,
                x=xValues,
                xUnit=xUnit,
                bbl=bbl
            )

            # Create output feature
            out_feature = QgsFeature(output_fields)
            out_feature.setGeometry(feature.geometry())  # Use original geometry

            # Add profile data
            pField = output_fields.field(self.F_PROFILE)
            encoded_profile = encodeProfileValueDict(profile_dict, pField)
            out_feature.setAttribute(self.F_PROFILE, encoded_profile)

            # Copy attributes from input feature
            for field in vector_layer.fields():
                if field.name() in [self.F_PROFILE, self.F_SOURCE, self.F_PX_X, self.F_PX_Y]:
                    continue
                if field.name() in output_fields.names():
                    out_feature.setAttribute(field.name(), feature.attribute(field.name()))

            # Write feature
            r = writer.addFeature(out_feature)

            features_processed += 1

            # Update progress
            progress = 20 + int(70 * features_processed / total_features)
            feedback.setProgress(progress)

        # Clean up
        del writer
        del ds

        lyr = QgsVectorLayer(output_path)
        assert lyr.isValid()
        if True:
            for i in range(lyr.fields().count()):
                name = lyr.fields().at(i).name()
                j = self._dstFields.indexFromName(name)
                if j >= 0:
                    lyr.setEditorWidgetSetup(i, self._dstFields.at(j).editorWidgetSetup())
            lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)

        feedback.setProgress(100)
        feedback.pushInfo(f'Successfully processed {features_processed} features')
        if features_skipped > 0:
            feedback.pushInfo(f'Skipped {features_skipped} features')

        return {self.P_OUTPUT: lyr}
