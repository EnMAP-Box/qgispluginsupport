from pathlib import Path
from typing import List

from qgis.testing import start_app
from qps.resources import compileResourceFiles


def create_resource_files() -> List[Path]:
    """
    Creates the resource file(s) for QPS.
    :return: List of created resource files
    """
    QPS_DIR = Path(__file__).resolve().parents[1] / 'qps'
    if not (QPS_DIR.is_dir()):
        raise AssertionError
    return compileResourceFiles(QPS_DIR)


if __name__ == '__main__':
    app = start_app()
    create_resource_files()
    app.quit()
    exit(0)
