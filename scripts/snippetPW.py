import site
import pathlib
import os
if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

os.environ['CI'] = 'True'
TEST_DIR = REPO / 'tests' / 'speclib'
TEST_DIR = pathlib.Path(r'D:\Repositories\QGIS\tests\src\python')
site.addsitedir(TEST_DIR)
args = f' {TEST_DIR}'
args = args.split(' ')
import pytest
pytest.main(args)
