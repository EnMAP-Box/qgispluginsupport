from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsRasterLayer

from .helpers import ExpressionFunctionUtils, HelpStringMaker, SPECLIB_FUNCTION_GROUP
from .raster_array import RasterArray
from ..speclib.core.spectralprofile import encodeProfileValueDict, prepareProfileValueDict

HM = HelpStringMaker()


class RasterProfile(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'raster_profile'
    _f = None  # Class attribute to store RasterArray instance

    def __init__(self):
        # Use class-level RasterArray instance to access parameters
        if RasterProfile._f is None:
            RasterProfile._f = RasterArray()

        f = RasterProfile._f
        args = [p for p in f.parameters()
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
             parent,
             node):
        if not isinstance(context, QgsExpressionContext):
            return None

        valuesRasterProfile = [
            values[0],
            values[1],
            values[2],
            True,
            values[3]
        ]
        results = RasterProfile._f.func(valuesRasterProfile, context, parent, node)

        if results is None or parent.parserErrorString() != '' or parent.evalErrorString() != '':
            return None

        if results is None or len(results) == 0:
            return None

        _ = str(values[2]).lower()
        has_multiple_profiles = isinstance(results[0], list)

        lyrR: QgsRasterLayer = ExpressionFunctionUtils.extractRasterLayer(self.parameters()[0], values[0], context)

        profile_encoding = ExpressionFunctionUtils.extractSpectralProfileEncoding(
            self.parameters()[-1], values[-1], context)

        if not hasattr(profile_encoding, 'name'):
            parent.setEvalErrorString('Unable to find profile encoding')
            return None

        try:
            spectral_properties = ExpressionFunctionUtils.cachedSpectralProperties(context, lyrR)
            wl = spectral_properties['wl']
            wlu = spectral_properties['wlu']
            if isinstance(wlu, list):
                for _wlu in wlu:
                    if _wlu is not None:
                        wlu = _wlu
                        break
            if isinstance(wlu, list):
                wlu = None
            bbl = spectral_properties['bbl']

            if not has_multiple_profiles:
                results = [results]

            profiles = []
            for y in results:
                pDict = prepareProfileValueDict(x=wl, y=y, xUnit=wlu, bbl=bbl)
                if profile_encoding.name != 'Dict':
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

    def referencedColumns(self, node) -> list:
        return [QgsExpressionContext.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True
