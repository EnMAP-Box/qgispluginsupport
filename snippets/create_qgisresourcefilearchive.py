import pathlib, os, zipfile, sys

if __name__ == '__main__':

    import getopt
    try:
        print(sys.argv)
        opts, qgis_repo = getopt.getopt(sys.argv[1:], "")
    except getopt.GetoptError as err:
        print(err)
    if len(qgis_repo) == 0:
        assert 'QGIS_REPO' in os.environ.keys(), 'QGIS_REPO is not specified'
        qgis_repo = os.environ['QGIS_REPO']
    else:
        qgis_repo = qgis_repo[0]

    QGIS_REPO = pathlib.Path(qgis_repo)
    from qps.make.make import compileQGISResourceFiles
    TARGET_DIR = pathlib.Path(__file__).parents[1] / 'qgisresources'
    TARGET_ZIP = pathlib.Path(__file__).parents[1] / 'qgisresources.zip'

    compileQGISResourceFiles(QGIS_REPO, TARGET_DIR)

    # create the zip file that contains all PLUGIN_FILES
    with zipfile.ZipFile(TARGET_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as f:
        for entry in os.scandir(TARGET_DIR):
            if entry.is_file and entry.name.endswith('_rc.py'):
                path = pathlib.Path(entry.path)
                arcName = path.relative_to(TARGET_DIR).as_posix()
                f.write(path, arcname=arcName)