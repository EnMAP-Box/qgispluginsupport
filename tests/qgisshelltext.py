import sys
sys.path.append(r'C:\Users\geo_beja\Repositories\QGIS_Plugins\qgispluginsupport')
from enmapboxtestdata import library
from qps.speclib.spectrallibraries import SpectralLibraryWidget, SpectralLibrary
w1 = SpectralLibraryWidget()
w1.show()
w1.importSpeclib(library)
w2 = SpectralLibraryWidget()
w2.show()



test_spectrallibraries.SHOW_GUI = True
TCore = test_spectrallibraries.TestCore()
TCore.test_SpectralLibraryWidget()
TCore.test_SpectralLibraryWidget()



from PyQt5.QtCore import QProcessEnvironment
for k in sorted(QProcessEnvironment.systemEnvironment().keys()):
    value = QProcessEnvironment.systemEnvironment().value(k)
    if k.upper() in ['PATH', 'PYTHONPATH', 'QT_PLUGIN_PATH']:
        value = '\n\t' + '\n\t'.join(value.split(';'))
    print('{}={}'.format(k, value))

import os
for k in sorted(os.environ.keys()):
    value = os.environ[k]
    if k.upper() in ['PATH', 'PYTHONPATH', 'QT_PLUGIN_PATH']:
        value = '\n\t' + '\n\t'.join(value.split(';'))
    print('{}={}'.format(k, value))

from PyQt5.QtCore import QLibrary


