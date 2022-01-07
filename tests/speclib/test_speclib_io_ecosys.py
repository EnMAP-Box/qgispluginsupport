# noinspection PyPep8Naming
import os
import re
import unittest
import xmlrunner

from qps.speclib.core.spectrallibraryio import SpectralLibraryExportDialog, SpectralLibraryImportDialog
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
from qps.speclib.io.geopackage import GeoPackageSpectralLibraryIO, GeoPackageSpectralLibraryImportWidget, \
    GeoPackageSpectralLibraryExportWidget
from qps.testing import TestObjects, TestCase

from qgis.core import QgsRasterLayer, QgsVectorLayer, QgsProject, QgsEditorWidgetSetup, QgsField

from qpstestdata import enmap, landcover
from qpstestdata import speclib as speclibpath

from qps.speclib.io.vectorsources import *
from qps.speclib.io.csvdata import *
from qps.speclib.io.envi import *
from qps.speclib.io.rastersources import *

from qps.utils import *


class TestSpeclibIO_EcoSIS(TestCase):
    @classmethod
    def setUpClass(cls, *args, **kwds) -> None:
        super(TestSpeclibIO_EcoSIS, cls).setUpClass(*args, **kwds)

    @classmethod
    def tearDownClass(cls):
        super(TestSpeclibIO_EcoSIS, cls).tearDownClass()

    def testDir(self) -> pathlib.Path:
        path = self.createTestOutputDirectory() / 'SPECLIB_IO'
        os.makedirs(path, exist_ok=True)
        return path

    def registerIO(self):

        ios = [
            EcoSISSpectralLibraryIO(),
        ]
        SpectralLibraryIO.registerSpectralLibraryIO(ios)

    def test_EcoSIS(self):
        feedback = QgsProcessingFeedback()

        from qps.speclib.io.ecosis import EcoSISSpectralLibraryIO
        import qpstestdata
        ecosysFiles = []
        for f in os.scandir(pathlib.Path(qpstestdata.__file__).parent / 'ecosis'):
            if re.search(r'\.(csv|xlsx)$', f.name):
                ecosysFiles.append(pathlib.Path(f.path))

        # 1. read
        feedback = QgsProcessingFeedback()

        from qpstestdata import DIR_ECOSIS
        for path in ecosysFiles:

            print('Read {}...'.format(path))

            importSettings = dict()
            continue
            profiles = EcoSISSpectralLibraryIO.importProfiles(path, importSettings=importSettings, feedback=feedback)

            self.assertIsInstance(profiles, list)
            self.assertTrue(len(profiles) > 0)

        # 2. write
        speclib = TestObjects.createSpectralLibrary(50)

        # remove x/y values from first profile. this profile should be skipped in the outputs
        p0 = speclib[0]
        self.assertIsInstance(p0, SpectralProfile)
        p0.setValues(x=[], y=[])
        speclib.startEditing()
        speclib.updateFeature(p0)
        self.assertTrue(speclib.commitChanges())

        pathCSV = os.path.join(TEST_DIR, 'speclib.ecosys.csv')
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, feedback=QProgressDialog())
        csvFiles = EcoSISSpectralLibraryIO.write(speclib, pathCSV, feedback=None)
        n = 0
        for p in csvFiles:
            self.assertTrue(os.path.isfile(p))
            self.assertTrue(EcoSISSpectralLibraryIO.canRead(p))

            slPart = EcoSISSpectralLibraryIO.readFrom(p, feedback=QProgressDialog())
            self.assertIsInstance(slPart, SpectralLibrary)

            n += len(slPart)

        self.assertEqual(len(speclib) - 1, n)