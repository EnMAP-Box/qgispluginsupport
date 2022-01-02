
from qgis.core import QgsProviderMetadata as A
from qgis._core import QgsProviderMetadata as B

def myFunc(*args, **kwds):
    return None

mdA = A('foo', 'bar', myFunc)
mdB = B('foo', 'bar', myFunc) #fails
