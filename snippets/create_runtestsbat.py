import os, sys, pathlib
from qps.utils import file_search
DIR_REPO = pathlib.Path(__file__).parents[1]
DIR_TESTS = DIR_REPO / 'tests'


PATH_RUNTESTS_BAT = DIR_REPO / 'runtests.bat'
PATH_RUNTESTS_SH = DIR_REPO / 'runtests.sh'

jUnitXML = r'nose2-junit.xml'

PREFACE = \
"""
:: use this script to run unit tests locally
::
set CI=True
python runfirst.py
"""

dirOut = 'test-reports/today'
linesBat = [PREFACE]
linesSh = [PREFACE]
linesBat.append('mkdir {}'.format(dirOut.replace('/', '\\')))
linesSh.append('mkdir {}'.format(dirOut))


for file in file_search(DIR_TESTS, 'test_*.py'):

    bn = os.path.basename(file)
    bn = os.path.splitext(bn)[0]
    lineBat = 'python -m nose2 -s tests {0} & move {1} {2}/{0}.xml'.format(bn, jUnitXML, dirOut)
    lineSh = 'python -m nose2 -s tests {0} ; mv {1} {2}/{0}.xml'.format(bn, jUnitXML, dirOut)
    linesBat.append(lineBat)
    linesSh.append(lineSh)

with open(PATH_RUNTESTS_BAT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(linesBat))

with open(PATH_RUNTESTS_SH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(linesSh))

