import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from qgis.PyQt.QtCore import NULL
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpressionContext,
    QgsExpressionFunction, QgsGeometry, QgsMapLayer, QgsProject, QgsRasterLayer
)
from qgis.core import QgsExpression, QgsMessageLog, Qgis
from qgis.core import QgsPointXY

from ..qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ..speclib.core.spectralprofile import ProfileEncoding
from ..speclib.core.spectralprofile import decodeProfileValueDict
from ..utils import noDataValues

SPECLIB_FUNCTION_GROUP = "Spectral Libraries"

QGIS_FUNCTION_INSTANCES: dict = dict()


class HelpStringMaker(object):

    def __init__(self):
        helpDir = Path(__file__).parent / 'help'
        self.mHELP = dict()

        if not (helpDir.is_dir()):
            raise AssertionError

        for e in os.scandir(helpDir):
            if e.is_file() and e.name.endswith('.json'):
                with open(e.path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        if isinstance(data, dict):
                            self._addHelpText(data)
                        elif isinstance(data, list):
                            for d in data:
                                self._addHelpText(d)
                    except json.JSONDecodeError as err:
                        raise Exception(f'Failed to read {e.path}:\n{err}')

    def _addHelpText(self, data: dict):
        if isinstance(data, dict) and 'name' in data.keys():
            self.mHELP[data['name']] = data

    def helpText(self,
                 name: str,
                 parameters: List[QgsExpressionFunction.Parameter] = []) -> str:
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
            import sys
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
                    if not (isinstance(P, QgsExpressionFunction.Parameter)):
                        raise AssertionError
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
                    if defaultValue not in [None, NULL]:
                        syntax += f'={defaultValue}'

                    syntax += '</span>'
                    if optional:
                        syntax += ']'
                    delim = ','
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
                    if not (isinstance(P, QgsExpressionFunction.Parameter)):
                        raise AssertionError

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


class ExpressionFunctionUtils(object):
    CONTEXT_CACHE = dict()

    @staticmethod
    def parameter(func: QgsExpressionFunction, parameter: str) -> QgsExpressionFunction.Parameter:
        for p in func.parameters():
            if p.name() == parameter:
                return p
        raise NotImplementedError(f'Missing parameter: {parameter}')

    @staticmethod
    def cachedSpectralPropertiesKey(rasterLayer: QgsRasterLayer) -> str:
        return f'spectralproperties_{rasterLayer.id()}'

    @staticmethod
    def cachedNoDataValues(context: QgsExpressionContext,
                           rasterLayer: QgsRasterLayer) -> Dict[int, List[float]]:
        k = f'nodatavalues_{rasterLayer.id()}'
        dump = context.cachedValue(k)
        if dump is None:

            NODATA: Dict = noDataValues(rasterLayer)
            dump = json.dumps(NODATA, ensure_ascii=False)
            context.setCachedValue(k, dump)
            return NODATA
        else:
            NODATA = json.loads(dump)
            NODATA = {int(k): v for k, v in NODATA.items()}
        return NODATA

    @staticmethod
    def cachedScaleValues(context: QgsExpressionContext,
                          raster_layer: QgsRasterLayer) -> Dict[int, tuple]:
        k = f'scalevalues_{raster_layer.id()}'
        dump = context.cachedValue(k)
        if dump is None:
            SCALEVALUES: Dict = dict()
            dp = raster_layer.dataProvider()
            for b in range(1, raster_layer.bandCount() + 1):
                SCALEVALUES[b] = (dp.bandOffset(b), dp.bandScale(b))
            dump = json.dumps(SCALEVALUES, ensure_ascii=False)
            context.setCachedValue(k, dump)
            return SCALEVALUES
        else:
            SCALEVALUES = json.loads(dump)
            SCALEVALUES = {int(k): v for k, v in SCALEVALUES.items()}
        return SCALEVALUES

    @staticmethod
    def cachedSpectralProperties(context: QgsExpressionContext, rasterLayer: QgsRasterLayer) -> dict:
        k = ExpressionFunctionUtils.cachedSpectralPropertiesKey(rasterLayer)
        dump = context.cachedValue(k)
        if dump is None:

            sp = QgsRasterLayerSpectralProperties.fromRasterLayer(rasterLayer)
            bbl = sp.badBands()
            wl = sp.wavelengths()
            wlu = sp.wavelengthUnits()

            if bbl.count(None) == len(bbl):
                bbl = None

            if wl.count(None) == len(wl):
                wl = None

            if wlu.count(None) == len(wlu):
                wlu = None

            dump = json.dumps(dict(bbl=bbl, wl=wl, wlu=wlu), ensure_ascii=False)
            context.setCachedValue(k, dump)

        spectral_properties = json.loads(dump)
        return spectral_properties

    @staticmethod
    def cachedCrsTransformationKey(context: QgsExpressionContext, source_layer: QgsMapLayer) -> str:
        k = f'{context.variable("layer_id")}->{source_layer.id()}'
        return k

    @staticmethod
    def cachedCrsTransformation(
        context: QgsExpressionContext,
        layer: QgsMapLayer
    ) -> QgsCoordinateTransform:
        context_crs = QgsExpression('@layer_crs').evaluate(context)
        if context_crs:
            context_crs = QgsCoordinateReferenceSystem(context_crs)
        else:
            context_crs = layer.crs()

        trans = QgsCoordinateTransform()
        trans.setSourceCrs(context_crs)
        trans.setDestinationCrs(layer.crs())
        return trans

    @staticmethod
    def extractSpectralProfileEncoding(p: QgsExpressionFunction.Parameter,
                                       value,
                                       context: QgsExpressionContext) -> ProfileEncoding:
        return ProfileEncoding.fromInput(value)

    @staticmethod
    def extractRasterLayer(p: QgsExpressionFunction.Parameter,
                           value,
                           context: QgsExpressionContext) -> QgsRasterLayer:
        if isinstance(value, str):
            layers = QgsExpression('@layers').evaluate(context)
            if layers is None:
                layers = []
            stores = [QgsProject.instance().layerStore()]
            try:
                stores = context.layerStores() + stores
            except AttributeError:
                pass
            for s in stores:
                layers.extend(s.mapLayers().values())
            layers = set(layers)
            for lyr in layers:
                if isinstance(lyr, QgsRasterLayer) and value in [lyr.name(), lyr.id()]:
                    return lyr

        if isinstance(value, QgsRasterLayer):
            return value
        else:
            return None

    @staticmethod
    def extractSpectralProfile(p: QgsExpressionFunction.Parameter,
                               value,
                               context: QgsExpressionContext,
                               raise_error: bool = True) -> Optional[dict]:
        if not isinstance(value, dict):
            if isinstance(value, str):
                e = QgsExpression(value)
                if e.isValid():
                    value = QgsExpression(value).evaluate(context)
            if value in [None, {}]:
                return None
            value = decodeProfileValueDict(value)

        if value in [None, {}]:
            return None
        return value

    @staticmethod
    def extractGeometry(p: QgsExpressionFunction.Parameter,
                        value,
                        context: QgsExpressionContext) -> QgsGeometry:
        from qgis.core import QgsGeometry, QgsExpression
        if isinstance(value, str):
            # Check if it's a variable reference
            for a in ['@geometry', '$geometry']:
                if value == a:
                    v = QgsExpression(a).evaluate(context)
                    if isinstance(v, QgsGeometry):
                        return v
            # If it's an expression string, evaluate it
            if value not in ['@geometry', '$geometry']:
                v = QgsExpression(value).evaluate(context)
                if isinstance(v, QgsGeometry):
                    return v
            # Return the value as-is if it's not a geometry
            return value
        elif isinstance(value, QgsPointXY):
            return QgsGeometry.fromPointXY(value)
        elif isinstance(value, QgsGeometry):
            return value
        elif isinstance(value, QgsExpressionContext):
            for a in ['@geometry', '$geometry']:
                v = QgsExpression(a).evaluate(value)
                if isinstance(v, QgsGeometry):
                    return v
        # Get geometry from feature if available
        feature = context.feature()
        if feature and feature.hasGeometry():
            return feature.geometry()
        # If no geometry found, return empty geometry or None
        return QgsGeometry()

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


def registerQgsExpressionFunctions():
    """
    Registers functions to support SpectraLibrary handling with QgsExpressions
    """

    from .format_py import Format_Py
    from .spectral_encoding import SpectralEncoding
    from .raster_array import RasterArray
    from .raster_profile import RasterProfile
    from .spectral_data import SpectralData
    from .spectral_math import SpectralMath
    from qps.speclib.processing.aggregateprofiles import createSpectralProfileFunctions
    functions = [Format_Py(), SpectralEncoding(), RasterArray(), RasterProfile(), SpectralData(), SpectralMath()]
    functions.extend(createSpectralProfileFunctions())
    for func in functions:

        if QgsExpression.isFunctionName(func.name()):
            msg = QCoreApplication.translate("UserExpressions",
                                             "User expression {0} already exists").format(func.name())
            QgsMessageLog.logMessage(msg + "\n", level=Qgis.MessageLevel.Info)
        else:
            if func.name() in QGIS_FUNCTION_INSTANCES.keys():
                QgsMessageLog.logMessage(
                    f'{func.name()} not registered, but python instance exists',
                    level=Qgis.MessageLevel.Info
                )
                func = QGIS_FUNCTION_INSTANCES[func.name()]

            if QgsExpression.registerFunction(func):
                QgsMessageLog.logMessage(f'Registered {func.name()}', level=Qgis.MessageLevel.Info)
                QGIS_FUNCTION_INSTANCES[func.name()] = func
            else:
                QgsMessageLog.logMessage(f'Failed to register {func.name()}', level=Qgis.MessageLevel.Warning)


def unregisterQgsExpressionFunctions():
    from qgis.core import QgsExpression, QgsMessageLog, Qgis

    for name, func in QGIS_FUNCTION_INSTANCES.items():
        if not (name == func.name()):
            raise AssertionError
        if QgsExpression.isFunctionName(name):
            if QgsExpression.unregisterFunction(name):
                QgsMessageLog.logMessage(f'Unregistered {name}', level=Qgis.MessageLevel.Info)
            else:
                QgsMessageLog.logMessage(f'Unable to unregister {name}', level=Qgis.MessageLevel.Warning)
