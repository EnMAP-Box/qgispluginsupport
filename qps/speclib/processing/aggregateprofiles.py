from typing import List, Dict, Any, Optional, Tuple

from qgis.PyQt.QtCore import QUrl, QVariant
from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource, QgsProcessing, \
    QgsProcessingParameterExpression, QgsProcessingParameterAggregate, QgsProcessingParameterFeatureSink, \
    QgsProcessingFeedback, QgsProcessingContext, QgsProcessingException, QgsDistanceArea, QgsExpression, QgsFields, \
    QgsProcessingFeatureSource, QgsExpressionContext, QgsFeature, QgsFeatureSink, QgsMapLayer, QgsProcessingUtils, \
    QgsWkbTypes, QgsExpressionContextUtils, QgsGeometry, QgsField, QgsVectorLayer, QgsAggregateCalculator, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsFeedback


class Group(object):
    def __init__(self):
        super().__init__()
        sink: QgsFeatureSink = None
        layer: QgsMapLayer = None
        firstFeature: QgsFeature = None
        lastFeature: QgsFeature = None


class AggregateCalculator(QgsAggregateCalculator):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)


class AggregateMemoryLayer(QgsVectorLayer):
    memoryLayerFieldType = {QVariant.Int: 'integer',
                            QVariant.LongLong: 'long',
                            QVariant.Double: 'double',
                            QVariant.String: 'string',
                            QVariant.Date: 'date',
                            QVariant.Time: 'time',
                            QVariant.DateTime: 'datetime',
                            QVariant.ByteArray: 'binary',
                            QVariant.Bool: 'boolean'}
    uri = 'memory:'

    def __init__(self,
                 name: str,
                 fields: QgsFields,
                 geometryType: QgsWkbTypes.Type,
                 crs: QgsCoordinateReferenceSystem):

        # see QgsMemoryProviderUtils.createMemoryLayer

        geomType = QgsWkbTypes.displayString(geometryType)
        if geomType in ['', None]:
            geomType = "none"

        parts = []
        if crs.isValid():
            if crs.authid() != '':
                parts.append(f'crs={crs.authid()}')
            else:
                parts.append(f'crs=wkt:{crs.toWkt(QgsCoordinateReferenceSystem.WKT_PREFERRED)}')
        for field in fields:
            field: QgsField
            lengthPrecission = f'({field.length()},{field.precision()})'
            if field.type() in [QVariant.List, QVariant.StringList]:
                ftype = field.subType()
                ltype = '[]'
            else:
                ftype = field.type()
                ltype = ''

            parts.append(f'field={QUrl.toPercentEncoding(field.name())}:'
                         f'{self.memoryLayerFieldType.get(ftype, "string")}'
                         f'{lengthPrecission}{ltype}')

        uri = f'{geomType}?{"&".join(parts)}'
        options = QgsVectorLayer.LayerOptions(QgsCoordinateTransformContext())
        options.skipCrsValidation = True
        super().__init__(uri, name, 'memory', options=options)

    def aggregate(self,
                  aggregate: QgsAggregateCalculator.Aggregate,
                  fieldOrExpression: str,
                  parameters: QgsAggregateCalculator.AggregateParameters = None,
                  context: Optional[QgsExpressionContext] = None,
                  fids: Optional[Any] = None,
                  feedback: Optional[QgsFeedback] = None) -> Tuple[Any, str]:

        print('# aggregate')
        s = ""


