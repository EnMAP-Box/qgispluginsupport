# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qgsfunctions.py
    QgsFunctions to be used in QgsExpressions,
    e.g. to access SpectralLibrary data
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import json
import os
import pathlib
import re
import sys
import typing
from json import JSONDecodeError
from typing import Union, List, Set, Callable, Iterable, Any, Tuple, Dict

from qgis.PyQt.QtCore import QByteArray
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtCore import QVariant, NULL
from qgis.core import QgsVectorLayer, QgsMapLayer
from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem
from qgis.core import QgsExpression, QgsFeatureRequest, QgsExpressionFunction, \
    QgsMessageLog, Qgis, QgsExpressionContext, QgsExpressionNode
from qgis.core import QgsExpressionNodeFunction, QgsField
from qgis.core import QgsGeometry, QgsRasterLayer, QgsRasterDataProvider, QgsRaster, QgsPointXY
from .qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from .speclib.core.spectrallibrary import FIELD_VALUES
from .speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict, \
    ProfileEncoding

SPECLIB_FUNCTION_GROUP = "Spectral Libraries"

QGIS_FUNCTION_INSTANCES: typing.Dict[str, QgsExpressionFunction] = dict()


class HelpStringMaker(object):

    def __init__(self):

        helpDir = pathlib.Path(__file__).parent / 'function_help'
        self.mHELP = dict()

        assert helpDir.is_dir()

        for e in os.scandir(helpDir):
            if e.is_file() and e.name.endswith('.json'):
                with open(e.path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        if isinstance(data, dict) and 'name' in data.keys():
                            self.mHELP[data['name']] = data
                    except JSONDecodeError as err:
                        raise Exception(f'Failed to read {e.path}:\n{err}')

    def helpText(self, name: str,
                 parameters: typing.List[QgsExpressionFunction.Parameter] = []) -> str:
        """
        re-implementation of QString QgsExpression::helpText( QString name )
        to generate similar help strings
        :param name:
        :param args:
        :return:
        """
        html = [f'<h3>{name}</h3>']
        LUT_PARAMETERS = dict()
        for p in parameters:
            LUT_PARAMETERS[p.name()] = p

        JSON = self.mHELP.get(name, None)
        ARGUMENT_DESCRIPTIONS = {}
        ARGUMENT_NAMES = []
        if isinstance(JSON, dict):
            for D in JSON.get('arguments', []):
                if isinstance(D, dict) and 'arg' in D:
                    ARGUMENT_NAMES.append(D['arg'])
                    ARGUMENT_DESCRIPTIONS[D['arg']] = D.get('description', '')

        if not isinstance(JSON, dict):
            print(f'No help found for {name}', file=sys.stderr)
            return '\n'.join(html)

        description = JSON.get('description', None)
        if description:
            html.append(f'<div class="description"><p>{description}</p></div>')

        arguments = JSON.get('arguments', None)
        if arguments:
            hasOptionalArgs: bool = False
            html.append('<h4>Syntax</h4>')
            syntax = f'<div class="syntax">\n<code>{name}('

            if len(parameters) > 0:
                delim = ''
                syntaxParameters = set()
                for P in parameters:
                    assert isinstance(P, QgsExpressionFunction.Parameter)
                    syntaxParameters.add(P.name())
                    optional: bool = P.optional()
                    if optional:
                        hasOptionalArgs = True
                        syntax += '['
                    syntax += delim
                    syntax += f'<span class="argument">{P.name()}'
                    defaultValue = P.defaultValue()
                    if isinstance(defaultValue, str):
                        defaultValue = f"'{defaultValue}'"
                    if defaultValue not in [None, QVariant()]:
                        syntax += f'={defaultValue}'

                    syntax += '</span>'
                    if optional:
                        syntax += ']'
                    delim = ','
                # add other optional arguments from help file
                for a in ARGUMENT_NAMES:
                    if a not in syntaxParameters:
                        pass

            syntax += ')</code>'

            if hasOptionalArgs:
                syntax += '<br/><br/>[ ] marks optional components'
            syntax += '</div>'
            html.append(syntax)

            if len(parameters) > 0:
                html.append('<h4>Arguments</h4>')
                html.append('<div class="arguments"><table>')

                for P in parameters:
                    assert isinstance(P, QgsExpressionFunction.Parameter)

                    description = ARGUMENT_DESCRIPTIONS.get(P.name(), '')
                    html.append(f'<tr><td class="argument">{P.name()}</td><td>{description}</td></tr>')

            html.append('</table></div>')

        examples = JSON.get('examples', None)
        if examples:
            html.append('<h4>Examples</h4>\n<div class=\"examples\">\n<ul>\n')

            for example in examples:
                str_exp = example['expression']
                str_ret = example['returns']
                str_note = example.get('note')
                html.append(f'<li><code>{str_exp}</code> &rarr; <code>{str_ret}</code>')
                if str_note:
                    html.append(f'({str_note})')
                html.append('</li>')
            html.append('</ul>\n</div>\n')

        return '\n'.join(html)


HM = HelpStringMaker()

"""
@qgsfunction(args='auto', group='String')
def format_py(fmt: str, *args):
    assert isinstance(fmt, str)
    fmtArgs = args[0:-2]
    feature, parent = args[-2:]

    return fmt.format(*fmtArgs)
"""


class Format_Py(QgsExpressionFunction):

    def __init__(self):
        group = 'String'
        name = 'format_py'

        args = [
            QgsExpressionFunction.Parameter('fmt', optional=False, defaultValue=FIELD_VALUES),
            QgsExpressionFunction.Parameter('arg1', optional=True),
            QgsExpressionFunction.Parameter('arg2', optional=True),
            QgsExpressionFunction.Parameter('argN', optional=True),
        ]
        helptext = HM.helpText(name, args)
        super(Format_Py, self).__init__(name, -1, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):
        if len(values) == 0 or values[0] in (None, NULL):
            return None
        assert isinstance(values[0], str)
        fmt: str = values[0]
        fmtArgs = values[1:]
        try:
            return fmt.format(*fmtArgs)
        except (ValueError, AttributeError):
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class SpectralEncoding(QgsExpressionFunction):

    def __init__(self):
        group = SPECLIB_FUNCTION_GROUP
        name = 'encodeProfile'

        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=False),
            QgsExpressionFunction.Parameter('encoding', optional=False),

        ]
        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):

        ba, encoding = values
        if context:
            feature = context.feature()
        if not isinstance(context, QgsExpressionContext):
            return None

        if ba is None:
            return None

        try:
            assert isinstance(encoding, str)
            encoding = encoding.lower()
            assert encoding in ('map', 'bytes', 'json', 'text')

            assert context.fields()
            values = decodeProfileValueDict(ba)
            if encoding == 'map':
                return values
            elif encoding == 'json':
                return encodeProfileValueDict(values, QgsField('dummy', 8))
            elif encoding == 'bytes':
                return encodeProfileValueDict(values, QgsField('dummy', QVariant.ByteArray))
            elif encoding == 'text':
                return encodeProfileValueDict(values, QgsField('dummy', QVariant.String))
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class StaticExpressionFunction(QgsExpressionFunction):
    """
    A Re-Implementation of QgsStaticExpressionFunction (not available in python API)
    """

    def __init__(self,
                 fnname: str,
                 params,
                 fcn,
                 group: str,
                 helpText: str = '',
                 usesGeometry: Union[bool, QgsExpressionNodeFunction] = None,
                 referencedColumns: Set[str] = None,
                 lazyEval: bool = False,
                 aliases: List[str] = [],
                 handlesNull: bool = False):
        super().__init__(fnname, params, group, helpText, lazyEval, handlesNull, False)

        self.mFnc = fcn
        self.mAliases = aliases
        self.mUsesGeometry = False
        self.mUsesGeometryFunc = None

        if usesGeometry is not None:
            if isinstance(usesGeometry, (bool, int)):
                self.mUsesGeometry = bool(usesGeometry)
            else:
                self.mUsesGeometryFunc = usesGeometry

        self.mReferencedColumnsFunc = referencedColumns
        self.mIsStatic = False
        self.mIsStaticFunc = None
        self.mPrepareFunc = None

    def aliases(self) -> List[str]:
        return self.mAliases

    def usesGeometry(self, node: QgsExpressionNodeFunction) -> bool:
        if self.mUsesGeometryFunc:
            return self.mUsesGeometryFunc(node)
        else:
            return self.mUsesGeometry

    def referencedColumns(self, node: QgsExpressionNodeFunction) -> Set[str]:
        if self.mReferencedColumnsFunc:
            return self.mReferencedColumnsFunc(node)
        else:
            return super().referencedColumns(node)

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent: QgsExpression,
                 context: QgsExpressionContext) -> bool:
        if self.mIsStaticFunc:
            return self.mIsStaticFunc(node, parent, context)
        else:
            return super().isStatic(node, parent, context)

    def prepare(self, node: QgsExpressionNodeFunction, parent: QgsExpression, context: QgsExpressionContext) -> bool:
        if self.mPrepareFunc:
            return self.mPrepareFunc(node, parent, context)
        else:
            return True

    def setIsStaticFunction(self,
                            isStatic: Callable[[QgsExpressionFunction, QgsExpression, QgsExpressionContext], bool]):

        self.mIsStaticFunc = isStatic

    def setIsStatic(self, isStatic: bool):
        self.mIsStaticFunc = None
        self.mIsStatic = isStatic

    def setPrepareFunction(self,
                           prepareFunc: Callable[[QgsExpressionFunction, QgsExpression, QgsExpressionContext], bool]):
        self.mPrepareFunc = prepareFunc

    @staticmethod
    def allParamsStatic(node: QgsExpressionNodeFunction, parent: QgsExpression, context: QgsExpressionContext) -> bool:
        if node:
            for argNode in node.args():
                argNode: QgsExpressionNode
                if not argNode.isStatic(parent, context):
                    return False
        return True

    def func(self,
             values: Iterable[Any],
             context: QgsExpressionContext,
             parent: QgsExpression,
             node: QgsExpressionNodeFunction) -> Any:
        if self.mFnc:
            return self.mFnc(values, context, parent, node)
        else:
            return QVariant()


