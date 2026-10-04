from qgis.core import QgsProject
from qgis.utils import iface

import qps.testing
from qps import registerMapLayerConfigWidgetFactory
from qps.layerconfigwidgets.gdalmetadata import GDALMetadataConfigWidgetFactory
from qps.layerconfigwidgets.rasterbands import RasterBandConfigWidgetFactory
from qps.testing import TestObjects

registerMapLayerConfigWidgetFactory(GDALMetadataConfigWidgetFactory())
registerMapLayerConfigWidgetFactory(RasterBandConfigWidgetFactory())

qps.testing._ref = []
lyr = TestObjects.createRasterLayer(nb=200)
QgsProject.instance().addMapLayer(lyr, True)
iface.showLayerProperties(lyr)
qps.testing._ref.append(lyr)
