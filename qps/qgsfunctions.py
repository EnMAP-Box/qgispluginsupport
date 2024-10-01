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
import math
import os
import pathlib
import re
import sys
from json import JSONDecodeError
from typing import Any, Callable, Dict, Iterable, List, Set, Tuple, Union

import numpy as np

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextScope, QgsExpressionFunction, QgsExpressionNode, QgsExpressionNodeFunction, QgsFeature, \
    QgsFeatureRequest, QgsField, QgsGeometry, QgsMapLayer, QgsMapToPixel, QgsMessageLog, QgsPointXY, QgsProject, \
    QgsRasterDataProvider, QgsRasterLayer
from qgis.PyQt.QtCore import NULL, QByteArray, QCoreApplication, QVariant
from .qgisenums import QGIS_WKBTYPE
from .qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from .speclib.core.spectrallibrary import FIELD_VALUES
from .speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict, prepareProfileValueDict, \
    ProfileEncoding, SpectralProfileFileReader
from .speclib.io.asd import ASDBinaryFile
from .speclib.io.spectralevolution import SEDFile
from .speclib.io.svc import SVCSigFile
from .utils import _geometryIsSinglePoint, aggregateArray, MapGeometryToPixel, noDataValues, rasterArray

SPECLIB_FUNCTION_GROUP = "Spectral Libraries"

QGIS_FUNCTION_INSTANCES: Dict[str, QgsExpressionFunction] = dict()


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
                        if isinstance(data, dict):
                            self._addHelpText(data)
                        elif isinstance(data, list):
                            for d in data:
                                self._addHelpText(d)
                    except JSONDecodeError as err:
                        raise Exception(f'Failed to read {e.path}:\n{err}')

    def _addHelpText(self, data: dict):
        if isinstance(data, dict) and 'name' in data.keys():
            self.mHELP[data['name']] = data

    def helpText(self,
                 name: str,
                 parameters: List[QgsExpressionFunction.Parameter] = []) -> str:
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
    NAME = 'format_py'
    GROUP = 'String'

    def __init__(self):

        args = [
            QgsExpressionFunction.Parameter('fmt', optional=False, defaultValue=FIELD_VALUES),
            QgsExpressionFunction.Parameter('arg1', optional=True),
            QgsExpressionFunction.Parameter('arg2', optional=True),
            QgsExpressionFunction.Parameter('argN', optional=True),
        ]
        helptext = HM.helpText(self.NAME, args)
        super(Format_Py, self).__init__(self.NAME, -1, self.GROUP, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node):
        if len(values) == 0 or values[0] in (None, NULL):
            return None
        assert isinstance(values[0], str)
        fmt: str = values[0]
        fmtArgs = values[1:]
        try:
            return fmt.format(*fmtArgs)
        except Exception as ex:
            if isinstance(parent, QgsExpression):
                errStr = parent.evalErrorString()
                errStr += str(ex)
                parent.setEvalErrorString(errStr)

            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class SpectralEncoding(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'encode_profile'

    def __init__(self):

        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=False),
            QgsExpressionFunction.Parameter('encoding', defaultValue='text', optional=True),

        ]
        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):

        profile = decodeProfileValueDict(values[0])
        if profile is None:
            return None

        try:
            encoding = ExpressionFunctionUtils.extractSpectralProfileEncoding(self.parameters()[1], values[1], context)
            if not isinstance(encoding, ProfileEncoding):
                return None
            return encodeProfileValueDict(profile, encoding)
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class ReadSpectralProfile(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_profile'

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('file', optional=False),
            QgsExpressionFunction.Parameter('type', optional=True)
        ]

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def handlesNull(self) -> bool:
        return True

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent: QgsExpression,
                 context: QgsExpressionContext) -> bool:
        return True

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def usesGeometry(self, node) -> bool:
        return False

    def supportedFileTypes(self) -> List[str]:

        return ['asd', 'sig', 'sed']

    def findFileType(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext.startswith('.'):
            return ext[1:]
        else:
            return ext

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):
        if not isinstance(context, QgsExpressionContext):
            return None

        try:
            path = values[0]
            filetype = values[1]
            assert os.path.isfile(path), f'File does not exists: {path}'

            if not filetype:
                filetype = self.findFileType(path)

            if filetype not in self.supportedFileTypes():
                raise Exception(f'Please specify type of spectral file: {",".join(self.supportedFileTypes())}')

            file = None
            if filetype == 'asd':
                file = ASDBinaryFile(path)
            elif filetype == 'sig':
                file = SVCSigFile(path)
            elif filetype == 'sed':
                file = SEDFile(path)

            if not isinstance(file, SpectralProfileFileReader):
                raise Exception(f'Unable to read file of type "{filetype}"')

            return file.asMap()

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

        s = ""


