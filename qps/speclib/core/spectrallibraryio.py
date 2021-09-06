import typing

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QMenu, QDialog, QFormLayout

from qgis._core import QgsVectorLayer, QgsFeature
from qgis.core import QgsField, QgsExpression, QgsExpressionContext

from qgis.core import QgsProcessingFeedback
from .spectrallibrary import SpectralLibrary
from .spectralprofile import SpectralProfile
from .. import speclibUiPath
from ...utils import loadUi


class AbstractSpectralLibraryExportWidget(QWidget):
    """
    Abstract Interface of an Widget to export / write a spectral library
    """

    EXPORT_PATH = 'export_path'
    EXPORT_FORMAT = 'export_format'
    EXPORT_LAYERNAME = 'export_layername'
    EXPORT_FIELDS = 'export_fields'

    def __init__(self, *args, **kwds):
        super(AbstractSpectralLibraryExportWidget, self).__init__(*args, **kwds)
        self.setLayout(QFormLayout())


    def formatName(self) -> str:
        raise NotImplementedError()

    def formatTooltip(self) -> str:
        return self.formatName()

    def supportsMultipleProfileFields(self) -> bool:
        """
        Returns True if the export format can write multiple profile fields.
        In this case multiple profile fields can be selected for export-
        :return: bool
        """
        return False

    def supportsMultipleSpectralSettings(self) -> bool:
        """
        Returns True if the export format can write profiles with varying spectral settings, e.g.
        different wavelength vectors.
        :return: bool
        """
        return False

    def supportsLayerName(self) -> bool:
        """
        Returns True if the export format can make use of a layer-name
        :return: bool
        """
        return False

    def setSpeclib(self, speclib: QgsVectorLayer):
        raise NotImplementedError()

    def filter(self) -> str:
        """
        Returns a filter string like "Images (*.png *.xpm *.jpg);;Text files (*.txt);;XML files (*.xml)"
        :return: str
        """
        raise NotImplementedError()

    def exportSettings(self, settings: dict) -> dict:
        """
        Returns a settings dictionary with all settings required to export the library within .writeProfiles
        :param settings:
        :return:
        """
        return settings

    @staticmethod
    def exportProfiles(exportSettings: dict,
                       profiles: typing.List[QgsFeature],
                       feedback: QgsProcessingFeedback) -> typing.List[str]:
        """
        Writes the files and returns a list of written files paths that can be used to import the profile
        :param exportSettings:
        :param profiles:
        :param feedback:
        :return:
        """
        raise NotImplementedError()


class AbstractSpectralLibraryImportWidget(QWidget):
    IMPORT_PATH = 'import_path'
    IMPORT_FIELDS = 'import_fields'
    IMPORT_LAYERNAME = 'import_layername'

    def __init__(self, *args, **kwds):
        super(AbstractSpectralLibraryImportWidget, self).__init__(*args, **kwds)
        self.setLayout(QFormLayout())

    def setSpeclib(self, speclib: QgsVectorLayer):
        raise NotImplementedError()

    def filter(self) -> str:
        """
        Returns a filter string like "Images (*.png *.xpm *.jpg);;Text files (*.txt);;XML files (*.xml)"
        with file types that can be imported
        :return: str
        """
        raise NotImplementedError()

    def importSettings(self, settings:dict) -> dict:
        """
        Returns the settings required to import the library
        :param settings:
        :return:
        """
        return settings

    @staticmethod
    def importProfiles(importSettings: dict, feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        raise NotImplementedError()


class AbstractSpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """

    def __init__(self):
        pass

    def icon(self) -> QIcon:
        return QIcon()

    def createImportWidget(self) -> AbstractSpectralLibraryImportWidget:
        return None

    def createExportWidget(self) -> AbstractSpectralLibraryExportWidget:
        return None

class SpectralLibraryExportDialog(QDialog):

    EXPORT_WIDGETS: typing.Dict[str, typing.Callable] = dict()

    @staticmethod
    def registerExportWidget(exportWidget: AbstractSpectralLibraryExportWidget):
        assert isinstance(exportWidget, AbstractSpectralLibraryExportWidget)
        name = exportWidget.__class__.__name__
        if name not in SpectralLibraryExportDialog.EXPORT_WIDGETS.keys():
            SpectralLibraryExportDialog.EXPORT_WIDGETS[name] = exportWidget.__class__

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryexportdialog.ui'), self)

        for n, c in SpectralLibraryExportDialog.EXPORT_WIDGETS.items():
            widget: AbstractSpectralLibraryExportWidget = c()
            name = widget.formatName()
            self.stackedWidgetFormatOptions.addWidget(widget)
