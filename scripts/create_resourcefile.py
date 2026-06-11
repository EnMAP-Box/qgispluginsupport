import pathlib

from qgis.testing import start_app
from qps.resources import compileResourceFiles


def create_resource_files():
    QPS_DIR = pathlib.Path(__file__).resolve().parents[1] / 'qps'
    if not (QPS_DIR.is_dir()):
        raise AssertionError
    compileResourceFiles(QPS_DIR)


if __name__ == '__main__':
    app = start_app()
    create_resource_files()
