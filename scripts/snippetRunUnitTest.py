import importlib
import os
import pathlib
import site

if not '__file__' in locals():
    __file__ = r'C:\Users\geo_beja\Repositories\qgispluginsupport\scripts\snippetRunUnitTest.py'

REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)
site.addsitedir(REPO / 'tests')
os.environ['CI'] = 'True'

import test_processing

importlib.reload(test_processing)
TestCases = test_processing.ProcessingToolsTest()

TestCases.test_aggregate_profiles()
