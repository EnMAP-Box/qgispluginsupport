
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
call %PYTHON% -m nose2 -s tests test_classificationscheme & move nose2-junit.xml test-reports/today/test_classificationscheme.xml
call %PYTHON% -m nose2 -s tests test_crosshair & move nose2-junit.xml test-reports/today/test_crosshair.xml
call %PYTHON% -m nose2 -s tests test_cursorlocationsvalues & move nose2-junit.xml test-reports/today/test_cursorlocationsvalues.xml
call %PYTHON% -m nose2 -s tests test_example & move nose2-junit.xml test-reports/today/test_example.xml
call %PYTHON% -m nose2 -s tests test_init & move nose2-junit.xml test-reports/today/test_init.xml
call %PYTHON% -m nose2 -s tests test_layerproperties & move nose2-junit.xml test-reports/today/test_layerproperties.xml
call %PYTHON% -m nose2 -s tests test_maptools & move nose2-junit.xml test-reports/today/test_maptools.xml
call %PYTHON% -m nose2 -s tests test_models & move nose2-junit.xml test-reports/today/test_models.xml
call %PYTHON% -m nose2 -s tests test_plotstyling & move nose2-junit.xml test-reports/today/test_plotstyling.xml
call %PYTHON% -m nose2 -s tests test_qgisissues & move nose2-junit.xml test-reports/today/test_qgisissues.xml
call %PYTHON% -m nose2 -s tests test_spectrallibraries_core & move nose2-junit.xml test-reports/today/test_spectrallibraries_core.xml
call %PYTHON% -m nose2 -s tests test_spectrallibraries_io & move nose2-junit.xml test-reports/today/test_spectrallibraries_io.xml
call %PYTHON% -m nose2 -s tests test_spectrallibraries_plotting & move nose2-junit.xml test-reports/today/test_spectrallibraries_plotting.xml
call %PYTHON% -m nose2 -s tests test_testing & move nose2-junit.xml test-reports/today/test_testing.xml
call %PYTHON% -m nose2 -s tests test_utils & move nose2-junit.xml test-reports/today/test_utils.xml