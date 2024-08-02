#!/bin/bash

SUBMODULE=qps/pyqtgraph
echo "Update $SUBMODULE"
cd $SUBMODULE
git checkout qps_modifications
git fetch
git pull
cd ../..
git add $SUBMODULE
echo 'Submodule status:'
git submodule status $SUBMODULE
