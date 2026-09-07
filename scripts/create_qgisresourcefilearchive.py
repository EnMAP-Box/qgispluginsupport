import argparse
import os
from pathlib import Path
import zipfile

REPO: Path = Path(__file__).parents[1]


def findQGISRepo() -> Path:
    if 'QGIS_REPO' in os.environ.keys():
        return Path(os.environ['QGIS_REPO'])

    QGISREPO = REPO.parent / 'QGIS'

    if QGISREPO.is_dir():
        return QGISREPO

    return None


def create_qgis_resource_file_archive(qgis_repo=None):
    from qps.resources import compileQGISResourceFiles

    if qgis_repo is None:
        qgis_repo = findQGISRepo()
    else:
        qgis_repo = Path(qgis_repo)

    if not (isinstance(qgis_repo, Path)):
        raise AssertionError
    if not (qgis_repo.is_dir()):
        raise AssertionError
    if not (Path(qgis_repo / '.git').is_dir()):
        raise AssertionError

    TARGET_DIR = REPO / 'qgisresources'
    TARGET_ZIP = REPO / 'qgisresources.zip'

    os.makedirs(TARGET_DIR, exist_ok=True)
    compileQGISResourceFiles(qgis_repo, TARGET_DIR)

    # create the zip file that contains all PLUGIN_FILES
    with zipfile.ZipFile(TARGET_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as f:
        for entry in os.scandir(TARGET_DIR):
            if entry.is_file and entry.name.endswith('_rc.py'):
                path = Path(entry.path)
                arcName = path.relative_to(TARGET_DIR).as_posix()
                f.write(path, arcname=arcName)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create QGIS Resource file archive',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-q', '--qgisrepo',
                        required=False,
                        default=None,
                        help='Path to local QGIS repository',
                        action='store_true')
    args = parser.parse_args()
    create_qgis_resource_file_archive(qgis_repo=args.qgisrepo)
