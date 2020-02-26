import pathlib, sys, site

def setupRepository():

    import os
    DIR_REPO = pathlib.Path(__file__).parent.resolve()
    site.addsitedir(DIR_REPO)

    from qps.make.make import compileResourceFiles

    makeQrc = False
    try:
        import os.path
        import qps.qpsresources

        pathQrc = DIR_REPO / 'qps' / 'qpsresources.qrc'
        pathPy  = DIR_REPO / 'qps' / 'qpsresources.py'

        if not pathPy.is_file() or os.path.getmtime(pathPy) < os.path.getmtime(pathQrc):
            makeQrc = True

    except Exception as ex:
        # compile resources
        makeQrc = True

    if makeQrc:
        print('Need to create qpsresources.py')
        print('Start *.qrc search  in {}'.format(DIR_REPO))
        compileResourceFiles(DIR_REPO)
    else:
        print('qpsresources.py exists and is up-to-date')

if __name__ == "__main__":
    setupRepository()