import sys

from qgis.core import Qgis
from qgis.testing import start_app

print('Python version: ', sys.version)
print('QGIS version: ', Qgis.version())

if True:
    # this crashes. QgsApplication is initialized before numba import
    app = start_app()
    from numba import jit, int32, __version__ as numba_version
else:
    # this works
    from numba import jit, int32, __version__ as numba_version

    app = start_app()

print('Numba version: ', numba_version)


@jit(int32(int32, int32))
def func(x, y):
    # A somewhat trivial example
    return x + y


print(func(1, 2))
