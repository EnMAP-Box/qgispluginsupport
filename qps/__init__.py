# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    <qps>/__init__.py
    QPS (QGIS Plugin Support) package definition
    ---------------------
    Beginning            : 2019-01-11
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""

import os
import pathlib
import sys
import warnings
from typing import List

from qgis.PyQt.QtCore import PYQT_VERSION_STR
from qgis.core import Qgis, QgsApplication
from qgis.gui import QgisInterface, QgsMapLayerConfigWidgetFactory

os.environ.setdefault('PYQTGRAPH_QT_LIB', f'PyQt{PYQT_VERSION_STR[0]}')
MIN_QGIS_VERSION = '3.38'
__version__ = '1.8'

DIR_QPS = pathlib.Path(__file__).parent
DIR_REPO = DIR_QPS.parent
DIR_UI_FILES = DIR_QPS / 'ui'
DIR_ICONS = DIR_UI_FILES / 'icons'
QPS_RESOURCE_FILE = DIR_QPS / 'qpsresources_rc.py'

MAPLAYER_CONFIGWIDGET_FACTORIES: List[QgsMapLayerConfigWidgetFactory] = list()

if Qgis.version() < MIN_QGIS_VERSION:
    warnings.warn(f'Your QGIS ({Qgis.QGIS_VERSION}) is outdated. '
                  f'Please update to QGIS >= {MIN_QGIS_VERSION}', RuntimeWarning)

KEY_MAPLAYERCONFIGWIDGETFACTORIES = 'QPS_MAPLAYER_CONFIGWIDGET_FACTORIES'


def debugLog(msg: str, prefix: str = 'DEBUG:'):
    """
    Prints message 'msg' to console only if environmental variable DEBUG is set
    :param msg: str
    """
    if str(os.environ.get('DEBUG', False)).lower() in ['1', 'true']:
        print(f'{prefix} {msg}', flush=True)


def registerMapLayerConfigWidgetFactory(factory: QgsMapLayerConfigWidgetFactory) -> QgsMapLayerConfigWidgetFactory:
    """
    Register a new tab in the map layer properties dialog.
    :param factory: QgsMapLayerConfigWidgetFactory
    :type factory:
    :return: QgsMapLayerConfigWidgetFactory or None, if a factory with similar name was registered before by this method
    """
    # global MAPLAYER_CONFIGWIDGET_FACTORIES
    assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
    name: str = factory.__class__.__name__

    registered = os.environ.get(KEY_MAPLAYERCONFIGWIDGETFACTORIES, '').split('::')

    from qgis.utils import iface
    if isinstance(iface, QgisInterface) and factory not in MAPLAYER_CONFIGWIDGET_FACTORIES and name not in registered:
        MAPLAYER_CONFIGWIDGET_FACTORIES.append(factory)
        registered.append(name)
        os.environ[KEY_MAPLAYERCONFIGWIDGETFACTORIES] = '::'.join(registered)
        iface.registerMapLayerConfigWidgetFactory(factory)

        QgsApplication.instance().messageLog().logMessage(f'Registered {name}', level=Qgis.Info)
        return factory
    else:
        return None


def unregisterMapLayerConfigWidgetFactory(factory: QgsMapLayerConfigWidgetFactory):
    """
    Unregister a previously registered tab in the map layer properties dialog.
    :param factory:
    :type factory:
    :return:
    :rtype:
    """
    assert isinstance(factory, QgsMapLayerConfigWidgetFactory)
    # global MAPLAYER_CONFIGWIDGET_FACTORIES
    name: str = factory.__class__.__name__

    while factory in MAPLAYER_CONFIGWIDGET_FACTORIES:
        MAPLAYER_CONFIGWIDGET_FACTORIES.remove(factory)

    registered = os.environ.get(KEY_MAPLAYERCONFIGWIDGETFACTORIES, '').split('::')
    while name in registered:
        registered.remove(name)
    os.environ[KEY_MAPLAYERCONFIGWIDGETFACTORIES] = '::'.join(registered)
    from qgis.utils import iface
    if isinstance(iface, QgisInterface):
        iface.unregisterMapLayerConfigWidgetFactory(factory)
        QgsApplication.instance().messageLog().logMessage(f'Unregistered {factory.__class__.__name__}', level=Qgis.Info)


