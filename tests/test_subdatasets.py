import unittest
import os
from qps.testing import TestCase

from qps.subdatasets import *
class TestSubDataSets(TestCase):

    ref_file = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'

    @unittest.skipIf(not os.path.isfile(ref_file), 'Missing S2 Testfile')
    def test_subdataset_info(self):

        info = DatasetInfo.fromRaster(TestSubDataSets.ref_file)

        self.assertIsInstance(info, DatasetInfo)
        s = ""
        for name, descr, sdtype in zip(info.subdataset_names(), info.subdataset_descriptions(), info.subdataset_types()):
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
        subs = [l.strip() for l in subs.splitlines()]
        subs = [l.split('###') for l in subs if len(l) > 0]
        subs = [(l[0], l[1]) for l in subs]
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

    def test_subdatasetdialog(self):
        files = self.create_references_filelist()
        filesString = r'"H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20191208T140049_N0208_R067_T21LWL_20191208T153903.SAFE\MTD_MSIL1C.xml" "H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20191211T141039_N0208_R110_T21LWL_20191211T154826.SAFE\MTD_MSIL1C.xml" "H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20200107T140049_N0208_R067_T21LWL_20200107T153927.SAFE\MTD_MSIL1C.xml" "H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20191218T140049_N0208_R067_T21LWL_20191218T153923.SAFE\MTD_MSIL1C.xml" "H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20191221T141039_N0208_R110_T21LWL_20191221T154811.SAFE\MTD_MSIL1C.xml" "H:\Processing_BJ\01_Data\Sentinel2\T21LWL\S2B_MSIL1C_20200110T141039_N0208_R110_T21LWL_20200110T154843.SAFE\MTD_MSIL1C.xml"'

        d = SubDatasetSelectionDialog()
        d.setWindowTitle('Select Sentinel2 Images')
        d.setFileFilter('*.xml')
        d.fileWidget.setFilePath(filesString)

        defRoot = pathlib.Path('~').expanduser().as_posix()
        d.setDefaultRoot(defRoot)
        self.assertEqual(defRoot, d.defaultRoot())

        def onAccepted():
            files = d.selectedSubDatasets()

            for file in files:
                print('Load {}'.format(file))
                self.assertIsInstance(file, str)
                lyr = QgsRasterLayer(file)
                self.assertIsInstance(lyr, QgsRasterLayer)
                self.assertTrue(lyr.isValid())

        d.accepted.connect(onAccepted)
        self.showGui(d)


if __name__ == '__main__':
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
