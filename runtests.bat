
:: use this script to run unit tests locally
::

mkdir test-reports
set CI=True
python runfirst.py

python -m nose2 -s tests test_classificationscheme & move nose2-junit.xml test-reports/test_classificationscheme.xml
python -m nose2 -s tests test_crosshair & move nose2-junit.xml test-reports/test_crosshair.xml
python -m nose2 -s tests test_cursorlocationsvalues & move nose2-junit.xml test-reports/test_cursorlocationsvalues.xml
python -m nose2 -s tests test_init & move nose2-junit.xml test-reports/test_init.xml
python -m nose2 -s tests test_layerproperties & move nose2-junit.xml test-reports/test_layerproperties.xml
python -m nose2 -s tests test_maptools & move nose2-junit.xml test-reports/test_maptools.xml
python -m nose2 -s tests test_models & move nose2-junit.xml test-reports/test_models.xml
python -m nose2 -s tests test_plotstyling & move nose2-junit.xml test-reports/test_plotstyling.xml
python -m nose2 -s tests test_qgisinstance & move nose2-junit.xml test-reports/test_qgisinstance.xml
python -m nose2 -s tests test_qgisissues & move nose2-junit.xml test-reports/test_qgisissues.xml
python -m nose2 -s tests test_spectrallibraries & move nose2-junit.xml test-reports/test_spectrallibraries.xml
python -m nose2 -s tests test_testing & move nose2-junit.xml test-reports/test_testing.xml
python -m nose2 -s tests test_utils & move nose2-junit.xml test-reports/test_utils.xml