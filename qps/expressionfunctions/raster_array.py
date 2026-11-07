import math

import numpy as np
from qgis.core import (
    QgsExpressionContext, QgsExpressionContextScope, QgsExpressionFunction, QgsExpressionNodeFunction,
    QgsGeometry, QgsMapToPixel, QgsPointXY, QgsRasterLayer
)

from .helpers import HelpStringMaker, ExpressionFunctionUtils
from ..utils import aggregateArray, MapGeometryToPixel, _geometryIsSinglePoint
from ..utils import rasterArray

HM = HelpStringMaker()


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

    def func(self, values, context: QgsExpressionContext, parent, node: QgsExpressionNodeFunction):

        if not isinstance(context, QgsExpressionContext):
            return None

        lyrR = ExpressionFunctionUtils.extractRasterLayer(self.parameters()[0], values[0], context)
        if not isinstance(lyrR, QgsRasterLayer):
            parent.setEvalErrorString('Unable to find raster layer')
            return None

        NODATA = ExpressionFunctionUtils.cachedNoDataValues(context, lyrR)

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
            if not geom.transform(crs_trans).name == 'Success':
                parent.setEvalErrorString('Unable to transform geometry into raster CRS')
                return None

        bbox = geom.boundingBox()

        if not lyrR.extent().intersects(bbox):
            return None

        c = bbox.center()
        e = lyrR.extent()
        resX, resY = lyrR.rasterUnitsPerPixelX(), lyrR.rasterUnitsPerPixelY()

        if geom.type().name == 'Point':
            pass
        elif 0 in [bbox.width(), bbox.height()]:
            if bbox.width() == 0:
                bbox.setXMinimum(c.x() - 0.5 * resX)
                bbox.setXMaximum(c.x() + 0.5 * resX)
            if bbox.height() == 0:
                bbox.setYMinimum(c.y() - 0.5 * resY)
                bbox.setYMaximum(c.y() + 0.5 * resY)
            bbox = e.intersect(bbox)
        else:
            if True:
                bbox = e.intersect(bbox)
                bbox.setXMinimum(e.xMinimum() + math.floor((bbox.xMinimum() - e.xMinimum()) / resX) * resX)
                bbox.setXMaximum(e.xMinimum() + math.ceil((bbox.xMaximum() - e.xMinimum()) / resX) * resX)
                bbox.setYMinimum(e.yMinimum() + math.floor((bbox.yMinimum() - e.yMinimum()) / resY) * resY)
                bbox.setYMaximum(e.yMinimum() + math.ceil((bbox.yMaximum() - e.yMinimum()) / resY) * resY)
                bbox = e.intersect(bbox)
        try:
            dp = lyrR.dataProvider()

            array = rasterArray(dp, rect=bbox)
            nb, nl, ns = array.shape

            mapUnitsPerPixel = lyrR.rasterUnitsPerPixelX()

            MG2P = MapGeometryToPixel.fromExtent(bbox, ns, nl,
                                                 mapUnitsPerPixel=mapUnitsPerPixel,
                                                 crs=dp.crs())
            if geom.wkbType().name == 'PolygonZ':
                geom = geom.coerceToType(QgsGeometry)[0]
            i_y, i_x = MG2P.geometryPixelPositions(geom, all_touched=all_touched)
            if not isinstance(i_x, np.ndarray):
                return None
            pixels = array[:, i_y, i_x]
            pixels = pixels.astype(float)

            for b in range(pixels.shape[0]):
                bandNo = b + 1
                for ndv in NODATA.get(bandNo, []):
                    band = pixels[b, :]
                    pixels[b, :] = np.where(band == ndv, np.nan, band)

            is_not_all_nan = np.logical_not(np.all(np.isnan(pixels), axis=0))

            M2P = QgsMapToPixel(mapUnitsPerPixel,
                                lyrR.extent().center().x(),
                                lyrR.extent().center().y(),
                                lyrR.width(),
                                lyrR.height(),
                                0)

            px_geo_x, px_geo_y = MG2P.px2geoArrays(i_x + 0.5, i_y + 0.5)

            is_in_image = (e.xMinimum() <= px_geo_x) * (px_geo_x <= e.xMaximum()) * \
                          (e.yMinimum() <= px_geo_y) * (px_geo_y <= e.yMaximum())

            i_valid = np.where(is_in_image * is_not_all_nan)[0]
            if len(i_valid) == 0:
                return None

            pixels = pixels[:, i_valid]
            pixels = aggregateArray(aggr, pixels, axis=1, keepdims=True)

            px_geo = [QgsPointXY(x, y) for x, y in zip(px_geo_x[i_valid], px_geo_y[i_valid])]
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
            if parent is not None:
                parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> list:
        return [QgsExpressionContext.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent,
                 context: QgsExpressionContext) -> bool:
        return False
