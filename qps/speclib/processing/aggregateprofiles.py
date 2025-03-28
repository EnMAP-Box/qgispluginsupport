from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from qgis.PyQt.QtCore import NULL, QByteArray, QMetaType, QVariant
from qgis.core import edit, QgsAggregateCalculator, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, \
    QgsDistanceArea, QgsEditorWidgetSetup, QgsExpression, QgsExpressionContext, QgsExpressionContextScope, \
    QgsExpressionContextUtils, QgsExpressionFunction, QgsExpressionNode, QgsExpressionNodeColumnRef, \
    QgsExpressionNodeFunction, QgsFeature, QgsFeatureRequest, QgsFeatureSink, QgsFeedback, QgsField, QgsFields, \
    QgsGeometry, QgsMapLayer, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingException, \
    QgsProcessingFeatureSource, QgsProcessingFeedback, QgsProcessingParameterAggregate, \
    QgsProcessingParameterExpression, QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource, \
    QgsProcessingUtils, QgsVectorLayer, QgsWkbTypes
from .. import EDITOR_WIDGET_REGISTRY_KEY
from ..core import is_profile_field
from ..core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict, \
    ProfileEncoding
from ...qgisenums import QMETATYPE_BOOL, QMETATYPE_DOUBLE, QMETATYPE_INT, QMETATYPE_QDATE, QMETATYPE_QDATETIME, \
    QMETATYPE_QSTRING, \
    QMETATYPE_QTIME
from ...qgsfunctions import HM, SPECLIB_FUNCTION_GROUP, SpectralMath, StaticExpressionFunction


class Group(object):
    def __init__(self):
        super().__init__()
        sink: QgsFeatureSink = None
        layer: QgsMapLayer = None
        firstFeature: QgsFeature = None
        lastFeature: QgsFeature = None


