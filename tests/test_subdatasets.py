import unittest
import os
from qps.testing import TestCase

from qps.subdatasets import *
class TestSubDataSets(TestCase):

    ref_file = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'

    @unittest.skipIf(not os.path.isfile(ref_file), 'Missing S2 Testfile')
    def test_subdataset_info(self):

        info = SubDatasetInfo.fromRaster(TestSubDataSets.ref_file)

        self.assertIsInstance(info, SubDatasetInfo)
        for name, descr in zip(info.subset_names(), info.subset_descriptions()):
            self.assertIsInstance(name, str)
            self.assertIsInstance(descr, str)
            #print('{}###{}'.format(name, descr))
        s = ""
    def create_subset_infos(self) -> typing.List[SubDatasetInfo]:

        subs = r"""
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:10m:EPSG_32631###Bands B2, B3, B4, B8 with 10m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:20m:EPSG_32631###Bands B5, B6, B7, B8A, B11, B12 with 20m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:60m:EPSG_32631###Bands B1, B9 with 60m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:TCI:EPSG_32631###True color image, UTM 31N
        """
        subs = [l.strip() for l in subs.splitlines()]
        subs = [l.split('###') for l in subs if len(l) > 0]
        subs = [(l[0], l[1]) for l in subs]
        results = []
        path = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'
        results.append(SubDatasetInfo(path, subs))
        return results

    def create_references_filelist(self) -> typing.List[str]:
        infos = self.create_subset_infos()
        return [i.mReferenceFile for i in infos]


    def test_subdatasetdescription(self):
        d = SubDatasetDescription('a', False)
        self.assertEqual(d.checked, False)
        self.assertEqual(d.name, 'a')

    def test_subdatasettask(self):
        files = self.create_references_filelist()

        foundInfos = []
        def onSubDatasetsFound(infos: typing.List[SubDatasetInfo]):
            self.assertIsInstance(infos, list)
            for info in infos:
                self.assertIsInstance(info, SubDatasetInfo)
                foundInfos.append(info)
        task = SubDatasetLoadingTask(files)
        task.sigFoundSubDataSets.connect(onSubDatasetsFound)
        task.run()

        self.assertTrue(len(foundInfos) > 0)

    def test_subdatasetdialog(self):
        files = self.create_references_filelist()
        for i in range(3):
            files.append(files[i])



        d = SubDatasetSelectionDialog()
        d.setWindowTitle('Select Sentinel2 Images')
        d.setFileFilter('*.xml')
        d.setFiles(files)

        def onAccepted():
            files = d.selectedSubDatasets()

            for file in files:
                self.assertIsInstance(file, str)
                lyr = QgsRasterLayer(file)
                self.assertIsInstance(lyr, QgsRasterLayer)
                self.assertTrue(lyr.isValid())

        d.accepted.connect(onAccepted)
        self.showGui(d)


if __name__ == '__main__':
    unittest.main()
