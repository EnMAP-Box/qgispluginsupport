import unittest

from qps.testing import TestCase, TestObjects

from qps.searchfiledialog import *

class SearchFileDialogTest(TestCase):

    def test_search_files_dialog(self):


        d = SearchFilesDialog()

        self.showGui(d)

if __name__ == '__main__':
    unittest.main()
