# noinspection PyPep8Naming
import pathlib
import re
import unittest
from datetime import datetime

import qpstestdata
from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.core import edit, QgsFeature, QgsField
from qps.fieldvalueconverter import collect_native_types
from qps.qgisenums import QMETATYPE_QDATE, QMETATYPE_QDATETIME
from qps.speclib.core import is_spectral_feature, profile_field_names
from qps.speclib.core.spectrallibraryio import initSpectralLibraryIOs, SpectralLibraryImportDialog
from qps.speclib.core.spectralprofile import decodeProfileValueDict, SpectralProfileFileReader, validateProfileValueDict
from qps.speclib.io.asd import ASDBinaryFile
from qps.speclib.io.spectralevolution import SEDFile
from qps.speclib.io.svc import SVCSigFile
from qps.testing import start_app, TestCase, TestObjects
from qps.utils import file_search
from qpstestdata import DIR_TESTDATA

start_app()


class TestSpeclibIO_SpectralProfileReaders(TestCase):

    def registerIO(self):
        initSpectralLibraryIOs()

    def profileFiles(self):
        return list(file_search(DIR_TESTDATA, re.compile(r'.*\.(asd|sed|sig)$'), recursive=True))

    def test_read_svc_de(self):

        path_de = qpstestdata.DIR_TESTDATA / 'svc/250527_0942_R001_T002-de.sig'
        path_en = qpstestdata.DIR_TESTDATA / 'svc/250527_0942_R001_T002-en.sig'

        svc1 = SVCSigFile(path_de)
        svc2 = SVCSigFile(path_en)

        self.assertEqual(svc1.mReference, svc2.mReference)
        self.assertEqual(svc1.mTarget, svc2.mTarget)
        self.assertEqual(svc1.mReferenceTime, svc2.mReferenceTime)
        self.assertEqual(svc1.mTargetTime, svc2.mTargetTime)

        self.assertEqual(svc1.mReferenceCoordinate, svc2.mReferenceCoordinate)
        self.assertEqual(svc1.mTargetCoordinate, svc2.mTargetCoordinate)

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
            profile = reader.asFeature()
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

    @unittest.skipIf(TestCase.runsInCI(), 'Skipped QDialog test in CI')
    def test_dialog(self):
        self.registerIO()
        sl = TestObjects.createSpectralLibrary()
        import qpstestdata
        root = pathlib.Path(qpstestdata.__file__).parent / 'svc'

        SpectralLibraryImportDialog.importProfiles(sl, defaultRoot=root.as_posix())

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
