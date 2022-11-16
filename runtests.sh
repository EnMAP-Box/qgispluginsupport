#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
# export PYTHONPATH="${PYTHONPATH}$(pwd)"
find . -name "*.pyc" -exec rm -f {} \;

mkdir -p test-reports
mkdir -p test-reports/today
python3 -m unittest -f tests/layers/test_gdal_metadata.py
python3 -m unittest -f tests/layers/test_layerconfigwidgets.py
python3 -m unittest -f tests/layers/test_layerproperties.py
python3 -m unittest -f tests/layers/test_qgsrasterlayerspectralproperties.py
python3 -m unittest -f tests/layers/test_subdatasets.py
python3 -m unittest -f tests/layers/test_vectorlayertools.py
python3 -m unittest -f tests/others/test_classificationscheme.py
python3 -m unittest -f tests/others/test_crosshair.py
python3 -m unittest -f tests/others/test_cursorlocationsvalues.py
python3 -m unittest -f tests/others/test_maptools.py
python3 -m unittest -f tests/others/test_models.py
python3 -m unittest -f tests/others/test_processing.py
python3 -m unittest -f tests/others/test_qgsfunctions.py
python3 -m unittest -f tests/others/test_searchfiledialog.py
python3 -m unittest -f tests/others/test_simplewidget.py
python3 -m unittest -f tests/others/test_unitmodel.py
python3 -m unittest -f tests/others/test_utils.py
python3 -m unittest -f tests/plotting/test_plotstyling.py
python3 -m unittest -f tests/speclib/test_speclib_core.py
python3 -m unittest -f tests/speclib/test_speclib_gui.py
python3 -m unittest -f tests/speclib/test_speclib_gui_processing.py
python3 -m unittest -f tests/speclib/test_speclib_plotting.py
python3 -m unittest -f tests/speclib/test_speclib_profile_editor.py
python3 -m unittest -f tests/speclib/test_speclib_profilesources.py
python3 -m unittest -f tests/speclib/test_speclib_rasterdataprovider.py
python3 -m unittest -f tests/speclib/test_speclib_spectralsetting.py
python3 -m unittest -f tests/speclib_io/test_speclib_io.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_asd.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_ecosys.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_envi.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_geojson.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_geopackage.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_rastersources.py
python3 -m unittest -f tests/speclib_io/test_speclib_io_sed.py
python3 -m unittest -f tests/test_deploy.py
python3 -m unittest -f tests/test_example.py
python3 -m unittest -f tests/test_init.py
python3 -m unittest -f tests/test_qps.py
python3 -m unittest -f tests/test_resources.py
python3 -m unittest -f tests/test_testing.py
python3 -m unittest -f tests/test_testobjects.py
python3 -m coverage report