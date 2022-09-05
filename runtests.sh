#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}$(pwd)"
find . -name "*.pyc" -exec rm -f {} \;
export PYTHONPATH="${PYTHONPATH}:$(pwd):/usr/share/qgis/python/plugins"

mkdir -p test-reports
mkdir -p test-reports/today
pytest -x tests/layers/test_gdal_metadata.py
pytest -x tests/layers/test_layerconfigwidgets.py
pytest -x tests/layers/test_layerproperties.py
pytest -x tests/layers/test_qgsrasterlayerspectralproperties.py
pytest -x tests/layers/test_subdatasets.py
pytest -x tests/layers/test_vectorlayertools.py
pytest -x tests/others/test_classificationscheme.py
pytest -x tests/others/test_crosshair.py
pytest -x tests/others/test_cursorlocationsvalues.py
pytest -x tests/others/test_maptools.py
pytest -x tests/others/test_models.py
pytest -x tests/others/test_processing.py
pytest -x tests/others/test_qgsfunctions.py
pytest -x tests/others/test_searchfiledialog.py
pytest -x tests/others/test_simplewidget.py
pytest -x tests/others/test_unitmodel.py
pytest -x tests/others/test_utils.py
pytest -x tests/plotting/test_plotstyling.py
pytest -x tests/speclib/test_speclib_core.py
pytest -x tests/speclib/test_speclib_gui.py
pytest -x tests/speclib/test_speclib_gui_processing.py
pytest -x tests/speclib/test_speclib_plotting.py
pytest -x tests/speclib/test_speclib_profilesources.py
pytest -x tests/speclib/test_speclib_profile_editor.py
pytest -x tests/speclib/test_speclib_rasterdataprovider.py
pytest -x tests/speclib/test_speclib_spectralsetting.py
pytest -x tests/speclib_io/test_speclib_io.py
pytest -x tests/speclib_io/test_speclib_io_asd.py
pytest -x tests/speclib_io/test_speclib_io_ecosys.py
pytest -x tests/speclib_io/test_speclib_io_envi.py
pytest -x tests/speclib_io/test_speclib_io_geojson.py
pytest -x tests/speclib_io/test_speclib_io_geopackage.py
pytest -x tests/speclib_io/test_speclib_io_rastersources.py
pytest -x tests/speclib_io/test_speclib_io_sed.py
pytest -x tests/test_deploy.py
pytest -x tests/test_example.py
pytest -x tests/test_init.py
pytest -x tests/test_qps.py
pytest -x tests/test_resources.py
pytest -x tests/test_testing.py