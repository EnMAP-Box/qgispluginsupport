from qgis.PyQt.QtWidgets import QWidget

from .. import speclibUiPath
from ..core.spectrallibrary import SpectralLibrary, consistencyCheck
from ...utils import loadUi


class SpectralLibraryConsistencyCheckWidget(QWidget):

    def __init__(self, speclib: SpectralLibrary = None, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryconsistencycheckwidget.ui'), self)
        self.mSpeclib: SpectralLibrary = speclib
        self.tbSpeclibInfo.setText('')
        if speclib:
            self.setSpeclib(speclib)

    def setSpeclib(self, speclib: SpectralLibrary):
        assert isinstance(speclib, SpectralLibrary)
        self.mSpeclib = speclib
        self.mSpeclib.nameChanged.connect(self.updateSpeclibInfo)
        self.updateSpeclibInfo()

    def updateSpeclibInfo(self):
        info = '{}: {} profiles'.format(self.mSpeclib.name(), len(self.mSpeclib))
        self.tbSpeclibInfo.setText(info)

    def speclib(self) -> SpectralLibrary:
        return self.mSpeclib

    def startCheck(self):
        consistencyCheck(self.mSpeclib)

