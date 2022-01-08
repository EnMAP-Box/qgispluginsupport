import unittest
import xmlrunner

from qps.searchfiledialog import SearchFilesDialog
from qps.testing import TestCase, TestObjects


class SearchFileDialogTest(TestCase):

    def test_search_files_dialog(self):
        d = SearchFilesDialog()

        self.showGui(d)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)
