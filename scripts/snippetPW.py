import site
import pathlib
import os
if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippetPW.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

os.environ['CI'] = 'True'
TEST_DIR = REPO / 'tests' / 'speclib'
site.addsitedir(TEST_DIR)
args = f' -x {TEST_DIR.as_posix()}'
args = args.split(' ')
import pytest
pytest.main(args)
