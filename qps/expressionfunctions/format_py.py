from qgis.PyQt.QtCore import NULL
from qgis.core import QgsExpressionContext, QgsExpressionFunction

from .helpers import HelpStringMaker


HM = HelpStringMaker()


class Format_Py(QgsExpressionFunction):
    NAME = 'format_py'
    GROUP = 'String'

    def __init__(self):
        args = [
            QgsExpressionFunction.Parameter('fmt', optional=False),
            QgsExpressionFunction.Parameter('arg1', optional=True),
            QgsExpressionFunction.Parameter('arg2', optional=True),
            QgsExpressionFunction.Parameter('argN', optional=True),
        ]
        helptext = HM.helpText(self.NAME, args)
        super(Format_Py, self).__init__(self.NAME, -1, self.GROUP, helptext)

    def func(self, values, context: QgsExpressionContext, parent, node):
        if len(values) == 0 or values[0] in (None, NULL):
            return None
        if not isinstance(values[0], str):
            raise AssertionError
        fmt: str = values[0]
        fmtArgs = values[1:]
        try:
            return fmt.format(*fmtArgs)
        except Exception as ex:
            if isinstance(parent, QgsExpressionFunction):
                errStr = parent.evalErrorString()
                errStr += str(ex)
                parent.setEvalErrorString(errStr)
            return None

    def usesGeometry(self, node) -> bool:
        return False

    def referencedColumns(self, node) -> list:
        return [QgsExpressionContext.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True
