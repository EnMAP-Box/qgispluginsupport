from typing import List, Dict, Any

from qgis._core import QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource, QgsProcessing, \
    QgsProcessingParameterExpression, QgsProcessingParameterAggregate, QgsProcessingParameterFeatureSink, \
    QgsProcessingFeedback, QgsProcessingContext, QgsProcessingException, QgsDistanceArea, QgsExpression, QgsFields, \
    QgsProcessingFeatureSource, QgsExpressionContext, QgsFeature, QgsFeatureSink, QgsMapLayer, QgsProcessingUtils, \
    QgsWkbTypes, QgsExpressionContextUtils, QgsGeometry, QgsField


class Group(object):
    def __init__(self):
        super().__init__()
        sink: QgsFeatureSink = None
        layer: QgsMapLayer = None
        firstFeature: QgsFeature = None
        lastFeature: QgsFeature = None


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
                sid = 'memory:'
                sink, path = QgsProcessingUtils.createFeatureSink(sid, context,
                                                                            self.mSource.fields(),
                                                                            self.mSource.wkbType(),
                                                                            self.mSource.sourceCrs())

                layer = QgsProcessingUtils.mapLayerFromString(sid, context)

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