def mapLayerConfigWidgetFactories() -> List[QgsMapLayerConfigWidgetFactory]:
    """
    Returns registered QgsMapLayerConfigWidgetFactories
    :return: list of QgsMapLayerConfigWidgetFactories
    :rtype:
    """
    # global MAPLAYER_CONFIGWIDGET_FACTORIES
    return MAPLAYER_CONFIGWIDGET_FACTORIES[:]


def registerSpectralLibraryPlotFactories():
    from .speclib.gui.spectrallibraryplotwidget import PropertyItemGroup, RasterRendererGroup, ProfileVisualizationGroup
    PropertyItemGroup.registerXmlFactory(PropertyItemGroup())
    PropertyItemGroup.registerXmlFactory(RasterRendererGroup())
    PropertyItemGroup.registerXmlFactory(ProfileVisualizationGroup())


def unregisterSpectralLibraryPlotFactories():
    from .speclib.gui.spectrallibraryplotwidget import PropertyItemGroup, RasterRendererGroup, ProfileVisualizationGroup
    PropertyItemGroup.unregisterXmlFactory(RasterRendererGroup.__name__)
    PropertyItemGroup.unregisterXmlFactory(ProfileVisualizationGroup.__name__)
    PropertyItemGroup.unregisterXmlFactory(PropertyItemGroup.__name__)


def registerEditorWidgets():
    """
    Call this function to register QgsEditorWidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'
    from .classification.classificationscheme import classificationSchemeEditorWidgetFactory
    classificationSchemeEditorWidgetFactory(register=True)

    from .speclib.gui.spectralprofileeditor import spectralProfileEditorWidgetFactory
    spectralProfileEditorWidgetFactory(register=True)

    from .plotstyling.plotstyling import plotStyleEditorWidgetFactory
    plotStyleEditorWidgetFactory(register=True)


def unregisterEditorWidgets():
    """
    Convenience function to remove registered widgets/factories.
    (Not implemented yet)
    """
    pass


def registerExpressionFunctions():
    try:
        from .qgsfunctions import registerQgsExpressionFunctions
        registerQgsExpressionFunctions()
    except Exception as ex:
        print('Failed to call qps.speclib.qgsfunctions.registerQgsExpressionFunctions()', file=sys.stderr)
        print(ex, file=sys.stderr)


def registerSpectralProfileSamplingModes():
    warnings.warn(DeprecationWarning('is not required anymore'), stacklevel=2)


def registerSpectralLibraryIOs():
    from .speclib.core.spectrallibraryio import initSpectralLibraryIOs
    initSpectralLibraryIOs()

    from .speclib.core.spectrallibraryrasterdataprovider import registerDataProvider
    registerDataProvider()


def unregisterExpressionFunctions():
    from .qgsfunctions import unregisterQgsExpressionFunctions as _unregisterQgsExpressionFunctions
    _unregisterQgsExpressionFunctions()


def registerMapLayerConfigWidgetFactories():
    from .layerconfigwidgets.gdalmetadata import GDALMetadataConfigWidgetFactory

    registerMapLayerConfigWidgetFactory(GDALMetadataConfigWidgetFactory())


def unregisterMapLayerConfigWidgetFactories():
    for factory in MAPLAYER_CONFIGWIDGET_FACTORIES[:]:
        unregisterMapLayerConfigWidgetFactory(factory)


def initResources():
    from .testing import initResourceFile
    initResourceFile(QPS_RESOURCE_FILE)


def initAll():
    initResources()
    registerSpectralLibraryPlotFactories()
    registerEditorWidgets()
    registerExpressionFunctions()
    registerMapLayerConfigWidgetFactories()
    registerSpectralLibraryIOs()


def unloadAll():
    unregisterEditorWidgets()
    unregisterExpressionFunctions()
    unregisterMapLayerConfigWidgetFactories()
