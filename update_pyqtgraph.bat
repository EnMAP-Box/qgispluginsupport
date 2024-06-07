git remote add pyqtgraph_qps git@github.com:EnMAP-Box/pyqtgraph.git
git fetch pyqtgraph_qps
git merge -s ours --allow-unrelated-histories --no-commit pyqtgraph/qps_modifications
:: mkdir qps/pyqtgraph
git read-tree -u --prefix=qps/pyqtgraph/ pyqtgraph_qps/qps_modifications
git commit -m "Added pyqtgraph_qps to project repository"