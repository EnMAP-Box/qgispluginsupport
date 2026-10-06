from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsExpressionNodeFunction, QgsFeatureRequest

from .helpers import ExpressionFunctionUtils, HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core import is_profile_field
from ..utils import band_index

HM = HelpStringMaker()


class SpectralData(QgsExpressionFunction):
    """
    A QgsExpressionFunction to extract spectral data from a profile field.
    """
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_data'

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=True),
            QgsExpressionFunction.Parameter('band', optional=True, defaultValue=None)
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

                if band_name is None:
                    return profile_data

                # return a single value from the profiles y data vector
                if isinstance(band_name, str):
                    band_idx = band_index(band_name, profile_data.get('x'), wlu=profile_data.get('xUnit', 'nm'))
                else:
                    band_idx = int(band_name)

                if 0 <= band_idx < len(profile_data['y']):
                    return profile_data['y'][band_idx]
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
