@echo off
set QT_QPA_PLATFORM=offscreen
set CI=True
set PYQTGRAPH_QT_LIB=PyQt6
set QGIS_CONTINUOUS_INTEGRATION_RUN=true
rmdir /s /q test-outputs
rmdir /s /q test-reports
pytest --no-cov-on-fail --cov-config=.coveragec %*
:: coverage-badge -o coverage.svg  -f -v