class AggregateProfiles(QgsProcessingAlgorithm):
    P_INPUT = 'INPUT'
    P_GROUP_BY = 'GROUP_BY'
    P_AGGREGATES = 'AGGREGATES'
    P_OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()

        self.mSource: QgsProcessingFeatureSource = None
        self.mGroupBy: str = None
        self.mGroupByExpression: QgsExpression = None
        self.mGeometryExpression: QgsExpression = None
        self.mFields: QgsFields = QgsFields()
        self.mDa: QgsDistanceArea = QgsDistanceArea()
        self.mExpressions: List[QgsExpression] = []
        self.mAttributesRequireLastFeature: List[int] = []

        self._TempLayers: List[AggregateMemoryLayer] = []

    def name(self) -> str:
        return 'aggregateprofiles'

    def displayName(self) -> str:
        return 'Aggregate Spectral Profiles'

    def shortHelpString(self) -> str:
        info = """
        Aggregate the profiles in a spectral library
        """
        return info

    def tags(self) -> List[str]:
        return 'attributes,sum,mean,collect,dissolve,statistics'.split(',')

    def group(self) -> str:
        return 'Spectral Library'

    def groupId(self) -> str:
        return 'spectrallibrary'

    def createInstance(self) -> 'QgsProcessingAlgorithm':
        return AggregateProfiles()

    def initAlgorithm(self, configuration: Dict[str, Any] = ...) -> None:
        self.addParameter(
            QgsProcessingParameterFeatureSource(self.P_INPUT, 'Input spectral library', [QgsProcessing.TypeVector]))
        self.addParameter(
            QgsProcessingParameterExpression(self.P_GROUP_BY, 'Group by expression (NULL to group all features)',
                                             "NULL", self.P_INPUT))
        self.addParameter(QgsProcessingParameterAggregate(self.P_AGGREGATES, 'Aggregates', self.P_INPUT))
        self.addParameter(QgsProcessingParameterFeatureSink(self.P_OUTPUT, 'Aggregated'))

    def prepareAlgorithm(self, parameters: Dict[str, Any], context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> bool:

        self.mSource = self.parameterAsSource(parameters, self.P_INPUT, context)
        if self.mSource is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.P_INPUT))

        self.mGroupBy = self.parameterAsExpression(parameters, self.P_GROUP_BY, context)

        self.mDa.setSourceCrs(self.mSource.sourceCrs(), context.transformContext())

        self.mGroupByExpression = self.createExpression(self.mGroupBy, context)
        self.mGeometryExpression = self.createExpression(f'collect($geometry, {self.mGroupBy})', context)

        aggregates: List[Dict] = parameters[self.P_AGGREGATES]

        for currentAttributeIndex, aggregate in enumerate(aggregates):
            aggregateDef: dict = aggregate
            fname = str(aggregateDef['name'])
            if fname in [None, '']:
                raise QgsProcessingException('Field name cannot be empty')

            ftype = int(aggregateDef['type'])
            ftypeName = aggregateDef['type_name']
            fsubType = int(aggregateDef['sub_type'])

            flength = int(aggregateDef['length'])
            fprecision = int(aggregateDef['precision'])

            self.mFields.append(QgsField(fname, ftype, ftypeName, flength, fprecision, '', fsubType))

            aggregateType = str(aggregateDef['aggregate'])
            source = str(aggregateDef['input'])
            delimiter = str(aggregateDef['delimiter'])

            expression: str = None
            if aggregateType == 'first_value':
                expression = source
            elif aggregateType == 'last_value':
                expression = source
                self.mAttributesRequireLastFeature.append(currentAttributeIndex)
            elif aggregateType in ['concatenate', 'concatenate_unique']:
                expression = f'{aggregateType}({source}, {self.mGroupBy}, TRUE, {QgsExpression.quotedString(delimiter)})'
            else:
                expression = f'{aggregateType}({source}, {self.mGroupBy})'
            self.mExpressions.append(self.createExpression(expression, context))

        return True

    def processAlgorithm(self,
                         parameters: Dict[str, Any],
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        expressionContext: QgsExpressionContext = self.createExpressionContext(parameters, context, self.mSource)
        self.mGeometryExpression.prepare(expressionContext)

        # Group features in memory layers
        count = self.mSource.featureCount()
        progressStep = 50.0 if count > 0 else 1

        groups: Dict[Any, Group] = dict()
        groupSinks: list[QgsFeatureSink] = []

        keys: list = list()
        for current, feature in enumerate(self.mSource.getFeatures()):
            feature: QgsFeature
            expressionContext.setFeature(feature)
            groupByValue = self.mGroupByExpression.evaluate(expressionContext)
            if self.mGroupByExpression.hasEvalError():
                raise QgsProcessingException(
                    f'Evaluation error in group by expression "{self.mGroupByExpression.expression()}"'
                    f':{self.mGroupByExpression.evalErrorString()}')
            key = groupByValue if isinstance(groupByValue, list) else [groupByValue]
            key = tuple(key)
            group = groups.get(key, None)
            if group is None:
                # sink, path = QgsProcessingUtils.createFeatureSink('memory:', context,
                #                                                            self.mSource.fields(),
                #                                                            self.mSource.wkbType(),
                #                                                            self.mSource.sourceCrs())

                sink, path = self._createFeatureSink(context,
                                                     self.mSource.fields(),
                                                     self.mSource.wkbType(),
                                                     self.mSource.sourceCrs())

                layer = QgsProcessingUtils.mapLayerFromString(path, context)
                assert isinstance(layer, QgsMapLayer)
                group = Group()
                group.sink = sink
                group.layer = layer
                group.firstFeature = feature
                groups[key] = group
                keys.append(key)

            group: Group = groups[key]
            if not group.sink.addFeature(feature, flags=QgsFeatureSink.FastInsert):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, ''))
            group.lastFeature = feature
            feedback.setProgress(current * progressStep)
            if feedback.isCanceled():
                break

        groupSinks.clear()

        sink, destId = self.parameterAsSink(parameters, self.P_OUTPUT,
                                            context, self.mFields,
                                            QgsWkbTypes.multiType(self.mSource.wkbType()),
                                            self.mSource.sourceCrs())
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.P_OUTPUT))

        # calculate aggregates on memory layers
        if len(keys) > 0:
            progressStep = 50.0 / len(keys)

        for current, key in enumerate(keys):
            group: Group = groups[key]

            exprContext = self.createExpressionContext(parameters, context)
            exprContext.appendScope(QgsExpressionContextUtils.layerScope(group.layer))
            exprContext.setFeature(group.firstFeature)

            geometry: QgsGeometry = self.mGeometryExpression.evaluate(exprContext)
            if geometry and not ((geometry.isEmpty() or geometry.isNull())):
                geometry = QgsGeometry.unaryUnion(geometry.asGeometryCollection())
                if geometry.isEmpty():
                    keyString: List[str] = []
                    for v in key:
                        keyString.append(str(v))

                    raise QgsProcessingException(
                        f'Impossible to combine geometries for {self.mGroupBy} = {",".join(keyString)}')

            attributes = []
            for currentAttributeIndex, it in enumerate(self.mExpressions):
                exprContext.setFeature(group.lastFeature
                                       if currentAttributeIndex in self.mAttributesRequireLastFeature
                                       else group.firstFeature)
                if it.isValid():
                    value = it.evaluate(exprContext)
                    if it.hasEvalError():
                        raise QgsProcessingException(
                            f'evaluation error in expression "{it.expression()}":{it.evalErrorString()}')
                    attributes.append(value)
                else:
                    attributes.append(None)

            # write output feature
            outFeat = QgsFeature()
            outFeat.setGeometry(geometry)
            outFeat.setAttributes(attributes)
            if not sink.addFeature(outFeat, QgsFeatureSink.FastInsert):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, self.P_OUTPUT))

            feedback.setProgress(50.0 + current * progressStep)
            if feedback.isCanceled():
                break

        results = {self.P_OUTPUT: destId}
        return results

    def _createFeatureSink(self,
                           context: QgsExpressionContext,
                           fields: QgsFields,
                           wkbType: QgsWkbTypes.GeometryType,
                           crs: QgsCoordinateReferenceSystem) -> Tuple[QgsFeatureSink, str]:

        createOptions = dict(encoding='utf-8')
        name = f'AggregationMemoryLayer{len(self._TempLayers)}'
        layer = AggregateMemoryLayer(name, fields, wkbType, crs)
        destination = layer.id()
        self._TempLayers.append(layer)
        sink = layer.dataProvider()
        context.temporaryLayerStore().addMapLayer(layer)

        return sink, destination

    def supportInPlaceEdit(self, layer: QgsMapLayer) -> bool:
        return False

    def createExpression(self, expressionString: str, context: QgsProcessingContext):
        expr = QgsExpression(expressionString)
        expr.setGeomCalculator(self.mDa)
        expr.setDistanceUnits(context.distanceUnit())
        expr.setAreaUnits(context.areaUnit())
        if expr.hasParserError():
            raise QgsProcessingException(f'Parser error in expression "{expressionString}":{expr.parserErrorString()}')
        return expr
