
::mkdir test-reports
set CI=True
@echo off
call :sub >test-report.txt
exit /b

:sub

:: python -m nose2 --verbose discover tests "test_*.py"  > test-reports/test_all.txt
python -m nose2 -s tests test_spectrallibraries > test-reports/test_spectrallibraries.txt
python -m nose2 -s tests test_classificationscheme > test-reports/test_classificationscheme.txt
python -m nose2 -s tests test_crosshair > test-reports/test_crosshair.txt
python -m nose2 -s tests test_cursorlocationsvalues > test-reports/test_cursorlocationsvalues.txt
python -m nose2 -s tests test_init > test-reports/test_init.txt
python -m nose2 -s tests test_layerproperties  > test-reports/test_layerproperties.txt
python -m nose2 -s tests test_maptools > test-reports/test_maptools.txt
python -m nose2 -s tests test_models > test-reports/test_models.txt
python -m nose2 -s tests test_plotstyling > test-reports/test_plotstyling.txt
python -m nose2 -s tests test_qgisinstance > test-reports/test_qgisinstance.txt
python -m nose2 -s tests test_qgisissues > test-reports/test_qgisissues.txt
python -m nose2 -s tests test_testing > test-reports/test_testing.txt
python -m nose2 -s tests test_utils > test-reports/test_utils.txt
