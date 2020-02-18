import os, sys, pathlib
from qps.utils import file_search
DIR_REPO = pathlib.Path(__file__).parents[1]
DIR_TESTS = DIR_REPO / 'tests'


PATH_RUNTESTS_BAT = DIR_REPO / 'runtests.bat'
PATH_RUNTESTS_SH = DIR_REPO / 'runtests.sh'

jUnitXML = r'nose2-junit.xml'

PREFACE_BAT = \
"""
:: use this script to run unit tests locally
::
:: use this script to run unit tests locally
::
@echo off
set CI=True

WHERE python3 >nul 2>&1 && (
    echo Found "python3" command
    set PYTHON=python3
) || (
    echo Did not found "python3" command. use "python" instead
    set PYTHON=python
)

start %PYTHON% runfirst.py
"""

PREFACE_SH = \
"""#!/bin/bash
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI

find . -name "*.pyc" -exec rm -f {} \;

python3 runfirst.py
"""

dirOut = 'test-reports/today'
linesBat = [PREFACE_BAT]
linesSh = [PREFACE_SH]
linesSh.append('mkdir {}'.format(os.path.dirname(dirOut)))
linesBat.append('mkdir {}'.format(os.path.dirname(dirOut)))
linesBat.append('mkdir {}'.format(dirOut.replace('/', '\\')))
linesSh.append('mkdir {}'.format(dirOut))

bnDirTests = os.path.basename(DIR_TESTS)
for i, file in enumerate(file_search(DIR_TESTS, 'test_*.py')):
    file = pathlib.Path(file)
    bn = os.path.basename(file)
    bn = os.path.splitext(bn)[0]
    #lineBat = 'call %PYTHON% -m nose2 -s {3} {0} & move {1} {2}/{0}.xml'.format(bn, jUnitXML, dirOut, bnDirTests)
    do_append = '' if i == 0 else '--append'
    pathTest = str(pathlib.Path(*file.parts[-2:]).as_posix())
    #lineBat = '%PYTHON% -m coverage run --source qps --omit qps/externals/*  {}  {}'.format(do_append, pathTest)
    lineBat = 'coverage run --rcfile=.coveragec {}  {}'.format(do_append, pathTest)
    #lineSh = 'python3 -m coverage run --source qps  --omit qps/externals/* {} {}'.format(do_append, pathTest)
    lineSh = 'coverage run --rcfile=.coveragec {}  {}'.format(do_append, pathTest)

    linesBat.append(lineBat)
    linesSh.append(lineSh)

linesBat.append('coverage report')
linesSh.append('coverage report')

with open(PATH_RUNTESTS_BAT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(linesBat))

with open(PATH_RUNTESTS_SH, 'w', encoding='utf-8', newline='\n') as f:
    f.write('\n'.join(linesSh))


