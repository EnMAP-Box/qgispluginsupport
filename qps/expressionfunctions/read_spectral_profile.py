import os

from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsExpressionNodeFunction

from .helpers import HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core.spectralprofile import SpectralProfileFileReader
from ..speclib.io.asd import ASDBinaryFile
from ..speclib.io.spectralevolution import SEDFile
from ..speclib.io.svc import SVCSigFile

HM = HelpStringMaker()


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
                 parent,
                 context: QgsExpressionContext) -> bool:
        return True

    def referencedColumns(self, node) -> list:
        return [QgsExpressionContext.ALL_ATTRIBUTES]

    def usesGeometry(self, node) -> bool:
        return False

    def supportedFileTypes(self) -> list:
        return ['asd', 'sig', 'sed']

    def findFileType(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext.startswith('.'):
            return ext[1:]
        else:
            return ext

    def func(self, values, context: QgsExpressionContext, parent, node: QgsExpressionNodeFunction):
        if not isinstance(context, QgsExpressionContext):
            return None

        try:
            path = values[0]
            filetype = values[1]
            if not os.path.isfile(path):
                raise AssertionError(f'File does not exists: {path}')

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