class RasterProfile(QgsExpressionFunction):

    def __init__(self):
        group = SPECLIB_FUNCTION_GROUP
        name = 'rasterProfile'

        args = [
            QgsExpressionFunction.Parameter('layer', optional=False),
            QgsExpressionFunction.Parameter('geometry', optional=True, defaultValue='@geometry'),
            QgsExpressionFunction.Parameter('encoding', optional=True, defaultValue='map'),
        ]

        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def parseArguments(self, values: tuple, context: QgsExpressionContext) \
            -> Tuple[QgsRasterLayer, QgsGeometry, QgsCoordinateTransform, ProfileEncoding]:

        lyrR = values[0]
        geom = values[1]
        format = values[2]

        if isinstance(lyrR, str):
            layers = QgsExpression('@layers').evaluate(context)
            for lyr in layers:
                if isinstance(lyr, QgsRasterLayer) and lyrR in [lyr.name(), lyr.id()]:
                    lyrR = lyr
                    break

        if not isinstance(lyrR, QgsRasterLayer):
            return None, None, None, None

        if not isinstance(geom, QgsGeometry):
            geom = QgsExpression('@geometry').evaluate(context)

        if not isinstance(geom, QgsGeometry):
            return None, None, None, None

        trans = context.cachedValue('crs_trans')
        if not isinstance(trans, QgsCoordinateTransform):
            lyr_crs = QgsExpression('@layer_crs').evaluate(context)
            crsV = QgsCoordinateReferenceSystem(lyr_crs)
            if isinstance(crsV, QgsCoordinateReferenceSystem) and crsV.isValid() and isinstance(lyrR, QgsRasterLayer):
                trans = QgsCoordinateTransform()
                trans.setSourceCrs(crsV)
                trans.setDestinationCrs(lyrR.crs())
                context.setCachedValue('crs_trans', trans)

        if format is None:
            # default: dictionary
            format = ProfileEncoding.Dict

            # todo: consider target field (if known from context)

        format = ProfileEncoding.fromInput(format)

        return lyrR, geom, trans, format

    CACHED_SPECTRAL_PROPERTIES = 'spectralProperties'

    def spectralProperties(self, rasterLayer: QgsRasterLayer, context: QgsExpressionContext) -> dict:

        spectral_properties = context.cachedValue(self.CACHED_SPECTRAL_PROPERTIES)
        if spectral_properties is None:
            sp = QgsRasterLayerSpectralProperties.fromRasterLayer(rasterLayer)

            bbl = sp.badBands()
            wl = sp.wavelengths()
            wlu = sp.wavelengthUnits()

            spectral_properties = dict(bbl=bbl, wl=wl, wlu=wlu)
            context.setCachedValue(self.CACHED_SPECTRAL_PROPERTIES, spectral_properties)

        return spectral_properties

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        if not isinstance(context, QgsExpressionContext):
            return None
        try:
            rasterLayer, geom, crs_trans, encoding = self.parseArguments(values, context)
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

        if not isinstance(geom, QgsGeometry):
            return None

        if not isinstance(rasterLayer, QgsRasterLayer):
            parent.setEvalErrorString('Unable to find raster layer')
            return None

        try:
            if not crs_trans.isShortCircuited():
                assert geom.transform(crs_trans) == Qgis.GeometryOperationResult.Success

            if not rasterLayer.extent().intersects(geom.boundingBox()):
                return None

            spectral_properties = self.spectralProperties(rasterLayer, context)
            wl = spectral_properties['wl']
            wlu = spectral_properties['wlu'][0]

            bbl = spectral_properties['bbl']

            point: QgsPointXY = geom.asPoint()
            dp: QgsRasterDataProvider = rasterLayer.dataProvider()
            results = dp.identify(point, QgsRaster.IdentifyFormatValue).results()

            y = list(results.values())
            y = [v if isinstance(v, (int, float)) else float('NaN') for v in y]

            result = prepareProfileValueDict(x=wl, y=y, xUnit=wlu, bbl=bbl)

            if encoding != ProfileEncoding.Dict:
                encoding = ProfileEncoding.fromInput(encoding)
                result = encodeProfileValueDict(result, encoding)
            return result

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class ExpressionFunctionUtils(object):

    @staticmethod
    def extractVectorLayer(p: QgsExpressionFunction.Parameter,
                           value, context: QgsExpressionContext) -> QgsVectorLayer:

        s = ""
        pass

    @staticmethod
    def cachedCrsTransformation(layer: QgsMapLayer,
                                context: QgsExpressionContext,
                                ) \
            -> QgsCoordinateTransform:

        k = f'crstrans_{context.variable("layer_id")}->{layer.id()}'
        trans = context.cachedValue(k)
        if not isinstance(trans, QgsCoordinateTransform):
            lyr_crs = QgsExpression('@layer_crs').evaluate(context)
            crs = QgsCoordinateReferenceSystem(lyr_crs)
            if isinstance(crs, QgsCoordinateReferenceSystem) and crs.isValid():
                trans = QgsCoordinateTransform()
                trans.setSourceCrs(crs)
                trans.setDestinationCrs(layer.crs())
                context.setCachedValue(k, trans)
        return trans
    @staticmethod
    def extractRasterLayer(p: QgsExpressionFunction.Parameter,
                           value,
                           context: QgsExpressionContext) -> QgsRasterLayer:

        if isinstance(value, str):
            for lyr in QgsExpression('@layers').evaluate(context):
                if isinstance(lyr, QgsRasterLayer) and value in [lyr.name(), lyr.id()]:
                    return lyr

        if isinstance(value, QgsRasterLayer):
            return value
        else:
            return None

    @staticmethod
    def extractSpectralProfileField(p: QgsExpressionFunction.Parameter,
                                    value,
                                    context: QgsExpressionFunction,
                                    raise_error: bool = True) -> QgsField:

        s = ""

    @staticmethod
    def extractGeometry(p: QgsExpressionFunction.Parameter,
                        value,
                        context: QgsExpressionFunction):

        if not isinstance(value, QgsGeometry):
            for a in ['@geometry', '$geometry']:
                v = QgsExpression(a).evaluate(context)
                if isinstance(v, QgsGeometry):
                    return v
        return None

    @staticmethod
    def extractValues(f: QgsExpressionFunction, values: tuple, context: QgsExpressionContext):

        results = []

        for p, v in zip(f.parameters(), values):
            name = p.name()
            if re.search(name, '.*vector.*', re.I):
                v = ExpressionFunctionUtils.extractVectorLayer(p, v)
            elif re.search(name, '.*raster.*', re.I):
                v = ExpressionFunctionUtils.extractRasterLayer(p, v)
            elif re.search(name, '.*profile.*', re.I):
                v = ExpressionFunctionUtils.extractSpectralProfileField(p, v)
            results.append(v)
        return results


