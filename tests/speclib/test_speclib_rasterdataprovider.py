from qgis.core import QgsProviderMetadata
from qps.testing import start_app
from qps.speclib.core.spectrallibraryrasterdataprovider import SpectralLibraryRasterDataProvider, registerDataProvider
app = start_app()

def myfunc(*args, **kwds):
    return ''

QgsProviderMetadata('t', 'test', myfunc)
registerDataProvider()

s = ""