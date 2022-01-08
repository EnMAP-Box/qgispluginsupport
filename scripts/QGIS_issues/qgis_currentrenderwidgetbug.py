




from qps.testing import initQgisApplication, TestObjects
import qgis.utils
QAPP = initQgisApplication()



path = r''
lyr = TestObjects.createRasterLayer()

QgsProject.instance().addMapLayer(lyr)

class MyRenderer(QgsSingleBandPseudoColorRenderer):

    def __init__(self, *args, **kwds):
        super()

w = QgsRendererRasterPropertiesWidget(lyr, qgis.utils.iface.mapCanvas())

w.show()

QAPP.exec_()

