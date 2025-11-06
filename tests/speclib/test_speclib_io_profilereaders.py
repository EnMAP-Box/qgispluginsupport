# noinspection PyPep8Naming
import re
import unittest
from datetime import datetime
from typing import List

import qpstestdata
from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.core import edit, QgsFeature, QgsField
from qps.fieldvalueconverter import collect_native_types
from qps.qgisenums import QMETATYPE_QDATE, QMETATYPE_QDATETIME
from qps.speclib.core import is_spectral_feature, profile_field_names, is_spectral_library
from qps.speclib.core.spectralprofile import decodeProfileValueDict, SpectralProfileFileReader, validateProfileValueDict
from qps.speclib.io.asd import ASDBinaryFile
from qps.speclib.io.spectralevolution import SEDFile
from qps.speclib.io.svc import SVCSigFile
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import file_search
from qpstestdata import DIR_TESTDATA

start_app()


class TestSpeclibIO_SpectralProfileReaders(TestCase):

    def profileFiles(self) -> List[str]:
        return list(file_search(DIR_TESTDATA, re.compile(r'.*\.(asd|sed|sig)$'), recursive=True))

    def test_read_svc_de(self):

        path_de = qpstestdata.DIR_TESTDATA / 'svc/250527_0942_R001_T002-de.sig'
        path_en = qpstestdata.DIR_TESTDATA / 'svc/250527_0942_R001_T002-en.sig'

        if False:
            svc1 = SVCSigFile(path_de)
            svc2 = SVCSigFile(path_en)

            self.assertEqual(svc1.mReference, svc2.mReference)
            self.assertEqual(svc1.mTarget, svc2.mTarget)
            self.assertEqual(svc1.mReferenceTime, svc2.mReferenceTime)
            self.assertEqual(svc1.mTargetTime, svc2.mTargetTime)

            self.assertEqual(svc1.mReferenceCoordinate, svc2.mReferenceCoordinate)
            self.assertEqual(svc1.mTargetCoordinate, svc2.mTargetCoordinate)

        alg = ImportSpectralProfiles()
        alg.initAlgorithm({})
        path_output = self.createTestOutputDirectory() / 'svc_examples.gpkg'
        par = {
            ImportSpectralProfiles.P_INPUT: [path_de.as_posix(), path_en.as_posix()],
            ImportSpectralProfiles.P_OUTPUT: path_output.as_posix(),
            # ImportSpectralProfiles.P_DATETIMEFORMAT: '%d/%m.%Y %H:%M:%S',
        }
        context, feedback = self.createProcessingContextFeedback()
        results, success = alg.run(par, context, feedback)
        self.assertTrue(success, msg=feedback.textLog())
        s = ""

    def test_import_files(self):
        from processing import run
        alg = ImportSpectralProfiles()
        alg.initAlgorithm({})
        par = {
            ImportSpectralProfiles.P_INPUT: self.profileFiles(),
        }
        context, feedback = self.createProcessingContextFeedback()

        results = run(alg, par, context=context, feedback=feedback)
        lyr = results[alg.P_OUTPUT]
        self.assertTrue(is_spectral_library(lyr))
        self.assertTrue(lyr.featureCount() > 0)

    def test_readFiles(self):

        for file in self.profileFiles():

            if file.endswith('.asd'):
                reader = ASDBinaryFile(file)
            elif file.endswith('.sed'):
                reader = SEDFile(file)
            elif file.endswith('.sig'):
                reader = SVCSigFile(file)
            else:
                raise NotImplementedError()

            self.assertIsInstance(reader, SpectralProfileFileReader)
            profiles = reader.asFeatures()
            assert len(profiles) > 0
            for profile in profiles:
                pfields = profile_field_names(profile)
                for name in pfields:
                    data = decodeProfileValueDict(profile.attribute(name))
                    self.assertTrue(validateProfileValueDict(data))

                attributes = profile.attributeMap()
                for k in [SpectralProfileFileReader.KEY_Metadata,
                          SpectralProfileFileReader.KEY_Target,
                          SpectralProfileFileReader.KEY_Path,
                          SpectralProfileFileReader.KEY_Name,
                          SpectralProfileFileReader.KEY_TargetTime]:
                    self.assertTrue(k in attributes, msg=f'Missing data "{k}" in {file}')

                metadata = profile.attribute(SpectralProfileFileReader.KEY_Metadata)
                self.assertIsInstance(metadata, dict)

                self.assertTrue(is_spectral_feature(profile))

    def test_fieldtypes(self):

        TEST_DIR = self.createTestOutputDirectory()
        path_gpkg = TEST_DIR / 'example.gpkg'
        vl = TestObjects.createVectorLayer(path=path_gpkg)

        nt = collect_native_types()
        with edit(vl):
            assert vl.addAttribute(QgsField('datetime', QMETATYPE_QDATETIME))
            assert vl.addAttribute(QgsField('date', QMETATYPE_QDATE))

        f = QgsFeature(vl.fields())
        dt = datetime.now()
        qdt = QDateTime.fromString(dt.isoformat(), Qt.ISODate)
        f.setAttribute('datetime', qdt)
        f.setAttribute('date', qdt.date())
        # f.setAttribute('time', QDateTime.fromString(dt.isoformat(), Qt.ISODate).time())

        with edit(vl):
            assert vl.addFeature(f)

        s = ""


if __name__ == '__main__':
    unittest.main(buffer=False)
