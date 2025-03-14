import unittest

from qgis.core import QgsProcessingContext, QgsRasterBlockFeedback, QgsRasterFileWriter, QgsRasterLayer, QgsRasterPipe
from qps.speclib.core.spectralprofile import SpectralSetting
from qps.testing import start_app, TestCase, TestObjects

start_app()


class TestCore(TestCase):

    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestCore, cls).setUpClass(*args, **kwds)
        from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs
        initSpectralLibraryIOs()

    def test_SpectralSetting(self):
        from qpstestdata import enmap
        lyr1: QgsRasterLayer = TestObjects.createRasterLayer(nb=10)
        lyr2: QgsRasterLayer = QgsRasterLayer(enmap.as_posix(), 'EnMAP Tiff', 'gdal')

        test_dir = self.createTestOutputDirectory()

        for i, lyr in enumerate([lyr1, lyr2]):
            rasterblockFeedback = QgsRasterBlockFeedback()
            processingContext = QgsProcessingContext()
            processingFeedback = processingContext.feedback()

            settingA: SpectralSetting = SpectralSetting.fromRasterLayer(lyr)
            self.assertIsInstance(settingA, SpectralSetting)

            file_name = test_dir / f'layer_{i}.tiff'
            file_name = file_name.as_posix()
            file_writer = QgsRasterFileWriter(file_name)

            dp = lyr.dataProvider().clone()
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

            del file_writer
            self.assertTrue(error == QgsRasterFileWriter.WriterError.NoError, msg='Error')
            settingA.writeToSource(file_name)

            self.assertEqual(settingA.bandCount(), lyr.bandCount())

            settingB = SpectralSetting.fromRasterLayer(file_name)
            self.assertIsInstance(settingB, SpectralSetting)

            self.assertEqual(settingA.keys(), settingB.keys())

            self.assertWavelengthsEqual(settingA.wavelengths(), settingA.wavelengthUnits(),
                                        settingB.wavelengths(), settingB.wavelengthUnits())

            self.assertWavelengthsEqual(settingA.fwhm(), settingA.wavelengthUnits(),
                                        settingB.fwhm(), settingB.wavelengthUnits())

        lyr = TestObjects.createRasterLayer()
        setting1 = SpectralSetting.fromRasterLayer(lyr)

        setting1.setFieldName('Field1')

        setting1.writeToLayer(lyr)

        setting2 = SpectralSetting.fromRasterLayer(lyr)

        self.assertEqual(setting1.fieldName(), setting2.fieldName())
        # self.assertEqual(setting1.fieldEncoding(), setting2.fieldEncoding())


if __name__ == '__main__':
    unittest.main(buffer=False)
