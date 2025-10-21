import os
import unittest

from osgeo import gdal

from qgis.PyQt.QtWidgets import QDialog
from qgis.core import QgsApplication, QgsProviderSublayerDetails
from qps.subdatasets import SubDatasetLoadingTask, SubDatasetSelectionDialog
from qps.testing import start_app, TestCase, TestObjects

start_app()


@unittest.skipIf(not TestObjects.repoDirGDAL(), 'Test requires GDAL repo testdata')
class TestSubDataSets(TestCase):
    @unittest.skipIf(not TestObjects.repoDirGDAL(), 'Test requires GDAL repo testdata')
    def test_subdatasettask(self):

        dir_gdal = TestObjects.repoDirGDAL()
        sources = [
            # dir_gdal / 'autotest/gdrivers/data/hdf5/groups.h5',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l1c/S2A_OPER_PRD_MSIL1C.SAFE/S2A_OPER_MTD_SAFL1C.xml',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l2a/S2A_USER_PRD_MSIL2A.SAFE/S2A_USER_MTD_SAFL2A.xml',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l2a/S2A_USER_PRD_MSIL2A.SAFE/S2A_USER_MTD_SAFL2A.xml',
            dir_gdal / 'autotest/gdrivers/data/gpkg/50000_25000_uint16.gpkg.zip'
        ]
        for s in sources:
            self.assertTrue(s.is_file(), msg=str(s))

        task = SubDatasetLoadingTask(sources)
        task.run()
        for p, results in task.results().items():
            self.assertTrue(os.path.isfile(p))
            ds = gdal.Open(p)
            if isinstance(ds, gdal.Dataset):
                self.assertTrue(len(results) > 0)
            for r in results:
                self.assertIsInstance(r, QgsProviderSublayerDetails)

    def test_tanager_h5(self):

        path_tanager = r'/home/jakimowb/Downloads/20250510_005001_00_4001_basic_radiance.h5'
        if os.path.isfile(path_tanager):
            task = SubDatasetLoadingTask([path_tanager])
            assert task.run()

            from qgis.gui import QgsProviderSublayersDialog

            results = task.results()
            for p, sublayers in results.items():
                for d in sublayers:
                    self.assertIsInstance(d, QgsProviderSublayerDetails)
                    d2 = QgsProviderSublayersDialog(d.uri(), d.providerKey(), d.uri(), [])
                    self.showGui(d2)
                    d.providerKey()

            d = SubDatasetSelectionDialog()
            d.setFiles([path_tanager])
            self.showGui(d)

    @unittest.skipIf(not TestObjects.repoDirGDAL(), 'Test requires GDAL repo testdata')
    def test_subdatasetDialog(self):

        dir_gdal = TestObjects.repoDirGDAL()

        sources = [
            dir_gdal / 'autotest/gdrivers/data/hdf5/groups.h5',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l1c/S2A_OPER_PRD_MSIL1C.SAFE/S2A_OPER_MTD_SAFL1C.xml',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l2a/S2A_USER_PRD_MSIL2A.SAFE/S2A_USER_MTD_SAFL2A.xml',
            dir_gdal / 'autotest/gdrivers/data/sentinel2/fake_l2a/S2A_USER_PRD_MSIL2A.SAFE/S2A_USER_MTD_SAFL2A.xml',
            dir_gdal / 'autotest/gdrivers/data/gpkg/50000_25000_uint16.gpkg.zip/50000_25000_uint16.gpkg',
            dir_gdal / 'autotest/ogr/data/gpkg/domains.gpkg',
            dir_gdal / 'autotest/ogr/data/gpkg/poly.gpkg.zip',
        ]

        d = SubDatasetSelectionDialog()
        d.setFiles(sources)
        QgsApplication.processEvents()
        d.showMultiFiles(False)
        d.showMultiFiles(True)

        while len(QgsApplication.taskManager().tasks()) > 0:
            QgsApplication.processEvents()

        self.assertTrue(d.tvSubDatasets.model().rowCount() > 0)

        d.tvSubDatasets.selectRow(0)
        sublayers = d.selectedSublayerDetails()
        self.assertEqual(len(sublayers), 1)

        if not TestCase.runsInCI():
            if d.exec() == QDialog.Accepted:
                sublayers = d.selectedSublayerDetails()
                print(f'Sub layers: {sublayers}')


if __name__ == '__main__':
    unittest.main(buffer=False)
