

from qps.utils import file_search, dn, jp
from qps.make.make import searchAndCompileResourceFiles
root = dn(__file__)

makeQrc = False
try:
    import os.path
    import qps.qpsresources

    pathQrc = jp(root, *['qps', 'qpsresources.qrc'])
    pathPy  = jp(root, *['qps', 'qpsresources.py'])

    if not os.path.isfile(pathPy) or os.path.getmtime(pathPy) < os.path.getmtime(pathQrc):
        makeQrc = True
    else:
        qps.qpsresources.qInitResources()
except Exception as ex:
    # compile resources
    makeQrc = True

if makeQrc:
    print('Need to create qpsresources.py')
    print('Start *.qrc search  in {}'.format(root))
    searchAndCompileResourceFiles(root)
else:
    print('qpsresources.py exists and is up-to-date')