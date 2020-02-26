import pathlib, os, zipfile, sys

def create_qgis_resource_file(qgis_repo=None):


    from qps.utils import findUpwardPath
    from qps.resources import compileQGISResourceFiles
    REPO = findUpwardPath(pathlib.Path(__file__).resolve(), '.git')

    assert isinstance(REPO, pathlib.Path) and REPO.is_dir()
    REPO = REPO.parent

    TARGET_DIR = pathlib.Path(__file__).parents[1] / 'qgisresources'
    TARGET_ZIP = pathlib.Path(__file__).parents[1] / 'qgisresources.zip'

    compileQGISResourceFiles(qgis_repo, TARGET_DIR)

    # create the zip file that contains all PLUGIN_FILES
    with zipfile.ZipFile(TARGET_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as f:
        for entry in os.scandir(TARGET_DIR):
            if entry.is_file and entry.name.endswith('_rc.py'):
                path = pathlib.Path(entry.path)
                arcName = path.relative_to(TARGET_DIR).as_posix()
                f.write(path, arcname=arcName)

if __name__ == '__main__':

    import getopt
    try:
        print(sys.argv)
        opts, qgis_repo = getopt.getopt(sys.argv[1:], "")
    except getopt.GetoptError as err:
        print(err)

    create_qgis_resource_file()

