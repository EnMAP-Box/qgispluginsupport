
::mkdir test-reports
set CI=True
@echo off
call :sub >test-report.txt
exit /b

:sub

:: python -m nose2 --verbose discover enmapboxtesting "test_*.py"
python -m nose2 -s tests test_classificationscheme
python -m nose2 -s tests test_crosshair
python -m nose2 -s tests test_cursorlocationsvalues
python -m nose2 -s tests test_init
python -m nose2 -s tests test_layerproperties
python -m nose2 -s tests test_maptools
python -m nose2 -s tests test_models
python -m nose2 -s tests test_plotstyling
python -m nose2 -s tests test_qgisinstance
python -m nose2 -s tests test_qgisissues
python -m nose2 -s tests test_spectrallibraries
python -m nose2 -s tests test_testing
python -m nose2 -s tests test_utils
