from osgeo import gdal
from qgis.core import QgsRasterLayer, QgsRasterFileWriter, QgsRasterPipe, QgsProcessingContext, QgsRasterBlockFeedback

from qps.speclib.core.spectralprofile import SpectralSetting
from qps.testing import TestCase, TestObjects
from qps.utils import parseWavelength


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestCore, cls).setUpClass(*args, **kwds)
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()

    def test_SpectralSetting(self):
        from qpstestdata import enmap
        lyr1: QgsRasterLayer = TestObjects.createRasterLayer(nb=10)
        lyr2: QgsRasterLayer = QgsRasterLayer(enmap, 'EnMAP Tiff', 'gdal')

        test_dir = self.createTestOutputDirectory()
        rasterblockFeedback = QgsRasterBlockFeedback()
        processingContext = QgsProcessingContext()
        processingFeedback = processingContext.feedback()
        for i, lyr in enumerate([lyr1, lyr2]):
            settingA = SpectralSetting.fromRasterLayer(lyr)
            self.assertIsInstance(settingA, SpectralSetting)

            file_name = test_dir / f'layer_{i}.tiff'
            file_name = file_name.as_posix()
            file_writer = QgsRasterFileWriter(file_name)
            dp = lyr.dataProvider()
            pipe = QgsRasterPipe()
            self.assertTrue(pipe.set(dp), msg=f'Cannot set pipe provider to write {file_name}')
            error = file_writer.writeRaster(
                pipe,
                dp.xSize(),
                dp.ySize(),
                dp.extent(),
                dp.crs(),
                processingContext.transformContext(),
                rasterblockFeedback
            )
            self.assertTrue(error == QgsRasterFileWriter.WriterError.NoError, msg='Error')
            settingA._writeToLayer(file_name)

            self.assertEqual(settingA.n_bands(), lyr.bandCount())
            settingB = SpectralSetting.fromRasterLayer(file_name)
            self.assertIsInstance(settingB, SpectralSetting)

            ds: gdal.Dataset = gdal.Open(file_name)

            wl, wlu = parseWavelength(ds)
            self.assertListEqual(settingB.x(), wl.tolist())
            self.assertEqual(settingB.xUnit(), wlu)
            self.assertEqual(settingA, settingB)

            s = ""
