"""
***************************************************************************
    layerconfigwidget/core.py - Helpers and emulations for QgsMapLayerConfigWidgets
    -----------------------------------------------------------------------
    begin                : <month and year of creation>
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

import pathlib

from qgis.PyQt.QtWidgets import QMenu
from qgis.core import QgsMapLayer
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget


def configWidgetUi(name: str) -> str:
    """
    Returns the full path to a '*.ui' file
    :param name:
    :type name:
    :return:
    :rtype:
    """
    path = pathlib.Path(__file__).parents[1] / 'ui' / name
    return path.as_posix()


class QpsMapLayerConfigWidget(QgsMapLayerConfigWidget):

    def __init__(self, mapLayer: QgsMapLayer, canvas: QgsMapCanvas, *args, **kwds):
        assert isinstance(mapLayer, QgsMapLayer)
        # assert isinstance(canvas, QgsMapCanvas)
        super().__init__(mapLayer, canvas, *args, **kwds)
        self.mMapLayer = mapLayer
        self.mCanvas = canvas

    def canvas(self) -> QgsMapCanvas:
        """
        Returns the QgsMapCanvas
        """
        return self.mCanvas

    def mapLayer(self) -> QgsMapLayer:
        """
        Returns the map layer
        """
        return self.mMapLayer

    def menuButtonMenu(self) -> QMenu:
        return None

    def menuButtonToolTip(self):
        return ''

    def syncToLayer(self, mapLayer: QgsMapLayer = None):
        """
        Implement this method to take up changes from the underlying map layer.
        """
        if isinstance(mapLayer, QgsMapLayer):
            self.mMapLayer = mapLayer

    def reset(self):
        """
        Implement this method to reset values
        """

    def apply(self):
        """
        Implement this method to apply changes to the underlying map layer.
        """
        pass
