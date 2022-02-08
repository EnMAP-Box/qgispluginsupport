import site
import pathlib
import importlib

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices

import test_speclib_plotting
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import QgsMapLayerModel, QgsApplication, QgsRasterDataProvider, Qgis

from qgis.gui import QgsMapToolIdentify

import qps
from qgis.gui import QgsMapLayerComboBox, QgsMapCanvas
from qgis.core import QgsProject, QgsRasterLayer, QgsContrastEnhancement
from qps.speclib.core.spectralprofile import groupBySpectralProperties

if not '__file__' in locals():
    __file__ = r'D:\Repositories\qgispluginsupport\scripts\snippet.py'
REPO = pathlib.Path(__file__).parents[1]
print(REPO)
site.addsitedir(REPO)

TESTS = REPO / 'tests' / 'speclib'
site.addsitedir(TESTS)

test_speclib_plotting.TestSpeclibPlotting.test_SpectralLibraryPlotWidget()