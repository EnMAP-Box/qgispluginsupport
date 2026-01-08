#!/usr/bin/env bash
docker run --rm \
  -v "$(pwd):/usr/src" \
  -w /usr/src \
  -e QT_QPA_PLATFORM=offscreen \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  /bin/bash .docker/run_docker_tests.sh