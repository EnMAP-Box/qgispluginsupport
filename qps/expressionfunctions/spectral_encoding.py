from qgis.core import QgsExpressionContext, QgsExpressionFunction

from .helpers import ExpressionFunctionUtils, HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core.spectralprofile import decodeProfileValueDict, encodeProfileValueDict

HM = HelpStringMaker()


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
            encoding = ExpressionFunctionUtils.extractSpectralProfileEncoding(
                self.parameters()[1], values[1], context)
            if not hasattr(encoding, 'name'):
                return None
            return encodeProfileValueDict(profile, encoding)
        except Exception as ex:
            parent.setEvalErrorString(str(ex))
            return None

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> list:
        return [QgsExpressionContext.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True
