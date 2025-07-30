#!/usr/bin/env bash
#***************************************************************************
#***************************************************************************
#
#***************************************************************************
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU General Public License as published by  *
#*   the Free Software Foundation; either version 2 of the License, or     *
#*   (at your option) any later version.                                   *
#*                                                                         *
#***************************************************************************

set -e

pushd /usr/src
DEFAULT_PARAMS='-x -v'
cd /usr/src
export QT_QPA_PLATFORM=offscreen
export CI=True
export PYTHONPATH="${PYTHONPATH}"\
":$(pwd)"\
":/usr/share/qgis/python/plugins"\
":$(pwd)/tests"
python3 runfirst.py
pytest --no-cov-on-fail
# --cov-config=.coveragec "$@"
# coverage-badge -o coverage.svg
# echo "coverage-badge=coverage.svg" >> $GITHUB_OUTPUT
popd