import pathlib, os, zipfile, sys

if __name__ == '__main__':


    from qps.make.make import compileResourceFiles

    QPS_DIR = pathlib.Path(__file__).parents[1] / 'qps'
    assert QPS_DIR.is_dir()
    compileResourceFiles(QPS_DIR)