class StaticExpressionFunction(QgsExpressionFunction):
    """
    A Re-Implementation of QgsStaticExpressionFunction (not available in python API)
    """

    def __init__(self,
                 fnname: str,
                 params,
                 fcn,
                 group: str,
                 helpText: str = None,
                 usesGeometry: Union[bool, QgsExpressionNodeFunction] = None,
                 referencedColumns: Set[str] = None,
                 lazyEval: bool = False,
                 aliases: List[str] = [],
                 handlesNull: bool = False):
        if helpText is None:
            helpText = HM.helpText(fnname, params)
        if helpText is None:
            helpText = ''
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
                           rasterLayer: QgsRasterLayer) -> Dict[int, List[Union[float, int]]]:

        k = f'nodatavalues_{rasterLayer.id()}'
        dump = context.cachedValue(k)
        if dump is None:
            NODATA: Dict = noDataValues(rasterLayer)
            dump = json.dumps(NODATA)
            context.setCachedValue(k, dump)
            return NODATA
        else:
            NODATA = json.loads(dump)
            NODATA = {int(k): v for k, v in NODATA.items()}
        return NODATA

    @staticmethod
    def cachedScaleValues(context: QgsExpressionContext,
                          rasterLayer: QgsRasterLayer) -> Dict[int, Tuple[float, float]]:

        k = f'scalevalues_{rasterLayer.id()}'
        dump = context.cachedValue(k)
        if dump is None:
            SCALEVALUES: Dict = dict()
            dp: QgsRasterDataProvider = rasterLayer.dataProvider()
            for b in range(1, rasterLayer.bandCount() + 1):
                SCALEVALUES[b] = (dp.bandOffset(b), dp.bandScale(b))
            dump = json.dumps(SCALEVALUES)
            context.setCachedValue(k, dump)
            return SCALEVALUES
        else:
            SCALEVALUES = json.loads(dump)
            SCALEVALUES = {int(k): v for k, v in SCALEVALUES.items()}
        return SCALEVALUES

    @staticmethod
    def cachedSpectralProperties(context: QgsExpressionContext, rasterLayer: QgsRasterLayer) -> dict:
        """
        Returns the spectral properties of the rasterLayer.
        """
        k = ExpressionFunctionUtils.cachedSpectralPropertiesKey(rasterLayer)
        dump = context.cachedValue(k)
        if dump is None:
            sp = QgsRasterLayerSpectralProperties.fromRasterLayer(rasterLayer)
            bbl = sp.badBands()
            wl = sp.wavelengths()
            wlu = sp.wavelengthUnits()

            if bbl.count(1) == len(bbl):
                bbl = None

            if wl.count(None) == len(wl):
                wl = None

            if wlu.count(None) == len(wlu):
                wlu = None

            dump = json.dumps(dict(bbl=bbl, wl=wl, wlu=wlu))
            context.setCachedValue(k, dump)

        spectral_properties = json.loads(dump)
        return spectral_properties

    @staticmethod
    def cachedCrsTransformationKey(context: QgsExpressionContext, source_layer: QgsMapLayer) -> str:
        k = f'{context.variable("layer_id")}->{source_layer.id()}'
        return k

    @staticmethod
    def cachedCrsTransformation(context: QgsExpressionContext, layer: QgsMapLayer) \
            -> QgsCoordinateTransform:
        """
        Returns a CRS Transformation from the context to the layer CRS
        """
        context_crs = QgsExpression('@layer_crs').evaluate(context)
        if context_crs:
            context_crs = QgsCoordinateReferenceSystem(context_crs)
        else:
            # no other CRS defined, we must assume that context and layer CRS are the same
            context_crs = layer.crs()

        if True:
            # seems there is no way to store QgsCoordinateTransform in the QgsExpressionContext
            # so we need to create a QgsCoordinateTransformation each time
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(context_crs)
            trans.setDestinationCrs(layer.crs())
            return trans
        else:
            # we cannot store QgsCoordinateTransform instance in the context
            k = ExpressionFunctionUtils.cachedCrsTransformationKey(context, layer)
            trans = context.cachedValue(k)
            if not isinstance(trans, QgsCoordinateTransform):
                if isinstance(context_crs, QgsCoordinateReferenceSystem) and context_crs.isValid():
                    trans = QgsCoordinateTransform()
                    trans.setSourceCrs(context_crs)
                    trans.setDestinationCrs(layer.crs())
                    context.setCachedValue(k, trans)
                    ExpressionFunctionUtils.CONTEXT_CACHE[k] = trans
                    # print(f'Added: {k}', flush=True)
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
        """
        Extracts a QgsRasterLayer instance
        """
        if isinstance(value, str):
            layers = QgsExpression('@layers').evaluate(context)
            if layers is None:
                layers = []
            stores = [QgsProject.instance().layerStore()]
            if Qgis.versionInt() >= 33000:
                stores = context.layerStores() + stores
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
                               context: QgsExpressionFunction,
                               raise_error: bool = True) -> dict:

        if not isinstance(value, dict):
            if isinstance(value, str):
                e = QgsExpression(value)
                if e.isValid():
                    value = QgsExpression(value).evaluate(context)
            if value is None:
                return None
            value = decodeProfileValueDict(value)
            if value == {}:
                return None
            return value
        return value

    @staticmethod
    def extractGeometry(p: QgsExpressionFunction.Parameter,
                        value,
                        context: QgsExpressionFunction) -> QgsGeometry:

        if isinstance(value, QgsFeature):
            return value.geometry()

        if not isinstance(value, QgsGeometry):
            for a in ['@geometry', '$geometry']:
                v = QgsExpression(a).evaluate(context)
                if isinstance(v, QgsGeometry):
                    return v
        else:
            return value

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
    GROUP = 'Rasters'
    NAME = 'raster_array'

    def __init__(self):

        args = [
            QgsExpressionFunction.Parameter('layer', optional=False),
            QgsExpressionFunction.Parameter('geometry', optional=True, defaultValue='@geometry'),
            QgsExpressionFunction.Parameter('aggregate', optional=True, defaultValue='mean'),
            QgsExpressionFunction.Parameter('t', optional=True, defaultValue=False),
            QgsExpressionFunction.Parameter('at', optional=True, defaultValue=False)
        ]

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        if not isinstance(context, QgsExpressionContext):
            return None

        lyrR = ExpressionFunctionUtils.extractRasterLayer(self.parameters()[0], values[0], context)
        if not isinstance(lyrR, QgsRasterLayer):
            parent.setEvalErrorString('Unable to find raster layer')
            return None

        NODATA = ExpressionFunctionUtils.cachedNoDataValues(context, lyrR)
        #  SCALING = ExpressionFunctionUtils.cachedScaleValues(context, lyrR)

        geom = ExpressionFunctionUtils.extractGeometry(self.parameters()[1], values[1], context)
        if not isinstance(geom, QgsGeometry):
            parent.setEvalErrorString('Unable to find geometry')
            return None

        crs_trans = ExpressionFunctionUtils.cachedCrsTransformation(context, lyrR)

        transpose: bool = values[3]
        all_touched: bool = values[4]
        aggr: str = str(values[2]).lower()

        if aggr not in ['none', 'mean', 'median', 'min', 'max']:
            parent.setEvalErrorString(f'Unknown aggregation "{aggr}"')
            return None

        if not crs_trans.isShortCircuited():
            geom = QgsGeometry(geom)
            if not geom.transform(crs_trans) == Qgis.GeometryOperationResult.Success:
                parent.setEvalErrorString('Unable to transform geometry into raster CRS')
                return None

        bbox = geom.boundingBox()

        if not lyrR.extent().intersects(bbox):
            return None

        c = bbox.center()
        e = lyrR.extent()
        # we want to capture pixel-centers. ensure that a line / point geometry has a
        # small buffer to indicate which pixels we overlap
        resX, resY = lyrR.rasterUnitsPerPixelX(), lyrR.rasterUnitsPerPixelY()
        if 0 in [bbox.width(), bbox.height()]:
            if bbox.width() == 0:
                bbox.setXMinimum(c.x() - 0.5 * resX)
                bbox.setXMaximum(c.x() + 0.5 * resX)
            if bbox.height() == 0:
                bbox.setYMinimum(c.y() - 0.5 * resY)
                bbox.setYMaximum(c.y() + 0.5 * resY)
            bbox = e.intersect(bbox)
        else:
            # expand the bounding box to include all touched pixel
            if True:
                bbox = e.intersect(bbox)
                bbox.setXMinimum(e.xMinimum() + math.floor((bbox.xMinimum() - e.xMinimum()) / resX) * resX)
                bbox.setXMaximum(e.xMinimum() + math.ceil((bbox.xMaximum() - e.xMinimum()) / resX) * resX)
                bbox.setYMinimum(e.yMinimum() + math.floor((bbox.yMinimum() - e.yMinimum()) / resY) * resY)
                bbox.setYMaximum(e.yMinimum() + math.ceil((bbox.yMaximum() - e.yMinimum()) / resY) * resY)
                bbox = e.intersect(bbox)
        # bbox = e
        try:
            dp: QgsRasterDataProvider = lyrR.dataProvider()

            # read the geometry bounding box only
            array = rasterArray(dp, rect=bbox)
            nb, nl, ns = array.shape

            mapUnitsPerPixel = lyrR.rasterUnitsPerPixelX()

            # get pixel locations within array subset
            MG2P = MapGeometryToPixel.fromExtent(bbox, ns, nl,
                                                 mapUnitsPerPixel=mapUnitsPerPixel,
                                                 crs=dp.crs())
            if geom.wkbType() == QGIS_WKBTYPE.PolygonZ:
                geom = geom.coerceToType(QGIS_WKBTYPE.Polygon)[0]
            i_y, i_x = MG2P.geometryPixelPositions(geom, all_touched=all_touched)
            # print(array.shape)
            if not isinstance(i_x, np.ndarray):
                return None
            pixels = array[:, i_y, i_x]
            pixels = pixels.astype(float)

            for b in range(pixels.shape[0]):
                # set no-data values to NaN / bad-band
                bandNo = b + 1
                for ndv in NODATA.get(bandNo, []):
                    band = pixels[b, :]
                    pixels[b, :] = np.where(band == ndv, np.nan, band)
                # set scaling - is already applied by QGIS API
                # if False:
                #    pixels[b, :] = SCALING[bandNo][0] + SCALING[bandNo][1] * pixels[b, :]

            # keep only pixels where not all bands are NaN -> either masked or out of image pixel
            is_not_all_nan = np.logical_not(np.all(np.isnan(pixels), axis=0))

            # map pixel indices from the subset array to the entire-raster array
            M2P = QgsMapToPixel(mapUnitsPerPixel,
                                lyrR.extent().center().x(),
                                lyrR.extent().center().y(),
                                lyrR.width(),
                                lyrR.height(),
                                0)

            # calculate geo-coordinates
            px_geo_x, px_geo_y = MG2P.px2geoArrays(i_x + 0.5, i_y + 0.5)

            # keep only pixels that are within the image extent
            is_in_image = (e.xMinimum() <= px_geo_x) * (px_geo_x <= e.xMaximum()) * \
                          (e.yMinimum() <= px_geo_y) * (px_geo_y <= e.yMaximum())

            i_valid = np.where(is_in_image * is_not_all_nan)[0]
            # i_y = i_y[i_valid]
            # i_x = i_x[i_valid]
            if len(i_valid) == 0:
                return None

            pixels = pixels[:, i_valid]
            pixels = aggregateArray(aggr, pixels, axis=1, keepdims=True)

            px_geo = [QgsPointXY(x, y) for x, y in zip(px_geo_x[i_valid], px_geo_y[i_valid])]
            # calculate pixel-coordinates in raster image
            px_px = [M2P.transform(p) for p in px_geo]
            px_x = [int(p.x()) for p in px_px]
            px_y = [int(p.y()) for p in px_px]

            scope = QgsExpressionContextScope('raster_array_extraction')
            scope.setVariable('raster_array_px', (px_x, px_y))

            scope.setVariable('raster_array_geo', px_geo)
            context.appendScope(scope)

            if aggr != 'none' or _geometryIsSinglePoint(geom):
                pixels = pixels.reshape((pixels.shape[0]))
            else:
                if transpose:
                    pixels = pixels.transpose()

            return pixels.tolist()

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent: QgsExpression,
                 context: QgsExpressionContext) -> bool:
        return False


