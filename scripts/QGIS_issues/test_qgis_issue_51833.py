# see https://github.com/qgis/QGIS/issues/51833
from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle, QgsCoordinateTransform
from qgis.gui import QgsMapCanvas
from qgis.testing import TestCase, start_app

app = start_app()


class MapCRSTest(TestCase):

    def test_mapCRS(self):
        crsLatLon = QgsCoordinateReferenceSystem('EPSG:4326')

        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32633'))
        extent = QgsRectangle(384418.42293523817,
                              5817479.542521443,
                              391319.6968762298,
                              5821746.336751187)
        canvas.setExtent(extent)

        def onExtentsChanged(*args):
            crs = canvas.mapSettings().destinationCrs()
            extent = canvas.extent()
            print(f' {crs.description()} : {extent.toString()}')

            # convert boundary coordinate of the MapCanvas CRS from LatLon to MapCanvas CRS values
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(crsLatLon)
            trans.setDestinationCrs(crs)
            bounds = trans.transform(crs.bounds())

            # the MapCanvas extent should still be within valid bound coordinates
            self.assertTrue(bounds.contains(extent))

        canvas.extentsChanged.connect(onExtentsChanged)
        print(f'Set CRS to {crsLatLon}')
        canvas.setDestinationCrs(crsLatLon)
