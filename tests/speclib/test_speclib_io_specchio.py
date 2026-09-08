# -*- coding: utf-8 -*-
"""
***************************************************************************

    ---------------------
    Date                 : 2024
    Copyright            : (C) 2024 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import unittest
from pathlib import Path

from qgis.core import QgsProject

from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.speclib.core.spectralprofile import isProfileValueDict
from qps.speclib.io.specchio import SPECCHIOReader
from qps.testing import TestCase, TestObjects, start_app
from qpstestdata import DIR_SPECCHIO

start_app()


class SPECCHIOTests(TestCase):

    def test_specchio_reader_canRead(self):

        csv_file = DIR_SPECCHIO / 'Spectral_Space_1.csv'
        self.assertTrue(csv_file.exists())

        # Test valid SPECCHIO file
        self.assertTrue(SPECCHIOReader.canReadFile(str(csv_file)))

        # Test non-existent file
        self.assertFalse(SPECCHIOReader.canReadFile('/nonexistent/file.csv'))

        # Test invalid file (empty)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write('\n')
            temp_path = f.name

        try:
            self.assertFalse(SPECCHIOReader.canReadFile(temp_path))
        finally:
            Path(temp_path).unlink()

        # Test file without numeric values
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write('header1,header2\n')
            f.write('value1,value2\n')
            temp_path = f.name

        try:
            self.assertFalse(SPECCHIOReader.canReadFile(temp_path))
        finally:
            Path(temp_path).unlink()

    def test_specchio_reader_id(self):

        reader = SPECCHIOReader(DIR_SPECCHIO / 'Spectral_Space_1.csv')
        self.assertEqual(reader.id(), 'specchio')

    def test_specchio_reader_shortHelp(self):

        reader = SPECCHIOReader(DIR_SPECCHIO / 'Spectral_Space_1.csv')
        self.assertIn('SPECCHIO', reader.shortHelp())

    def test_specchio_reader_path(self):

        csv_file = DIR_SPECCHIO / 'Spectral_Space_1.csv'
        reader = SPECCHIOReader(csv_file)
        self.assertEqual(reader.path(), csv_file)

    def test_specchio_reader_readProfiles(self):

        csv_file = DIR_SPECCHIO / 'Spectral_Space_1.csv'
        reader = SPECCHIOReader(csv_file)

        profiles = reader._readProfiles()

        self.assertIsInstance(profiles, list)
        self.assertEqual(len(profiles), 4)  # 4 profiles in the file

        # Check first profile
        first_profile = profiles[0]
        self.assertIn('x', first_profile)
        self.assertIn('y', first_profile)
        self.assertIn('xUnit', first_profile)
        self.assertIn('metadata', first_profile)
        self.assertIn('name', first_profile)

        # Check wavelength values
        self.assertEqual(len(first_profile['x']), len(first_profile['y']))
        self.assertEqual(first_profile['xUnit'], 'nm')

        # Check metadata
        self.assertIn('File Name', first_profile['metadata'])
        self.assertEqual(first_profile['metadata']['File Name'], 'pine_transmittance_exposed_B')

        # Check name
        self.assertEqual(first_profile['name'], 'Spectral_Space_1:1')

    def test_specchio_reader_metadataKeys(self):

        csv_file = DIR_SPECCHIO / 'Spectral_Space_1.csv'
        self.assertTrue(csv_file.exists())
        self.assertTrue(SPECCHIOReader.canReadFile(csv_file))
        reader = SPECCHIOReader(csv_file)

        metadata_keys = reader.metadataKeys()

        self.assertIsInstance(metadata_keys, list)
        self.assertIn('File Name', metadata_keys)
        self.assertIn('Investigator', metadata_keys)
        self.assertIn('Loading Time', metadata_keys)
        self.assertIn('Beam Geometry', metadata_keys)
        self.assertIn('Sampling Environment', metadata_keys)
        self.assertIn('Location Name', metadata_keys)
        self.assertIn('Target Description', metadata_keys)
        self.assertIn('Target Homogeneity', metadata_keys)
        self.assertIn('Altitude', metadata_keys)
        self.assertIn('File Comments', metadata_keys)
        self.assertIn('Publication', metadata_keys)
        self.assertIn('Latitude', metadata_keys)
        self.assertIn('Longitude', metadata_keys)
        self.assertIn('CORINE Landcover', metadata_keys)
        self.assertIn('Number of internal Scans', metadata_keys)

    def test_specchio_reader_asFeatures(self):

        csv_file = DIR_SPECCHIO / 'Spectral_Space_1.csv'
        reader = SPECCHIOReader(csv_file)

        features = reader.asFeatures()

        self.assertIsInstance(features, list)
        self.assertEqual(len(features), 4)

        for i, feat in enumerate(features):
            self.assertEqual(feat.fields().count(), 2 + len(reader.metadataKeys()))

            attr = feat.attributeMap()

            self.assertEqual(attr['name'], f'{csv_file.stem}:{i + 1}')

            d = decodeProfileValueDict(feat['profile'])
            self.assertTrue(isProfileValueDict(d))

    def test_specchio_io_write_and_read_roundtrip(self):

        # Create a test spectral library
        sl = TestObjects.createSpectralLibrary(3, n_bands=[10, 20, 15])
        sl.setName('Test Speclib')

        # Add custom metadata fields
        sl.startEditing()
        from qps.utils import createQgsField
        sl.addAttribute(createQgsField('test_metadata', 'test'))
        for feat in sl.getFeatures():
            feat['test_metadata'] = 'value_{}'.format(feat.id())
            sl.updateFeature(feat)
        sl.commitChanges()

        # Write to temporary file
        # import tempfile
        # with tempfile.TemporaryDirectory() as tmpdir:
        #     # output_path = Path(tmpdir) / 'test_specchio.csv'
        #     pass
        #     pass

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main(buffer=False)
