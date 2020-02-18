
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

mkdir test-reports
mkdir test-reports\today
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