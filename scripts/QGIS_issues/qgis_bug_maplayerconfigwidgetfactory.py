from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel
from qgis.core import QgsMapLayer
from qgis.gui import QgsGui, QgsProviderGuiRegistry, QgsMapLayerConfigWidgetFactory, QgsMapCanvas, \
    QgsMapLayerConfigWidget
from qgis.utils import iface


class MyMapLayerConfigWidget(QgsMapLayerConfigWidget):

    def __init__(self, layer: QgsMapLayer, canvas: QgsMapCanvas, parent: QWidget | None = None):
        super().__init__(layer, canvas, parent=parent)

        self.label = QLabel("Hello World")

        layout = QHBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)


class MyConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super().__init__('My Factory', QIcon(':/images/themes/default/processingAlgorithm.svg'))

    def supportsLayer(self, layer):
        return

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True

    def createWidget(
        self,
        layer: QgsMapLayer,
        canvas: QgsMapCanvas,
        dockWidget: bool = True,
        parent: QWidget | None = None
    ) -> QgsMapLayerConfigWidget:
        w = MyMapLayerConfigWidget(layer, canvas, parent=parent)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w


reg: QgsProviderGuiRegistry = QgsGui.providerGuiRegistry()
n0 = len(reg.mapLayerConfigWidgetFactories())

myFactory = MyConfigWidgetFactory()
iface.registerMapLayerConfigWidgetFactory(myFactory)
n1 = len(reg.mapLayerConfigWidgetFactories())

print(f'Factories before: {n0} after: {n1}')

registered_factories = reg.mapLayerConfigWidgetFactories()
if myFactory not in registered_factories:
    raise Exception(f'{myFactory} not in {registered_factories}')
