#!/bin/bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUBMODULE="qps/pyqtgraph"
echo "Update $SUBMODULE"
cd "$ROOT/$SUBMODULE"

git checkout qps_modifications
git fetch
git pull
cd "$ROOT"
git add $SUBMODULE
echo 'Submodule status:'
git submodule status "$SUBMODULE"
