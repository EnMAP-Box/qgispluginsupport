import argparse
import io
import os
import pathlib
import shutil
import zipfile

import requests

URL_QGIS_RESOURCES = r'https://box.hu-berlin.de/f/6949ab1099044018a5e4/?dl=1'

DIR_REPO = pathlib.Path(__file__).parents[1]


def install_zipfile(url: str, localPath: pathlib.Path, zip_root: str = None):
    assert isinstance(localPath, pathlib.Path)
    localPath = localPath.resolve()

    print('Download {} \nto {}'.format(url, localPath))

    response = requests.get(url, stream=True)

    z = zipfile.ZipFile(io.BytesIO(response.content))
    os.makedirs(localPath, exist_ok=True)
    for src in z.namelist():
        srcPath = pathlib.Path(src)
        if isinstance(zip_root, str):
            if zip_root not in srcPath.parts:
                continue
            i = srcPath.parts.index(zip_root)
            dst = localPath / pathlib.Path(*srcPath.parts[i + 1:])
        else:
            dst = localPath / pathlib.Path(*srcPath.parts)
        info = z.getinfo(src)
        if info.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            os.makedirs(dst, exist_ok=True)
        else:
            if dst.exists():
                os.remove(dst)
            with open(dst, "wb") as f:
                f.write(z.read(src))

    # z.extractall(path=localPath, members=to_extract)
    del response


def install_qgisresources():
    localpath = DIR_REPO / 'qgisresources'
    install_zipfile(URL_QGIS_RESOURCES, localpath)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Install testdata')

    parser.add_argument('-q', '--qgisresources',
                        required=False,
                        default='-q',
                        help='Download and install QGIS resource files compiled as *_rc.py modules',
                        action='store_true')

    args = parser.parse_args()

    if args.qgisresources:
        install_qgisresources()
