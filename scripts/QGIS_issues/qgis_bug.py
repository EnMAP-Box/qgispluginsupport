from qgis.core import (
    QgsExpressionContextGenerator, QgsExpressionContext, QgsExpressionContextUtils
)

from qgis.gui import QgsExpressionLineEdit

class Generator(QgsExpressionContextGenerator):

    def __init__(self, *args, **kwds):
        super(Generator, self).__init__(*args, **kwds)

    def createExpressionContext(self) -> QgsExpressionContext:
        context = QgsExpressionContext([QgsExpressionContextUtils.globalScope()])
        print(f'Generated QgsExpressionContext: {context}', flush=True)
        return context

gen = Generator()
w = QgsExpressionLineEdit()
w.registerExpressionContextGenerator(gen)
w.show()

# now click on edit button to produce a crash
