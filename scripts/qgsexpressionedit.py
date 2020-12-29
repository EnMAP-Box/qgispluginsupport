from qgis.testing import start_app

from qgis.core import (
    QgsExpressionContextGenerator, QgsExpressionContext, QgsExpressionContextUtils
)
from qgis.gui import QgsExpressionLineEdit
app = start_app(True)

class Generator(QgsExpressionContextGenerator):

    def __init__(self, *args, **kwds):
        super(Generator, self).__init__(*args, **kwds)
        self.mScope = QgsExpressionContextUtils.globalScope()

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext([self.mScope])
        print(f'Generated QgsExpressionContext: {context}', flush=True)
        return context

gen = Generator()
w = QgsExpressionLineEdit()
w.setExpression("'click edit button ->'")
w.registerExpressionContextGenerator(gen)
w.show()

app.exec_()