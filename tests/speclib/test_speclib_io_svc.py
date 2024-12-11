import os.path
import pathlib
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import List

from qgis.core import QgsFeature, QgsVectorLayer

from qps import initAll
from qps.speclib.core import is_spectral_feature, is_spectral_library, profile_field_names
from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs, SpectralLibraryImportDialog
from qps.speclib.core.spectralprofile import decodeProfileValueDict, isProfileValueDict, validateProfileValueDict
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.svc import SVCSigFile, SVCSpectralLibraryIO
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import file_search

start_app()


class TestSpeclibIO_SVC(TestCase):

    def registerIO(self):
        initSpectralLibraryIOs()

    def test_read_sigFile(self):

        for file in self.svcFiles():
            print(f'read {file}')
            svc = SVCSigFile(file)
            self.assertIsInstance(svc, SVCSigFile)
            self.assertTrue(isProfileValueDict(svc.reference()))
            self.assertTrue(isProfileValueDict(svc.target()))
            self.assertIsInstance(svc.targetTime(), datetime)
            self.assertIsInstance(svc.referenceTime(), datetime)
            self.assertIsInstance(svc.metadata(), dict)
            self.assertIsInstance(svc.path(), Path)
            self.assertTrue(svc.path().is_file())
            self.assertIsInstance(svc.picturePath(), Path)
            self.assertTrue(svc.picturePath().is_file())
            profile = svc.asFeature()
            self.assertIsInstance(profile, QgsFeature)
            self.assertTrue(is_spectral_feature(profile))

            picture_path = profile.attribute(SVCSigFile.KEY_Picture)
            self.assertIsInstance(picture_path, str)
            self.assertTrue(os.path.isfile(picture_path))

        for file in self.svcFiles():
            settings = {}
            profiles = SVCSpectralLibraryIO.importProfiles(file, importSettings=settings)
            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)
            for p in profiles:
                self.assertTrue(is_spectral_feature(p))

                for name in profile_field_names(p):
                    data = decodeProfileValueDict(p.attribute(name))
                    self.assertTrue(validateProfileValueDict(data))
                    s = ""

    def svcFiles(self) -> List[str]:
        import qpstestdata
        svc_dir = pathlib.Path(qpstestdata.__file__).parent / 'svc'
        return list(file_search(svc_dir, re.compile(r'.*\.sig$'), recursive=True))

    @unittest.skipIf(TestCase.runsInCI(), 'Skipped QDialog test in CI')
    def test_dialog(self):
        sl = TestObjects.createSpectralLibrary()
        import qpstestdata.asd
        root = pathlib.Path(qpstestdata.__file__).parent / 'svc'

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())

    @unittest.skipIf(TestCase.runsInCI(), 'Skipped CI')
    def test_speclib(self):
        initAll()
        alg = ImportSpectralProfiles()

        svc_files = self.svcFiles()
        path_test = '/vsimem/exampleimport.gpkg'
        par = {
            ImportSpectralProfiles.P_INPUT: svc_files,
            ImportSpectralProfiles.P_OUTPUT: path_test
        }

        context, feedback = self.createProcessingContextFeedback()
        conf = {}
        alg = ImportSpectralProfiles()
        alg.initAlgorithm(conf)

        results, success = alg.run(par, context, feedback, conf)
        self.assertTrue(success, msg=feedback.textLog())

        lyr = results[ImportSpectralProfiles.P_OUTPUT]
        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr)
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        self.assertTrue(lyr.featureCount() > 0)
        self.assertTrue(is_spectral_library(lyr))
        self.assertTrue(lyr.fields()['picture'].editorWidgetSetup().type() == 'ExternalResource')
        slw = SpectralLibraryWidget(speclib=lyr)
        self.showGui(slw)

        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
