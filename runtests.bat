
::mkdir test-results
set CI=True
@echo off
call :sub >test-results.txt
exit /b

:sub

:: python -m nose2 --verbose discover tests "test_*.py"  > test-results/test_all.txt
python -m nose2 -s tests test_spectrallibraries > test-results/test_spectrallibraries.txt
python -m nose2 -s tests test_classificationscheme > test-results/test_classificationscheme.txt
python -m nose2 -s tests test_crosshair > test-results/test_crosshair.txt
python -m nose2 -s tests test_cursorlocationsvalues > test-results/test_cursorlocationsvalues.txt
python -m nose2 -s tests test_init > test-results/test_init.txt
python -m nose2 -s tests test_layerproperties  > test-results/test_layerproperties.txt
python -m nose2 -s tests test_maptools > test-results/test_maptools.txt
python -m nose2 -s tests test_models > test-results/test_models.txt
python -m nose2 -s tests test_plotstyling > test-results/test_plotstyling.txt
python -m nose2 -s tests test_qgisinstance > test-results/test_qgisinstance.txt
python -m nose2 -s tests test_qgisissues > test-results/test_qgisissues.txt
python -m nose2 -s tests test_testing > test-results/test_testing.txt
python -m nose2 -s tests test_utils > test-results/test_utils.txt
