#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}"\
":$(pwd)"\
":/usr/share/qgis/python/plugins"

rm -Rf test-outputs
rm -Rf test-reports
pytest --no-cov-on-fail --cov-config=.coveragec "$@"
coverage-badge -o coverage.svg -f -v