class AggregateProfilesCalculator(QgsAggregateCalculator):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mFIDs = None

    def setFidsFilter(self, fids: Any) -> None:
        super(AggregateProfilesCalculator, self).setFidsFilter(fids)
        self.mFIDs = fids

    def calculate(self,
                  aggregate: QgsAggregateCalculator.Aggregate,
                  fieldOrExpression: str,
                  context: Optional[QgsExpressionContext] = ...,
                  feedback: Optional[QgsFeedback] = ...) -> Optional[dict]:

        if not isinstance(self.layer(), QgsVectorLayer):
            return QVariant()
        error = ''
        context = context if isinstance(context, QgsExpressionContext) else self.layer().createExpressionContext()
        if not isinstance(feedback, QgsFeedback):
            feedback = context.feedback()

        expression = QgsExpression(fieldOrExpression)
        attrNum = QgsExpression.expressionToLayerFieldIndex(fieldOrExpression, self.layer())
        if attrNum == -1:
            context.setFields(self.layer().fields())
            expression = QgsExpression(fieldOrExpression)
            if expression.hasParserError() or not expression.prepare(context):
                error = expression.parserErrorString() if expression.hasParserError() else expression.evalErrorString()
                return QVariant()

        if not expression:
            lst = set(self.layer().fields().at(attrNum).name())
        else:
            lst = expression.referencedColumns()

        attrField = self.layer().fields().at(attrNum)

        request = QgsFeatureRequest()
        request.setFlags(
            QgsFeatureRequest.NoFlags if expression and expression.needsGeometry() else QgsFeatureRequest.NoGeometry)
        request.setSubsetOfAttributes(lst, self.layer().fields())
        if self.mFIDs:
            request.setFilterFids(self.mFIDs[:])

        # todo: set order by
        resultType = QVariant.UserType
        request.setExpressionContext(context)
        request.setFeedback(feedback)
        features = list(self.layer().getFeatures(request))

        profileDictionaries = []
        n = None
        x = None
        xUnit = None
        yUnit = None
        bbl = None

        # get values for x axis, x axis unit and y axis unit
        for feature in features:
            d = decodeProfileValueDict(feature.attribute(attrNum), numpy_arrays=True)
            if len(d) > 0:
                if n is None:
                    # 1st profile is reference
                    n = len(d['y'])
                    profileDictionaries.append(d)
                elif len(d['y'] == n):
                    profileDictionaries.append(d)

                if x is None:
                    x = d.get('x')

                if xUnit is None:
                    xUnit = d.get('xUnit')

                if yUnit is None:
                    yUnit = d.get('yUnit')

        if len(profileDictionaries) == 0:
            return QVariant()
        y = None
        x = profileDictionaries[0].get('x', None)

        y_values = [d['y'] for d in profileDictionaries]
        vstack = np.vstack(y_values)

        if aggregate == QgsAggregateCalculator.Aggregate.Mean:
            y = np.mean(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.Median:
            y = np.median(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.Max:
            y = np.max(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.Min:
            y = np.min(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.Count:
            y = len(profileDictionaries)
        elif aggregate == QgsAggregateCalculator.Aggregate.Sum:
            y = np.sum(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.StDev:
            y = np.std(vstack, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.FirstQuartile:
            y = np.quantile(vstack, 0.25, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.ThirdQuartile:
            y = np.quantile(vstack, 0.75, axis=0)
        elif aggregate == QgsAggregateCalculator.Aggregate.Range:
            y = np.max(vstack, axis=0) - np.min(vstack, axis=0)
        else:
            raise NotImplementedError(f'aggregate={aggregate}')

        if isinstance(y, np.ndarray):
            dump = prepareProfileValueDict(y=y.tolist(), x=x, xUnit=xUnit, bbl=bbl)
            return dump

        return None


class AggregateMemoryLayer(QgsVectorLayer):
    memoryLayerFieldType = {QMETATYPE_INT: 'integer',
                            QVariant.LongLong: 'long',
                            QMETATYPE_DOUBLE: 'double',
                            QMETATYPE_QSTRING: 'string',
                            QMETATYPE_QDATE: 'date',
                            QMETATYPE_QTIME: 'time',
                            QMETATYPE_QDATETIME: 'datetime',
                            QVariant.ByteArray: 'binary',
                            QMETATYPE_BOOL: 'boolean'}
    uri = 'memory:'

    def __init__(self,
                 name: str,
                 fields: QgsFields,
                 geometryType: QgsWkbTypes.Type,
                 crs: QgsCoordinateReferenceSystem):

        # see QgsMemoryProviderUtils.createMemoryLayer

        uri = AggregateMemoryLayer.createInitArguments(crs, fields, geometryType)
        options = QgsVectorLayer.LayerOptions(QgsCoordinateTransformContext())
        options.skipCrsValidation = True
        super().__init__(uri, name, 'memory', options=options)

    @staticmethod
    def createInitArguments(crs, fields, geometryType):
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
            if field.type() in [QVariant.List, QMetaType.QStringList]:
                ftype = field.subType()
                ltype = '[]'
            else:
                ftype = field.type()
                ltype = ''

            parts.append(f'field={field.name()}:'
                         f'{AggregateMemoryLayer.memoryLayerFieldType.get(ftype, "string")}'
                         f'{lengthPrecission}{ltype}')
        uri = f'{geomType}?{"&".join(parts)}'
        return uri

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

        self.mOutputProfileFields: List[str] = []
        self._TempLayers: List[AggregateMemoryLayer] = []
        self._results: Dict = dict()

    def name(self) -> str:
        return 'aggregateprofiles'

    def displayName(self) -> str:
        return 'Aggregate Spectral Profiles'

    def shortHelpString(self) -> str:
        info = """This algorithm takes a vector or table layer and aggregates features based on a group by expression.
In addition to the native QGIS Aggregate algorithm (native:aggregate), it allows to aggregate spectral profiles.

Features for which group by expression return the same value are grouped together.

It is possible to group all source features together using constant value in group by parameter, example: NULL.

It is also possible to group features using multiple fields using Array function, example: Array("Field1", "Field2").
Geometries (if present) are combined into one multipart geometry for each group.
Output attributes are computed depending on each given aggregate definition.

Please not that not each aggregate function might be available for each field type.
        """
        return info

    def tags(self) -> List[str]:
        return 'attributes,sum,mean,collect,dissolve,statistics'.split(',')

    def group(self) -> str:
        return 'Spectral Library'

    def groupId(self) -> str:
        return 'spectrallibrary'

    def createInstance(self) -> 'AggregateProfiles':
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
        vl = self.parameterAsVectorLayer(parameters, self.P_INPUT, context)
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

            field: QgsField = QgsField(fname, ftype, ftypeName, flength, fprecision, '', fsubType)

            aggregateType = str(aggregateDef['aggregate'])
            source = str(aggregateDef['input'])
            delimiter = str(aggregateDef['delimiter'])

            source_idx = QgsExpression.expressionToLayerFieldIndex(source, vl)
            is_profile = source_idx > -1 and is_profile_field(self.mSource.fields().at(source_idx))
            if is_profile:
                field.setEditorWidgetSetup(QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

            expression: str = None
            if aggregateType == 'first_value':
                expression = source
            elif aggregateType == 'last_value':
                expression = source
                self.mAttributesRequireLastFeature.append(currentAttributeIndex)
            elif aggregateType in ['concatenate', 'concatenate_unique']:
                if is_profile:
                    expression = self.spectralProfileAggregateExpression(aggregateType, source, True, self.mGroupBy)
                    self.mOutputProfileFields.append(fname)
                else:
                    expression = f'{aggregateType}({source}, {self.mGroupBy}, TRUE, {QgsExpression.quotedString(delimiter)})'
            else:
                if is_profile:
                    expression = self.spectralProfileAggregateExpression(aggregateType, source, False, self.mGroupBy)
                    self.mOutputProfileFields.append(fname)
                else:
                    expression = f'{aggregateType}({source}, {self.mGroupBy})'

            self.mFields.append(field)
            self.mExpressions.append(self.createExpression(expression, context))

        return True

    def spectralProfileAggregateExpression(self, aggregateType: str, source: str, concatenate: bool, groupBy):
        # expr = f"spectralAggregate(@layer, '{aggregateType}', '{source}', '{groupBy}')"
        expr = f'{aggregateType}_profile({source}, {groupBy})'

        return expr

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

        profile_attribute_indices = [i for i, field in enumerate(self.mFields) if is_profile_field(field)]

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

                    if currentAttributeIndex in profile_attribute_indices:
                        value = encodeProfileValueDict(value, encoding=self.mFields[currentAttributeIndex])

                    attributes.append(value)
                else:
                    attributes.append(None)

            # write output feature
            outFeat = QgsFeature(self.mFields)
            outFeat.setGeometry(geometry)
            outFeat.setAttributes(attributes)
            if not sink.addFeature(outFeat, QgsFeatureSink.FastInsert):
                raise QgsProcessingException(self.writeFeatureError(sink, parameters, self.P_OUTPUT))

            feedback.setProgress(50.0 + current * progressStep)
            if feedback.isCanceled():
                break
        del sink
        self._results = {self.P_OUTPUT: destId}

        return self._results

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> Dict[str, Any]:

        vl = self._results.get(self.P_OUTPUT)
        if isinstance(vl, str):
            lyr_id = vl
            vl = QgsProcessingUtils.mapLayerFromString(vl, context,
                                                       allowLoadingNewLayers=True,
                                                       typeHint=QgsProcessingUtils.LayerHint.Vector)
            if isinstance(vl, QgsVectorLayer) and vl.isValid():
                for fieldName in self.mOutputProfileFields:
                    idx = vl.fields().lookupField(fieldName)
                    if idx > -1:
                        setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
                        vl.setEditorWidgetSetup(idx, setup)
                vl.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)
            else:
                feedback.pushWarning(f'Unable to reload {lyr_id} as vectorlayer and set profile fields')
        return {self.P_OUTPUT: vl}

    def _createFeatureSink(self,
                           context: QgsExpressionContext,
                           fields: QgsFields,
                           wkbType: QgsWkbTypes.GeometryType,
                           crs: QgsCoordinateReferenceSystem) -> Tuple[QgsFeatureSink, str]:

        createOptions = dict(encoding='utf-8')
        name = f'AggregationMemoryLayer{len(self._TempLayers)}'
        uri = AggregateMemoryLayer.createInitArguments(crs, [], wkbType)
        # layer = AggregateMemoryLayer(name, fields, wkbType, crs)
        layer = QgsVectorLayer(uri, name, 'memory')
        with edit(layer):
            for field in fields:
                layer.addAttribute(QgsField(field))

        for field in fields:
            idx = layer.fields().lookupField(field.name())
            layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup(field.editorWidgetSetup().type(), {}))
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


class SpectralAggregation(QgsExpressionFunction):
    """
    Doese the same like fcnAggregateGeneric, just for spectral profiles
    """

    def __init__(self):
        group = SPECLIB_FUNCTION_GROUP
        name = 'spectralAggregate'

        args = [
            QgsExpressionFunction.Parameter('layer', optional=False),
            QgsExpressionFunction.Parameter('aggregate', optional=False),
            QgsExpressionFunction.Parameter('expression', optional=False),
            QgsExpressionFunction.Parameter('filter', optional=True),
            QgsExpressionFunction.Parameter('concatenator', defaultValue='', optional=True),
            QgsExpressionFunction.Parameter('order_by', optional=True),
        ]
        helptext = HM.helpText(name, args)
        # super().__init__(name, args, group, helptext)
        super().__init__(name, -1, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        if len(values) < 1:
            parent.setEvalErrorString(f'{self.name()}: requires at least 1 argument')
            return QVariant()
        if not isinstance(values[-1], str):
            parent.setEvalErrorString(f'{self.name()}: last argument needs to be a string')
            return QVariant()

        encoding = None

        if SpectralMath.RX_ENCODINGS.search(values[-1]) and len(values) >= 2:
            encoding = ProfileEncoding.fromInput(values[-1])
            iPy = -2
        else:
            iPy = -1

        pyExpression: str = values[iPy]
        if not isinstance(pyExpression, str):
            parent.setEvalErrorString(
                f'{self.name()}: Argument {iPy + 1} needs to be a string with python code')
            return QVariant()

        try:
            profilesData = values[0:-1]
            DATA = dict()
            fieldType: QgsField = None
            for i, dump in enumerate(profilesData):
                d = decodeProfileValueDict(dump, numpy_arrays=True)
                if len(d) == 0:
                    continue
                if i == 0:
                    DATA.update(d)
                    if encoding is None:
                        #       # use same input type as output type
                        if isinstance(dump, (QByteArray, bytes)):
                            encoding = ProfileEncoding.Bytes
                        elif isinstance(dump, dict):
                            encoding = ProfileEncoding.Map
                        else:
                            encoding = ProfileEncoding.Text

                n = i + 1
                # append position number
                # y of 1st profile = y1, y of 2nd profile = y2 ...
                for k, v in d.items():
                    if isinstance(k, str):
                        k2 = f'{k}{n}'
                        DATA[k2] = v

            assert context.fields()
            exec(pyExpression, DATA)

            # collect output profile values
            d = prepareProfileValueDict(x=DATA.get('x', None),
                                        y=DATA['y'],
                                        xUnit=DATA.get('xUnit', None),
                                        yUnit=DATA.get('yUnit', None),
                                        bbl=DATA.get('bbl', None),
                                        )
            return encodeProfileValueDict(d, encoding)
        except Exception as ex:
            parent.setEvalErrorString(f'{ex}')
            return QVariant()

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


def spfcnAggregateGeneric(
        aggregate: QgsAggregateCalculator.Aggregate,
        values: list,
        parameters: QgsAggregateCalculator.AggregateParameters,
        context: QgsExpressionContext,
        parent: QgsExpression,
        orderByPos: int = -1
):
    if not isinstance(context, QgsExpressionContext):
        parent.setEvalErrorString('Cannot use aggregate function in this context')
        return QVariant()

    # find current layer:
    vl: QgsVectorLayer = context.variable('layer')
    if not isinstance(vl, QgsVectorLayer):
        parent.setEvalErrorString('Cannot use aggregate function in this context')
        return QVariant()

    nodeProfile: QgsExpressionNode = values[0]
    nodeGroupBy: QgsExpressionNode = values[1]
    nodeFilter: QgsExpressionNode = values[2]
    nodeFormat: QgsExpressionNode = values[3]

    subExpression: str = nodeProfile.dump()
    if subExpression == 'NULL':
        # no profile field defined. Take that from 1st
        for field in context.fields():
            if is_profile_field(field):
                subExpression = field.name()
                break
        if subExpression == 'NULL':
            parent.setEvalErrorString('Unable to find spectral profile field.')
            return None

    groupBy: Optional[str] = None
    dmp = nodeGroupBy.dump()
    if dmp != 'NULL':
        # todo: handle none-string cases
        if isinstance(nodeGroupBy, QgsExpressionNodeColumnRef):
            groupBy = QgsExpression.quotedColumnRef(dmp)
        else:
            groupBy = dmp

    # the filter node
    dmp = nodeFilter.dump()
    if dmp != 'NULL':
        # todo: handle none-string cases
        parameters.filter = QgsExpression.quotedValue(dmp)

    encoding = None
    dmp = nodeFormat.dump()
    if dmp not in ['NULL', NULL, None]:
        try:
            encoding = ProfileEncoding.fromInput(dmp)
        except Exception as ex:
            parent.setEvalErrorString(f'{ex}')

    if encoding is None:
        encoding = ProfileEncoding.Map

    orderBy: str = None
    if orderByPos >= 0 and len(values) > orderByPos:
        node = values[orderByPos]
        if isinstance(node, QgsExpressionNode):
            dmp = node.dump()
            if dmp not in ['', None, NULL, 'NULL']:
                orderBy = dmp
                parameters.orderBy.append(QgsFeatureRequest.OrderByClause(orderBy))
    # build up filter with group by
    # find current group by value

    if groupBy:
        groupByExp = QgsExpression(groupBy)
        groupByValue = groupByExp.evaluate(context)
        if groupByValue:
            groupByClause = f'{groupBy} = {QgsExpression.quotedValue(groupByValue)}'
        else:
            groupByClause = f'{groupBy} is {QgsExpression.quotedValue(groupByValue)}'
        if parameters.filter != '':
            parameters.filter = f'({parameters.filter}) AND ({groupByClause})'
        else:
            parameters.filter = groupByClause

    subExp = QgsExpression(subExpression)
    filterExp = QgsExpression(parameters.filter)

    isStatic: bool = True
    refVars = filterExp.referencedVariables() | subExp.referencedVariables()
    for varName in refVars:
        scope: QgsExpressionContextScope = context.activeScopeForVariable(varName)
        if scope and not scope.isStatic(varName):
            isStatic = False
            break

    if not isStatic:
        cacheKey = 'agg:{}:{}:{}:{}:{}:{}:{}'.format(vl.id(), aggregate, subExpression, parameters.filter,
                                                     context.feature().id(), context.feature(), orderBy)
    else:
        cacheKey = 'agg:{}:{}:{}:{}:{}'.format(vl.id(), aggregate, subExpression, parameters.filter, orderBy)

    if context.hasCachedValue(cacheKey):
        return context.cachedValue(cacheKey)

    ok: bool = False

    subContext: QgsExpressionContext = QgsExpressionContext(context)
    subScope: QgsExpressionContextScope = QgsExpressionContextScope()
    subScope.setVariable('parent', context.feature())
    subContext.appendScope(subScope)

    field_index = QgsExpression.expressionToLayerFieldIndex(subExpression, vl)
    result = QVariant()
    if field_index != -1:
        field = vl.fields().at(field_index)
        fids = []
        if parameters.filter != '':
            request = QgsFeatureRequest()
            request.setFilterExpression(parameters.filter)
            request.setFlags(QgsFeatureRequest.NoGeometry)
            request.setSubsetOfAttributes([])
            fids = [f.id() for f in vl.getFeatures(request)]

        if is_profile_field(field):
            AGG = AggregateProfilesCalculator(vl)
        else:
            AGG = QgsAggregateCalculator(vl)

        if len(fids) > 0:
            AGG.setFidsFilter(fids)

        AGG.setParameters(parameters)
        try:
            result = AGG.calculate(aggregate, subExpression, context, context.feedback())
        except Exception as ex:
            parent.setEvalErrorString(f'Unable to aggregate:<br>{ex}')
            return QVariant()

    if isinstance(result, dict):
        if encoding is not None:
            result = encodeProfileValueDict(result, encoding)
        context.setCachedValue(cacheKey, result)
        return result
    # print(f'# Result: {result}')
    return QVariant()
    # return


def spfcnAggregateMinimum(values: list, context: QgsExpressionContext, parent: QgsExpression,
                          node: QgsExpressionNodeFunction):
    return spfcnAggregateGeneric(QgsAggregateCalculator.Aggregate.Min, values,
                                 QgsAggregateCalculator.AggregateParameters(), context, parent)


def spfcnAggregateMaximum(values: list, context: QgsExpressionContext, parent: QgsExpression,
                          node: QgsExpressionNodeFunction):
    return spfcnAggregateGeneric(QgsAggregateCalculator.Aggregate.Max, values,
                                 QgsAggregateCalculator.AggregateParameters(), context, parent)


def spfcnAggregateMean(values: list, context: QgsExpressionContext, parent: QgsExpression,
                       node: QgsExpressionNodeFunction):
    return spfcnAggregateGeneric(QgsAggregateCalculator.Aggregate.Mean, values,
                                 QgsAggregateCalculator.AggregateParameters(), context, parent)


def spfcnAggregateMedian(values: list, context: QgsExpressionContext, parent: QgsExpression,
                         node: QgsExpressionNodeFunction):
    return spfcnAggregateGeneric(QgsAggregateCalculator.Aggregate.Median, values,
                                 QgsAggregateCalculator.AggregateParameters(), context, parent)


def createSpectralProfileFunctions() -> List[QgsExpressionFunction]:
    aggParams = [
        QgsExpressionFunction.Parameter('profiles', optional=True),
        QgsExpressionFunction.Parameter('group_by', optional=True),
        QgsExpressionFunction.Parameter('filter', optional=True),
        QgsExpressionFunction.Parameter('encoding', optional=True),

    ]

    functions = [
        # StaticExpressionFunction('aggregateProfiles', aggParams2,
        #                         spfcnAggregate, 'Aggregates', '',
        #                         usesGeometry=usesGeometryCallback,
        #                         referencedColumns=referencedColumnsCallback),
        StaticExpressionFunction('mean_profile',
                                 aggParams,
                                 spfcnAggregateMean,
                                 SPECLIB_FUNCTION_GROUP,
                                 None, False, [],
                                 True),
        StaticExpressionFunction('median_profile',
                                 aggParams,
                                 spfcnAggregateMedian,
                                 SPECLIB_FUNCTION_GROUP,
                                 None,
                                 False,
                                 [],
                                 True),
        StaticExpressionFunction('minimum_profile',
                                 aggParams,
                                 spfcnAggregateMinimum,
                                 SPECLIB_FUNCTION_GROUP,
                                 None, False,
                                 [],
                                 True),
        StaticExpressionFunction('maximum_profile',
                                 aggParams,
                                 spfcnAggregateMaximum,
                                 SPECLIB_FUNCTION_GROUP,
                                 None,
                                 False,
                                 [],
                                 True),
    ]

    return functions
