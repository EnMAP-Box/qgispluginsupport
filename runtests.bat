
:: use this script to run unit tests locally
::

@echo off
set CI=True
set PYTHONPATH=%~dp0;%PYTHONPATH%
set PYTHONPATH

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
pytest -x tests/speclib/test_speclib_core.py
pytest -x tests/speclib/test_speclib_gui.py
pytest -x tests/speclib/test_speclib_gui_processing.py
pytest -x tests/speclib/test_speclib_io.py
pytest -x tests/speclib/test_speclib_io_asd.py
pytest -x tests/speclib/test_speclib_io_ecosys.py
pytest -x tests/speclib/test_speclib_io_envi.py
pytest -x tests/speclib/test_speclib_io_geopackage.py
pytest -x tests/speclib/test_speclib_io_rastersources.py
pytest -x tests/speclib/test_speclib_plotting.py
pytest -x tests/speclib/test_speclib_profilesources.py
pytest -x tests/speclib/test_speclib_rasterdataprovider.py
pytest -x tests/test_classificationscheme.py
pytest -x tests/test_crosshair.py
pytest -x tests/test_cursorlocationsvalues.py
pytest -x tests/test_example.py
pytest -x tests/test_init.py
pytest -x tests/test_layerconfigwidgets.py
pytest -x tests/test_layerproperties.py
pytest -x tests/test_maptools.py
pytest -x tests/test_models.py
pytest -x tests/test_plotstyling.py
pytest -x tests/test_processing.py
pytest -x tests/test_qgsfunctions.py
pytest -x tests/test_qps.py
pytest -x tests/test_resources.py
pytest -x tests/test_searchfiledialog.py
pytest -x tests/test_simplewidget.py
pytest -x tests/test_subdatasets.py
pytest -x tests/test_testing.py
pytest -x tests/test_utils.py
pytest -x tests/test_vectorlayertools.py