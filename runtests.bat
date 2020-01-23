
:: use this script to run unit tests locally
::
set CI=True
python3 runfirst.py

mkdir test-reports
mkdir test-reports\today
python -m nose2 -s tests test_classificationscheme & move nose2-junit.xml test-reports/today/test_classificationscheme.xml
python -m nose2 -s tests test_crosshair & move nose2-junit.xml test-reports/today/test_crosshair.xml
python -m nose2 -s tests test_cursorlocationsvalues & move nose2-junit.xml test-reports/today/test_cursorlocationsvalues.xml
python -m nose2 -s tests test_init & move nose2-junit.xml test-reports/today/test_init.xml
python -m nose2 -s tests test_layerproperties & move nose2-junit.xml test-reports/today/test_layerproperties.xml
python -m nose2 -s tests test_maptools & move nose2-junit.xml test-reports/today/test_maptools.xml
python -m nose2 -s tests test_models & move nose2-junit.xml test-reports/today/test_models.xml
python -m nose2 -s tests test_plotstyling & move nose2-junit.xml test-reports/today/test_plotstyling.xml
python -m nose2 -s tests test_qgisinstance & move nose2-junit.xml test-reports/today/test_qgisinstance.xml
python -m nose2 -s tests test_qgisissues & move nose2-junit.xml test-reports/today/test_qgisissues.xml
python -m nose2 -s tests test_spectrallibraries & move nose2-junit.xml test-reports/today/test_spectrallibraries.xml
python -m nose2 -s tests test_testing & move nose2-junit.xml test-reports/today/test_testing.xml
python -m nose2 -s tests test_utils & move nose2-junit.xml test-reports/today/test_utils.xml