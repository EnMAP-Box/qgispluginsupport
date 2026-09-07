import unittest
from pathlib import Path

from qgis.core import QgsFeature, QgsGeometry

from qps.speclib.core import is_spectral_feature
from qps.speclib.io.spectralevolution import SEDFile
from qps.testing import TestCase, start_app
from qps.utils import file_search

start_app()


class TestSpeclibIO_SED(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_SED, cls).setUpClass(*args, **kwds)

    def test_read_sed_files(self):
        import qpstestdata
        SED_DIR = Path(qpstestdata.__file__).parent / 'spectralevolution'
        files = list(file_search(SED_DIR, '*.sed', recursive=True))

        self.assertTrue(len(files) > 0)

        features = []
        for file in files:
            reader = SEDFile(file)

            for feature in reader.asFeatures():
                self.assertIsInstance(feature, QgsFeature)
                is_spectral_feature(feature)

                g = feature.geometry()
                self.assertIsInstance(g, QgsGeometry)

                features.append(feature)


if __name__ == '__main__':
    unittest.main(buffer=False)
