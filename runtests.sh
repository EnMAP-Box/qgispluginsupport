#!/bin/bash
export QT_QPA_PLATFORM=offscreen
export CI=True

find . -name "*.pyc" -exec rm -f {} \;
if [["$OSTYPE" == "msys"]]; then
  export PYTHONPATH="${PYTHONPATH}$(pwd)"
else
  export PYTHONPATH="${PYTHONPATH}$(pwd)"
fi

echo $PYTHONPATH
mkdir test-reports
mkdir test-reports/today
# pytest -x tests/layers/test_gdal_metadata.py
python tests/layers/test_gdal_metadata.py
