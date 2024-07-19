import pathlib
import site

import test_speclib_plotting

if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

TESTS = REPO / 'tests' / 'speclib'
site.addsitedir(TESTS)

test_speclib_plotting.TestSpeclibPlotting.test_SpectralLibraryPlotWidget()