class RasterArray(QgsExpressionFunction):

    def __init__(self):
        group = 'Rasters'
        name = 'raster_array'

        args = [
            QgsExpressionFunction.Parameter('layer', optional=False),
            QgsExpressionFunction.Parameter('geometry', optional=True, defaultValue='@geometry'),
        ]

        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        if not isinstance(context, QgsExpressionContext):
            return None

        lyrR = ExpressionFunctionUtils.extractRasterLayer(self.parameters()[0], values[0], context)
        geom = ExpressionFunctionUtils.extractGeometry(self.parameters()[1], values[1], context)
        crs_trans = ExpressionFunctionUtils.cachedCrsTransformation(lyrR, context)

        if not isinstance(geom, QgsGeometry):
            return None

        if not isinstance(lyrR, QgsRasterLayer):
            parent.setEvalErrorString('Unable to find raster layer')
            return None
        try:
            if not crs_trans.isShortCircuited():
                assert geom.transform(crs_trans) == Qgis.GeometryOperationResult.Success

            if not lyrR.extent().intersects(geom.boundingBox()):
                return None

            point: QgsPointXY = geom.asPoint()
            dp: QgsRasterDataProvider = lyrR.dataProvider()
            results = dp.identify(point, QgsRaster.IdentifyFormatValue).results()

            y = list(results.values())
            y = [v if isinstance(v, (int, float)) else float('NaN') for v in y]

            return y

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent: QgsExpression,
                 context: QgsExpressionContext) -> bool:
        return False

