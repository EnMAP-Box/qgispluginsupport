import os.path
import pathlib
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import List

from qgis.core import QgsFeature, QgsVectorLayer
from qps import initAll
from qps.speclib.core import is_spectral_feature, is_spectral_library
from qps.speclib.core.spectralprofile import isProfileValueDict
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.svc import SVCSigFile
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import start_app, TestCase
from qps.utils import file_search

start_app()


class TestSpeclibIO_SVC(TestCase):

    def test_read_sigFile(self):

        for file in self.svcFiles():

            print(f'read {file}')

            self.assertTrue(SVCSigFile.canReadFile(file))

            svc = SVCSigFile(file)
            self.assertIsInstance(svc, SVCSigFile)
            self.assertTrue(isProfileValueDict(svc.reference()))
            self.assertTrue(isProfileValueDict(svc.target()))
            self.assertIsInstance(svc.targetTime(), datetime)
            self.assertIsInstance(svc.referenceTime(), datetime)
            self.assertIsInstance(svc.metadata(), dict)
            self.assertIsInstance(svc.path(), Path)
            self.assertTrue(svc.path().is_file())
            if svc.picturePath():
                self.assertIsInstance(svc.picturePath(), Path)
                self.assertTrue(svc.picturePath().is_file())

            for profile in svc.asFeatures():
                self.assertIsInstance(profile, QgsFeature)
                self.assertTrue(is_spectral_feature(profile))

                picture_path = profile.attribute(SVCSigFile.KEY_Picture)
                if picture_path:
                    self.assertIsInstance(picture_path, str)
                    self.assertTrue(os.path.isfile(picture_path))

    def svcFiles(self) -> List[str]:
        import qpstestdata
        svc_dir = pathlib.Path(qpstestdata.__file__).parent / 'svc'
        return list(file_search(svc_dir, re.compile(r'.*\.sig$'), recursive=True))

    def test_parse_datetime(self):

        # dt = datetime.now().replace(microsecond=0)
        dt = datetime(2025, 10, 15, 12, 21, 50)
        # dt = datetime(2025, 10, 15, 8, 21, 50)
        formats = [
            '%d.%m.%Y %H:%M:%S',  # 27.05.2025 09:39:32
            '%m/%d/%Y %H:%M:%S%p',  # 5/27/2025 9:39:32AM
            '%m/%d/%Y %H:%M:%S %p',  # 5/27/2025 9:39:32 AM
            '%m/%d/%Y %H:%M:%S',  # 5/27/2025 9:39:32
        ]
        self.assertEqual(dt, SVCSigFile._readDateTime(dt.isoformat()))
        for fmt in formats:
            text = dt.strftime(fmt)
            dt2 = SVCSigFile._readDateTime(text)
            if dt != dt2:
                s = ""
            self.assertEqual(dt, dt2, msg=f'Failed for format "{fmt}" : {text}')

    # @unittest.skipIf(TestCase.runsInCI(), 'Skipped CI')
    def test_speclib(self):
        initAll()
        alg = ImportSpectralProfiles()

        svc_files = self.svcFiles()

        test_dir = self.createTestOutputDirectory()

        path_test = test_dir / 'exampleimport.gpkg'

        par = {
            ImportSpectralProfiles.P_INPUT: svc_files,
            ImportSpectralProfiles.P_INPUT_TYPE: 'SVC',
            ImportSpectralProfiles.P_OUTPUT: path_test.as_posix(),
        }

        context, feedback = self.createProcessingContextFeedback()
        conf = {}
        alg = ImportSpectralProfiles()
        alg.initAlgorithm(conf)

        alg.prepareAlgorithm(par, context, feedback)
        results = alg.processAlgorithm(par, context, feedback)

        results, success = alg.run(par, context, feedback, conf)
        self.assertTrue(success, msg=feedback.textLog())

        lyr = results[ImportSpectralProfiles.P_OUTPUT]
        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr)
        self.assertIsInstance(lyr, QgsVectorLayer)
        self.assertTrue(lyr.isValid())
        self.assertTrue(lyr.featureCount() > 0)
        self.assertTrue(is_spectral_library(lyr))

        setup = lyr.fields()['picture'].editorWidgetSetup()
        conf = setup.config()
        self.assertTrue(setup.type() == 'ExternalResource')

        from qgis.core import QgsProject
        QgsProject.instance().addMapLayer(lyr)
        slw = SpectralLibraryWidget(speclib=lyr)

        self.showGui(slw)
        QgsProject.instance().removeAllMapLayers()
        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
