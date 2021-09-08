import typing
import re

from PyQt5.QtCore import pyqtSignal, QRegExp
from PyQt5.QtGui import QIcon, QRegExpValidator
from PyQt5.QtWidgets import QWidget, QMenu, QDialog, QFormLayout, QComboBox, QStackedWidget, QDialogButtonBox, QLineEdit

from qgis._core import QgsVectorLayer, QgsFeature, QgsFields, QgsExpressionContextGenerator, QgsProperty

from qgis._gui import QgsFileWidget, QgsFieldMappingWidget, QgsFieldMappingModel
from qgis.core import QgsField, QgsExpression, QgsExpressionContext

from qgis.core import QgsProcessingFeedback
from . import is_spectral_library
from .. import speclibUiPath
from ...utils import loadUi


class SpectralLibraryIOWidget(QWidget):

    def __init__(self, *args, **kwds):
        super(SpectralLibraryIOWidget, self).__init__(*args, **kwds)
        self.mSpeclib: QgsVectorLayer = None
        l = QFormLayout()
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(7)
        self.setLayout(l)

    def formatName(self) -> str:
        raise NotImplementedError()

    def formatTooltip(self) -> str:
        return self.formatName()

    def setSpeclib(self, speclib: QgsVectorLayer):
        assert is_spectral_library(speclib)
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib


class SpectralLibraryExportWidget(SpectralLibraryIOWidget):
    """
    Abstract Interface of an Widget to export / write a spectral library
    """

    EXPORT_PATH = 'export_path'
    EXPORT_FORMAT = 'export_format'
    EXPORT_LAYERNAME = 'export_layername'
    EXPORT_FIELDS = 'export_fields'

    def __init__(self, *args, **kwds):
        super(SpectralLibraryExportWidget, self).__init__(*args, **kwds)
        self.setLayout(QFormLayout())

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


