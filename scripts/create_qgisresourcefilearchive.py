import argparse
import os
import pathlib
import sys
import zipfile
import os

REPO:pathlib.Path = pathlib.Path(__file__).parents[1]
def findQGISRepo() -> pathlib.Path:

    if 'QGIS_REPO' in os.environ.keys():
        return pathlib.Path(os.environ['QGIS_REPO'])

    QGISREPO = REPO.parent / 'QGIS'

    if QGISREPO.is_dir():
        return QGISREPO

    return None


def create_qgis_resource_file_archive(qgis_repo=None):

    from qps.resources import compileQGISResourceFiles

    if qgis_repo is None:
        qgis_repo = findQGISRepo()
    else:
        qgis_repo = pathlib.Path(qgis_repo)

    assert isinstance(qgis_repo, pathlib.Path)
    assert qgis_repo.is_dir()
    assert pathlib.Path(qgis_repo/'.git').is_dir()

    TARGET_DIR = REPO / 'qgisresources'
    TARGET_ZIP = REPO / 'qgisresources.zip'

    os.makedirs(TARGET_DIR, exist_ok=True)
    compileQGISResourceFiles(qgis_repo, TARGET_DIR)

    # create the zip file that contains all PLUGIN_FILES
    with zipfile.ZipFile(TARGET_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as f:
        for entry in os.scandir(TARGET_DIR):
            if entry.is_file and entry.name.endswith('_rc.py'):
                path = pathlib.Path(entry.path)
                arcName = path.relative_to(TARGET_DIR).as_posix()
                f.write(path, arcname=arcName)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create QGIS Resource file archive', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-q', '--qgisrepo',
                        required=False,
                        default=None,
                        help='Path to local QGIS repository',
                        action='store_true')
    args = parser.parse_args()
    create_qgis_resource_file_archive(qgis_repo=args.qgisrepo)
