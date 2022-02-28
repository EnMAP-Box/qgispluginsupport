# noinspection PyPep8Naming
import pathlib
import typing
import unittest

import xmlrunner
from qgis.core import QgsProcessingFeedback

from qgis.core import QgsVectorLayer
from qps.speclib.core import is_spectral_feature
from qps.speclib.core.spectrallibraryio import SpectralLibraryImportDialog, \
    SpectralLibraryIO
from qps.speclib.io.asd import ASDSpectralLibraryIO, ASDSpectralLibraryImportWidget, ASDBinaryFile
from qps.testing import TestObjects, TestCase
from qps.utils import file_search


class TestSpeclibIO_ASD(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_ASD, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_ASD, cls).tearDownClass()

    def registerIO(self):

        ios = [ASDSpectralLibraryIO()]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_read_with_gps(self):
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd' / 'gps'
        files = list(file_search(ASD_DIR, '*.asd', recursive=True))

        for file in files:
            asd = ASDBinaryFile(file)

            GPS = asd.gps_data
            s = ""

    def test_read_asdFile(self):

        for file in self.asdBinFiles():
            print(f'read {file}')
            asd = ASDBinaryFile(file)
            self.assertIsInstance(asd, ASDBinaryFile)
            profile = asd.asFeature()
            self.assertTrue(is_spectral_feature(profile))

        for file in self.asdCSVFiles():

            profiles = ASDSpectralLibraryIO.readCSVFile(file)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

    def asdBinFiles(self) -> typing.List[str]:
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd'
        return list(file_search(ASD_DIR, '*.asd', recursive=True))

    def asdCSVFiles(self):
        import qpstestdata
        ASD_DIR = pathlib.Path(qpstestdata.__file__).parent / 'asd'
        return list(file_search(ASD_DIR, '*.txt', recursive=True))

    def test_read_profiles(self):
        self.registerIO()

        IO = ASDSpectralLibraryIO()

        importWidget = IO.createImportWidget()
        self.assertIsInstance(importWidget, ASDSpectralLibraryImportWidget)
        sl: QgsVectorLayer = TestObjects.createSpectralLibrary()
        importWidget.setSpeclib(sl)

        files = self.asdBinFiles() + self.asdCSVFiles()

        paths = '"' + '" "'.join(files) + '"'
        feedback = QgsProcessingFeedback()
        profiles = IO.importProfiles(paths, {}, feedback)
        self.assertTrue(len(profiles) == len(files))
        for p in profiles:
            self.assertTrue(is_spectral_feature(p))

        self.showGui(importWidget)

    @unittest.skipIf(TestCase.runsInCI(), 'Skipped QDialog test in CI')
    def test_dialog(self):
        self.registerIO()
        sl = TestObjects.createSpectralLibrary()
        import qpstestdata.asd
        root = pathlib.Path(qpstestdata.__file__).parent / 'asd'

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
