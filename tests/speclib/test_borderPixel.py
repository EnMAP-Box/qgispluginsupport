# noinspection PyPep8Naming
import unittest

from qgis.PyQt.QtCore import QSize
from qgis.core import QgsRasterLayer, QgsRectangle, QgsProject
from qgis.gui import QgsMapCanvas

from qps import initAll
from qps.maptools import CursorLocationMapTool
from qps.speclib.gui.spectralprofilesources import (
    ProfileSamplingMode, StandardLayerProfileSource, SpectralLibraryWidget, SpectralProfileSourcePanel)
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import SpatialPoint

start_app()
initAll()


class TestBorderPixel(TestCase):

    def test_borderPixel(self):
        from qpstestdata import enmap
        lyr: QgsRasterLayer = QgsRasterLayer(enmap.as_posix())
        lyr.setName('EnMAP')
        ext = lyr.extent()

        _ = lyr.dataProvider()
        _, _, _ = lyr.bandCount(), lyr.height(), lyr.width()
        pxx, _ = lyr.rasterUnitsPerPixelX(), lyr.rasterUnitsPerPixelY()

        out_of_image = [
            SpatialPoint(lyr.crs(), ext.xMinimum() - 0.0001 * pxx, ext.yMaximum()),
            SpatialPoint(lyr.crs(), ext.xMaximum() + 0.0001 * pxx, ext.yMaximum())
        ]

        source = StandardLayerProfileSource(lyr)

        k_mode = ProfileSamplingMode()
        k_mode.setKernelSize(3, 3)
        k_mode.setAggregation(ProfileSamplingMode.NO_AGGREGATION)

        for pt in out_of_image:
            self.assertFalse(lyr.extent().contains(pt), msg=f'Center point of kernel must be outside raster extent')

            kernel_rect = QgsRectangle(pt.x() - 1.5 * pxx, pt.y() - 1.5 * pxx,
                                       pt.x() + 1.5 * pxx, pt.y() + 1.5 * pxx)

            self.assertTrue(kernel_rect.intersects(lyr.extent()), msg=f'Kernel window must intersect raster extent')
            size = k_mode.kernelSize()
            x, y = size.width(), size.height()
            profiles = source.collectProfiles(pt, QSize(x, y))

            # having a kernel-size of 3x3 or larger, we should still collect profiles,
            # although the center coordinate is outside the image
            self.assertTrue(
                len(profiles) > 0,
                msg=f'No profiles for {pt}'
            )
            self.assertTrue(len(profiles) < x * y)

        sl = TestObjects.createSpectralLibrary()
        slw = SpectralLibraryWidget(speclib=sl)
        panel = SpectralProfileSourcePanel()
        panel.addSources(lyr)
        panel.addSpectralLibraryWidgets(slw)
        gnode = panel.createRelation()
        gnode.setSpeclib(sl)
        for n in gnode.spectralProfileGeneratorNodes():
            n.setProfileSource(lyr)

        canvas = QgsMapCanvas()
        canvas.setLayers([sl, lyr])
        canvas.zoomToFullExtent()
        mt = CursorLocationMapTool(canvas, showCrosshair=True)
        mt.sigLocationRequest.connect(lambda crs, pt: panel.loadCurrentMapSpectra(SpatialPoint(crs, pt)))
        canvas.setMapTool(mt)

        self.showGui([canvas, panel, slw])

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
