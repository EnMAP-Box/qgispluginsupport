# -*- coding: utf-8 -*-

"""
***************************************************************************

    ---------------------
    Date                 : 25.11.2019
    Copyright            : (C) 2017 by Benjamin Jakimow
    Email                : benjamin jakimow at geo dot hu-berlin dot de
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 3 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
# noinspection PyPep8Naming
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qps.testing import initQgisApplication, TestObjects, QgisMockup

QAPP = initQgisApplication()
from qps import initResources, registerEditorWidgets
initResources()
registerEditorWidgets()

from qps.speclib.spectrallibraries import SpectralLibrary, SpectralProfile, SpectralLibraryWidget
from qps.maptools import CursorLocationMapTool
from qps.utils import SpatialPoint


# get the QGIS map canvas
from qgis.utils import iface
assert isinstance(iface, QgisInterface)

if isinstance(iface, QgisMockup):
    iface.ui.show()

class ExampleApp(QWidget):

    def __init__(self, *args, **kwds):
        super(ExampleApp, self).__init__(*args, **kwds)
        self.setWindowTitle('Example: Select Profiles from QGIS Map Canvas')
        self.mapToolSelectProfiles = None # will be created later

        self.speclibWidget = SpectralLibraryWidget()
        self.speclibWidget.setMapInteraction(True)
        self.speclibWidget.sigLoadFromMapRequest.connect(self.onActivateProfileMapTool)
        l = QVBoxLayout()
        l.addWidget(self.speclibWidget)

        self.setLayout(l)



    def onLocationClicked(self, spatialPoint:SpatialPoint, mapCanvas:QgsMapCanvas):
        """
        Reacts on clicks to the QGIS Map canvas
        """
        profiles = SpectralProfile.fromMapCanvas(mapCanvas, spatialPoint)

        # filter & modify profiles here before sending them to a SpectralLibraryWidget
        # e.g. change profile names

        self.speclibWidget.setCurrentProfiles(profiles)

    def onActivateProfileMapTool(self, *args):
        """
        Activates a maptool that informs on clicked map locations
        """
        from qgis.utils import iface
        canvas = iface.mapCanvas()
        assert isinstance(canvas, QgsMapCanvas)
        self.mapToolSelectProfiles = CursorLocationMapTool(canvas)
        self.mapToolSelectProfiles.sigLocationRequest[SpatialPoint, QgsMapCanvas].connect(self.onLocationClicked)
        canvas.setMapTool(self.mapToolSelectProfiles)


if __name__ == '__main__':

    from qgis.utils import iface

    canvas = iface.mapCanvas()
    assert isinstance(canvas, QgsMapCanvas)

    from qpstestdata import enmap
    lyr = QgsRasterLayer(enmap)
    lyr.setName('Example Layer')
    QgsProject.instance().addMapLayer(lyr)

    canvas.setLayers([lyr])
    canvas.mapSettings().setDestinationCrs(lyr.crs())
    canvas.setExtent(lyr.extent())


    widget = ExampleApp()
    widget.show()

    QAPP.exec_()





