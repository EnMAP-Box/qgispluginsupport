import pathlib

if __name__ == '__main__':
    from qps.resources import compileResourceFiles

    QPS_DIR = pathlib.Path(__file__).resolve().parents[1] / 'qps'
    assert QPS_DIR.is_dir()
    compileResourceFiles(QPS_DIR)
