
# use this script to run unit tests locally
#
python3 runfirst.py

mkdir test-reports
mkdir test-reports/today
python3 -m nose2 -s tests test_classificationscheme ; mv nose2-junit.xml test-reports/today/test_classificationscheme.xml
python3 -m nose2 -s tests test_crosshair ; mv nose2-junit.xml test-reports/today/test_crosshair.xml
python3 -m nose2 -s tests test_cursorlocationsvalues ; mv nose2-junit.xml test-reports/today/test_cursorlocationsvalues.xml
python3 -m nose2 -s tests test_init ; mv nose2-junit.xml test-reports/today/test_init.xml
python3 -m nose2 -s tests test_layerproperties ; mv nose2-junit.xml test-reports/today/test_layerproperties.xml
python3 -m nose2 -s tests test_maptools ; mv nose2-junit.xml test-reports/today/test_maptools.xml
python3 -m nose2 -s tests test_models ; mv nose2-junit.xml test-reports/today/test_models.xml
python3 -m nose2 -s tests test_plotstyling ; mv nose2-junit.xml test-reports/today/test_plotstyling.xml
python3 -m nose2 -s tests test_qgisinstance ; mv nose2-junit.xml test-reports/today/test_qgisinstance.xml
python3 -m nose2 -s tests test_qgisissues ; mv nose2-junit.xml test-reports/today/test_qgisissues.xml
python3 -m nose2 -s tests test_spectrallibraries ; mv nose2-junit.xml test-reports/today/test_spectrallibraries.xml
python3 -m nose2 -s tests test_testing ; mv nose2-junit.xml test-reports/today/test_testing.xml
python3 -m nose2 -s tests test_utils ; mv nose2-junit.xml test-reports/today/test_utils.xml