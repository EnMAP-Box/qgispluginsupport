import site
import pathlib
import os
import importlib

if not '__file__' in locals():
    # replace with local path
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\run_from_qgis_python.py'

REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

import tests.speclib.test_speclib_plotting
importlib.reload(tests.speclib.test_speclib_plotting)
os.environ['CI'] = 'True'
CASE = tests.speclib.test_speclib_plotting.TestSpeclibPlotting()
CASE.test_SpectralProfilePlotControlModel()