class SpectralData(QgsExpressionFunction):
    def __init__(self):
        group = SPECLIB_FUNCTION_GROUP
        name = 'spectralData'

        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=False)
        ]

        helptext = HM.helpText(name, args)
        super().__init__(name, args, group, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        ba = values[0]

        if not isinstance(context, QgsExpressionContext):
            return None

        if ba is None:
            return None

        try:
            assert context.fields()
            assert isinstance(ba, QByteArray)
            return decodeProfileValueDict(ba)

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class SpectralMath(QgsExpressionFunction):
    RX_ENCODINGS = re.compile('^({})$'.format('|'.join(ProfileEncoding.__members__.keys())), re.I)

    def __init__(self):
        group = SPECLIB_FUNCTION_GROUP
        name = 'spectralMath'

        args = [
            QgsExpressionFunction.Parameter('p1', optional=True),
            QgsExpressionFunction.Parameter('p2', optional=True),
            QgsExpressionFunction.Parameter('pN', optional=True),
            QgsExpressionFunction.Parameter('expression', optional=False, isSubExpression=True),
            QgsExpressionFunction.Parameter('format', optional=True),
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

    def referencedColumns(self, node) -> typing.List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


def registerQgsExpressionFunctions():
    """
    Registers functions to support SpectraLibrary handling with QgsExpressions
    """
    global QGIS_FUNCTION_INSTANCES
    functions = [Format_Py(), SpectralMath(), SpectralData(), SpectralEncoding(), RasterArray(), RasterProfile()]
    if Qgis.versionInt() > 32400:
        from .speclib.processing.aggregateprofiles import createSpectralProfileFunctions
        functions.extend(createSpectralProfileFunctions())
    for func in functions:

        if QgsExpression.isFunctionName(func.name()):
            msg = QCoreApplication.translate("UserExpressions",
                                             "User expression {0} already exists").format(func.name())
            QgsMessageLog.logMessage(msg + "\n", level=Qgis.Info)
        else:
            if func.name() in QGIS_FUNCTION_INSTANCES.keys():
                QgsMessageLog.logMessage(f'{func.name()} not registered, but python instance exists', level=Qgis.Info)
                func = QGIS_FUNCTION_INSTANCES[func.name()]

            if QgsExpression.registerFunction(func):
                QgsMessageLog.logMessage(f'Registered {func.name()}', level=Qgis.Info)
                QGIS_FUNCTION_INSTANCES[func.name()] = func
            else:
                QgsMessageLog.logMessage(f'Failed to register {func.name()}', level=Qgis.Warning)


def unregisterQgsExpressionFunctions():
    for name, func in QGIS_FUNCTION_INSTANCES.items():
        assert name == func.name()
        if QgsExpression.isFunctionName(name):
            if QgsExpression.unregisterFunction(name):
                QgsMessageLog.logMessage(f'Unregistered {name}', level=Qgis.Info)
            else:
                QgsMessageLog.logMessage(f'Unable to unregister {name}', level=Qgis.Warning)
