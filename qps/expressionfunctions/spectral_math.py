import re

from qgis.PyQt.QtCore import QByteArray
from qgis.core import QgsExpressionContext, QgsExpressionFunction, QgsExpressionNodeFunction
from qgis.core import QgsFeatureRequest

from .helpers import HelpStringMaker, SPECLIB_FUNCTION_GROUP
from ..speclib.core.spectralprofile import ProfileEncoding, decodeProfileValueDict, encodeProfileValueDict, \
    prepareProfileValueDict

HM = HelpStringMaker()


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

    def func(self, values, context: QgsExpressionContext, parent, node: QgsExpressionNodeFunction):
        from qgis.PyQt.QtCore import NULL

        if len(values) < 1:
            parent.setEvalErrorString(f'{self.name()}: requires at least 1 argument')
            return NULL
        if not isinstance(values[-1], str):
            parent.setEvalErrorString(f'{self.name()}: last argument needs to be a string')
            return NULL

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
            return NULL

        try:
            profilesData = values[0:-1]
            DATA = dict()
            _ = None
            for i, dump in enumerate(profilesData):
                d = decodeProfileValueDict(dump, numpy_arrays=True)
                if len(d) == 0:
                    continue
                if i == 0:
                    DATA.update(d)
                    if encoding is None:
                        if isinstance(dump, (QByteArray, bytes)):
                            encoding = ProfileEncoding.Bytes
                        elif isinstance(dump, dict):
                            encoding = ProfileEncoding.Map
                        else:
                            encoding = ProfileEncoding.Text

                n = i + 1
                for k, v in d.items():
                    if isinstance(k, str):
                        k2 = f'{k}{n}'
                        DATA[k2] = v

            if not (context.fields()):
                raise AssertionError
            exec(pyExpression, DATA)  # nosec: B102

            d = prepareProfileValueDict(x=DATA.get('x', None),
                                        y=DATA['y'],
                                        xUnit=DATA.get('xUnit', None),
                                        yUnit=DATA.get('yUnit', None),
                                        bbl=DATA.get('bbl', None),
                                        )
            return encodeProfileValueDict(d, encoding)
        except Exception as ex:
            parent.setEvalErrorString(f'{ex}')
            return NULL

    def usesGeometry(self, node) -> bool:
        return True

    def referencedColumns(self, node) -> list:
        return [QgsFeatureRequest.ALL_ATTRIBUTES]

    def handlesNull(self) -> bool:
        return True
