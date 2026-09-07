@echo off
set QT_QPA_PLATFORM=offscreen
set CI=True
set QGIS_CONTINUOUS_INTEGRATION_RUN=true
set PYQTGRAPH_QT_LIB=PyQt6
rmdir /s /q test-outputs
rmdir /s /q test-reports
:: set QGIS_PREFIX_PATH=D:\OSGeo4W\apps\qgis
pytest --no-cov-on-fail --cov-config=.coveragec %*
:: coverage-badge -o coverage.svg  -f -v
