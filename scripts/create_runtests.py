import os
import pathlib

from qps.utils import file_search

DIR_REPO = pathlib.Path(__file__).parents[1]
DIR_TESTS = DIR_REPO / 'tests'

RUN_PYTEST = True
PATH_RUNTESTS_SH = DIR_REPO / 'runtests.sh'

PREFACE_SH = \
    """#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}$(pwd)"
find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd):/usr/share/qgis/python/plugins"
"""

dirOut = 'test-reports/today'
linesSh = [PREFACE_SH,
           'mkdir -p {}'.format(os.path.dirname(dirOut)),
           'mkdir -p {}'.format(dirOut)]

bnDirTests = os.path.basename(DIR_TESTS)
for i, file in enumerate(file_search(DIR_TESTS, 'test_*.py', recursive=True)):
    file = pathlib.Path(file)
    bn = os.path.basename(file)
    bn = os.path.splitext(bn)[0]

    do_append = '' if i == 0 else '--append'
    pathTest = file.relative_to(DIR_TESTS.parent)
    if RUN_PYTEST:
        lineSh = 'pytest -x {}'.format(pathTest.as_posix())
    else:
        lineSh = 'python3 -m coverage run --rcfile=.coveragec {}  {}'.format(do_append, pathTest.as_posix())
    linesSh.append(lineSh)

if not RUN_PYTEST:
    linesSh.append('python3 -m coverage report')

with open(PATH_RUNTESTS_SH, 'w', encoding='utf-8', newline='\n') as f:
    f.write('\n'.join(linesSh))
