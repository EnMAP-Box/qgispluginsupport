import importlib

from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsExpressionNodeFunction, QgsFeatureRequest

from .helpers import ExpressionFunctionUtils, HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core import is_profile_field
from ..utils import band_values

HM = HelpStringMaker()

has_spyndex = importlib.util.find_spec('spyndex') is not None

if has_spyndex:
    import spyndex.axioms

    SPYNDEX_BANDS = spyndex.axioms.bands
    SPYNDEX_CONSTANTS = spyndex.axioms.constants
    SPYNDEX_INDICES = spyndex.axioms.indices
else:
    SPYNDEX_INDICES = None
    SPYNDEX_BANDS = None
    SPYNDEX_CONSTANTS = None


class SpectralData(QgsExpressionFunction):
    """
    A QgsExpressionFunction to extract spectral data from a profile field.
    """
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_data'

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=True),
            QgsExpressionFunction.Parameter('band', optional=True, defaultValue=None),
            QgsExpressionFunction.Parameter('indices', optional=True, defaultValue=False)
        ]

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self, values: list, context: QgsExpressionContext, parent, node: QgsExpressionNodeFunction):
        try:
            if node.referencedColumns() == set([QgsFeatureRequest.ALL_ATTRIBUTES]):
                profile_dump = None
                for field in context.fields():
                    if is_profile_field(field):
                        feat = context.feature()
                        profile_dump = feat.attribute(field.name())
                        break
            else:
                profile_dump = values[0]
            if profile_dump is not None:
                profile_data = ExpressionFunctionUtils.extractSpectralProfile(
                    self.parameters()[0], profile_dump,
                    context
                )

                if not isinstance(profile_data, dict):
                    return None

                band_name = values[1]
                return_band_indices = values[2] is True

                # default: return entire profile dictionary
                if band_name is None:
                    return profile_data
                elif isinstance(band_name, (int, float)):
                    # return a single value from the profiles y data vector
                    # using the band index
                    band_idx = int(band_name)
                    n = len(profile_data['y'])
                    if 0 <= band_idx < n:
                        if return_band_indices:
                            return {band_name: band_idx}
                        else:
                            return profile_data['y'][band_idx]
                    else:
                        raise NotImplementedError(f'band index out of range [0, {n}]')

                elif isinstance(band_name, str):
                    # return a single value from the profiles y data vector
                    # using a band name or spectral index name
                    if not has_spyndex:
                        raise ModuleNotFoundError('spyndex package is not installed.')
                    #  b_values = band_values()
                    y = profile_data.get('y', [])
                    wl = profile_data.get('x', [])
                    wlu = profile_data.get('xUnit', 'nm')
                    results = band_values(
                        band_name, wl, y,
                        wavelength_unit=wlu,
                        return_band_indices=return_band_indices,
                        compute=True,
                    )
                    if not return_band_indices:
                        return results.get(band_name, None)
                    else:
                        return results
                else:
                    return None

        except Exception as ex:
            parent.setEvalErrorString(str(ex))

        return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> list:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True

    def isStatic(self, node, parent, context) -> bool:
        return False
