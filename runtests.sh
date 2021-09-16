#!/bin/bash
export QT_QPA_PLATFORM=offscree
export CI=True

find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd):/usr/share/qgis/python/plugins"
python3 runfirst.py

mkdir test-reports
mkdir test-reports/today
python3 -m coverage run --rcfile=.coveragec   speclib/test_speclib_core.py
python3 -m coverage run --rcfile=.coveragec --append  speclib/test_speclib_gui.py
python3 -m coverage run --rcfile=.coveragec --append  speclib/test_speclib_io.py
python3 -m coverage run --rcfile=.coveragec --append  speclib/test_speclib_plotting.py
python3 -m coverage run --rcfile=.coveragec --append  speclib/test_speclib_processing.py
python3 -m coverage run --rcfile=.coveragec --append  speclib/test_speclib_profilesources.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_classificationscheme.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_crosshair.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_cursorlocationsvalues.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_example.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_init.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_layerconfigwidgets.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_layerproperties.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_maptools.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_models.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_plotstyling.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_qgisissues.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_qgsfunctions.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_qps.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_resources.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_searchfiledialog.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_simplewidget.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_subdatasets.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_testing.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_utils.py
python3 -m coverage run --rcfile=.coveragec --append  tests/test_vectorlayertools.py
python3 -m coverage report