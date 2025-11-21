# noinspection PyPep8Naming
import json
import unittest

import numpy as np

from qps.speclib.core import is_spectral_feature, profile_field_names
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.io.envi import findENVIHeader, EnviSpectralLibraryReader, EnviSpectralLibraryWriter
from qps.testing import start_app, TestCase, TestObjects
from qpstestdata import enmap, envi_sli as envi_sli_path

start_app()


class TestSpeclibIO_ENVI(TestCase):

    def test_findEnviHeader(self):
        import qpstestdata

        hdr, bin = findENVIHeader(qpstestdata.envi_sli)
        self.assertEqual(hdr, qpstestdata.envi_sli_hdr.as_posix())
        self.assertEqual(bin, qpstestdata.envi_sli.as_posix())

        hdr, bin = findENVIHeader(qpstestdata.envi_sli_hdr)
        self.assertEqual(hdr, qpstestdata.envi_sli_hdr.as_posix())
        self.assertEqual(bin, qpstestdata.envi_sli.as_posix())

        hdr, bin = findENVIHeader(qpstestdata.envi_bsq)
        self.assertEqual(hdr, qpstestdata.envi_hdr.as_posix())
        self.assertEqual(bin, qpstestdata.envi_bsq.as_posix())

        hdr, bin = findENVIHeader(qpstestdata.envi_hdr)
        self.assertEqual(hdr, qpstestdata.envi_hdr.as_posix())
        self.assertEqual(bin, qpstestdata.envi_bsq.as_posix())

        pathWrong = enmap
        hdr, bin = findENVIHeader(pathWrong)
        self.assertTrue((hdr, bin) == (None, None))

    def test_read_ENVI(self):
        reader = EnviSpectralLibraryReader(envi_sli_path)

        profiles = reader.asFeatures()
        self.assertIsInstance(profiles, list)
        self.assertTrue(len(profiles) > 0)

        for p in profiles:
            self.assertTrue(is_spectral_feature(p))

    def test_write_ENVI(self):
        n_bands = [[25, 50],
                   [75, 100]
                   ]
        n_bands = np.asarray(n_bands)
        speclib = TestObjects.createSpectralLibrary(n_bands=n_bands)

        field_names = profile_field_names(speclib)

        testdir = self.createTestOutputDirectory()
        for field_name in field_names:
            path = testdir / f'exampleENVI.{field_name}.sli'

            writer = EnviSpectralLibraryWriter(path, field=field_name)

            profiles = list(speclib.getFeatures())
            files = writer.writeFeatures(path, profiles)

            self.assertIsInstance(files, list)
            self.assertEqual(len(files), 2)

            p_jsons_in = []
            for p in profiles:
                data = decodeProfileValueDict(p.attribute(field_name))
                self.assertIsInstance(data, dict)
                self.assertTrue(len(data) > 0)
                p_jsons_in.append(json.dumps(data, sort_keys=True))
            p_jsons_out = []
            for file in files:
                self.assertTrue(EnviSpectralLibraryReader.canReadFile(file))
                reader = EnviSpectralLibraryReader(file)
                profiles_out = reader.asFeatures()
                for p in profiles_out:
                    data = decodeProfileValueDict(p.attribute('profiles'))
                    self.assertIsInstance(data, dict)
                    self.assertTrue(len(data) > 0)
                    dump = json.dumps(data, sort_keys=True)
                    self.assertTrue(dump in p_jsons_in)


if __name__ == '__main__':
    unittest.main(buffer=False)
