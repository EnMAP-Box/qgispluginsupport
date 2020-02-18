#!/bin/bash
QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM
CI=True
export CI

find . -name "*.pyc" -exec rm -f {} \;

python3 runfirst.py

mkdir test-reports
mkdir test-reports/today
coverage run --rcfile=.coveragec   tests/test_classificationscheme.py
coverage run --rcfile=.coveragec --append  tests/test_crosshair.py
coverage run --rcfile=.coveragec --append  tests/test_cursorlocationsvalues.py
coverage run --rcfile=.coveragec --append  tests/test_example.py
coverage run --rcfile=.coveragec --append  tests/test_init.py
coverage run --rcfile=.coveragec --append  tests/test_layerproperties.py
coverage run --rcfile=.coveragec --append  tests/test_maptools.py
coverage run --rcfile=.coveragec --append  tests/test_models.py
coverage run --rcfile=.coveragec --append  tests/test_plotstyling.py
coverage run --rcfile=.coveragec --append  tests/test_qgisissues.py
coverage run --rcfile=.coveragec --append  tests/test_resources.py
coverage run --rcfile=.coveragec --append  tests/test_speclib_core.py
coverage run --rcfile=.coveragec --append  tests/test_speclib_gui.py
coverage run --rcfile=.coveragec --append  tests/test_speclib_io.py
coverage run --rcfile=.coveragec --append  tests/test_testing.py
coverage run --rcfile=.coveragec --append  tests/test_utils.py
coverage report