#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
export QGIS_CONTINUOUS_INTEGRATION_RUN=true
export PYQTGRAPH_QT_LIB=PyQt6
export PYTHONPATH="${PYTHONPATH}"\
":$(pwd)"
# ":/usr/share/qgis/python/plugins"

# Use venv Python if available
if [ -f /venv/qps/bin/python ]; then
    export PATH=/venv/qps/bin:$PATH
fi

rm -Rf test-outputs
rm -Rf test-reports
python -m pytest --no-cov-on-fail "$@"
# coverage-badge -o coverage.svg -f -v