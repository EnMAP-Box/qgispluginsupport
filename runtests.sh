
:: use this script to run unit tests locally
::
set CI=True
python runfirst.py

mkdir test-reports/today
python -m nose2 -s tests test_classificationscheme ; mv nose2-junit.xml test-reports/today/test_classificationscheme.xml
python -m nose2 -s tests test_crosshair ; mv nose2-junit.xml test-reports/today/test_crosshair.xml
python -m nose2 -s tests test_cursorlocationsvalues ; mv nose2-junit.xml test-reports/today/test_cursorlocationsvalues.xml
python -m nose2 -s tests test_init ; mv nose2-junit.xml test-reports/today/test_init.xml
python -m nose2 -s tests test_layerproperties ; mv nose2-junit.xml test-reports/today/test_layerproperties.xml
python -m nose2 -s tests test_maptools ; mv nose2-junit.xml test-reports/today/test_maptools.xml
python -m nose2 -s tests test_models ; mv nose2-junit.xml test-reports/today/test_models.xml
python -m nose2 -s tests test_plotstyling ; mv nose2-junit.xml test-reports/today/test_plotstyling.xml
python -m nose2 -s tests test_qgisinstance ; mv nose2-junit.xml test-reports/today/test_qgisinstance.xml
python -m nose2 -s tests test_qgisissues ; mv nose2-junit.xml test-reports/today/test_qgisissues.xml
python -m nose2 -s tests test_spectrallibraries ; mv nose2-junit.xml test-reports/today/test_spectrallibraries.xml
python -m nose2 -s tests test_testing ; mv nose2-junit.xml test-reports/today/test_testing.xml
python -m nose2 -s tests test_utils ; mv nose2-junit.xml test-reports/today/test_utils.xml