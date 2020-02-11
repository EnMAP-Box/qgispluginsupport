import pathlib, os, zipfile



QPS_REPO = pathlib.Path(__file__).parents[1]
assert 'QGIS_REPO' in os.environ.keys()
QGIS_REPO = pathlib.Path(os.environ.get('QGIS_REPO'))
assert QGIS_REPO.is_dir()

QGIS_RESOURCES = QPS_REPO / 'qgisresources'
QGIS_RESOURCES_ZIP = QPS_REPO / 'qgisresources.zip'

os.makedirs(QGIS_RESOURCES, exist_ok=True)
from qps.make.make import compileQGISResourceFiles
compileQGISResourceFiles(QGIS_REPO, target=QGIS_RESOURCES)

# create the zip file that contains all PLUGIN_FILES
with zipfile.ZipFile(QGIS_RESOURCES_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as f:
    for entry in os.scandir(QGIS_RESOURCES):
        if entry.is_file and entry.name.endswith('_rc.py'):
            path = pathlib.Path(entry.path)
            arcName = path.relative_to(QGIS_RESOURCES).as_posix()
            f.write(path, arcname=arcName)


