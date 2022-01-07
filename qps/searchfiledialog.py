# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    qps/searchfiledialog.py

    A dialog to search multiple files, fast.
    ---------------------
    Beginning            : 2020-08-17
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
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.gui import QgsFileWidget
from . import DIR_UI_FILES
from .utils import loadUi


class SearchFilesDialog(QDialog):
    """
    A dialog to select multiple files, fast
    """
    sigFilesFound = pyqtSignal(list)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(DIR_UI_FILES / 'searchfilesdialog.ui', self)

        self.btnMatchCase.setDefaultAction(self.optionMatchCase)
        self.btnRegex.setDefaultAction(self.optionRegex)
        self.btnRecursive.setDefaultAction(self.optionRecursive)
        self.btnReload.setDefaultAction(self.actionReload)

        self.fileWidget: QgsFileWidget
        #self.fileWidget.setReadOnly(True)
        self.fileWidget.setStorageMode(QgsFileWidget.GetDirectory)
        self.fileWidget.fileChanged.connect(self.reloadFiles)

        s = ""

    def validate(self):
        s = ""

    def reloadFiles(self, *args):
        print('#RELOAD FILES')

