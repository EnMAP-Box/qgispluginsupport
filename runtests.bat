
:: use this script to run unit tests locally
::
set CI=True
python runfirst.py

mkdir test-reports
mkdir test-reports\today
python3 -m nose2 -s tests test_classificationscheme & move nose2-junit.xml test-reports/today/test_classificationscheme.xml
python3 -m nose2 -s tests test_crosshair & move nose2-junit.xml test-reports/today/test_crosshair.xml
python3 -m nose2 -s tests test_cursorlocationsvalues & move nose2-junit.xml test-reports/today/test_cursorlocationsvalues.xml
python3 -m nose2 -s tests test_init & move nose2-junit.xml test-reports/today/test_init.xml
python3 -m nose2 -s tests test_layerproperties & move nose2-junit.xml test-reports/today/test_layerproperties.xml
python3 -m nose2 -s tests test_maptools & move nose2-junit.xml test-reports/today/test_maptools.xml
python3 -m nose2 -s tests test_models & move nose2-junit.xml test-reports/today/test_models.xml
python3 -m nose2 -s tests test_plotstyling & move nose2-junit.xml test-reports/today/test_plotstyling.xml
python3 -m nose2 -s tests test_qgisinstance & move nose2-junit.xml test-reports/today/test_qgisinstance.xml
python3 -m nose2 -s tests test_qgisissues & move nose2-junit.xml test-reports/today/test_qgisissues.xml
python3 -m nose2 -s tests test_spectrallibraries & move nose2-junit.xml test-reports/today/test_spectrallibraries.xml
python3 -m nose2 -s tests test_testing & move nose2-junit.xml test-reports/today/test_testing.xml
python3 -m nose2 -s tests test_utils & move nose2-junit.xml test-reports/today/test_utils.xml