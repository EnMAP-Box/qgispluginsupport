import pathlib
import inspect
import re
import qgis.core
import qgis.gui


LINES = ['# auto-generated file.']
path_dst = pathlib.Path(__file__).parents[1] / 'qps' / 'qgisclasses.py'
qgis_modules = [qgis.core, qgis.gui]
pathlib.Path(__file__).parents[1] / 'qps' / 'qgisclasses.py'
rxQgsClass = re.compile(r'^(Qgs|Qgis).*')
for module in qgis_modules:
    class_names = []
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and rxQgsClass.search(name):
            class_names.append(name)
    if len(class_names) > 0:
        LINES.append('from {} import \\'.format(module.__name__))
        LINES.append('\t' + ', \\\n\t'.join(class_names) + '\n')


with open(path_dst, 'w', encoding='utf-8') as f:
    f.write('\n'.join(LINES))

from qps.qgisclasses import *