class RasterProfile(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'raster_profile'

    f = RasterArray()

    def __init__(self):

        args = [p for p in self.f.parameters()
                if p.name() not in ['t']]
        self.mPOffset = len(args)
        args.extend([
            QgsExpressionFunction.Parameter('encoding', optional=True, defaultValue='text'),
        ])

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self,
             values,
             context: QgsExpressionContext,
             parent: QgsExpression,
             node: QgsExpressionNodeFunction):

        if not isinstance(context, QgsExpressionContext):
            return None

        # user RasterProfile to return the raster values
        # transpose = t = True to get values in [band, profile] array
        valuesRasterProfile = [
            values[0],  # raster layer
            values[1],  # geometry
            values[2],  # aggregate
            True,  # transpose
            values[3]  # enable ALL_TOUCHED
        ]
        results = self.f.func(valuesRasterProfile, context, parent, node)

        if results is None or parent.parserErrorString() != '' or parent.evalErrorString() != '':
            return None

        if results is None or len(results) == 0:
            return None

        aggr = str(values[2]).lower()
        has_multiple_profiles = isinstance(results[0], list)

        lyrR: QgsRasterLayer = ExpressionFunctionUtils.extractRasterLayer(self.parameters()[0], values[0], context)

        profile_encoding = ExpressionFunctionUtils.extractSpectralProfileEncoding(
            self.parameters()[-1], values[-1], context)

        if not isinstance(profile_encoding, ProfileEncoding):
            parent.setEvalErrorString('Unable to find profile encoding')
            return None

        try:
            spectral_properties = ExpressionFunctionUtils.cachedSpectralProperties(context, lyrR)
            wl = spectral_properties['wl']
            wlu = spectral_properties['wlu']
            if isinstance(wlu, list):
                wlu = wlu[0]
            bbl = spectral_properties['bbl']

            if not has_multiple_profiles:
                results = [results]

            profiles = []
            for y in results:
                pDict = prepareProfileValueDict(x=wl, y=y, xUnit=wlu, bbl=bbl)
                if profile_encoding != ProfileEncoding.Dict:
                    pDict = encodeProfileValueDict(pDict, profile_encoding)
                profiles.append(pDict)

            if not has_multiple_profiles:
                profiles = profiles[0]
            return profiles

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True


class SpectralData(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_data'

    def __init__(self):

        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=False)
        ]

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self, values, context: QgsExpressionContext, parent: QgsExpression, node: QgsExpressionNodeFunction):

        try:
            return ExpressionFunctionUtils.extractSpectralProfile(
                self.parameters()[0], values[0], context)

        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> List[str]:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True

    def isStatic(self, node: 'QgsExpressionNodeFunction', parent: 'QgsExpression',
                 context: 'QgsExpressionContext') -> bool:
        return False


class SpectralMath(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_math'

    RX_ENCODINGS = re.compile('^({})$'.format('|'.join(ProfileEncoding.__members__.keys())), re.I)

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('p1', optional=False),
            QgsExpressionFunction.Parameter('p2', optional=True),
            QgsExpressionFunction.Parameter('pN', optional=True),
            QgsExpressionFunction.Parameter('expression', optional=False, isSubExpression=True),
            QgsExpressionFunction.Parameter('format', optional=True, defaultValue='map'),
        ]
        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, -1, self.GROUP, helptext)

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
