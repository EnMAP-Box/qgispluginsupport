from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsExpressionNodeFunction, QgsFeatureRequest

from .helpers import ExpressionFunctionUtils, HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core import is_profile_field

HM = HelpStringMaker()


class SpectralData(QgsExpressionFunction):
    GROUP = SPECLIB_FUNCTION_GROUP
    NAME = 'spectral_data'

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('profile_field', optional=True)
        ]

        helptext = HM.helpText(self.NAME, args)
        super().__init__(self.NAME, args, self.GROUP, helptext)

    def func(self, values: list, context: QgsExpressionContext, parent, node: QgsExpressionNodeFunction):
        try:
            if node.referencedColumns() == set([QgsFeatureRequest.ALL_ATTRIBUTES]):
                value = None
                for field in context.fields():
                    if is_profile_field(field):
                        feat = context.feature()
                        value = feat.attribute(field.name())
                        break
            else:
                value = values[0]
            if value is not None:
                result = ExpressionFunctionUtils.extractSpectralProfile(self.parameters()[0], value, context)
                return result

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
