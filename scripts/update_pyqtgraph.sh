#!/bin/bash

git fetch pyqtgraph
git rm -r qps/pyqtgraph
git read-tree --prefix=qps/pyqtgraph -u pyqtgraph/qps_modifications
git commit -m "Updated pyqtgraph"