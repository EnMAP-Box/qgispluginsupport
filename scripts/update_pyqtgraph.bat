@echo off
setlocal
set "ROOT=%~dp0.."
set SUBMODULE=qps/pyqtgraph
:: echo "Update $SUBMODULE"
cd /d %ROOT%\%SUBMODULE%
git checkout qps_modifications
git fetch
git pull
cd /d %ROOT%
git add %SUBMODULE%
echo 'Submodule status:'
git submodule status %SUBMODULE%
