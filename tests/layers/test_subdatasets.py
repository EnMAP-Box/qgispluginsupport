import os
import typing
import unittest

from qps.subdatasets import DatasetInfo, SubDatasetType, \
    SubDatasetLoadingTask
from qps.testing import TestCase


class TestSubDataSets(TestCase):
    ref_file = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'

    @unittest.skipIf(not os.path.isfile(ref_file), 'Missing S2 Testfile')
    def test_subdataset_info(self):

        info = DatasetInfo.fromRaster(TestSubDataSets.ref_file)

        self.assertIsInstance(info, DatasetInfo)
        s = ""
        for name, descr, sdtype in zip(info.subdataset_names(), info.subdataset_descriptions(),
                                       info.subdataset_types()):
            self.assertIsInstance(name, str)
            self.assertIsInstance(descr, str)
            self.assertIsInstance(sdtype, SubDatasetType)
            self.assertEqual(sdtype.name, descr)

    def create_subset_infos(self) -> typing.List[DatasetInfo]:

        subs = r"""
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:10m:EPSG_32631###Bands B2, B3, B4, B8 with 10m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:20m:EPSG_32631###Bands B5, B6, B7, B8A, B11, B12 with 20m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:60m:EPSG_32631###Bands B1, B9 with 60m resolution, UTM 31N
SENTINEL2_L2A:D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml:TCI:EPSG_32631###True color image, UTM 31N
        """
        subs = [line.strip() for line in subs.splitlines()]
        subs = [line.split('###') for line in subs if len(line) > 0]
        subs = [(line[0], line[1]) for line in subs]
        results = []
        path = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'
        results.append(DatasetInfo(path, subs))
        return results

    def create_references_filelist(self) -> typing.List[str]:
        infos = self.create_subset_infos()
        return [i.mReferenceFile for i in infos]

    def test_subdatasetdescription(self):
        d = SubDatasetType('a', False)
        self.assertEqual(d.checked, False)
        self.assertEqual(d.name, 'a')

    def test_subdatasettask(self):
        files = self.create_references_filelist()
        files = [f for f in files if os.path.isfile(f)]
        if len(files) > 0:
            foundInfos = []

            def onSubDatasetsFound(infos: typing.List[DatasetInfo]):
                self.assertIsInstance(infos, list)
                for info in infos:
                    self.assertIsInstance(info, DatasetInfo)
                    foundInfos.append(info)

            task = SubDatasetLoadingTask(files)
            task.sigFoundSubDataSets.connect(onSubDatasetsFound)
            task.run()

            self.assertTrue(len(foundInfos) > 0)


if __name__ == '__main__':

    unittest.main(buffer=False)
