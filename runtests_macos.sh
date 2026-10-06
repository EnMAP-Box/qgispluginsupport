#!/bin/bash
QGIS_APP=${QGIS_APP:-/Applications/QGIS-final-4_2_2.app}
export QT_QPA_PLATFORM=offscreen
export CI=True
export QGIS_CONTINUOUS_INTEGRATION_RUN=true
export PYQTGRAPH_QT_LIB=PyQt6
export PYTHON_EXECUTABLE=${QGIS_APP}/Contents/MacOS/python
export PYTHONPATH="${PYTHONPATH}"\
":${QGIS_APP}/Contents/Resources/qgis/python"\
":${QGIS_APP}/Contents/Resources/qgis/python/plugins"
$(dirname "$0")/runtests.sh "$@"