class SpectralLibraryImportWidget(SpectralLibraryIOWidget, QgsExpressionContextGenerator):
    IMPORT_PATH = 'import_path'
    IMPORT_FIELDS = 'import_fields'
    IMPORT_LAYERNAME = 'import_layername'

    sigSourceChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralLibraryImportWidget, self).__init__(*args, **kwds)
        self.mSource: str = None

    def setSpeclib(self, speclib: QgsVectorLayer):
        super(SpectralLibraryImportWidget, self).setSpeclib(speclib)

    def setSource(self, source: str):
        """
        Applies changes related to the new source.
        Needs to emit the sigSourceChanged afterwards.
        """
        raise NotImplementedError

    def filter(self) -> str:
        """
        Returns a filter string like "Images (*.png *.xpm *.jpg);;Text files (*.txt);;XML files (*.xml)"
        with file types that can be imported
        :return: str
        """
        raise NotImplementedError()

    def createExpressionContext(self) -> QgsExpressionContext:
        raise NotImplementedError()

    def sourceFields(self) -> QgsFields:
        raise NotImplementedError()

    def supportsMultipleFiles(self) -> bool:
        """
        Returns True if profiles can be read from multiple files.
        :return: bool
        """
        return False

    def importSettings(self, settings: dict) -> dict:
        """
        Returns the settings required to import the library
        :param settings:
        :return:
        """
        return settings

    @staticmethod
    def importProfiles(path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        """
        Import the profiles based on the import settings defined in 'importSettings'
        :param importSettings:
        :param feedback:
        :return:
        """
        raise NotImplementedError()


class SpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    SPECTRAL_LIBRARY_IO_REGISTRY: typing.Dict[str, typing.Callable] = dict()

    @staticmethod
    def registerSpectralLibraryIO(speclibIO: typing.Union[
        'SpectralLibraryIO',
        typing.List['SpectralLibraryIO']]):

        if isinstance(speclibIO, list):
            for io in speclibIO:
                SpectralLibraryIO.registerSpectralLibraryIO(io)
            return

        assert isinstance(speclibIO, SpectralLibraryIO)
        name = speclibIO.formatName()
        if name not in SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY.keys():
            SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY[name] = speclibIO

    @staticmethod
    def spectralLibraryIOs() -> typing.List['SpectralLibraryIO']:
        return list(SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY.values())

    @classmethod
    def icon(cls) -> QIcon:
        return QIcon()

    @classmethod
    def formatName(cls) -> str:
        raise NotImplementedError()

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return None

    @classmethod
    def createExportWidget(cls) -> SpectralLibraryExportWidget:
        return None


class SpectralLibraryImportDialog(QDialog):

    def __init__(self, *args, speclib: QgsVectorLayer = None, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryimportdialog.ui'), self)
        self.setWindowIcon(QIcon(r':/qps/ui/icons/speclib_add.svg'))
        self.cbFormat: QComboBox
        self.fileWidget: QgsFileWidget
        self.fieldMappingWidget: QgsFieldMappingWidget
        self.buttonBox: QDialogButtonBox
        self.cbFormat.currentIndexChanged.connect(self.setImportWidget)
        self.fileWidget.fileChanged.connect(self.setSource)

        self.mFIELD_PROPERTY_MAPS: typing.Dict[str, typing.Dict[str, QgsProperty]] = dict()

        for io in SpectralLibraryIO.spectralLibraryIOs():
            assert isinstance(io, SpectralLibraryIO)
            widget = io.createImportWidget()
            if isinstance(widget, SpectralLibraryImportWidget):
                name = widget.formatName()
                widget.sigSourceChanged.connect(self.onSourceFieldsChanged)
                self.stackedWidgetFormatOptions.addWidget(widget)
                self.cbFormat.addItem(name)
                self.cbFormat: QComboBox

        if isinstance(speclib, QgsVectorLayer):
            self.setSpeclib(speclib)

        self.accepted.connect(self.importProfiles)

    def setSource(self, source: str):
        assert isinstance(source, str)
        w = self.currentImportWidget()
        if isinstance(w, SpectralLibraryImportWidget):
            w.setSource(source)

    def onSourceFieldsChanged(self):
        w = self.currentImportWidget()
        if isinstance(w, SpectralLibraryImportWidget):
            self.fieldMappingWidget.setFieldPropertyMap({})
            self.fieldMappingWidget.setSourceFields(w.sourceFields())
            self.fieldMappingWidget.registerExpressionContextGenerator(w)

    def setImportWidget(self, import_format: typing.Union[int, str, SpectralLibraryImportWidget]):
        import_widgets = self.importWidgets()
        last_widget = self.currentImportWidget()
        if isinstance(last_widget, SpectralLibraryImportWidget):
            self.mFIELD_PROPERTY_MAPS[last_widget.formatName()] = self.fieldMappingWidget.fieldPropertyMap()

        import_widget: SpectralLibraryImportWidget = None
        if isinstance(import_format, SpectralLibraryImportWidget):

            import_widget = import_format
        elif isinstance(import_format, str):
            for i, w in enumerate(import_widgets):
                w: SpectralLibraryImportWidget
                if w.formatName() == import_format:
                    import_widget = w
                    break
        elif isinstance(import_format, int):
            import_widget = import_widgets[import_format]
        else:
            raise NotImplementedError()

        assert isinstance(import_widget, SpectralLibraryImportWidget)
        assert import_widget in import_widgets

        self.fileWidget.setFilter(import_widget.filter())

        if import_widget.supportsMultipleFiles():
            self.fileWidget.setStorageMode(QgsFileWidget.GetMultipleFiles)
        else:
            self.fileWidget.setStorageMode(QgsFileWidget.GetFile)

        self.stackedWidgetFormatOptions.setCurrentWidget(import_widget)

        self.gbFormatOptions.setVisible(import_widget.findChild(QWidget) is not None)

        self.onSourceFieldsChanged()

    def importWidgets(self) -> typing.List[SpectralLibraryImportWidget]:
        self.stackedWidgetFormatOptions: QStackedWidget
        return [self.stackedWidgetFormatOptions.widget(i)
                for i in range(self.stackedWidgetFormatOptions.count())
                if isinstance(self.stackedWidgetFormatOptions.widget(i), SpectralLibraryImportWidget)]

    def currentImportWidget(self) -> SpectralLibraryImportWidget:
        return self.stackedWidgetFormatOptions.currentWidget()

    def setSpeclib(self, speclib: QgsVectorLayer):
        self.fieldMappingWidget.setDestinationFields(speclib.fields())
        for w in self.importWidgets():
            w.setSpeclib(speclib)

    def importProfiles(self) -> typing.List[QgsFeature]:

        return []


class SpectralLibraryExportDialog(QDialog):

    def __init__(self, *args, speclib: QgsVectorLayer = None, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryexportdialog.ui'), self)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))
        self.cbFormat: QComboBox
        self.fileWidget: QgsFileWidget
        self.tbLayerName: QLineEdit
        self.mLayerNameValidator = QRegExpValidator(QRegExp('[A-Za-z0-9_]+'))
        self.tbLayerName.setValidator(self.mLayerNameValidator)

        self.cbFormat.currentIndexChanged.connect(self.setExportWidget)

        self.mSpeclib: QgsVectorLayer = None
        for io in SpectralLibraryIO.spectralLibraryIOs():
            assert isinstance(io, SpectralLibraryIO)
            widget = io.createExportWidget()
            if isinstance(widget, SpectralLibraryExportWidget):
                name = widget.formatName()
                self.cbFormat: QComboBox
                self.stackedWidgetFormatOptions.addWidget(widget)
                self.cbFormat.addItem(name)

        if isinstance(speclib, QgsVectorLayer):
            self.setSpeclib(speclib)

    def exportWidgets(self) -> typing.List[SpectralLibraryExportWidget]:
        self.stackedWidgetFormatOptions: QStackedWidget
        return [self.stackedWidgetFormatOptions.widget(i)
                for i in range(self.stackedWidgetFormatOptions.count())
                if isinstance(self.stackedWidgetFormatOptions.widget(i), SpectralLibraryExportWidget)]

    def currentExportWidget(self) -> SpectralLibraryExportWidget:
        return self.stackedWidgetFormatOptions.currentWidget()

    def setExportWidget(self, widget: typing.Union[int, str, SpectralLibraryExportWidget]):
        last_widget = self.currentExportWidget()
        if isinstance(last_widget, SpectralLibraryExportWidget):
            s = ""

        export_widgets = self.exportWidgets()
        export_widget: SpectralLibraryExportWidget = None
        if isinstance(widget, SpectralLibraryExportWidget):
            export_widget = widget
        elif isinstance(widget, int):
            export_widget = export_widgets[widget]
        elif isinstance(widget, str):
            for w in export_widgets:
                if w.formatName() == widget:
                    export_widget = w
                    break
        assert isinstance(export_widget, SpectralLibraryExportWidget)

        self.stackedWidgetFormatOptions.setCurrentWidget(export_widget)
        b = export_widget.supportsLayerName()
        self.tbLayerName.setEnabled(b)
        self.labelLayerName.setEnabled(b)

        self.gbFormatOptions.setVisible(export_widget.findChild(QWidget) is not None)

    def setSpeclib(self, speclib: QgsVectorLayer):

        if isinstance(self.mSpeclib, QgsVectorLayer):
            self.mSpeclib.selectionChanged.disconnect(self.onSelectionChanged)

        self.mSpeclib = speclib
        self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
        if self.tbLayerName.text() == '':

            self.tbLayerName.setText(re.sub(r'[^0-9a-zA-Z_]', '_', speclib.name()))
        for w in self.exportWidgets():
            w.setSpeclib(speclib)

        self.onSelectionChanged()

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def onSelectionChanged(self):
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            self.cbSaveSelectedOnly.setEnabled(speclib.selectedFeatureCount() > 0)


def initSpectralLibraryIOs():

    from ..io.geopackage import GeoPackageSpectralLibraryIO
    from ..io.envi import EnviSpectralLibraryIO

    speclibIOs = [
        GeoPackageSpectralLibraryIO(),
        EnviSpectralLibraryIO()
    ]

    for speclibIO in speclibIOs:
        SpectralLibraryIO.registerSpectralLibraryIO(speclibIO)