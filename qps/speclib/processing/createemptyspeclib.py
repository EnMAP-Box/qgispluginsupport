import re
from typing import Dict

from enmapbox.qgispluginsupport.qps.speclib.core.spectrallibrary import SpectralLibraryUtils
from qgis.PyQt.QtCore import QVariant, NULL
from qgis.core import (Qgis, QgsProcessingAlgorithm, QgsProcessingParameterCrs, QgsProcessing, QgsField, QgsFields,
                       QgsMapLayer, QgsVectorLayer, QgsProcessingException, QgsProcessingFeedback, QgsProcessingUtils,
                       QgsProcessingContext,
                       QgsProcessingParameterString, QgsProcessingParameterFieldMapping,
                       QgsProcessingParameterFeatureSink)


class CreateEmptySpectralLibrary(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    PROFILE_FIELDS = 'PROFILE_FIELDS'
    OTHER_FIELDS = 'OTHER_FIELDS'
    CRS = 'CRS'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self._dest_id = None

    def initAlgorithm(self, config: Dict = None):
        # self.addParameter(
        #    QgsProcessingParameterGeometry(
        #        self.GEOMETRY,
        #        description="Geometry Type",
        #        defaultValue=Qgis.GeometryType.Point,
        #        geometryTypes=[Qgis.GeometryType.Point]
        #    )
        # )

        p1 = QgsProcessingParameterCrs(
            self.CRS,
            description="Coordinate Reference System",
            defaultValue='EPSG:4326'
        )
        p1.setHelp('Coordinate Reference System for the output layer.')

        p2 = QgsProcessingParameterString(
            self.PROFILE_FIELDS,
            description="Profile Field Name(s)",
            defaultValue="profiles")
        p2.setHelp(
            'Name of the field to store spectral profiles. '
            "To add multiple fields separate field names by ',' or whitespace")

        p4 = QgsProcessingParameterFieldMapping(
            self.OTHER_FIELDS,
            description='Other fields',
            optional=True,
        )
        p4.setHelp('Define other fields and data types.')

        p3 = QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            description="Output Vector Layer",
            type=Qgis.ProcessingSourceType.VectorPoint,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT,
            createByDefault=True)
        p3.setHelp('Path of output vector.')

        for p in [p1, p2, p3, p4]:
            self.addParameter(p)

    def processAlgorithm(self, parameters, context, feedback):
        # geom_type = self.parameterAsEnum(parameters, self.GEOMETRY, context)

        feedback.pushInfo(f"Parameters: {parameters}")
        geom_type = Qgis.WkbType.Point
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        field_names = self.parameterAsString(parameters, self.PROFILE_FIELDS, context)
        field_names = re.split(r'[,;: ]+', field_names)

        fields = QgsFields()
        other_fields: dict = parameters.get(self.OTHER_FIELDS, {})

        default_field_attributes = {
            'alias': None,
            'comment': None,
            'expression': None,
            'length': 0,
            'precision': 0,
            'sub_type': 0,
            'type': 10,
            'type_name': 'text'}

        # LUT between output QgsProcessingParameterFeatureSink and keywords of QgsField
        LUT_KW = {
            'name': 'name',
            'type': 'type',
            'type_name': 'typeName',
            'length': 'len',
            'precision': 'prec',
            'comment': 'comment',
            'sub_type': 'subType'
        }

        for fdef in other_fields:
            fdef: dict
            # replace QVariant() with None
            for k in fdef.keys():
                if fdef[k] in [QVariant(), NULL]:
                    fdef[k] = None

            if 'name' not in fdef:
                raise QgsProcessingException(f'{self.OTHER_FIELDS} description misses "name": {fdef}')
            fname = fdef['name']
            if fname in field_names:
                new_field = SpectralLibraryUtils.createProfileField(fname)
                if 'comment' in fdef:
                    new_field.setComment(fdef['comment'])
            else:

                field_kw = default_field_attributes.copy()
                field_kw.update(fdef)
                field_kw = {LUT_KW[k]: v for k, v in field_kw.items() if k in LUT_KW}

                new_field = QgsField(**field_kw)
            if 'alias' in fdef:
                new_field.setAlias(fdef['alias'])
            fields.append(new_field)

        for fn in field_names:
            if fn not in fields.names():
                fields.append(SpectralLibraryUtils.createProfileField(fn))

        profile_fields = [f.name() for f in fields if SpectralLibraryUtils.isProfileField(f)]

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields=fields,
                                               geometryType=geom_type,
                                               crs=crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        if hasattr(sink, 'finalize'):
            sink.finalize()
        else:
            sink.flushBuffer()

        del sink
        lyr = QgsProcessingUtils.mapLayerFromString(dest_id, context)

        for f in profile_fields:
            i = lyr.fields().indexFromName(f)
            assert i >= 0, f'Failed to generate profile field "{f}"'
            lyr.setEditorWidgetSetup(i, SpectralLibraryUtils.widgetSetup())
        lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
        self._dest_id = dest_id
        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback: QgsProcessingFeedback):

        result = {}
        if self._dest_id:
            lyr = QgsProcessingUtils.mapLayerFromString(self._dest_id, context)
            assert isinstance(lyr, QgsVectorLayer)
            assert lyr.isValid()
            # lyr.setEditorWidgetSetup(self._field_id, TemporalProfileUtils.widgetSetup())
            lyr.saveDefaultStyle(QgsMapLayer.StyleCategory.Forms)
            assert SpectralLibraryUtils.isProfileLayer(lyr)
            # context.project().addMapLayer(lyr)
            result[self.OUTPUT] = self._dest_id

        # context.project().addMapLayer(self._layer)
        return result

    def createInstance(self):
        return self.__class__()

    @classmethod
    def name(cls):
        return cls.__name__.lower()

    def displayName(self):
        return "Create Temporal Profile Layer"

    def shortHelpString(self):
        return 'Create a new point layer with fields to store temporal profiles.'
