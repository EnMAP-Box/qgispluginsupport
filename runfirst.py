def setupRepository():

    import os
    from qps.utils import file_search, dn, jp
    from qps.make.make import searchAndCompileResourceFiles
    root = os.path.dirname(os.path.realpath(__file__))
    assert os.path.isdir(root), 'Unable to find root / repository directory: "{}" __file__ = {}'.format(root, __file__)
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

if __name__ == "__main__":
    setupRepository()