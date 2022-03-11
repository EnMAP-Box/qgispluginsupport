import site
import pathlib
import os
import importlib
if not '__file__' in locals():
    __file__ = r'C:\Users\geo_beja\Repositories\qgispluginsupport\scripts\snippetRunUnitTest.py'

REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)
site.addsitedir(REPO / 'tests' / 'speclib')

os.environ['CI'] = 'True'
import test_speclib_io_geojson
from qps.speclib.core import spectrallibraryio
importlib.reload(test_speclib_io_geojson)
importlib.reload(spectrallibraryio)
TestCases = test_speclib_io_geojson.TestSpeclibIOGeoJSON()
TestCases.test_write_profiles()
